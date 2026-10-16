# Ticket: GRAD-002 — AI Confidence Scoring Algorithm & Prioritization Routing

- **Epic**: Epic 6 — AI Essay Auto-Grading & Teacher Override
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: AI / Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md#32-automated-grading-engine-penilaian-hibrida--override)

---

## 1. User Story / Objective
> **Sebagai** Guru,  
> **Saya ingin** sistem secara otomatis menghitung tingkat keyakinan penilaian AI (*Confidence Level: High, Medium, Low*) berdasarkan kesesuaian semantik dan kata kunci, serta menyortir jawaban dengan tingkat keyakinan rendah ke daftar antrean teratas untuk direview manual,  
> **Agar** waktu koreksi guru difokuskan pada jawaban-jawaban yang paling berpotensi ambigu atau memerlukan penilaian manusia.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
└── services/grading/confidence_calculator.py # Mathematical formula implementation for C_ai
```

### B. Formulasi Matematis:
$$C_{ai} = 0.5 \cdot S_{semantic} + 0.3 \cdot (1 - \sigma_{subscores}) + 0.2 \cdot P_{keyword}$$
- $C_{ai} \ge 0.85 \rightarrow$ `high` (Aman untuk auto-accept).
- $0.70 \le C_{ai} < 0.85 \rightarrow$ `medium`.
- $C_{ai} < 0.70 \rightarrow$ `low` (Prioritas review manual guru).

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Jawaban esai yang ambigu menghasilkan confidence level "low"
  Given Jawaban siswa memiliki kata kunci yang minim dan struktur kalimat tidak lazim
  When Confidence calculator menghitung indeks keyakinan
  Then ai_confidence_level bernilai "low" dengan nilai numerik < 0.70
  And Sesi diberi badge review oranye pada dashboard guru
```
