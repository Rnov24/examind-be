# Ticket: TAKE-001 — Student Exam Session Initialization & Security Check

- **Epic**: Epic 4 — Student Exam Taking & Offline-First Resilience
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#41-memulai-sesi-ujian-start-exam)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** memulai sesi ujian yang sah dengan validasi waktu mulai/selesai, pencatatan IP/User-Agent, pencegahan multi-login di dua tab berbeda, dan pembuatan token pairing QR untuk kamera HP,  
> **Agar** sesi ujian saya tercatat secara aman dan terproteksi dari akses ganda yang tidak sah.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/student_exam.py # POST /student/exam/{id}/start, GET /student/exams/active
└── services/exam/session_guard.py  # Single session concurrency lock & QR token generator
```

### B. Aturan Bisnis & Validasi:
1. Ujian hanya bisa dimulai jika `start_time <= now <= end_time`.
2. Jika siswa sudah memiliki sesi `in_progress`, kembalikan sesi yang sama (jangan buat sesi ganda).
3. Jika sesi telah `submitted`, tolak request dengan error 400 `EXAM_ALREADY_SUBMITTED`.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa memulai ujian tepat pada jadwalnya
  Given Ujian Fisika dijadwalkan buka pukul 08:00 dan waktu saat ini adalah 08:05
  When Siswa mengirimkan POST `/api/v1/student/exam/1/start`
  Then Server membuat record `exam_sessions` berstatus "in_progress"
  And Mengembalikan daftar butir soal, durasi sisa, dan pairing token QR
```
