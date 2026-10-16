import json
import logging
import hashlib
from typing import Dict, Any, List, Optional
import requests

from app.core.config import settings
from app.core.cache import memory_cache
from app.services.ai.base import AIServiceInterface
from app.services.ai.mock_adapter import mock_ai_service
from app.services.ai.safety import SAFETY_SYSTEM_PROMPT
from app.schemas.question import (
    AIGenerateRequest,
    AIGenerateData,
    GeneratedQuestionMCQ,
    GeneratedQuestionEssay,
    OptionSchema,
)

logger = logging.getLogger(__name__)


class GeminiAdapter(AIServiceInterface):
    """Google Gemini AI Adapter for EXAMIND.
    Uses official Gemini REST API (v1beta) with structured JSON generation.
    Gracefully falls back to mock service if API key is not configured or network fails.
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY or settings.AI_API_KEY
        self.model = settings.GEMINI_MODEL or "gemini-2.5-flash"

    def _call_gemini(
        self,
        prompt: Optional[str] = None,
        contents: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        from app.core.secret_manager import get_secret
        effective_key = api_key or get_secret("GEMINI_API_KEY") or self.api_key or settings.GEMINI_API_KEY or settings.AI_API_KEY
        if not effective_key:
            logger.info("[GeminiAdapter] No Gemini API key provided, using contextual fallback.")
            return None

        model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={effective_key}"
        headers = {"Content-Type": "application/json"}

        if contents is None:
            contents = [{"role": "user", "parts": [{"text": prompt or ""}]}]

        body: Dict[str, Any] = {"contents": contents}

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        gen_config: Dict[str, Any] = {"temperature": temperature}
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        body["generationConfig"] = gen_config

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        raw_text = parts[0]["text"].strip()
                        # Clean JSON code fences if present
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:]
                        elif raw_text.startswith("```"):
                            raw_text = raw_text[3:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        return raw_text.strip()
            else:
                logger.warning(f"[GeminiAdapter] API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"[GeminiAdapter] Request failed: {e}")

    def _format_conversation_contents(
        self, history: Optional[List[Dict[str, str]]], message: str
    ) -> List[Dict[str, Any]]:
        """Constructs valid alternating turns for Gemini: user -> model -> user -> ...
        Guarantees that roles alternate, previous trailing user duplicate is deduplicated,
        and the final turn is the current user message.
        """
        raw_turns = []
        if history:
            for item in history:
                role = "user" if item.get("role") == "user" else "model"
                text = (item.get("content") or "").strip()
                if text:
                    raw_turns.append({"role": role, "text": text})

        # Remove duplicate of current message at end of history if present
        if raw_turns and raw_turns[-1]["role"] == "user" and raw_turns[-1]["text"] == message.strip():
            raw_turns.pop()

        # Append current user prompt turn
        raw_turns.append({"role": "user", "text": message.strip()})

        # Limit to last 9 turns to stay within context
        raw_turns = raw_turns[-9:]

        cleaned: List[Dict[str, Any]] = []
        for turn in raw_turns:
            if not cleaned:
                if turn["role"] == "user":
                    cleaned.append({"role": "user", "parts": [{"text": turn["text"]}]})
            else:
                prev_role = cleaned[-1]["role"]
                if turn["role"] != prev_role:
                    cleaned.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
                else:
                    cleaned[-1]["parts"][0]["text"] += f"\n\n{turn['text']}"

        if not cleaned or cleaned[-1]["role"] != "user":
            cleaned.append({"role": "user", "parts": [{"text": message.strip()}]})

        return cleaned

    def generate_questions(self, request: AIGenerateRequest) -> AIGenerateData:
        system_prompt = (
            "Anda adalah pakar kurikulum dan penyusun soal ujian nasional Kemendikbud. "
            "Buat butir soal bermutu tinggi dengan analisis distractor rasional pada setiap opsi salah "
            "dan matriks rubrik 4 dimensi (Konsep, Argumen, Terminologi, Kejelasan) untuk soal esai. "
            "Output WAJIB berupa JSON murni dengan format:\n"
            "{\n"
            '  "mcq_questions": [\n'
            '    {\n'
            '      "prompt": "teks soal",\n'
            '      "difficulty": "medium",\n'
            '      "bloom_level": "C3",\n'
            '      "options": [\n'
            '        {"id": "A", "text": "...", "is_correct": false, "rationale": "..."},\n'
            '        {"id": "B", "text": "...", "is_correct": true, "rationale": "..."}\n'
            "      ],\n"
            '      "correct_option_id": "B",\n'
            '      "explanation": "...",\n'
            '      "points": 10.0\n'
            "    }\n"
            "  ],\n"
            '  "essay_questions": [\n'
            '    {\n'
            '      "prompt": "teks pertanyaan esai/short answer",\n'
            '      "difficulty": "medium",\n'
            '      "bloom_level": "C3",\n'
            '      "sample_answer": "Jawaban acuan ringkas 1-2 kalimat",\n'
            '      "ref_points": [\n'
            '        {"id": "p1", "statement": "Kriteria/konsep kunci 1 yang harus ada", "weight": 0.5},\n'
            '        {"id": "p2", "statement": "Kriteria/konsep kunci 2 yang harus ada", "weight": 0.5}\n'
            '      ],\n'
            '      "rubric": {"dimension_1_concept": 50, "dimension_2_argument": 50},\n'
            '      "points": 10.0\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"Mata Pelajaran: {request.subject}\n"
            f"Topik/Materi: {request.topic_content}\n"
            f"Tingkat Kelas: {request.grade_level}\n"
            f"Jumlah Soal Pilihan Ganda: {request.mcq_count}\n"
            f"Jumlah Soal Esai: {request.essay_count}\n"
            f"Tingkat Kesulitan: {request.difficulty}\n"
        )

        raw_json = self._call_gemini(
            user_prompt,
            system_instruction=system_prompt,
            json_mode=True,
            api_key=request.api_key,
        )
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                mcq_list = []
                for q in parsed.get("mcq_questions", []):
                    opts = [OptionSchema(**opt) for opt in q.get("options", [])]
                    mcq_list.append(
                        GeneratedQuestionMCQ(
                            prompt=q["prompt"],
                            difficulty=q.get("difficulty", request.difficulty),
                            bloom_level=q.get("bloom_level", "C3"),
                            options=opts,
                            correct_option_id=q["correct_option_id"],
                            explanation=q.get("explanation", ""),
                            points=float(q.get("points", 10.0)),
                        )
                    )

                essay_list = []
                for q in parsed.get("essay_questions", []):
                    rubric_dict = q.get("rubric", {})
                    ref_pts = q.get("ref_points")
                    if ref_pts:
                        rubric_dict["ref_points"] = ref_pts

                    essay_list.append(
                        GeneratedQuestionEssay(
                            prompt=q["prompt"],
                            difficulty=q.get("difficulty", request.difficulty),
                            bloom_level=q.get("bloom_level", "C4"),
                            rubric=rubric_dict,
                            ideal_answer=q.get("sample_answer") or q.get("ideal_answer", ""),
                            explanation=q.get("explanation", ""),
                            points=float(q.get("points", 20.0)),
                        )
                    )

                if mcq_list or essay_list:
                    return AIGenerateData(mcq_questions=mcq_list, essay_questions=essay_list)
            except Exception as parse_err:
                logger.warning(f"[GeminiAdapter] Failed to parse Gemini response: {parse_err}")

        # Fallback to mock service
        return mock_ai_service.generate_questions(request)

    def grade_essay(
        self, prompt: str, rubric: Dict[str, Any], ideal_answer: str, student_answer: str
    ) -> Dict[str, Any]:
        # 1. High-Efficiency Respan Span-01 Lite Decision Model
        try:
            from app.services.ai.respan_grader import get_respan_grader
            respan_grader = get_respan_grader()
            if respan_grader.is_configured():
                res = respan_grader.grade_short_answer(
                    prompt=prompt,
                    rubric=rubric,
                    ideal_answer=ideal_answer,
                    student_answer=student_answer,
                )
                if res and "total_score" in res:
                    evals = res.get("rationale_json", {}).get("evaluations", [])
                    dim_scores = {}
                    for idx, ev in enumerate(evals, 1):
                        dim_scores[f"kriteria_{idx}"] = round(ev.get("noul", 0.0) * 100, 1)

                    passed = [ev["statement"] for ev in evals if ev.get("status") == "passed"]
                    missed = [ev["statement"] for ev in evals if ev.get("status") != "passed"]
                    feedback_parts = []
                    if passed:
                        feedback_parts.append(f"Poin yang sudah baik: {', '.join(passed)}.")
                    if missed:
                        feedback_parts.append(f"Perlu dilengkapi: {', '.join(missed)}.")
                    if res.get("rationale_json", {}).get("misconception_detected"):
                        feedback_parts.append("Perhatikan kembali konsep dasar agar tidak tertukar.")

                    student_explanation = " ".join(feedback_parts) or "Jawaban telah dinilai secara objektif sesuai rubrik."

                    return {
                        "total_score": res["total_score"],
                        "dimension_scores": dim_scores or {"konsep": res["total_score"]},
                        "confidence_level": res["confidence_level"],
                        "rationale": json.dumps(res.get("rationale_json", {})),
                        "explanation": student_explanation,
                        "raw_rationale": res.get("rationale"),
                        "decision_model": res.get("model", "respan/span-01-lite"),
                    }
        except Exception as respan_err:
            logger.warning(f"[GeminiAdapter] Respan evaluation exception: {respan_err}")

        system_prompt = (
            "Anda adalah asisten pengoreksi ujian akademik yang objektif dan adil. "
            "Evaluasi jawaban esai siswa berdasarkan rubrik 4 dimensi (Konsep maks 40, Argumen maks 30, Terminologi maks 15, Kejelasan maks 15). "
            "Output WAJIB berupa JSON:\n"
            "{\n"
            '  "total_score": 85.0,\n'
            '  "dimension_scores": {\n'
            '    "dimension_1_concept": 35.0,\n'
            '    "dimension_2_argument": 25.0,\n'
            '    "dimension_3_terminology": 13.0,\n'
            '    "dimension_4_clarity": 12.0\n'
            "  },\n"
            '  "confidence_level": "high",\n'
            '  "rationale": "alasan penilaian untuk guru",\n'
            '  "explanation": "umpan balik ramah untuk siswa"\n'
            "}"
        )

        user_prompt = (
            f"Pertanyaan: {prompt}\n"
            f"Rubrik/Kunci Jawaban: {json.dumps(rubric)}\n"
            f"Jawaban Ideal: {ideal_answer}\n"
            f"Jawaban Siswa:\n{student_answer}\n"
        )

        raw_json = self._call_gemini(user_prompt, system_instruction=system_prompt, json_mode=True)
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                if "total_score" in parsed and "dimension_scores" in parsed:
                    return parsed
            except Exception as e:
                logger.warning(f"[GeminiAdapter] Essay grading parse error: {e}")

        return mock_ai_service.grade_essay(prompt, rubric, ideal_answer, student_answer)

    def generate_explanation(
        self, prompt: str, correct_answer: str, student_response: str, is_correct: bool
    ) -> str:
        system_prompt = (
            "Anda adalah guru pembimbing yang ramah dan edukatif. "
            "Jelaskan mengapa pilihan jawaban benar dan mengapa respon siswa tepat atau kurang tepat."
        )
        user_prompt = (
            f"Soal: {prompt}\n"
            f"Kunci Jawaban: {correct_answer}\n"
            f"Respon Siswa: {student_response}\n"
            f"Status: {'BENAR' if is_correct else 'SALAH'}\n"
        )

        text = self._call_gemini(user_prompt, system_instruction=system_prompt, json_mode=False)
        if text:
            return text.strip()

        return mock_ai_service.generate_explanation(prompt, correct_answer, student_response, is_correct)

    def chat_assistant(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        scoped_context: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        system_prompt = (
            f"{SAFETY_SYSTEM_PROMPT}\n\n"
            "Anda adalah EXAMIND AI Assistant — asisten pendidikan pintar yang ramah, akurat, dan berwawasan luas "
            "di platform ujian online EXAMIND. Anda memiliki akses ke DATA AKADEMIK TEROTENTIKASI REALTIME dari pengguna yang sedang aktif. "
            "Jawab pertanyaan pengguna mengenai nilai ujian, riwayat ujian, jadwal ujian mendatang, kelas, dan performa belajar "
            "secara presisi dan faktual berdasarkan data realtime yang disediakan di dalam konteks. "
            "Jika pengguna menanyakan informasi di luar kewenangannya (misalnya meminta nilai siswa lain atau kunci jawaban ujian aktif), "
            "tolak dengan santun dan jelaskan komitmen terhadap integritas dan privasi data akademik. "
            "Gunakan bahasa Indonesia yang santun, jelas, terstruktur, dan memotivasi."
        )

        # 1. Response Caching Check
        cache_key = f"ai_asst:{hashlib.md5(f'{scoped_context}:{message}'.encode()).hexdigest()}"
        cached_res = memory_cache.get(cache_key)
        if cached_res:
            logger.info(f"[MemoryCache] Hit cached assistant response for query: {message[:40]}")
            return cached_res

        system_instruction = (
            f"{system_prompt}\n\n"
            f"[DATA REALTIME DATABASE TEROTENTIKASI]\n{scoped_context or 'Tidak ada data khusus.'}\n[AKHIR DATA DATABASE]\n"
            f"Konteks Halaman: {context or 'Portal EXAMIND'}"
        )

        # 2. Build Native Multi-Turn Conversation Memory for Gemini
        gemini_contents = self._format_conversation_contents(history, message)

        text = self._call_gemini(
            contents=gemini_contents,
            system_instruction=system_instruction,
            json_mode=False,
            temperature=0.6,
            api_key=api_key,
        )

        if text:
            reply_text = text.strip()
            memory_cache.set(cache_key, reply_text, ttl=300)
            return reply_text

        # Resilient contextual fallback response
        fallback_res = mock_ai_service.chat_assistant(
            message=message,
            history=history,
            context=context,
            scoped_context=scoped_context,
            api_key=api_key,
        )
        memory_cache.set(cache_key, fallback_res, ttl=180)
        return fallback_res

    def chat_question_explanation(
        self,
        question_context: Dict[str, Any],
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        api_key: Optional[str] = None,
    ) -> str:
        q_id = question_context.get("question_id", 0)
        # 1. Response Caching Check (Question level)
        student_resp = str(question_context.get("student_response") or "")
        cache_hash = hashlib.md5(f"{student_resp}:{message}".encode()).hexdigest()
        cache_key = f"ai_tutor:{q_id}:{cache_hash}"
        cached_res = memory_cache.get(cache_key)
        if cached_res:
            logger.info(f"[MemoryCache] Hit cached tutor explanation for question #{q_id}")
            return cached_res

        system_prompt = (
            f"{SAFETY_SYSTEM_PROMPT}\n\n"
            "Anda adalah EXAMIND Socratic Tutor AI — guru privat interaktif yang membimbing siswa memahami pembahasan "
            "butir soal ujian yang telah dikerjakan. Tugas Anda:\n"
            "1. Jelaskan konsep dasar di balik pertanyaan secara runtut, jelas, dan mudah dipahami.\n"
            "2. Jelaskan mengapa jawaban siswa benar atau mengapa kurang tepat/salah secara konstruktif dan suportif.\n"
            "3. Jelaskan mengapa kunci jawaban resmi tersebut tepat dan uraikan alur penalarannya langkah demi langkah.\n"
            "4. Jawab pertanyaan lanjutan dari siswa (misal: 'Kenapa opsi C salah?', 'Bisa beri contoh kehidupan sehari-hari?', 'Rumus apa yang dipakai?').\n"
            "5. Berikan analogi sederhana atau tips praktis agar siswa tidak mengulangi kesalahan serupa.\n"
            "Gunakan bahasa Indonesia yang hangat, bersahabat, edukatif, dan memicu antusiasme belajar."
        )

        detail_lines = [
            "=== DETAIL BUTIR SOAL & EVALUASI SISWA ===",
            f"Judul Ujian: {question_context.get('exam_title')}",
            f"Nomor Butir Soal: #{question_context.get('question_id')}",
            f"Pertanyaan: {question_context.get('prompt')}",
            f"Tipe Soal: {question_context.get('question_type')}",
        ]

        opts = question_context.get("options") or []
        if opts:
            detail_lines.append("Pilihan Jawaban:")
            for opt in opts:
                is_key = opt.get("id") == question_context.get("correct_answer")
                detail_lines.append(f"  - [{opt.get('id')}] {opt.get('text')} {'(KUNCI JAWABAN RESMI)' if is_key else ''}")

        detail_lines.append(f"Kunci Jawaban Resmi: {question_context.get('correct_answer')}")
        detail_lines.append(f"Jawaban Siswa: {question_context.get('student_response') or '(Tidak dijawab)'}")
        detail_lines.append(
            f"Status Evaluasi: {'BENAR' if question_context.get('is_correct') else 'SALAH / KURANG TEPAT'} "
            f"(Skor: {question_context.get('score_obtained')}/{question_context.get('allocated_points')})"
        )

        if question_context.get("explanation"):
            detail_lines.append(f"Pembahasan Resmi Soal: {question_context.get('explanation')}")
        if question_context.get("sample_answer"):
            detail_lines.append(f"Contoh Jawaban Ideal Esai: {question_context.get('sample_answer')}")
        rationale_raw = question_context.get("ai_grading_rationale")
        if rationale_raw:
            try:
                parsed_rationale = json.loads(rationale_raw) if isinstance(rationale_raw, str) else rationale_raw
                if isinstance(parsed_rationale, dict) and "evaluations" in parsed_rationale:
                    detail_lines.append("\n=== DIAGNOSIS KOREKSI DECISION ENGINE (RESPAN SPAN-01 LITE) ===")
                    detail_lines.append(f"Model Penilai: {parsed_rationale.get('model', 'respan/span-01-lite')}")
                    for ev in parsed_rationale.get("evaluations", []):
                        status_str = "TERPENUHI (Sudah Benar)" if ev.get("status") == "passed" else "BELUM TERPENUHI (Terlewat / Kurang)"
                        detail_lines.append(f"- Kriteria: '{ev.get('statement')}' -> {status_str} (Tingkat Pemenuhan: {int(ev.get('noul', 0)*100)}%)")
                    if parsed_rationale.get("misconception_detected"):
                        detail_lines.append(f"- PERINGATAN MISKONSEPSI: Terdeteksi konsep terbalik atau kekeliruan fatal ({int(parsed_rationale.get('misconception_score', 0)*100)}%). Luruskan poin ini kepada siswa!")
                    else:
                        detail_lines.append("- Integritas Konsep: Tidak ada miskonsepsi fatal.")
                else:
                    detail_lines.append(f"Catatan Evaluasi AI: {rationale_raw}")
            except Exception:
                detail_lines.append(f"Catatan Evaluasi AI: {rationale_raw}")

        full_system_instruction = f"{system_prompt}\n\n" + "\n".join(detail_lines)

        # 2. Build Native Multi-Turn Conversation Memory for Tutor
        gemini_contents = self._format_conversation_contents(history, message)

        text = self._call_gemini(
            contents=gemini_contents,
            system_instruction=full_system_instruction,
            json_mode=False,
            temperature=0.6,
            api_key=api_key,
        )

        if text:
            reply_text = text.strip()
            memory_cache.set(cache_key, reply_text, ttl=600)
            return reply_text

        # Fallback to mock adapter
        fallback_res = mock_ai_service.chat_question_explanation(
            question_context=question_context,
            message=message,
            history=history,
            api_key=api_key,
        )
        memory_cache.set(cache_key, fallback_res, ttl=300)
        return fallback_res


# Singleton
gemini_ai_service = GeminiAdapter()

