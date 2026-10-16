# Ticket: FND-002 — Backend Core Config, CORS & Global Exception Handlers

- **Epic**: Epic 0 — Project Setup, Database & DevOps Foundation
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 3 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md) | [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

---

## 1. User Story / Objective
> **Sebagai** Backend Developer,  
> **Saya ingin** membangun fondasi aplikasi FastAPI dengan konfigurasi berbasis Pydantic v2 Settings, middleware CORS untuk origin Next.js, logging terstruktur, dan global exception handler yang seragam,  
> **Agar** seluruh endpoint API menghasilkan respon JSON yang konsisten dan aman dari kebocoran stack trace internal.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── core/
│   ├── config.py               # Pydantic Settings (.env loader)
│   ├── security.py             # Password hashing (bcrypt) & JWT helpers
│   └── exceptions.py           # Custom AppException & global handlers
└── main.py                     # FastAPI application factory, CORS, router mounting
```

### B. Spesifikasi Respon Error Global
Setiap error (400, 401, 403, 404, 422, 500) wajib diformat:
```json
{
  "success": false,
  "data": null,
  "message": "Pesan error ramah pengguna",
  "error": {
    "code": "ERROR_CODE_STRING",
    "details": "Detail teknis jika dalam mode debug"
  }
}
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Request dari origin frontend Next.js lolos pre-flight CORS
  Given Server FastAPI berjalan pada port 8000
  When Browser frontend Next.js pada port 3000 mengirimkan OPTIONS request
  Then Server mengembalikan header Access-Control-Allow-Origin: http://localhost:3000
  And Status code 200 OK

Scenario: Validasi input gagal memicu respon 422 berformat seragam
  Given Endpoint API menerima payload yang tidak sesuai skema Pydantic
  When Client memanggil endpoint tersebut
  Then Server mengembalikan status 422 Unprocessable Entity
  And Body respon memuat properti `success: false` dan `error.code: "VALIDATION_ERROR"`
```
