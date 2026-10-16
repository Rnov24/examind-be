# Ticket: PROC-001 — Primary Camera Edge Vision Engine (MediaPipe Face Mesh)

- **Epic**: Epic 5 — Dual-Camera AI Proctoring & Realtime Monitoring
- **Priority**: P1 (High)
- **Status**: Ready for Development
- **Estimasi Effort**: 8 Story Points (SP)
- **Assignee / Role**: Frontend / Computer Vision Engineer
- **Dokumen Terkait**: [docs/ARCHITECTURE.md](../../ARCHITECTURE.md#3-spesifikasi-komputer-vision-di-sisi-klien-edge-cv-heuristics)

---

## 1. User Story / Objective
> **Sebagai** Guru Pengawas,  
> **Saya ingin** webcam laptop siswa memproses deteksi keberadaan wajah (*face presence*), jumlah wajah (*multi-face*), arah tatapan (*gaze/head pose*), dan deteksi perpindahan tab browser (*tab switch / fullscreen blur*) secara lokal di browser siswa,  
> **Agar** anomali visual dapat terdeteksi secara real-time tanpa membebani bandwidth jaringan sekolah dengan video streaming mentah.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
frontend/src/
├── lib/proctoring/
│   ├── faceMeshEngine.ts       # MediaPipe Face Mesh WASM loader & frame analyzer
│   ├── headPoseEstimator.ts    # Yaw, Pitch, Roll calculation from 3D facial landmarks
│   └── tabSwitchDetector.ts    # Document visibilitychange & fullscreen event listeners
└── hooks/usePrimaryProctoring.ts # Lifecycle hook running inference loop at 3-5 FPS
```

### B. Aturan Deteksi Anomali:
1. `face_absent`: Tidak ada wajah terdeteksi selama $> 10$ detik.
2. `multiple_faces`: Terdeteksi $\ge 2$ wajah dalam frame.
3. `gaze_away`: Sudut kepala menyimpang ($|Yaw| > 35^\circ$ atau $Pitch < -20^\circ / > 25^\circ$) selama $> 15$ detik.
4. `tab_switch`: Event `document.visibilityState === 'hidden'` atau keluar dari mode fullscreen.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Siswa meninggalkan kursi ujian selama lebih dari 10 detik
  Given Siswa sedang mengerjakan ujian dengan kamera primer aktif
  When Siswa beranjak dari kursi dan wajah tidak terdeteksi selama 10 detik
  Then Engine mendeteksi anomali "face_absent"
  And Mengambil snapshot JPEG dari canvas video
  And Memicu pengiriman log event ke backend
```
