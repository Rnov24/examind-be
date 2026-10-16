# Ticket: TAKE-004 — Exam Submission Pipeline & Instant MCQ Evaluator

- **Epic**: Epic 4 — Student Exam Taking & Offline-First Resilience
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#43-submit-final-ujian)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** mengumpulkan lembar jawaban ujian saat waktu habis atau setelah menekan tombol submit, di mana sistem secara instan menilai seluruh butir pilihan ganda dan mengalihkan tugas penilaian esai ke worker latar belakang,  
> **Agar** saya menerima konfirmasi submit seketika tanpa harus menunggu lama di layar ujian.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/student_exam.py # POST /student/exam/{id}/submit
└── services/grading/mcq_evaluator.py # Instant O(1) MCQ evaluation & point accumulator
```

### B. Alur Eksekusi:
1. Validasi sesi aktif.
2. Hitung nilai seluruh soal PG dengan membandingkan `student_response` vs `correct_answer`.
3. Simpan nilai PG ke `student_answers` dan hitung subtotal nilai PG.
4. Set status sesi menjadi `grading_in_progress`.
5. Panggil `BackgroundTasks.add_task(grade_exam_session_async, session_id)`.
6. Kembalikan respon sukses ke siswa ($< 150$ ms).

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa submit ujian yang berisi 30 soal PG dan 5 soal Esai
  Given Siswa telah selesai menjawab seluruh soal
  When Siswa mengklik tombol "Kumpulkan Ujian" dan konfirmasi pada modal
  Then Seluruh 30 soal PG dinilai secara instan di database
  And Status sesi berubah menjadi "grading_in_progress"
  And Worker async AI grading esai terpicu di latar belakang
  And Siswa menerima respon sukses 200 OK
```
