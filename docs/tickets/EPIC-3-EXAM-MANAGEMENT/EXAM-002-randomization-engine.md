# Ticket: EXAM-002 — Question & Option Randomization Engine

- **Epic**: Epic 3 — Exam Configuration, Scheduling & Publishing
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 3 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** sistem dapat mengacak urutan soal dan opsi jawaban PG secara unik per sesi siswa jika opsi `randomize_questions` dan `randomize_options` diaktifkan,  
> **Agar** memperkecil potensi kecurangan saling contek antar siswa yang duduk berdampingan.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
└── services/exam/randomizer.py # Deterministic seeded randomizer per student session
```

### B. Algoritma:
- Menggunakan pseudo-random shuffle dengan seed unik `hash(exam_id + "_" + student_id)` agar susunan soal tetap konsisten jika siswa me-refresh browser.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa A dan Siswa B menerima urutan soal berbeda pada ujian yang sama
  Given Ujian "Matematika" memiliki opsi randomize_questions = TRUE
  When Siswa A dan Siswa B memulai sesi ujian
  Then Urutan daftar soal Siswa A berbeda dengan urutan daftar soal Siswa B
  And Jika Siswa A me-refresh halaman, urutan soal Siswa A tetap sama persis
```
