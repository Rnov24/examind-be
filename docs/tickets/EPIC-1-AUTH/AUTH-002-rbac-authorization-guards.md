# Ticket: AUTH-002 — Role-Based Access Control (RBAC) Dependency Guards

- **Epic**: Epic 1 — Authentication, Authorization & User Management
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 3 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md) | [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

---

## 1. User Story / Objective
> **Sebagai** Security Engineer,  
> **Saya ingin** menerapkan dependency injection guards di FastAPI (`require_admin`, `require_teacher`, `require_student`) yang memvalidasi role dari token JWT pada setiap request endpoint,  
> **Agar** siswa tidak dapat mengakses rute guru/admin (seperti kunci jawaban atau override nilai) dan sebaliknya.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
└── core/
    └── dependencies.py         # get_current_user, require_role(roles: list)
```

### B. Spesifikasi Dependency
```python
# Contoh implementasi decorator / dependency
def require_roles(allowed_roles: list[str]):
    def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk peran Anda.")
        return current_user
    return role_checker
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa mencoba mengakses endpoint khusus guru
  Given Pengguna login sebagai Siswa dengan role "student"
  When Siswa mengirimkan GET request ke `/api/v1/questions/bank`
  Then Server mengembalikan status 403 Forbidden
  And Respon memuat pesan "Akses ditolak untuk peran Anda"

Scenario: Guru mengakses endpoint bank soal dengan hak akses sah
  Given Pengguna login sebagai Guru dengan role "teacher"
  When Guru mengirimkan GET request ke `/api/v1/questions/bank`
  Then Server mengizinkan request dan mengembalikan status 200 OK
```
