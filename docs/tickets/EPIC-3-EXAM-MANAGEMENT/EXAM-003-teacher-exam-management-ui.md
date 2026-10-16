# Ticket: EXAM-003 — Teacher Exam Management & Publish Wizard UI

- **Epic**: Epic 3 — Exam Configuration, Scheduling & Publishing
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** antarmuka Wizard bertahap (*Step 1: Info & Jadwal, Step 2: Pilih Soal & Poin, Step 3: Aturan Pengawasan & Rilis, Step 4: Konfirmasi Publish*),  
> **Agar** proses penyusunan dan penerbitan ujian terstruktur, intuitif, dan bebas dari kesalahan konfigurasi.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(dashboard)/exams/
├── page.tsx                    # Daftar Paket Ujian (Draft, Published, In Progress, Completed)
├── create/page.tsx             # 4-Step Exam Creation Wizard
└── [id]/edit/page.tsx          # Edit Exam Configuration
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru menyelesaikan pembuatan ujian melalui 4-step wizard
  Given Guru berada di halaman `/exams/create`
  When Guru mengisi detail info, memilih 10 soal (total 100 poin), dan mengaktifkan Dual-Camera
  And Guru menekan tombol "Terbitkan Ujian Sekarang"
  Then Ujian tersimpan dengan status "published" dan diarahkan ke halaman detail ujian
```
