import random
import re
from typing import Dict, Any, List, Optional
from app.services.ai.base import AIServiceInterface
from app.services.ai.rubric_generator import generate_4d_rubric
from app.schemas.question import (
    AIGenerateRequest,
    AIGenerateData,
    GeneratedQuestionMCQ,
    GeneratedQuestionEssay,
    OptionSchema,
)


class MockAIService(AIServiceInterface):
    """Robust, deterministic mock generator and grader for offline testing and demo."""

    def generate_questions(self, request: AIGenerateRequest) -> AIGenerateData:
        topic = request.topic_content.strip() if request.topic_content else "Materi Terkait"
        subject = request.subject.strip() if request.subject else "Umum"
        topic_clean = topic[:80]

        # Categorize domain for richer semantic templates
        text_lower = f"{subject} {topic}".lower()

        is_bio = any(k in text_lower for k in ["bio", "sel", "fotosintesis", "tumbuhan", "hewan", "organ", "genet", "darah", "tubuh", "pernapasan"])
        is_math = any(k in text_lower for k in ["matematika", "hitung", "aljabar", "trigonometri", "sudut", "fungsi", "integral", "turunan", "matriks"])
        is_social = any(k in text_lower for k in ["sejarah", "ekonomi", "sosio", "geografi", "hukum", "politik", "pancasila", "pasar", "inflasi"])

        mcqs: List[GeneratedQuestionMCQ] = []
        for i in range(1, request.mcq_count + 1):
            if is_bio:
                if i == 1:
                    prompt = f"Dalam mekanisme biologis {topic_clean}, fungsi fisiologis utama yang membedakan proses ini adalah..."
                    opts = [
                        OptionSchema(id="A", text=f"Regulasi transport aktif melalui membran semipermeabel", is_correct=False, rationale=f"Transport membran adalah mekanisme seluler umum, bukan spesifik pada {topic_clean}."),
                        OptionSchema(id="B", text=f"Transduksi energi biokimia dan sintesis molekul organik spesifik", is_correct=True, rationale=f"Inti dari proses {topic_clean} adalah konversi biokimiawi molekuler secara terarah."),
                        OptionSchema(id="C", text=f"Lisis dinding sel akibat tekanan turgor berlebih", is_correct=False, rationale=f"Lisis seluler merupakan respon degradasi abnormal, bukan fungsi utama."),
                        OptionSchema(id="D", text=f"Penimbunan asam laktat secara anaerobik berkelanjutan", is_correct=False, rationale=f"Respon anaerobik hanya terjadi saat defisiensi oksigen ekstrem."),
                    ]
                    correct_id = "B"
                    expl = f"Prinsip fundamental {topic_clean} bertumpu pada efisiensi biokimiawi dalam metabolisme dan adaptasi organisme."
                elif i == 2:
                    prompt = f"Apakah konsekuensi yang terjadi apabila tahapan enzimatik pada {topic_clean} mengalami inhibisi kompetitif?"
                    opts = [
                        OptionSchema(id="A", text=f"Laju reaksi menurun karena substrat terhalang menduduki sisi aktif enzim", is_correct=True, rationale=f"Inhibitor kompetitif bersaing langsung dengan substrat pada sisi aktif enzim terkait {topic_clean}."),
                        OptionSchema(id="B", text=f"Struktur primer protein enzim terdenaturasi secara permanen", is_correct=False, rationale=f"Inhibisi kompetitif bersifat reversibel dan tidak mengubah struktur primer rantai polipeptida."),
                        OptionSchema(id="C", text=f"Nilai Km enzim tetap konstan sementara Vmax menurun", is_correct=False, rationale=f"Pada inhibisi kompetitif, Vmax tetap dapat tercapai jika konsentrasi substrat dinaikkan."),
                        OptionSchema(id="D", text=f"Reaksi berhenti total tanpa dipengaruhi konsentrasi substrat", is_correct=False, rationale=f"Efek inhibisi dapat diatasi dengan penambahan substrat yang melimpah."),
                    ]
                    correct_id = "A"
                    expl = f"Dinamika regulasi enzim dalam {topic_clean} dipengaruhi afinitas pengikatan pada sisi aktif kompleks enzim-substrat."
                else:
                    prompt = f"Manakah analisis komparatif berikut yang PALING TEPAT mengenai signifikansi ekologis atau anatomis dari {topic_clean}?"
                    opts = [
                        OptionSchema(id="A", text=f"Memicu akumulasi toksin sekunder dalam jaringan vaskular", is_correct=False, rationale=f"Akumulasi toksin sekunder adalah patologi, bukan fungsi biologis adaptif."),
                        OptionSchema(id="B", text=f"Mendukung homeostasis dan efisiensi konversi biomassa pada organisme", is_correct=True, rationale=f"Peran esensial {topic_clean} adalah memelihara keseimbangan internal (homeostasis) tubuh."),
                        OptionSchema(id="C", text=f"Menghambat sintesis ATP pada membran mitokondria", is_correct=False, rationale=f"Inhibisi ATP synthase justru merusak metabolisme seluler."),
                        OptionSchema(id="D", text=f"Mengurangi keragaman alel pada populasi lokal", is_correct=False, rationale=f"Variasi alel diatur oleh genetika populasi dan seleksi alam."),
                    ]
                    correct_id = "B"
                    expl = f"Keberlangsungan sistem biologi pada topik {topic_clean} menjamin integritas homeostasis metabolik."
            elif is_math:
                if i == 1:
                    prompt = f"Berdasarkan definisi matematis dan kaidah aljabar pada materi {topic_clean}, kondisi esensial yang harus dipenuhi adalah..."
                    opts = [
                        OptionSchema(id="A", text=f"Determinan matriks koefisien selalu bernilai nol", is_correct=False, rationale=f"Determinan nol menunjukkan matriks singular tanpa invers unik."),
                        OptionSchema(id="B", text=f"Konsistensi relasi fungsi dan terpenuhinya domain real yang terdefinisi", is_correct=True, rationale=f"Kaidah dasar {topic_clean} menuntut argumen operasi berada dalam himpunan domain valid."),
                        OptionSchema(id="C", text=f"Turunan parsial kedua selalu bernilai konstan negatif", is_correct=False, rationale=f"Hanya berlaku pada fungsi kuadratik cekung ke bawah khusus."),
                        OptionSchema(id="D", text=f"Asimtot tegak terbentuk pada setiap titik diskontinu", is_correct=False, rationale=f"Titik lubang (removable discontinuity) tidak selalu membentuk asimtot tegak."),
                    ]
                    correct_id = "B"
                    expl = f"Fondasi kalkulasi {topic_clean} mewajibkan pemenuhan syarat eksistensi domain dan ketunggalan pemetaan fungsi."
                else:
                    prompt = f"Dalam menyelesaikan permasalahan {topic_clean}, langkah analisis yang paling terstruktur dan terverifikasi secara matematis adalah..."
                    opts = [
                        OptionSchema(id="A", text=f"Mengeliminasi variabel terikat secara acak tanpa memperhatikan ekuivalensi", is_correct=False, rationale=f"Operasi aljabar harus mempertahankan relasi ekuivalensi kedua ruas."),
                        OptionSchema(id="B", text=f"Menerapkan transformasi aljabar yang mempertahankan invarian solusi dan menguji titik uji", is_correct=True, rationale=f"Metode ini menjamin tidak ada akar semu yang terlewat atau solusi asing yang keliru."),
                        OptionSchema(id="C", text=f"Mengabaikan syarat batas pertidaksamaan pada penyebut", is_correct=False, rationale=f"Penyebut nol menyebabkan nilai tak terdefinisi."),
                        OptionSchema(id="D", text=f"Mengasumsikan semua variabel bernilai skalar non-negatif", is_correct=False, rationale=f"Restriksi sempit dapat menghilangkan himpunan penyelesaian real lainnya."),
                    ]
                    correct_id = "B"
                    expl = f"Validitas pembuktian dan perhitungan {topic_clean} memerlukan penegakan ketat sifat-sifat aljabar ekuivalen."
            elif is_social:
                if i == 1:
                    prompt = f"Berdasarkan perspektif kajian {subject} mengenai {topic_clean}, faktor struktural utama yang memicu dinamika fenomena tersebut adalah..."
                    opts = [
                        OptionSchema(id="A", text=f"Interaksi dialektis antara kondisi sosio-ekologis dan kebijakan institusional", is_correct=True, rationale=f"Analisis komprehensif {topic_clean} menunjukkan dinamika selalu dipicu perpaduan faktor struktural dan sosial."),
                        OptionSchema(id="B", text=f"Ketiadaan interaksi budaya antar kelompok masyarakat", is_correct=False, rationale=f"Isolasi mutlak sangat jarang menjadi penyebab tunggal fenomena modern."),
                        OptionSchema(id="C", text=f"Penyeragaman total pola konsumsi tanpa diferensiasi peran", is_correct=False, rationale=f"Masyarakat selalu memiliki stratifikasi dan diferensiasi peran."),
                        OptionSchema(id="D", text=f"Fluktuasi iklim mikro semata tanpa variabel demografis", is_correct=False, rationale=f"Faktor geografis lingkungan bersifat kontekstual, bukan determinan tunggal."),
                    ]
                    correct_id = "A"
                    expl = f"Pemahaman {topic_clean} dalam {subject} menuntut penelaahan holistik terhadap korelasi sebab-akibat sosial."
                else:
                    prompt = f"Manakah argumen berikut yang paling representatif dalam mengevaluasi implikasi jangka panjang dari {topic_clean}?"
                    opts = [
                        OptionSchema(id="A", text=f"Stagnasi permanen dalam seluruh tatanan kelembagaan", is_correct=False, rationale=f"Dinamika masyarakat selalu memicu proses adaptasi dan transformasi."),
                        OptionSchema(id="B", text=f"Terbentuknya konsensus baru dan transformasi pola adaptasi masyarakat", is_correct=True, rationale=f"Dampak fundamental {topic_clean} mengarah pada rekonseptualisasi norma dan struktur masyarakat."),
                        OptionSchema(id="C", text=f"Hilangnya seluruh kearifan lokal dalam waktu seketika", is_correct=False, rationale=f"Perubahan budaya berlangsung bertahap melalui akulturasi atau asimilasi."),
                        OptionSchema(id="D", text=f"Ketergantungan absolut pada satu figur otoritas formal", is_correct=False, rationale=f"Dinamika sosial melibatkan partisipasi multi-aktor."),
                    ]
                    correct_id = "B"
                    expl = f"Evaluasi kritis terhadap {topic_clean} memperlihatkan bagaimana tatanan adaptif berkembang seiring waktu."
            else:
                # General scientific / academic question template tailored to topic
                if i == 1:
                    prompt = f"Berdasarkan konsep dasar {subject} mengenai '{topic_clean}', prinsip fundamental yang paling esensial dalam memahami materi ini adalah..."
                    opts = [
                        OptionSchema(id="A", text=f"Penerapan hukum konservasi dan relasi sebab-akibat yang mendasari {topic_clean}", is_correct=True, rationale=f"Setiap analisis dalam {topic_clean} harus berpijak pada prinsip kausalitas ilmiah yang teruji."),
                        OptionSchema(id="B", text=f"Karakteristik acak yang tidak dapat diprediksi melalui formulasi konseptual", is_correct=False, rationale=f"Konsep {topic_clean} memiliki pola terstruktur dan hukum empiris yang jelas."),
                        OptionSchema(id="C", text=f"Asumsi bahwa semua variabel lingkungan bernilai tetap tanpa variasi", is_correct=False, rationale=f"Dunia nyata selalu memiliki dinamika parameter dinamis yang saling berinteraksi."),
                        OptionSchema(id="D", text=f"Pengabaian hubungan timbal balik antar komponen sistem", is_correct=False, rationale=f"Pendekatan sistemik menuntut pemahaman interkoneksi antar elemen."),
                    ]
                    correct_id = "A"
                    expl = f"Penguasaan {topic_clean} memerlukan identifikasi hukum dasar dan logika keteraturan sistemnya."
                elif i == 2:
                    prompt = f"Manakah di antara pernyataan berikut yang PALING TEPAT menggambarkan aplikasi atau analisis kasus dari '{topic_clean}'?"
                    opts = [
                        OptionSchema(id="A", text=f"Efisiensi optimal tercapai ketika variabel penentu dikondisikan sesuai ambang kritis", is_correct=True, rationale=f"Studi empiris pada {topic_clean} membuktikan bahwa nilai ambang kritis menentukan keberhasilan proses."),
                        OptionSchema(id="B", text=f"Hasil proses selalu menurun seiring bertambahnya sumber daya pendukung", is_correct=False, rationale=f"Dalam rentang kerja ideal, penambahan sumber daya justru meningkatkan output."),
                        OptionSchema(id="C", text=f"Tidak diperlukan verifikasi data lapangan untuk membuktikan keabsahan hipotesis", is_correct=False, rationale=f"Metode saintifik mewajibkan validasi data empiris."),
                        OptionSchema(id="D", text=f"Semua komponen bekerja independen tanpa ada keterkaitan fungsional", is_correct=False, rationale=f"Komponen dalam {topic_clean} saling bertaut dan terkoordinasi."),
                    ]
                    correct_id = "A"
                    expl = f"Penerapan praktis {topic_clean} mendemonstrasikan pentingnya pengendalian variabel dan ambang batas optimal."
                else:
                    prompt = f"Butir Soal {i}: Jika dilakukan evaluasi komprehensif terhadap '{topic_clean}', bagaimanakah cara mengoptimalkan pemahaman konsep dan hasil evaluasinya?"
                    opts = [
                        OptionSchema(id="A", text=f"Hanya menghafal definisi tekstual tanpa memahami aplikasi penalaran", is_correct=False, rationale=f"Hafalan mekanis tidak melatih kemampuan penalaran tingkat tinggi (HOTS)."),
                        OptionSchema(id="B", text=f"Menghubungkan teori konseptual dengan bukti empiris dan pemecahan masalah kontekstual", is_correct=True, rationale=f"Pembelajaran mendalam pada {topic_clean} dicapai melalui sintesis konseptual dan pemecahan masalah nyata."),
                        OptionSchema(id="C", text=f"Menolak data eksperimen yang tidak sesuai praduga awal", is_correct=False, rationale=f"Sikap ilmiah menuntut objektivitas terhadap temuan data yang valid."),
                        OptionSchema(id="D", text=f"Menggeneralisasi satu kasus khusus menjadi hukum universal tanpa pengujian", is_correct=False, rationale=f"Generalisasi terburu-buru adalah kekeliruan logika (hasty generalization)."),
                    ]
                    correct_id = "B"
                    expl = f"Evaluasi bermutu pada materi {topic_clean} menguji kapabilitas sintesis dan penalaran kritis siswa."

            mcqs.append(
                GeneratedQuestionMCQ(
                    prompt=prompt,
                    difficulty=request.difficulty or "medium",
                    bloom_level="C3" if i % 2 == 1 else "C4",
                    options=opts,
                    correct_option_id=correct_id,
                    explanation=expl,
                    points=10.0,
                )
            )

        essays: List[GeneratedQuestionEssay] = []
        for j in range(1, request.essay_count + 1):
            if j == 1:
                p = f"Jelaskan secara mendalam konsep fundamental mengenai '{topic_clean}' dalam mata pelajaran {subject}! Uraikan prinsip-prinsip utamanya dan berikan contoh konkret penerapannya dalam kehidupan sehari-hari."
                ideal = f"Jawaban yang komprehensif harus memuat: 1) Definisi dan konsep esensial dari {topic_clean}, 2) Penjelasan mekanisme kerja atau alur penalaran utama dengan terminologi ilmiah yang tepat, 3) Contoh kasus nyata yang relevan, dan 4) Analisis dampak atau implikasi dari fenomena tersebut."
            else:
                p = f"Lakukan analisis kritis mengenai tantangan atau studi kasus yang berkaitan dengan '{topic_clean}'. Bagaimana strategi pemecahan masalah yang efektif berdasarkan kaidah ilmiah {subject}?"
                ideal = f"Analisis harus mencakup identifikasi akar masalah terkait {topic_clean}, elaborasi alternatif solusi terstruktur dengan argumen logis yang kuat, serta evaluasi kelebihan dan keterbatasan dari masing-masing pendekatan."

            rubric = generate_4d_rubric(p, subject)
            ref_pts = [
                {
                    "id": "p1",
                    "statement": f"Konsep esensial dan definisi mekanisme {topic_clean}",
                    "weight": 0.5,
                },
                {
                    "id": "p2",
                    "statement": f"Alur penalaran logis, terminologi tepat, dan contoh konkret {topic_clean}",
                    "weight": 0.5,
                },
            ]
            rubric["ref_points"] = ref_pts

            essays.append(
                GeneratedQuestionEssay(
                    prompt=p,
                    difficulty="hard",
                    bloom_level="C4" if j == 1 else "C5",
                    rubric=rubric,
                    ideal_answer=ideal,
                    explanation=f"Penilaian esai {topic_clean} menitikberatkan pada ketepatan konsep (50%) dan penalaran kontekstual (50%).",
                    points=20.0,
                )
            )

        return AIGenerateData(mcq_questions=mcqs, essay_questions=essays)

    def grade_essay(
        self, prompt: str, rubric: Dict[str, Any], ideal_answer: str, student_answer: str
    ) -> Dict[str, Any]:
        """Evaluates student essay using respan/span-01-lite if available, or heuristic fallback."""
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
                        "decision_model": res.get("model", "respan/span-01-lite"),
                    }
        except Exception as exc:
            pass

        if not student_answer or len(student_answer.strip()) < 10:
            return {
                "total_score": 0.0,
                "dimension_scores": {
                    "dimension_1_concept": 0.0,
                    "dimension_2_argument": 0.0,
                    "dimension_3_terminology": 0.0,
                    "dimension_4_clarity": 0.0,
                },
                "confidence_level": "high",
                "rationale": "Jawaban kosong atau terlalu pendek untuk dinilai.",
                "explanation": "Siswa belum memberikan jawaban yang memadai.",
            }

        text = student_answer.lower()
        word_count = len(text.split())

        # Simple semantic keyword matching heuristic
        concept_keywords = ["foton", "energi", "frekuensi", "kuantum", "gelombang", "elektron", "klasik", "fungsi kerja", "h", "cahaya", "paket", "emisi"]
        found_keywords = [k for k in concept_keywords if k in text]
        keyword_ratio = min(len(found_keywords) / 5.0, 1.0)

        # Length factor (up to 60 words = full length score)
        length_factor = min(word_count / 50.0, 1.0)

        score_1 = round(40.0 * (0.4 * length_factor + 0.6 * keyword_ratio), 1)
        score_2 = round(30.0 * (0.5 * length_factor + 0.5 * keyword_ratio), 1)
        score_3 = round(15.0 * keyword_ratio, 1)
        score_4 = round(15.0 * (0.7 * length_factor + 0.3), 1)

        total = round(score_1 + score_2 + score_3 + score_4, 1)

        # Determine confidence
        if word_count > 40 and keyword_ratio > 0.6:
            confidence = "high"
        elif word_count > 20 and keyword_ratio > 0.3:
            confidence = "medium"
        else:
            confidence = "low"

        rationale = (
            f"Jawaban memuat {len(found_keywords)} kata kunci esensial ({', '.join(found_keywords[:4])}). "
            f"Struktur argumen dan elaborasi konsep dinilai cukup komprehensif dengan panjang {word_count} kata."
        )
        explanation = (
            f"Kekuatan: Menjelaskan konsep utama dengan baik. "
            f"Saran peningkatan: Perkuat perbandingan komparatif dengan teori klasik dan rumusan matematis pendukung."
        )

        return {
            "total_score": total,
            "dimension_scores": {
                "dimension_1_concept": score_1,
                "dimension_2_argument": score_2,
                "dimension_3_terminology": score_3,
                "dimension_4_clarity": score_4,
            },
            "confidence_level": confidence,
            "rationale": rationale,
            "explanation": explanation,
        }

    def generate_explanation(
        self, prompt: str, correct_answer: str, student_response: str, is_correct: bool
    ) -> str:
        if is_correct:
            return (
                f"Pilihan Anda ('{student_response}') tepat! Konsep ini berakar pada prinsip bahwa "
                f"kunci jawaban '{correct_answer}' secara akurat merefleksikan kaidah ilmiah yang ditanyakan."
            )
        else:
            return (
                f"Jawaban Anda ('{student_response}') belum tepat. Jawaban yang benar adalah '{correct_answer}'. "
                f"Alasan: Pada konteks soal ini, parameter utama ditentukan oleh kaidah dasar teori terkait, "
                f"sehingga opsi '{correct_answer}' adalah satu-satunya pilihan yang konsisten secara logis dan fisis."
            )

    def chat_assistant(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        scoped_context: Optional[str] = None,
        api_key: Optional[str] = None,
        role: Optional[str] = None,
    ) -> str:
        msg_lower = message.lower()
        
        # Scoped Database Information Fallback
        if scoped_context:
            if any(k in msg_lower for k in ["nilai terakhir", "skor terakhir", "ujian terakhir"]):
                for line in scoped_context.split("\n"):
                    if "Nilai Ujian Terakhir:" in line:
                        return f"Berdasarkan data akademik Anda di EXAMIND:\n{line.strip()}."
                return "Anda belum memiliki data riwayat ujian yang telah selesai dinilai."

            if any(k in msg_lower for k in ["rata", "rata-rata", "average"]):
                for line in scoped_context.split("\n"):
                    if "Rata-rata Nilai:" in line:
                        return f"Rata-rata nilai ujian Anda saat ini adalah: {line.split(':')[-1].strip()}."
                return "Data rata-rata nilai belum dapat dihitung karena belum ada ujian yang selesai dinilai."

            if any(k in msg_lower for k in ["jadwal", "mendatang", "kapan ujian", "ujian besok", "aktif"]):
                if "=== JADWAL UJIAN MENDATANG / AKTIF ===" in scoped_context:
                    parts = scoped_context.split("=== JADWAL UJIAN MENDATANG / AKTIF ===")[1].split("===")[0].strip()
                    return f"Berikut jadwal ujian mendatang yang terdaftar untuk kelas Anda:\n\n{parts}"
                return "Saat ini belum ada jadwal ujian baru untuk kelas Anda."

            if any(k in msg_lower for k in ["daftar ujian", "riwayat", "rekap", "semua ujian", "daftar nilai"]):
                if "=== DAFTAR RIWAYAT UJIAN & NILAI SISWA ===" in scoped_context:
                    parts = scoped_context.split("=== DAFTAR RIWAYAT UJIAN & NILAI SISWA ===")[1].split("===")[0].strip()
                    return f"Berikut riwayat pengerjaan ujian Anda:\n\n{parts}"
                return "Belum ada riwayat ujian yang tercatat di akun Anda."

        if any(k in msg_lower for k in ["soal", "bank", "buat"]):
            return (
                "Tentu! Anda dapat membuka menu 'Bank Soal & AI Generator' di navigasi kiri "
                "untuk membuat butir soal otomatis berstandar kurikulum nasional."
            )
        elif any(k in msg_lower for k in ["rubrik", "esai", "koreksi"]):
            return (
                "Sistem penilaian esai EXAMIND menggunakan matriks 4 Dimensi: "
                "1) Konsep Inti (40%), 2) Alur Argumen (30%), 3) Terminologi (15%), dan 4) Kejelasan Bahasa (15%)."
            )
        elif any(k in msg_lower for k in ["proctoring", "kamera", "curang", "integritas"]):
            return (
                "Sistem pengawasan EXAMIND menggunakan Dual-Camera Proctoring dengan prinsip Human-in-the-Loop. "
                "AI hanya menandai (flagging) insiden untuk ditinjau secara objektif oleh guru/pengawas."
            )
        elif any(k in msg_lower for k in ["promo", "voucher", "diskon", "harga", "pricing", "paket"]):
            if scoped_context and "=== DATA PROMO" in scoped_context:
                parts = scoped_context.split("=== DATA PROMO")[1]
                if "\n===" in parts:
                    parts = parts.split("\n===")[0]
                lines_in_part = [
                    line.strip()
                    for line in parts.splitlines()
                    if line.strip() and not line.strip().endswith("===")
                ]
                promo_content = "\n".join(lines_in_part)
                return f"Berikut informasi promo dan paket harga yang tersedia di EXAMIND:\n\n{promo_content}"

            user_role = (role or "").strip().lower()
            if not user_role and scoped_context:
                for line in scoped_context.splitlines():
                    if line.startswith("Role:"):
                        user_role = line.split(":", 1)[1].strip().lower()
                        break

            if user_role in ["student", "teacher"] or (
                scoped_context and any(r in scoped_context for r in ["Role: STUDENT", "Role: TEACHER"])
            ):
                return (
                    "Maaf, sebagai AI Assistant pada platform ujian EXAMIND, peran saya didedikasikan khusus "
                    "untuk pendampingan evaluasi pembelajaran, pembahasan butir soal, dan pengecekan data akademik Anda. "
                    "Saya tidak dapat memberikan informasi mengenai promo atau paket harga platform."
                )
            # Admin role but no promo section in context (should not happen): fail gracefully.
            return (
                "Data promo dan paket harga belum tersedia dalam konteks saat ini. "
                "Silakan coba lagi sesaat atau hubungi administrator sistem."
            )
        else:
            return (
                f"Halo! Saya EXAMIND AI Assistant. Berdasarkan data akun Anda, saya dapat membantu memeriksa "
                f"nilai ujian terakhir, jadwal ujian mendatang, ringkasan rekapitulasi nilai, serta menjawab pertanyaan pembelajaran. "
                f"Silakan ketik pertanyaan Anda atau pilih salah satu menu pintas di bawah!"
            )

    def chat_question_explanation(
        self,
        question_context: Dict[str, Any],
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        api_key: Optional[str] = None,
    ) -> str:
        prompt = question_context.get("prompt", "")
        q_type = question_context.get("question_type", "multiple_choice")
        student_ans = question_context.get("student_response") or "(Belum dijawab)"
        correct_ans = question_context.get("correct_answer") or "-"
        is_corr = question_context.get("is_correct")
        official_exp = question_context.get("explanation") or ""
        score = question_context.get("score_obtained", 0.0)
        alloc = question_context.get("allocated_points", 10.0)

        status_text = "Benar" if is_corr else "Kurang Tepat"
        
        reply = (
            f"**Tutor AI — Analisis Butir Soal #{question_context.get('question_id', '')}**\n\n"
            f"📌 **Pertanyaan:** {prompt}\n\n"
            f"👤 **Jawaban Anda:** `{student_ans}` ({status_text}, Skor: {score}/{alloc})\n"
            f"🔑 **Kunci Jawaban:** `{correct_ans}`\n\n"
            f"💡 **Pembahasan Konseptual:**\n"
            f"{official_exp or 'Prinsip utama materi ini bertumpu pada pemahaman kaidah ilmiah dasar dan penalaran analitis yang konsisten.'}\n\n"
            f"🎓 **Saran Tutor:**\n"
            f"Perhatikan kata kunci pada pertanyaan dan hindari asumsi di luar premis yang diberikan. "
            f"Jika ada bagian konsep tertentu yang masih membingungkan, silakan tanyakan langsung ke saya!"
        )
        return reply


# Singleton
mock_ai_service = MockAIService()

