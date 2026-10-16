# Ticket: PROC-004 — Teacher Live Monitoring Grid & Direct Broadcast Alert

- **Epic**: Epic 5 — Dual-Camera AI Proctoring & Realtime Monitoring
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Full-Stack Engineer
- **Dokumen Terkait**: [docs/UX_SPECIFICATION.md](../../UX_SPECIFICATION.md#3-rincian-antarmuka-guru-teacher-grading--review-suite)

---

## 1. User Story / Objective
> **Sebagai** Guru Pengawas,  
> **Saya ingin** antarmuka Live Monitoring Hub yang menampilkan kisi-kisi thumbnail status seluruh siswa kelas secara real-time via WebSocket, memfilter siswa yang memiliki peringatan (*flagged*), melihat timeline insiden snapshot, dan mengirim pesan peringatan langsung ke layar siswa,  
> **Agar** saya dapat mengawasi jalannya ujian secara komprehensif dan mengambil tindakan preventif langsung saat terjadi anomali.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/app/(dashboard)/exams/[id]/monitor/
├── page.tsx                    # Live Monitoring Grid Container
├── components/
│   ├── StudentGridCard.tsx     # Thumbnail view (status pill, score integritas, preview)
│   ├── FlagDetailModal.tsx     # Snapshot timeline & verdict selector (ignore/confirm)
│   └── SendWarningModal.tsx    # Modal form kirim pesan peringatan langsung
└── hooks/useLiveMonitorSocket.ts # WebSocket listener for exam room

backend/app/
├── api/v1/endpoints/proctoring_ws.py # WS /ws/exam/{id}/live-monitor
└── api/v1/endpoints/proctoring.py    # POST /api/v1/proctoring/send-warning
```

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Guru mengirim peringatan langsung ke siswa berstatus flagged
  Given Siswa terdeteksi menoleh keluar layar dan berstatus 🔴 Flagged di grid guru
  When Guru mengklik "Kirim Pesan" dan mengetik "Harap pandangan fokus ke layar monitor"
  Then Siswa menerima modal pop-up berkedip di layar ujian secara real-time tanpa refresh
```
