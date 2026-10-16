# Ticket: AUTH-001 — JWT Authentication Engine & Password Hashing

- **Epic**: Epic 1 — Authentication, Authorization & User Management
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#2-modul-autentikasi-apiv1auth)

---

## 1. User Story / Objective
> **Sebagai** Pengguna (Admin, Guru, atau Siswa),  
> **Saya ingin** dapat melakukan autentikasi login menggunakan NISN/NIP/Email dan kata sandi untuk memperoleh token akses JWT yang aman,  
> **Agar** saya dapat mengakses fitur dan data sesuai hak otorisasi peran saya.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/
│   └── auth.py                 # POST /login, GET /me, POST /refresh
├── core/
│   └── security.py             # verify_password, get_password_hash, create_access_token
└── schemas/
    └── auth.py                 # LoginRequest, TokenResponse, UserProfileResponse
```

### B. Spesifikasi Endpoint
1. **`POST /api/v1/auth/login`**:
   - Menerima `identifier` (NISN/NIP/Username/Email) dan `password`.
   - Melakukan verifikasi Bcrypt terhadap `password_hash`.
   - Mengembalikan JWT token dengan payload: `{ sub: user_id, role: user_role, exp: timestamp }`.
2. **`GET /api/v1/auth/me`**:
   - Mengembalikan data profil lengkap user yang sedang terautentikasi.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Login berhasil dengan kredensial valid
  Given Pengguna terdaftar dengan identifier "198507232010011005" dan password "Password123!"
  When Client mengirimkan request POST /api/v1/auth/login dengan kredensial tersebut
  Then Server mengembalikan status 200 OK
  And Body respon memuat access_token JWT valid dan data profil user role "teacher"

Scenario: Login gagal dengan password salah
  Given Pengguna mengirimkan password yang tidak cocok
  When Client mengirimkan request POST /api/v1/auth/login
  Then Server mengembalikan status 401 Unauthorized
  And Body respon memuat pesan error "Identifier atau kata sandi tidak valid"
```
