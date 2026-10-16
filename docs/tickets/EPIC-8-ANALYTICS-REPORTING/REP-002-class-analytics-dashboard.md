# Ticket: REP-002 — Class Analytics Dashboard & Distribution Graphs

- **Epic**: Epic 8 — Class Analytics, Item Analysis & Reporting
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Guru dan Kepala Sekolah,  
> **Saya ingin** dashboard analitik visual yang menampilkan kurva distribusi nilai kelas (histogram), rata-rata kelas, standar deviasi, persentase ketuntasan KKM, dan ringkasan pelanggaran integritas,  
> **Agar** pimpinan sekolah dan guru dapat mengevaluasi efektivitas pembelajaran secara objektif.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(dashboard)/exams/[id]/analytics/
├── page.tsx                    # Class Analytics Dashboard Container
└── components/
    ├── ScoreDistributionChart.tsx # Recharts Histogram Kurva Nilai
    ├── MasteryKpiCards.tsx     # Rata-rata, Ketuntasan KKM (%), Nilai Min/Maks
    └── ProctoringIntegritySummary.tsx # Rekapitulasi insiden & rata-rata indeks integritas
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru melihat ringkasan analitik kelas
  Given Guru membuka halaman analitik ujian Fisika Kelas XII MIPA 1
  When Halaman dimuat
  Then Menampilkan grafik histogram distribusi nilai, rata-rata kelas 82.4, dan ketuntasan KKM 88.5%
```
