# EXAMIND — Test Plan & Quality Assurance Specifications

**Versi:** 1.0  
**Tanggal:** 31 Agustus 2026  
**Dokumen Induk:** [docs/PRD.md](./PRD.md) | [docs/ARCHITECTURE.md](./ARCHITECTURE.md)  

---

## 1. Piramida Pengujian & Metrik Cakupan

```
             / \
            /   \       End-to-End (E2E) Browser Tests (Playwright)
           / E2E \      - Alur Pengerjaan Ujian Siswa & Live Proctoring
          /-------\
         / Integr- \    Integration Tests (FastAPI TestClient + MySQL)
        /   ation   \   - REST API Endpoints, WebSocket Hub, Auth Flow
       /-------------\
      /   Unit Tests  \ Unit Tests (Pytest & Jest/Vitest)
     /                 \ - Algoritma Scoring, MediaPipe Heuristics, Validasi Pydantic
    /-------------------\
```

- **Target Code Coverage**: Minimal 85% untuk modul Backend Core & Services, minimal 80% untuk Komponen Frontend.

---

## 2. Skenario UAT Berbasis Gherkin (Given - When - Then)

### Skenario 1: Autosave & Ketahanan Jaringan Putus (Offline Tolerance)
```gherkin
Feature: Ketahanan Autosave Jawaban Siswa

  Scenario: Siswa mengalami gangguan jaringan saat mengetik jawaban esai
    Given Siswa sedang aktif dalam sesi ujian "Fisika Kuantum"
    And Siswa telah mengetik 50 kata pada jawaban soal esai No. 14
    When Koneksi internet siswa terputus secara tiba-tiba (Network Offline)
    And Siswa terus mengetik tambahan 30 kata dalam kondisi offline
    Then Sistem menyimpan 80 kata tersebut ke dalam IndexedDB lokal secara instan
    And UI menampilkan indikator "Mode Offline (Tersimpan Lokal)" tanpa memblokir input siswa
    When Koneksi internet siswa pulih kembali (Network Online)
    Then Sistem secara otomatis menyinkronkan seluruh 80 kata ke server backend FastAPI
    And Status UI berubah menjadi "Tersinkronisasi ke Server"
```

---

### Skenario 2: Handshake Dual-Camera Pairing
```gherkin
Feature: Pairing Kamera HP Sekunder via QR Code

  Scenario: Siswa memindai QR Code untuk mengaktifkan kamera kedua
    Given Siswa berada pada halaman verifikasi pra-ujian di laptop
    And Laptop menampilkan QR Code pairing unik dengan token valid
    When Siswa memindai QR Code tersebut menggunakan browser kamera HP
    Then HP membuka halaman companion web dan meminta izin akses kamera
    When Siswa mengizinkan akses kamera pada HP
    Then WebSocket mengirim event COMPANION_PAIRED_SUCCESS ke laptop
    And Status kamera pada layar laptop berubah menjadi hijau [🟢 Cam 2: OK]
    And Tombol "Mulai Ujian" menjadi aktif
```

---

### Skenario 3: Penilaian Esai Asinkron & Override Guru
```gherkin
Feature: AI Essay Auto-Grading & Teacher Override

  Scenario: Penilaian esai otomatis menghasilkan flag low confidence dan dioverride guru
    Given Siswa mengumpulkan lembar jawaban ujian
    When Worker asinkron mengevaluasi jawaban esai yang memiliki bahasa ambigu
    Then Nilai AI dihitung dengan confidence level "low"
    And Sesi siswa diberi badge prioritas review oranye di dashboard guru
    When Guru membuka rincian jawaban siswa dan menaikkan nilai dari 8.0 menjadi 12.0
    And Guru menambahkan catatan "Penalaran siswa sebenarnya sudah tepat secara konsep"
    And Guru menekan tombol "Simpan & Setujui"
    Then Sistem memperbarui final_score menjadi 12.0 dan mencatat teacher_override_score
```

---

## 3. Matriks Uji Beban & Kinerja (Load Testing)

| Parameter Uji | Target Benchmark | Kondisi Uji |
|---|---|---|
| **Siswa Aktif Serentak** | 100 Siswa / Kelas Bersama | Ujian serentak pada 1 instance XAMPP MySQL + FastAPI |
| **Throughput Autosave** | ~3.3 request/detik rata-rata | Tiap siswa mengirim autosave berkala per 30 detik |
| **Waktu Respon Autosave** | $< 100$ ms (p95) | Beban puncak autosave serentak |
| **Durasi Grading Batch** | $< 45$ detik untuk 35 siswa | Background queue worker dengan model LLM berkecepatan tinggi |
| **CPU Utilization Server** | $< 60\%$ stabil | Beban penuh 100 koneksi WebSocket aktif |

---

## 4. Checklist Audit Keamanan & Privasi UU PDP

- [x] **Enkripsi Data In-Transit**: Seluruh lalu lintas data HTTP dan WebSocket menggunakan SSL/TLS (HTTPS/WSS).
- [x] **Hashing Password**: Menggunakan Bcrypt dengan salt factor 12.
- [x] **Minimalisasi Rekaman**: Video mentah tidak diunggah ke server; hanya snapshot terkompresi ($< 50$ KB) saat ada insiden terverifikasi.
- [x] **Consent Form**: Dialog persetujuan kamera eksplisit sebelum sesi dimulai sesuai UU PDP No. 27 Tahun 2022.
- [x] **Auto-Pruning Storage**: Skrip cron/worker otomatis menghapus snapshot proctoring setelah 60 hari.
