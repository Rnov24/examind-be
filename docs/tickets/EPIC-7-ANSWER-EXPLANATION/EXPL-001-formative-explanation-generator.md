# Ticket: EXPL-001 — Formative Answer Explanation AI Generator

- **Epic**: Epic 7 — Formative Answer Explanation & Results
- **Priority**: P2 (Medium)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: AI / Backend Engineer
- **Dokumen Terkait**: [docs/AI_SPECIFICATION.md](../../AI_SPECIFICATION.md#23-prompt-formative-answer-explanation-penjelasan-formatif)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** sistem menghasilkan penjelasan formatif yang menjelaskan mengapa jawaban saya benar atau di mana letak miskonsepsi/kekurangan konsep jika jawaban saya salah,  
> **Agar** saya dapat belajar secara efektif dari kesalahan ujian dan memahami materi ajar secara mendalam.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── services/ai/explanation_generator.py # Formative feedback LLM prompt engine
└── schemas/grading.py                  # ExplanationResponseSchema
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa yang menjawab salah menerima diagnosis miskonsepsi
  Given Siswa menjawab salah pada soal fisika efek fotolistrik
  When Explanation generator memproses respon siswa
  Then Penjelasan formatif mengidentifikasi kesalahan konsep siswa secara santun
  And Memberikan referensi teori kuantum Einstein yang seharusnya dijawab
```
