# Ticket: REP-003 — Official Report Exporter (Excel & PDF Berita Acara)

- **Epic**: Epic 8 — Class Analytics, Item Analysis & Reporting
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md#35-dashboard-guru-manajemen-ujian--analitik-kelas)

---

## 1. User Story / Objective
> **Sebagai** Guru dan Bagian Kurikulum Sekolah,  
> **Saya ingin** mengunduh rekapitulasi nilai resmi kelas dalam format spreadsheet Excel (`.xlsx`) dan dokumen PDF Berita Acara Ujian resmi lengkap dengan tanda tangan pengawas dan catatan integritas,  
> **Agar** nilai dan dokumentasi resmi ujian dapat diarsipkan untuk keperluan administrasi akademik sekolah.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── services/reporting/
│   ├── excel_exporter.py       # OpenPyXL generator for student gradebook
│   └── pdf_exporter.py         # ReportLab / WeasyPrint generator for official Berita Acara PDF
└── api/v1/endpoints/analytics.py # GET /analytics/exam/{id}/export/excel, /export/pdf
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru mengunduh rekapitulasi nilai Excel
  Given Ujian Fisika telah selesai dan seluruh nilai telah difinalisasi
  When Guru mengklik tombol "Ekspor Excel (.xlsx)"
  Then Server mengembalikan file spreadsheet biner berekstensi `.xlsx`
  And Spreadsheet memuat kolom NISN, Nama Siswa, Skor PG, Skor Esai, Nilai Akhir, dan Indeks Integritas
```
