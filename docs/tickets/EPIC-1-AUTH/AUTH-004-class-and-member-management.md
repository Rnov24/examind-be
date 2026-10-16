# Ticket: AUTH-004 — Class & Academic Roster Management

- **Epic**: Epic 1 — Authentication, Authorization & User Management
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Full-Stack Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Guru atau Admin Sekolah,  
> **Saya ingin** membuat kelas akademik, mendaftarkan siswa ke dalam kelas, dan melihat daftar anggota kelas,  
> **Agar** paket ujian yang dibuat dapat ditugaskan secara tepat ke kelas yang bersangkutan.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/classes.py # CRUD /classes, /classes/{id}/members
└── schemas/academic.py         # ClassCreate, ClassResponse, MemberAddRequest

frontend/src/app/(dashboard)/classes/
├── page.tsx                    # Daftar Kelas & Card View
└── [id]/page.tsx               # Roster Siswa & Penugasan Guru
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru membuat kelas baru
  Given Guru membuka halaman manajemen kelas di `/classes`
  When Guru mengisi nama "XII MIPA 2", tingkat "12", dan tahun "2026/2027" lalu klik Simpan
  Then Kelas baru tersimpan di database dan muncul di daftar kelas aktif
```
