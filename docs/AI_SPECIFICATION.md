# EXAMIND — AI & LLM Engine Specifications

**Versi:** 1.0  
**Tanggal:** 31 Agustus 2026  
**Dokumen Induk:** [docs/PRD.md](./PRD.md) | [docs/ARCHITECTURE.md](./ARCHITECTURE.md)  

---

## 1. Arsitektur Adapter AI Modular

EXAMIND dirancang dengan pola **Adapter Pattern** yang memisahkan logika aplikasi utama dari implementasi spesifik vendor LLM (Google Gemini, OpenAI, Groq, Anthropic, atau Ollama Lokal).

```
┌───────────────────────────────────────────────────────────┐
│                    AIServiceInterface                     │
│  + generate_questions(payload: QuestionGenRequest)        │
│  + grade_essay(payload: EssayGradingRequest)              │
│  + generate_explanation(payload: ExplanationRequest)      │
└─────────────────────────────┬─────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ GeminiAdapter│       │ OpenAIAdapter│       │ OllamaAdapter│
└──────────────┘       └──────────────┘       └──────────────┘
```

---

## 2. Spesifikasi Prompt & Skema Validasi Pydantic

### 2.1 Prompt AI Question Generator

#### System Prompt:
```text
Anda adalah pakar kurikulum dan penyusun soal ujian profesional berstandar nasional (Kemendikbud).
Tugas Anda adalah membuat butir soal ujian berkualitas tinggi berdasarkan topik, materi, tingkat kesulitan, dan taksonomi Bloom yang ditentukan.

ATURAN WAJIB:
1. Soal harus memiliki konteks jelas, tidak ambigu, dan berbasis penalaran kritis.
2. Untuk Pilihan Ganda: buat 4 atau 5 opsi jawaban. Setiap opsi pengecoh (distractor) harus masuk akal dan memiliki penjelasan rasional (distractor analysis) mengapa opsi tersebut salah.
3. Untuk Soal Esai: wajib sertakan matriks rubrik penilaian 4 dimensi lengkap dengan bobot dan kata kunci esensial.
4. Output WAJIB berupa JSON murni yang mematuhi skema yang ditentukan tanpa teks pengantar atau penutup.
```

#### User Prompt Template:
```text
Buatkan paket soal ujian dengan spesifikasi berikut:
- Mata Pelajaran: {subject}
- Topik / Materi: {topic_content}
- Tingkat Kelas: {grade_level}
- Jumlah Soal Pilihan Ganda: {mcq_count}
- Jumlah Soal Esai: {essay_count}
- Tingkat Kesulitan: {difficulty} (easy/medium/hard)
- Bahasa: Bahasa Indonesia baku
```

#### Skema Output Pydantic (Pilihan Ganda):
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class DistractorRationale(BaseModel):
    option_id: str = Field(description="Huruf opsi, misal 'A', 'B'")
    text: str = Field(description="Teks pilihan jawaban")
    is_correct: bool = Field(description="True jika ini adalah kunci jawaban")
    rationale: str = Field(description="Penjelasan ilmiah mengapa opsi ini benar atau salah")

class GeneratedQuestionMCQ(BaseModel):
    prompt: str = Field(description="Teks pertanyaan utama (bisa markdown)")
    difficulty: str = Field(description="easy, medium, atau hard")
    bloom_level: str = Field(description="C1, C2, C3, C4, C5, atau C6")
    options: List[DistractorRationale]
    correct_option_id: str
    explanation: str = Field(description="Pembahasan konseptual lengkap")
    points: float = Field(default=10.0)
```

---

### 2.2 Prompt AI Essay Auto-Grading (Penilai Esai Cerdas)

#### System Prompt:
```text
Anda adalah asisten pengoreksi ujian akademik yang objektif, adil, dan cermat.
Tugas Anda adalah menilai jawaban esai siswa berdasarkan Rubrik Penilaian 4 Dimensi yang telah ditetapkan oleh guru.

METODOLOGI EVALUASI:
1. Baca pertanyaan dan jawaban ideal/kunci terlebih dahulu.
2. Bandingkan jawaban siswa terhadap masing-masing 4 dimensi rubrik:
   - Dimensi 1: Kesesuaian Konsep Inti (Maks 40 Poin)
   - Dimensi 2: Kedalaman & Kelengkapan Argumen (Maks 30 Poin)
   - Dimensi 3: Akurasi Terminologi & Fakta (Maks 15 Poin)
   - Dimensi 4: Kejelasan Struktur & Logika (Maks 15 Poin)
3. Hitung total skor (0 - 100).
4. Tentukan tingkat keyakinan Anda (high, medium, low) berdasarkan kejelasan argumen siswa dan kesesuaian rubrik.
5. Berikan penjelasan edukatif kepada siswa mengenai apa yang sudah tepat dan bagian mana yang kurang lengkap.
6. Output WAJIB berupa JSON murni sesuai skema.
```

#### User Prompt Template:
```text
PERTANYAAN:
{question_prompt}

KUNCI JAWABAN IDEAL / PANDUAN GURU:
{rubric_guidelines}

JAWABAN SISWA:
"""
{student_response}
"""

Evaluasilah jawaban siswa di atas dan berikan skor sesuai rubrik!
```

#### Skema Output Pydantic (Grading Result):
```python
class RubricDimensionScore(BaseModel):
    dimension_name: str
    max_points: float
    awarded_points: float
    comment: str

class EssayGradingOutput(BaseModel):
    dimensions: List[RubricDimensionScore]
    total_score: float = Field(ge=0, le=100, description="Total nilai akhir skala 0-100")
    ai_confidence_level: str = Field(description="high, medium, atau low")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Nilai probabilitas keyakinan AI")
    grading_rationale: str = Field(description="Alasan penilaian mendalam untuk guru")
    student_explanation: str = Field(description="Umpan balik penjelasan ramah untuk siswa")
```

---

### 2.3 Prompt Formative Answer Explanation (Penjelasan Formatif)

#### System Prompt:
```text
Anda adalah guru pembimbing yang ramah dan suportif.
Tugas Anda adalah memberikan penjelasan formatif atas hasil pengerjaan soal siswa agar siswa dapat belajar dari kesalahan mereka atau memperdalam pemahaman konsep mereka.

PANDUAN PENULISAN:
- Gunakan bahasa Indonesia yang santun, memotivasi, dan mudah dipahami siswa.
- Jika siswa menjawab BENAR: Berikan apresiasi, rangkum poin kunci keberhasilan logikanya, dan berikan wawasan pengayaan singkat.
- Jika siswa menjawab SALAH / KURANG LENGKAP: Jangan hanya menyalahkan. Jelaskan dengan runtut di mana letak miskonsepsinya, bagian konsep apa yang terlupa, dan langkah berpikir yang benar.
```

---

## 3. Strategi Penanganan Error & Anti-Halusinasi

1. **Schema Strictness**: Menggunakan *Structured Outputs* (OpenAI JSON Mode / Gemini JSON Schema) untuk memastikan output tidak pernah gagal di-parse oleh backend Pydantic.
2. **Deterministic Fallback**: Jika model LLM mengalami kegagalan respons (timeout/rate limit):
   - Backend menandai status jawaban sebagai `needs_manual_review` dengan confidence `low`.
   - Guru mendapatkan notifikasi prioritas di dashboard untuk mengoreksi secara manual tanpa mengganggu proses siswa lain.
3. **Keyword Proximity Validation**: Sistem melakukan pra-pemeriksaan kata kunci esensial menggunakan regex/string matching sederhana sebelum hasil LLM diterima, memastikan skor tidak menyimpang secara ekstrem.
