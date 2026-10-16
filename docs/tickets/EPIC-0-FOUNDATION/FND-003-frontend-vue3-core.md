# Ticket: FND-003 — Frontend Vue 3 Architecture, Vite, Pinia & Base Views

- **Epic**: Epic 0 — Project Setup, Database & DevOps Foundation
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Frontend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md) | [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md)

---

## 1. User Story / Objective
> **Sebagai** Frontend Developer,  
> **Saya ingin** mengonfigurasi arsitektur dasar Vue 3 (Composition API) dengan Vite, TypeScript, Tailwind CSS, shadcn-vue (Radix Vue), Pinia state store terpusat, Vue Router dengan navigation guards, dan Axios API client dengan JWT interceptor,  
> **Agar** seluruh modul antarmuka pengguna dapat dikembangkan secara modular, reaktif, cepat, dan konsisten terhadap design system EXAMIND.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/
├── views/
│   ├── LoginView.vue           # Login page
│   ├── DashboardView.vue       # Teacher & Admin workspace view
│   ├── ExamWorkspaceView.vue   # Fullscreen distraction-free Student exam view
│   └── CompanionView.vue       # Zero-chrome Mobile companion view
├── components/
│   ├── ui/                     # Button, Card, Badge, Modal, Input (shadcn-vue)
│   └── layout/                 # Navbar, Sidebar, ExamHeader
├── router/
│   └── index.ts                # Vue Router definitions & navigation auth guards
├── stores/
│   ├── auth.ts                 # User session & token state (Pinia)
│   ├── exam.ts                 # Active exam & question state
│   └── proctoring.ts           # Proctoring & camera status
└── lib/
    ├── api.ts                  # Axios instance with JWT interceptors
    └── utils.ts                # Tailwind merge & formatters
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Interceptor menyisipkan Bearer token pada request terautentikasi
  Given Pengguna telah login dan memiliki token tersimpan di Pinia auth store
  When Frontend melakukan panggilan API ke `/api/v1/student/exams/active`
  Then Request header secara otomatis menyertakan `Authorization: Bearer <token>`

Scenario: Token kedaluwarsa memicu redirect otomatis ke halaman login
  Given Sesi token pengguna telah kedaluwarsa di server
  When Frontend menerima respon 401 Unauthorized dari backend
  Then State Pinia auth dibersihkan dan pengguna diarahkan ke `/login?reason=session_expired`
```
