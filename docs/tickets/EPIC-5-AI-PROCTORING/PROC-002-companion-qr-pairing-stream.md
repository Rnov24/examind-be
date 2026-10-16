# Ticket: PROC-002 — Secondary Camera Mobile Companion QR Pairing & Stream

- **Epic**: Epic 5 — Dual-Camera AI Proctoring & Realtime Monitoring
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Full-Stack Engineer
- **Dokumen Terkait**: [docs/ARCHITECTURE.md](../../ARCHITECTURE.md#21-alur-handshake-pairing-kamera-hp-sekunder-companion-qr-handshake)

---

## 1. User Story / Objective
> **Sebagai** Siswa,  
> **Saya ingin** memindai QR Code di layar laptop menggunakan kamera smartphone untuk membuka antarmuka web pendamping (*mobile companion web*) tanpa instalasi aplikasi,  
> **Agar** kamera HP dapat berfungsi sebagai kamera sekunder yang memantau area meja dan keyboard saya secara real-time.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(companion)/companion/
├── page.tsx                    # Mobile Companion QR Landing & Camera Stream View
└── hooks/useCompanionSocket.ts # WebSocket signaling & pairing handshake

backend/app/
└── api/v1/endpoints/proctoring_ws.py # WS /ws/proctoring/{session_id}/companion
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Pairing kamera HP sekunder berhasil via scan QR
  Given Siswa berada pada halaman verifikasi di laptop dengan QR code aktif
  When Siswa memindai QR code tersebut di HP dan mengizinkan akses kamera
  Then WebSocket room menghubungkan HP dan laptop siswa
  And Layar laptop menampilkan status "[🟢 Cam 2: OK]"
```
