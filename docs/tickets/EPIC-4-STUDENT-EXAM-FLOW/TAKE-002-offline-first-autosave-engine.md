# Ticket: TAKE-002 — Offline-First Autosave Engine (Local IndexedDB + Server Sync)

- **Epic**: Epic 4 — Student Exam Taking & Offline-First Resilience
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Full-Stack Engineer
- **Dokumen Terkait**: [docs/ARCHITECTURE.md](../../ARCHITECTURE.md#22-alur-autosave-berlapis--toleransi-putus-jaringan-offline-first-resilience)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** setiap ketikan jawaban esai dan pilihan jawaban PG saya tersimpan seketika di penyimpanan lokal browser (IndexedDB) dan disinkronkan ke server secara periodik setiap 30 detik,  
> **Agar** tidak ada satupun jawaban yang hilang jika laptop mati mendadak, browser ter-refresh, atau koneksi internet sekolah mengalami gangguan.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/
├── hooks/useAutosave.ts        # IndexedDB storage + 30s background sync timer + network status listener
└── lib/indexedDb.ts            # Dexie.js / Idb wrapper for exam answers cache

backend/app/
├── api/v1/endpoints/student_exam.py # POST /student/exam/{id}/autosave
└── schemas/exam_session.py     # AutosavePayloadSchema
```

### B. Mekanisme Kerja:
1. *Input Event*: Simpan state jawaban ke IndexedDB lokal ($< 5$ ms).
2. *Periodic Heartbeat*: Tiap 30 detik panggil `POST /student/exam/{id}/autosave`.
3. *Network Reconnect*: Begitu browser memicu event `window.addEventListener('online')`, jalankan sinkronisasi instan seluruh cache lokal ke server.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Autosave memulihkan jawaban siswa setelah browser di-refresh
  Given Siswa telah menjawab 15 soal dan me-refresh tab browser
  When Halaman ujian selesai dimuat ulang
  Then Seluruh 15 jawaban terisi kembali secara otomatis dari cache lokal / snapshot server
  And Siswa dapat langsung melanjutkan pengerjaan tanpa jeda
```
