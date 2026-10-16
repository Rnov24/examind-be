# Ticket: EXAM-001 — Exam Packaging, Scheduling & Policy API

- **Epic**: Epic 3 — Exam Configuration, Scheduling & Publishing
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#4-modul-pengerjaan-ujian-siswa-apiv1student)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** membuat paket ujian baru, memilih butir soal dari bank soal, mengatur alokasi bobot poin, durasi pengerjaan, jendela jadwal (start/end time), tingkat pengawasan proctoring, dan kebijakan rilis pembahasan,  
> **Agar** paket ujian siap dipublikasikan untuk kelas target.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/exams.py   # CRUD /exams, /exams/{id}/publish, /exams/{id}/questions
└── schemas/exam.py             # ExamCreate, ExamUpdate, ExamResponse, ExamPublishRequest
```

### B. Validasi Bisnis:
- `end_time` wajib $> start\_time$.
- Durasi (`duration_minutes`) tidak boleh melebihi rentang antara `start_time` dan `end_time`.
- Total alokasi poin seluruh butir soal wajib sama dengan 100.00.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Publikasi paket ujian berhasil
  Given Guru memiliki draft ujian dengan 10 butir soal bernilai total 100 poin
  When Guru memanggil endpoint POST `/api/v1/exams/1/publish`
  Then Status ujian berubah menjadi "published"
  And Ujian kini dapat dilihat oleh siswa yang terdaftar di kelas tersebut
```
