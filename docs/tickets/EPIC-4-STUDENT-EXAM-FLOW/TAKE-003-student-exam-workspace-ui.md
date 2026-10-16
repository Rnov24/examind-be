# Ticket: TAKE-003 — Student Exam Workspace UI & Question Matrix Navigator

- **Epic**: Epic 4 — Student Exam Taking & Offline-First Resilience
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md#2-rincian-antarmuka-siswa-student-exam-experience)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** antarmuka pengerjaan ujian berbasis Vue 3 yang bebas distraksi (*distraction-free fullscreen*), navigasi kisi-kisi nomor soal dengan kode warna status (terjawab, ragu-ragu, belum dijawab), countdown timer server-anchored, dan indikator status kamera yang jelas,  
> **Agar** saya dapat mengerjakan soal ujian dengan fokus, tenang, dan nyaman.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/
├── views/ExamWorkspaceView.vue # Exam Workspace View Container
├── components/exam/
│   ├── QuestionViewer.vue      # Teks soal, opsi PG (Radio), Editor Esai (Textarea)
│   ├── QuestionMatrix.vue      # Grid navigasi nomor soal (1-40) dengan status color pills
│   ├── ExamTimer.vue           # Countdown timer dengan peringatan warna merah saat < 5 menit
│   └── CameraStatusBadges.vue  # Status koneksi Cam 1 & Cam 2
└── stores/exam.ts              # Pinia state store untuk sesi pengerjaan ujian
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa menandai soal nomor 5 sebagai ragu-ragu
  Given Siswa berada pada soal nomor 5 dan telah memilih jawaban "A"
  When Siswa mencentang checkbox "Tandai Ragu-ragu"
  Then Kotak nomor 5 pada navigator soal berubah warna menjadi kuning (🟡)
  And State ragu-ragu tersimpan di Pinia store dan IndexedDB
```
