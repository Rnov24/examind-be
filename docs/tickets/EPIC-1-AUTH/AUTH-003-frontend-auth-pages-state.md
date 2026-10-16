# Ticket: AUTH-003 — Frontend Authentication Pages, State Store & Route Middleware

- **Epic**: Epic 1 — Authentication, Authorization & User Management
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Pengguna,  
> **Saya ingin** halaman login yang responsif, validasi form instan, penyimpanan token aman di Pinia store, dan routing otomatis sesuai role setelah login berhasil menggunakan Vue Router navigation guards,  
> **Agar** saya dapat masuk ke portal ujian (Siswa) atau dashboard kelas (Guru) dengan mulus.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/
├── views/LoginView.vue         # Login Form View (Vue 3 SFC)
├── router/index.ts             # Vue Router navigation guards (Token & Role redirection)
└── stores/auth.ts              # Pinia Auth Store (token, user, setAuth(), logout())
```

### B. Aturan Routing:
- Role `teacher` / `admin` $\rightarrow$ Redirect ke `/dashboard`.
- Role `student` $\rightarrow$ Redirect ke `/student/exams`.
- Unauthenticated user membuka rute proteksi $\rightarrow$ Redirect ke `/login?redirect=...`.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Login sukses mengarahkan siswa ke portal ujian
  Given Siswa mengisi form login dengan NISN dan kata sandi valid
  When Siswa menekan tombol "Masuk ke EXAMIND"
  Then Pinia auth store menyimpan data user dan token
  And Vue Router mengarahkan secara otomatis ke `/student/exams`
```
