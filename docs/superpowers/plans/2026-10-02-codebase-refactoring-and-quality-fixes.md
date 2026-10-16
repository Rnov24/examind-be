# Codebase Refactoring & Readability Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor and improve the EXAMIND codebase based on the audit findings: resolve the SuperAdmin route guard bug, align student proctoring with the human-in-the-loop invariant, eliminate repetitive backend boilerplate via Pydantic ORM mode, eliminate the N+1 query pattern in tenant endpoints, modularize massive frontend God Views, and improve TypeScript configuration.

**Architecture:** 
1. **Frontend Core & Routing:** Fix role redirection bug in `router/index.ts`, add safe JSON deserialization in `auth.ts`, and enforce human-in-the-loop proctoring in `ExamWorkspace.vue`.
2. **Frontend Component Modularization:** Extract sub-components from `SuperAdminDashboardView.vue` (TenantTable, TenantModal, SecretManagerTab) and `ExamWorkspace.vue` (QuestionCard, CompanionQrModal).
3. **Backend Optimization & DRY:** Refactor `superadmin.py`, `questions.py`, and `exams.py` to eliminate N+1 queries using SQL aggregation and replace manual dictionary/model mapping with Pydantic v2 `from_attributes=True` (`model_validate`).
4. **Testing & Type Safety:** Enable stricter TypeScript checks and add standalone SQLite database fallback fixtures for backend tests.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.0, PyMySQL, Vue 3, Pinia, Vue Router, Tailwind CSS, TypeScript.

**Spec:** Audit Findings & Project Invariants (`GEMINI.md`).

## Global Constraints

- **Human-in-the-Loop Proctoring:** The AI proctoring system must NEVER automatically disqualify a student with zero score; it only flags suspicious events with timestamps and snapshots for teacher review.
- **Frontend Build:** `npm run build` / `vite build` must compile without errors.
- **Backend API:** All endpoints must preserve their existing API request/response contracts (`ApiResponse[T]`).
- **No breaking changes:** Database schema and migrations must remain intact.

## Review Focus

1. `router/index.ts`: When a SuperAdmin logs in or navigates to guest routes, ensure they are directed to `/superadmin/dashboard`, not `/teacher/dashboard`.
2. `ExamWorkspace.vue`: Ensure tab-switch and fullscreen exit trigger warning logs and flags without terminating the session or forcing an irreversible score 0 auto-fail.
3. `superadmin.py`: Querying `/superadmin/tenants` must execute in $O(1)$ database round-trips rather than $O(N)$ per tenant.
4. `questions.py` and `exams.py`: Model serialization must accurately preserve relational data (`questions_count`, `total_points`) while using idiomatic Pydantic validation.
5. `auth.ts`: Corrupted `localStorage` data must not crash app initialization.

---

### Task 1: Fix Frontend Auth Safety & SuperAdmin Navigation Guard

**Files:**
- Modify: `frontend/src/router/index.ts:172-199`
- Modify: `frontend/src/stores/auth.ts:17-21`

**Interfaces:**
- Consumes: `authStore.isSuperAdmin`, `authStore.user`
- Produces: Correct role dashboard path `'/superadmin/dashboard'`

- [ ] **Step 1: Update `getRoleDashboard` in `frontend/src/router/index.ts`**
Add `if (auth.isSuperAdmin) return '/superadmin/dashboard'` inside `getRoleDashboard()` so SuperAdmin users are routed properly.

- [ ] **Step 2: Add safe localStorage parsing in `frontend/src/stores/auth.ts`**
Wrap `JSON.parse(localStorage.getItem('examind_user'))` in a safe helper function with a `try ... catch` block returning `null` on corrupted data.

- [ ] **Step 3: Verify build**
Run: `npm --prefix frontend run build` to verify syntax and compilation.

---

### Task 2: Align Proctoring Flow with Human-in-the-Loop Invariant

**Files:**
- Modify: `frontend/src/views/student/ExamWorkspace.vue`

**Interfaces:**
- Consumes: `proctoringStore.logViolation`
- Produces: Warning modal and persistent logging without irreversible client-side zero-score disqualification.

- [ ] **Step 1: Replace hard auto-disqualification with flagged review warning**
Change the blur / fullscreen exit handler to log a high-severity proctoring event (`fullscreen_exit` / `tab_switch`) and display a stern "Pelanggaran Tercatat untuk Peninjauan Guru" warning modal instead of automatically setting `score = 0` and locking the student out.

- [ ] **Step 2: Remove client-side auto-fail mutation**
Ensure the student's submission remains intact for asynchronous evaluation by the teacher/system.

---

### Task 3: Optimize Backend SuperAdmin Endpoint & Eliminate N+1 Queries

