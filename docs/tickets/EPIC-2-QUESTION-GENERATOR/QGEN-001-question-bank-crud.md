# Ticket: QGEN-001 — Question Bank Database & CRUD Endpoints

- **Epic**: Epic 2 — Question Bank & AI Question Generator
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#3-modul-ai-question-generator-apiv1ai)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** mengelola Bank Soal per mata pelajaran, menambahkan soal pilihan ganda maupun esai secara manual, memperbarui butir soal, dan mengorganisasi tingkat kesukaran soal,  
> **Agar** saya memiliki kumpulan bank soal yang terstruktur untuk diikutsertakan ke dalam berbagai paket ujian.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/questions.py # CRUD /questions/bank, /questions/bank/{id}/items
└── schemas/question.py           # QuestionBankCreate, QuestionCreate, QuestionResponse
```

### B. Spesifikasi Endpoint
1. `POST /api/v1/questions/bank`: Membuat bank soal baru.
2. `GET /api/v1/questions/bank/{bank_id}`: Mengambil seluruh butir soal di bank tertentu.
3. `POST /api/v1/questions/bank/{bank_id}/items`: Menambahkan butir soal PG/Esai ke bank soal.
4. `PUT /api/v1/questions/items/{question_id}`: Memperbarui teks soal, opsi, kunci, bobot poin, atau rubrik.
5. `DELETE /api/v1/questions/items/{question_id}`: Menghapus butir soal.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Menambahkan soal Pilihan Ganda lengkap dengan distractor analysis
  Given Guru memiliki bank soal "Fisika Kuantum" yang aktif
  When Guru mengirimkan POST /api/v1/questions/bank/1/items dengan 4 opsi dan kunci "B"
  Then Soal tersimpan di database dengan format options_json valid dan default_points 10.0
```
