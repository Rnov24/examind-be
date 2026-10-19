import logging
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_DECISION_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


class RespanDecisionGrader:
    """High-efficiency short answer and essay evaluator powered by Respan Span-01 Lite.

    Uses OpenRouter's Decisions API to perform zero-output-token evaluation against
    atomic semantic reference criteria with calibrated Bayesian probabilities.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 12.0,
        task_id: Optional[str] = None,
    ):
        # Vault first (settable via Secret Manager UI), then env settings.
        # task_id selects which task config to read (TASK_SHORT_ANSWER_GRADING or TASK_CHATBOT_GUARDRAIL).
        vault_key = None
        task_model = None
        try:
            from app.core.secret_manager import get_secret
            import json
            vault_key = get_secret("OPENROUTER_API_KEY")
            if task_id:
                task_raw = get_secret(task_id)
                if task_raw:
                    try:
                        task_cfg = json.loads(task_raw)
                        if isinstance(task_cfg, dict):
                            if task_cfg.get("model"):
                                task_model = task_cfg["model"]
                            # Task-level dedicated key wins over global vault key
                            if task_cfg.get("api_key"):
                                vault_key = task_cfg["api_key"]
                    except Exception:
                        pass
        except Exception:
            pass
        self.api_key = api_key or vault_key or settings.OPENROUTER_API_KEY
        self.model = model or task_model or getattr(settings, "OPENROUTER_DECISION_MODEL", "respan/span-01-lite")
        self.timeout = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-or-"))

    def call_decisions_api(
        self,
        state: str,
        questions: Dict[str, Any],
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls OpenRouter alpha decisions API.

        Expected question format for Respan:
        {
          "question_key": {
            "type": "noul",
            "instructions": "plain string question",
            "criteria": {
              "true": "plain string criteria for true",
              "false": "plain string criteria for false"
            }
          }
        }
        """
        active_key = custom_key or self.api_key
        if not active_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }

        headers = {
            "Authorization": f"Bearer {active_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://examind.id",
            "X-Title": "EXAMIND CBT Education Platform",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(OPENROUTER_DECISION_ENDPOINT, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(
                    f"[RespanDecisionGrader] OpenRouter returned status {resp.status_code}: {resp.text}"
                )
                raise RuntimeError(f"OpenRouter Decision API error: {resp.text}")
            return resp.json()

    def build_rubric_questions(
        self,
        prompt: str,
        rubric: Optional[Dict[str, Any]],
        ideal_answer: str,
    ) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """Builds state string and typed noul questions from rubric_json or ideal_answer.

        Returns (ref_state_str, questions_dict, ref_metadata_list)
        """
        ref_points = []

        # Check if rubric already has structured ref_points
        if isinstance(rubric, dict) and "ref_points" in rubric and isinstance(rubric["ref_points"], list):
            ref_points = rubric["ref_points"]
        elif isinstance(rubric, dict) and any(k.startswith("dimension_") for k in rubric.keys()):
            # Adapt legacy 4D rubric
            idx = 1
            for k, v in rubric.items():
                crit_text = v.get("criteria", "") if isinstance(v, dict) else str(v)
                if crit_text:
                    label = k.replace("dimension_", "").replace("_", " ").title()
                    ref_points.append({
                        "id": f"dim_{idx}",
                        "statement": f"{label}: {crit_text}",
                        "weight": 0.25,
                        "instructions": f"Apakah jawaban siswa memenuhi dimensi {label}?",
                        "criteria": {
                            "true": f"Memenuhi kriteria: {crit_text}",
                            "false": f"Gagal memenuhi kriteria: {crit_text}",
                        },
                    })
                    idx += 1

        # Fallback to parsing ideal_answer if ref_points is empty
        if not ref_points:
            raw_lines = [
                line.strip().lstrip("0123456789.-)• ")
                for line in (ideal_answer or prompt).split("\n")
                if len(line.strip()) > 6
            ]
            if not raw_lines:
                raw_lines = [
                    s.strip()
                    for s in (ideal_answer or prompt).split(".")
                    if len(s.strip()) > 10
                ]

            raw_lines = raw_lines[:4]  # Maximum 4 key points for token efficiency
            if not raw_lines:
                raw_lines = [ideal_answer or "Jawaban tepat sesuai konsep pertanyaan"]

            weight_per_point = round(1.0 / len(raw_lines), 3)
            for idx, line in enumerate(raw_lines, 1):
                ref_points.append({
                    "id": f"point_{idx}",
                    "statement": line,
                    "weight": weight_per_point,
                    "instructions": f"Apakah jawaban siswa secara tepat memuat atau mengimplikasikan konsep: '{line}'?",
                    "criteria": {
                        "true": f"Memuat inti konsep '{line}'. Sinonim, parafrase, atau analogi valid.",
                        "false": f"Tidak memuat atau bertentangan dengan '{line}'.",
                    },
                })

        # Build Ref string for state
        ref_lines = []
        for idx, pt in enumerate(ref_points, 1):
            ref_lines.append(f"({idx}) {pt.get('statement')}")
        ref_state_str = "\n".join(ref_lines)

        # Build Questions payload for Respan
        questions = {}
        for pt in ref_points:
            pid = pt["id"]
            statement = pt.get("statement", "")
            questions[pid] = {
                "type": "noul",
                "instructions": f"Apakah Teks Jawaban Siswa secara tepat memuat atau mengimplikasikan konsep: '{statement}'?",
                "criteria": {
                    "true": f"Teks Jawaban Siswa memuat atau mengimplikasikan inti konsep '{statement}'. Sinonim, parafrase, dan bahasa sehari-hari valid.",
                    "false": f"Teks Jawaban Siswa sama sekali tidak memuat, melewatkan, atau bertentangan dengan '{statement}'.",
                },
            }

        # Add Misconception detector
        questions["has_misconception"] = {
            "type": "noul",
            "instructions": "Apakah pada Teks Jawaban Siswa terdapat miskonsepsi prinsip dasar, konsep terbalik, atau kekeliruan fakta fatal?",
            "criteria": {
                "true": "Teks Jawaban Siswa memuat kekeliruan konsep fundamental, prinsip terbalik, atau penjelasan yang salah fatal.",
                "false": "Teks Jawaban Siswa konsisten secara konsep dasar dan tidak memuat pernyataan terbalik.",
            },
        }

        return ref_state_str, questions, ref_points

    def grade_short_answer(
        self,
        prompt: str,
        rubric: Optional[Dict[str, Any]],
        ideal_answer: str,
        student_answer: str,
        allocated_points: float = 10.0,
        custom_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Grades a short answer / essay using respan/span-01-lite.

        Returns comprehensive result dictionary with 0-token rationale.
        """
        cleaned_ans = (student_answer or "").strip()
        if not cleaned_ans:
            return {
                "total_score": 0.0,
                "confidence_level": "high",
                "confidence_score": 1.0,
                "rationale": "Siswa tidak mengisi lembar jawaban (jawaban kosong).",
                "rationale_json": {
                    "model": self.model,
                    "provider": "Respan",
                    "total_score": 0.0,
                    "confidence_level": "high",
                    "evaluations": [],
                    "misconception_score": 0.0,
                    "misconception_detected": False,
                    "token_usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0},
                },
                "answers": {},
                "usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0},
                "model": self.model,
                "provider": "Respan",
            }

        ref_state_str, questions, ref_points = self.build_rubric_questions(
            prompt=prompt,
            rubric=rubric,
            ideal_answer=ideal_answer,
        )

        state = f"Soal: {prompt.strip()}\n\nTeks Jawaban Siswa:\n\"{cleaned_ans}\""

        try:
            api_res = self.call_decisions_api(
                state=state,
                questions=questions,
                custom_key=custom_key,
            )
        except Exception as e:
            logger.warning(f"[RespanDecisionGrader] API call failed: {e}. Falling back to rule-based evaluation.")
            return self._heuristic_fallback(prompt, ref_points, cleaned_ans, allocated_points)

        answers = api_res.get("answers", {})
        usage = api_res.get("usage", {"input_tokens": 0, "output_tokens": 0, "cost": 0})
        model_name = api_res.get("model", self.model)

        # 1. Compute weighted score from noul probabilities
        evaluations = []
        total_weight = sum(pt.get("weight", 1.0) for pt in ref_points) or 1.0
        weighted_sum = 0.0
        min_prob_delta = 1.0

        for pt in ref_points:
            pid = pt["id"]
            noul_val = answers.get(pid, {}).get("noul", 0.0)
            weight = pt.get("weight", 1.0) / total_weight
            weighted_sum += noul_val * weight

            status = "passed" if noul_val >= 0.70 else ("partial" if noul_val >= 0.45 else "missed")
            evaluations.append({
                "point_id": pid,
                "statement": pt.get("statement"),
                "noul": round(noul_val, 4),
                "status": status,
                "weight_pct": round(weight * 100, 1),
            })
            min_prob_delta = min(min_prob_delta, abs(noul_val - 0.5))

        # 2. Misconception analysis
        misconception_val = answers.get("has_misconception", {}).get("noul", 0.0)
        has_fatal_misconception = misconception_val >= 0.75

        # Penalty if misconception detected
        final_ratio = weighted_sum
        if has_fatal_misconception:
            # Dampen score if fundamentally flawed
            penalty_factor = max(0.15, 1.0 - (misconception_val * 0.8))
            final_ratio *= penalty_factor

        final_ratio = max(0.0, min(1.0, final_ratio))
        total_score = round(final_ratio * 100.0, 1)

        # 3. Confidence level calculation
        # If decisions are clear (>0.8 or <0.2), confidence is high. If hovering near 0.5, medium/low.
        if min_prob_delta >= 0.28:
            confidence_level = "high"
            confidence_score = 0.95
        elif min_prob_delta >= 0.14:
            confidence_level = "medium"
            confidence_score = 0.75
        else:
            confidence_level = "low"
            confidence_score = 0.50

        # 4. Assemble human-readable rationale
        rationale_lines = [
            f"Evaluasi Respan Span-01 Lite ({len(ref_points)} Kriteria Teruji):",
        ]
        for ev in evaluations:
            icon = "✅" if ev["status"] == "passed" else ("🟡" if ev["status"] == "partial" else "❌")
            rationale_lines.append(
                f"{icon} {ev['statement']} (Probabilitas: {int(ev['noul'] * 100)}%)"
            )

        if has_fatal_misconception:
            rationale_lines.append(
                f"⚠️ Miskonsepsi Fatal Terdeteksi ({int(misconception_val * 100)}%) — skor disesuaikan."
            )
        else:
            rationale_lines.append(
                f"🛡️ Bebas Miskonsepsi (Integritas Konsep: {int((1.0 - misconception_val) * 100)}%)"
            )

        rationale_lines.append(
            f"Skor Relatif: {total_score}% • Tingkat Keyakinan: {confidence_level.upper()}"
        )

        rationale_str = "\n".join(rationale_lines)

        rationale_json = {
            "model": model_name,
            "provider": "Respan",
            "total_score": total_score,
            "confidence_level": confidence_level,
            "confidence_score": confidence_score,
            "evaluations": evaluations,
            "misconception_score": round(misconception_val, 4),
            "misconception_detected": has_fatal_misconception,
            "token_usage": usage,
        }

        return {
            "total_score": total_score,
            "confidence_level": confidence_level,
            "confidence_score": confidence_score,
            "rationale": rationale_str,
            "rationale_json": rationale_json,
            "answers": answers,
            "usage": usage,
            "model": model_name,
            "provider": "Respan",
        }

    def _heuristic_fallback(
        self,
        prompt: str,
        ref_points: List[Dict[str, Any]],
        student_answer: str,
        allocated_points: float,
    ) -> Dict[str, Any]:
        """Simple keyword overlap heuristic if OpenRouter endpoint is completely offline."""
        student_words = set(student_answer.lower().split())
        matched = 0
        evaluations = []
        for pt in ref_points:
            pt_words = set(pt.get("statement", "").lower().split())
            intersection = student_words.intersection(pt_words)
            overlap_ratio = len(intersection) / max(len(pt_words), 1)
            is_pass = overlap_ratio >= 0.35
            if is_pass:
                matched += 1
            evaluations.append({
                "point_id": pt["id"],
                "statement": pt.get("statement"),
                "noul": round(min(1.0, overlap_ratio + 0.2), 2),
                "status": "passed" if is_pass else "missed",
                "weight_pct": round(100 / max(len(ref_points), 1), 1),
            })

        score_pct = round((matched / max(len(ref_points), 1)) * 100.0, 1)
        return {
            "total_score": score_pct,
            "confidence_level": "medium",
            "confidence_score": 0.70,
            "rationale": f"Penilaian Heuristik Cadangan: {matched}/{len(ref_points)} konsep terdeteksi.",
            "rationale_json": {
                "model": "heuristic-fallback",
                "provider": "Local",
                "total_score": score_pct,
                "confidence_level": "medium",
                "confidence_score": 0.70,
                "evaluations": evaluations,
                "misconception_score": 0.0,
                "misconception_detected": False,
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0},
            },
            "answers": {},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0},
            "model": "heuristic-fallback",
            "provider": "Local",
        }


# Singleton accessor
_respan_grader_instances: dict = {}


def get_respan_grader(task_id: Optional[str] = None) -> RespanDecisionGrader:
    global _respan_grader_instances
    # Per-task instances: grading and guardrail can have independent configs.
    # Re-create if not configured: the key may have been added via Secret Manager UI after first use.
    key = task_id or "default"
    inst = _respan_grader_instances.get(key)
    if inst is None or not inst.is_configured():
        inst = RespanDecisionGrader(task_id=task_id)
        _respan_grader_instances[key] = inst
    return inst
