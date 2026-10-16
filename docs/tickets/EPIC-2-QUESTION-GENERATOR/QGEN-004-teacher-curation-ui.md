# Ticket: QGEN-004 — Teacher Question Curation & Distractor Analysis UI

- **Epic**: Epic 2 — Question Bank & AI Question Generator
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** antarmuka Curation Workspace interaktif untuk mereview hasil generate soal AI, mengedit teks/opsi secara inline, melihat penjelasan pengecoh (*distractor analysis*), meminta variasi baru (*regenerate*), dan menyimpan butir terpilih ke Bank Soal,  
> **Agar** guru memegang kendali penuh atas kualitas konten soal sebelum digunakan pada ujian resmi.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(dashboard)/questions/
├── bank/page.tsx               # Daftar Bank Soal
├── bank/[id]/page.tsx          # Butir Soal dalam Bank
└── generate/page.tsx           # AI Generator Workspace & Curation Modal
```

### B. Fitur UI:
- Form input topik, upload dokumen dropzone, slider kesulitan, dan counter jumlah soal.
- Card preview soal dengan badge Bloom level (C1-C6) dan accordion *Distractor Rationale*.
- Tombol: *Accept*, *Edit Inline*, *Regenerate Item*, *Discard*.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru mengedit opsi soal sebelum menyetujui
  Given Guru melihat 5 draft soal hasil generate AI di workspace
  When Guru mengubah teks opsi "C" pada soal No. 2 dan mengklik "Simpan ke Bank Soal"
  Then Soal tersimpan di database dengan perubahan teks guru
  And Toast notifikasi menampilkan "Soal berhasil disimpan ke Bank Soal"
```
