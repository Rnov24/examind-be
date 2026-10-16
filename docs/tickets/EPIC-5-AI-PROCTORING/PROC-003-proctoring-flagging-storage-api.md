# Ticket: PROC-003 — Proctoring Incident Flagging, Snapshots & Storage API

- **Epic**: Epic 5 — Dual-Camera AI Proctoring & Realtime Monitoring
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/API_SPECIFICATION.md](../../API_SPECIFICATION.md#5-modul-pengawasan--protokol-websocket-ws)

---

## 1. User Story / Objective
> **Sebagai** Sistem Pengawasan EXAMIND,  
> **Saya ingin** menerima payload insiden proctoring dari klien (berupa event type, severity, timestamp, dan snapshot JPEG terkompresi), menyimpannya ke tabel `proctoring_logs`, memperbarui skor integritas sesi, dan menyiarkannya (*broadcast*) ke WebSocket ruang pengawasan guru,  
> **Agar** guru pengawas menerima notifikasi insiden secara instan lengkap dengan bukti visual snapshot.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── api/v1/endpoints/proctoring.py # POST /api/v1/proctoring/log-event
├── services/proctoring/
│   ├── storage.py              # Local/S3 storage writer for snapshot JPEG (<50 KB)
│   └── integrity_calculator.py # Mathematical formula calculation for session integrity score
└── schemas/proctoring.py       # ProctoringEventCreate, ProctoringLogResponse
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Pencatatan event insiden tab switch dan pengurangan skor integritas
  Given Siswa berpindah tab browser selama ujian
  When Klien mengirimkan POST `/api/v1/proctoring/log-event` dengan event "tab_switch"
  Then Record baru tersimpan di tabel `proctoring_logs`
  And Skor integritas sesi siswa berkurang dari 100% menjadi 95%
  And Event disiarkan ke WebSocket live monitoring guru
```
