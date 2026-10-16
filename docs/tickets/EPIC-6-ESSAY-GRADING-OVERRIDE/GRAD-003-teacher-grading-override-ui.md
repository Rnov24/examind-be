# Ticket: GRAD-003 — Teacher Grading Review & Override Suite UI

- **Epic**: Epic 6 — AI Essay Auto-Grading & Teacher Override
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md#3-rincian-antarmuka-guru-teacher-grading--review-suite)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** antarmuka koreksi *side-by-side* yang menampilkan jawaban siswa di sisi kiri dan pertimbangan rubrik AI di sisi kanan, lengkap dengan input slider/number untuk mengubah (*override*) nilai akhir, menambahkan catatan guru, dan menyetujui nilai massal (*bulk auto-accept high confidence*),  
> **Agar** guru tetap memegang kendali pedagogis mutlak (*human-in-the-loop*) atas nilai akhir siswa.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(dashboard)/exams/[id]/grading/
├── page.tsx                    # Daftar Submission Siswa & Filter Confidence
└── [sessionId]/page.tsx        # Side-by-side Review & Override Workspace
```

### B. Fitur UI:
- Visualisasi skor 4 dimensi dalam bentuk bar/radar chart mini.
- Form input `teacher_override_score` dan textarea `teacher_notes`.
- Tombol: *Simpan Perubahan*, *Setujui Nilai AI*, *Lanjut ke Siswa Berikutnya*.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru melakukan override nilai esai siswa
  Given Guru membuka review jawaban esai No. 14 milik Siswa "Budi Santoso"
  When Guru menaikkan skor dari 10.0 menjadi 14.0 dan mengklik "Simpan & Setujui"
  Then Backend mengupdate `final_score = 14.0` dan `teacher_override_score = 14.0`
  And Nilai total ujian siswa diperbarui secara instan
```
