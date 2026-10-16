# Ticket: EXPL-002 — Student Results & Concept Explanation Review UI

- **Epic**: Epic 7 — Formative Answer Explanation & Results
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** melihat ringkasan nilai ujian, butir soal yang benar/salah, breakdown rubrik esai, dan penjelasan konseptual interaktif sesuai kebijakan rilis guru (*instant* atau *after_exam_closed*),  
> **Agar** saya memperoleh evaluasi belajar yang transparan dan mendidik.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(exam)/results/[sessionId]/
├── page.tsx                    # Student Score & Explanation Review Page
└── components/
    ├── ScoreSummaryCard.tsx    # Nilai Akhir, Akurasi PG, Skor Esai, Indeks Integritas
    └── QuestionReviewCard.tsx  # Opsi terpilih, kunci jawaban, dan pembahasan AI
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa melihat pembahasan setelah ujian resmi ditutup
  Given Kebijakan ujian adalah "after_exam_closed" dan jendela ujian telah berakhir
  When Siswa membuka halaman `/results/108`
  Then Halaman menampilkan nilai total 85.0/100 dan pembahasan lengkap untuk setiap butir soal
```