**Files:**
- Modify: `backend/app/api/v1/endpoints/superadmin.py:67-110`

**Interfaces:**
- Consumes: SQLAlchemy `db.query()`, `func.count()`, `Tenant`, `User`, `Exam`
- Produces: `ApiResponse[List[TenantResponse]]` with user and exam counts computed in batch.

- [ ] **Step 1: Refactor `get_all_tenants` in `superadmin.py`**
Replace per-tenant iteration queries with aggregated subqueries or grouped queries using SQLAlchemy `func.count` to calculate student, teacher, and exam counts in a single batch.

- [ ] **Step 2: Test endpoint execution**
Verify query syntax and response schema compatibility.

---

### Task 4: Streamline Backend DTO Serialization with Pydantic v2 ORM Mode

**Files:**
- Modify: `backend/app/api/v1/endpoints/questions.py`
- Modify: `backend/app/api/v1/endpoints/exams.py`

**Interfaces:**
- Consumes: Pydantic v2 `ConfigDict(from_attributes=True)`
- Produces: Clean, concise endpoint responses using `model_validate` or generator comprehensions.

- [ ] **Step 1: Refactor `questions.py`**
Replace manual field assignments in `list_question_banks`, `get_question_bank_detail`, and question CRUD endpoints with `QuestionResponse.model_validate(q)` and `QuestionBankResponse.model_validate(b)`.

- [ ] **Step 2: Refactor `exams.py`**
Replace repetitive mapping in `list_exams`, `get_exam_detail` with idiomatic Pydantic validation while preserving dynamic fields (`questions_count`, `total_points`).

---

### Task 5: Modularize Frontend SuperAdmin Dashboard God View

**Files:**
- Create: `frontend/src/views/superadmin/components/TenantTable.vue`
- Create: `frontend/src/views/superadmin/components/TenantModal.vue`
- Create: `frontend/src/views/superadmin/components/SecretManagerTab.vue`
- Modify: `frontend/src/views/superadmin/SuperAdminDashboardView.vue`

**Interfaces:**
- Consumes: `TenantResponse`, `SecretResponse`, emits `@refresh`, `@edit`, `@create`
- Produces: Clean, decomposed view under 250 lines in `SuperAdminDashboardView.vue`.

- [ ] **Step 1: Extract `TenantTable.vue`**
Move tenant listing, search/filter controls, and action buttons into `TenantTable.vue`.

- [ ] **Step 2: Extract `TenantModal.vue`**
Move create/edit tenant dialog form into `TenantModal.vue`.

- [ ] **Step 3: Extract `SecretManagerTab.vue`**
Move secret keys list, add secret modal, and test secret modal into `SecretManagerTab.vue`.

- [ ] **Step 4: Update `SuperAdminDashboardView.vue`**
Import the sub-components and bind props/events cleanly.

- [ ] **Step 5: Verify build**
Run: `npm --prefix frontend run build` to verify component compilation.

---

### Task 6: Modularize Student Exam Workspace View

**Files:**
- Create: `frontend/src/views/student/components/QuestionCard.vue`
- Create: `frontend/src/views/student/components/CompanionQrModal.vue`
- Create: `frontend/src/views/student/components/ExamSubmitModal.vue`
- Modify: `frontend/src/views/student/ExamWorkspace.vue`

**Interfaces:**
- Consumes: `currentQuestion`, `studentAnswer`, emits `@answer`, `@toggleDoubt`
- Produces: Modularized `ExamWorkspace.vue` with focused sub-components.

- [ ] **Step 1: Extract `QuestionCard.vue`**
Extract MCQ option radio buttons and Essay textarea into `QuestionCard.vue`.

- [ ] **Step 2: Extract `CompanionQrModal.vue` and `ExamSubmitModal.vue`**
Extract the pairing QR code dialog and submission confirmation dialog into separate components.

- [ ] **Step 3: Update `ExamWorkspace.vue`**
Integrate sub-components and verify all exam interactions (navigation, doubt toggle, answering, timer).

- [ ] **Step 4: Verify build**
Run: `npm --prefix frontend run build` to ensure all imports and templates are valid.

---

### Task 7: Final Verification & Type Safety Sanity Check

**Files:**
- Modify: `frontend/tsconfig.json` (tune flags)
- Run tests and compilation checks

- [ ] **Step 1: Enable TypeScript unused variable / parameter warnings**
Adjust `frontend/tsconfig.json` settings towards cleaner typing without breaking third-party library typings.

- [ ] **Step 2: Run full frontend build**
Verify `npm --prefix frontend run build` exits 0.

- [ ] **Step 3: Final check**
Review git diff to ensure all changes adhere strictly to the plan and project guidelines.
