# Ticket: REP-001 — Item Analysis Engine (Difficulty & Discrimination Index)

- **Epic**: Epic 8 — Class Analytics, Item Analysis & Reporting
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md#35-dashboard-guru-manajemen-ujian--analitik-kelas)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** sistem secara otomatis menghitung Tingkat Kesukaran ($P$) dan Daya Pembeda ($D$) untuk setiap butir soal ujian berdasarkan hasil seluruh siswa di kelas,  
> **Agar** saya dapat mengidentifikasi butir soal yang cacat/membingungkan dan menyempurnakan kualitas bank soal di masa depan.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── services/analytics/
│   └── item_analysis.py       # P-Index & D-Index calculator algorithms
└── api/v1/endpoints/analytics.py # GET /api/v1/analytics/exam/{id}/items
```

### B. Formulasi Statistik:
1. **Tingkat Kesukaran ($P$)**:
   $$P = \frac{B}{N}$$
   ($B$ = jumlah siswa benar, $N$ = total siswa). Klasifikasi: Sukar ($P < 0.30$), Sedang ($0.30 \le P \le 0.70$), Mudah ($P > 0.70$).
2. **Daya Pembeda ($D$)**:
   $$D = \frac{B_A - B_B}{N_{kelompok}}$$
   ($B_A$ = benar kelompok atas 27%, $B_B$ = benar kelompok bawah 27%).

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Perhitungan analisis butir soal untuk ujian dengan 35 siswa
  Given Seluruh 35 siswa di kelas telah menyelesaikan ujian Fisika
  When Guru membuka menu Analisis Butir Soal
  Then Sistem mengembalikan matriks indeks kesukaran dan daya pembeda per nomor soal
  And Mengidentifikasi soal No. 8 sebagai "Perlu Direvisi" (Daya Pembeda Negatif)
```
