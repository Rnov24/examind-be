# Ticket: GRAD-001 — Async Background AI Essay Grading Worker & ML Pipeline

- **Epic**: Epic 6 — AI Essay Auto-Grading & Teacher Override
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: AI / Backend Engineer
- **Dokumen Terkait**: [docs/AI_SPECIFICATION.md](../../AI_SPECIFICATION.md#22-prompt-ai-essay-auto-grading-penilai-esai-cerdas)

---

## 1. User Story / Objective
> **Sebagai** Sistem EXAMIND,  
> **Saya ingin** worker asinkron yang berjalan di latar belakang (*FastAPI BackgroundTasks*) untuk mengambil seluruh jawaban esai siswa dari sesi yang baru di-submit, mengevaluasi setiap butir jawaban terhadap rubrik 4 dimensi menggunakan ML Pipeline dan LLM, dan menyimpan skor sub-dimensi serta rasional penilaian,  
> **Agar** koreksi ratusan jawaban esai selesai dalam waktu $< 45$ detik per kelas tanpa memblokir alur kerja siswa.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── ml/
│   ├── pipeline.py             # Feature extraction and semantic similarity pipeline
│   └── model_serving.py        # PyTorch model loader & inference engine
├── services/grading/
│   ├── essay_grader.py         # LLM Prompt Orchestrator for 4-dimension rubric evaluation
│   └── background_worker.py    # Async task runner iterating through student answers
└── schemas/grading.py          # RubricScoreSchema, EssayGradingResultSchema
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Worker asinkron menilai 3 jawaban esai siswa
  Given Siswa telah submit ujian yang memuat 3 soal esai
  When Worker background memproses sesi siswa tersebut
  Then Setiap jawaban esai terisi dengan auto_score, ai_grading_rationale, dan skor 4 dimensi
  And Status sesi siswa diperbarui dari "grading_in_progress" menjadi "graded"
```
