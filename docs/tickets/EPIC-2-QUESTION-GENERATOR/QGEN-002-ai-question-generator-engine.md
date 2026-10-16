# Ticket: QGEN-002 — AI Question Generator Engine (LLM Pipeline)

- **Epic**: Epic 2 — Question Bank & AI Question Generator
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: AI / Backend Engineer
- **Dokumen Terkait**: [docs/AI_SPECIFICATION.md](../../AI_SPECIFICATION.md#21-prompt-ai-question-generator)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** memasukkan topik/materi pelajaran atau mengunggah dokumen PDF/DOCX dan meminta AI menghasilkan draft paket soal (PG & Esai) dengan analisis pengecoh (*distractor rationale*) dan level taksonomi Bloom,  
> **Agar** waktu pembuatan soal ujian dapat dipersingkat dari beberapa jam menjadi kurang dari 1 menit.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── services/ai/
│   ├── base.py                 # AIServiceInterface
│   ├── gemini_adapter.py       # Google Gemini Implementation
│   ├── openai_adapter.py       # OpenAI GPT-4o Implementation
│   └── prompts.py              # System & User prompts generator
└── api/v1/endpoints/ai.py      # POST /api/v1/ai/generate-questions
```

### B. Fitur & Validasi:
- Mendukung ekstraksi teks dari PDF/DOCX (menggunakan `pypdf` / `python-docx`).
- Output JSON dipaksa mematuhi skema `GeneratedQuestionMCQ` dan `GeneratedQuestionEssay` melalui *Structured Outputs / JSON Mode*.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: AI menghasilkan 5 soal PG Fisika Kuantum level C3-C4
  Given Guru mengirimkan request generate dengan topik "Efek Fotolistrik" dan jumlah PG = 5
  When Service AI memproses prompt melalui LLM Adapter
  Then Backend mengembalikan 5 butir soal PG
  And Setiap soal memiliki 4 opsi, 1 kunci jawaban benar, dan distractor rationale pada setiap opsi salah
```
