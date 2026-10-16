# Ticket: QGEN-003 — Multi-Dimensional Essay Rubric Generator

- **Epic**: Epic 2 — Question Bank & AI Question Generator
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: AI / Backend Engineer
- **Dokumen Terkait**: [docs/AI_SPECIFICATION.md](../../AI_SPECIFICATION.md#22-prompt-ai-essay-auto-grading-penilai-esai-cerdas)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** setiap soal esai yang digenerate oleh AI otomatis dilengkapi dengan matriks rubrik penilaian 4 dimensi (Konsep Inti, Kelengkapan Argumen, Terminologi, dan Kejelasan Struktur Logika),  
> **Agar** standar penilaian esai objektif, terukur, dan siap digunakan oleh modul AI Auto-Grading.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── services/ai/rubric_generator.py # Generates 4-dimension scoring rubric from essay prompt
└── schemas/question.py             # RubricDimension, RubricSchema
```

### B. Spesifikasi Rubrik 4 Dimensi:
1. `dimension_1_concept` (Maks 40% Poin) — Pemahaman esensi materi.
2. `dimension_2_argument` (Maks 30% Poin) — Bukti dan langkah penalaran.
3. `dimension_3_terminology` (Maks 15% Poin) — Kosakata dan istilah ilmiah.
4. `dimension_4_clarity` (Maks 15% Poin) — Runtutan logika dan bahasa.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Soal esai menghasilkan rubrik valid dengan total bobot 100%
  Given AI meng-generate sebuah pertanyaan esai panjang
  When Rubric generator memproses pertanyaan tersebut
  Then Rubrik JSON memuat tepat 4 dimensi dengan total akumulasi bobot 100%
```
