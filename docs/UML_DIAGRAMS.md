# EXAMIND — UML Use Case & Activity Diagrams Specification

**Versi:** 1.0 (Formal Software Modeling)  
**Tanggal:** 31 Agustus 2026  
**Dokumen Induk:** [docs/PRD.md](./PRD.md) | [docs/SRS.md](./SRS.md) | [docs/ARCHITECTURE.md](./ARCHITECTURE.md)  

---

## 1. UML Use Case Diagrams

### 1.1 Diagram Use Case Global Sistem (System-Level Use Case Diagram)

Diagram berikut memodelkan arsitektur Use Case formal EXAMIND sesuai kaidah UML menggunakan sintaks universal `flowchart LR`, memisahkan secara tegas antara **Aktor Utama (Primary Actors)** di sisi kiri dan **Aktor Pendukung (Supporting / Secondary Actors)** di sisi kanan:

*(Catatan: Digunakan format `flowchart LR` agar kompatibel 100% dengan seluruh markdown renderer seperti VSCode, GitHub, GitLab, Notion, dan browser tanpa dependensi engine eksperimental).*

```mermaid
flowchart LR
    %% ==========================================
    %% 1. AKTOR UTAMA (PRIMARY ACTORS - KIRI)
    %% ==========================================
    subgraph Primary_Actors ["👥 Aktor Utama (Primary)"]
        direction TB
        Admin["👨‍💼 Administrator Sekolah"]:::primaryActor
        Guru["👨‍🏫 Guru / Pengawas"]:::primaryActor
        Siswa["👨‍🎓 Siswa / Peserta Ujian"]:::primaryActor
    end

    %% ==========================================
    %% 2. BOUNDARY SISTEM EXAMIND (TENGAH)
    %% ==========================================
    subgraph EXAMIND_System ["🌐 Boundary Sistem: Platform Ujian Online EXAMIND"]
        direction TB

        %% Kelompok Administrasi
        subgraph Group_Admin ["Modul Administrasi & Akses"]
            UC01(["UC-01: Autentikasi & Otorisasi RBAC"])
            UC02(["UC-02: Kelola Akun Pengguna & Kelas"])
        end

        %% Kelompok Authoring & AI
        subgraph Group_Authoring ["Modul Bank Soal & Kurasi AI"]
            UC03(["UC-03: Kelola Bank Soal"])
            UC04(["UC-04: Generate Soal Cerdas & Rubrik"])
            UC04_Inc(["UC-04.1: Susun Rubrik 4D & Distraktor"])
            UC05(["UC-05: Buat & Publikasikan Paket Ujian"])
        end

        %% Kelompok Pengerjaan & Proctoring
        subgraph Group_Exam ["Modul Pengerjaan Ujian & Keamanan CBT"]
            UC06(["UC-06: Setup & Pairing Dual-Camera (QR Code)"])
            UC06_Inc(["UC-06.1: Kalibrasi Sudut Meja Mobile (45°)"])
            UC07(["UC-07: Kerjakan Ujian Online"])
            UC07_Sec(["UC-07.1: Enforce Fullscreen Lock & Auto-Fail"])
            UC07_Save(["UC-07.2: Autosave Lokal & Heartbeat Sync"])
            UC08(["UC-08: Pengawasan Cerdas & Deteksi Anomali"])
            UC09(["UC-09: Live Monitoring & Kirim Peringatan"])
        end

        %% Kelompok Penilaian & Analisis
        subgraph Group_Grading ["Modul Evaluasi & Analitik Hasil"]
            UC10(["UC-10: Kumpulkan Lembar Ujian & Auto-Grade PG"])
            UC11(["UC-11: Evaluasi Esai Asinkron via LLM"])
            UC11_Ext(["UC-11.1: Override Nilai Manual Guru"])
            UC12(["UC-12: Akses Hasil Ujian & Penjelasan AI"])
            UC13(["UC-13: Analisis Butir Soal & Ekspor Rekap Nilai"])
        end

        %% Relasi <<include>> dan <<extend>> Antar Use Case
        UC04 -.->|&laquo;include&raquo;| UC04_Inc
        UC06 -.->|&laquo;include&raquo;| UC06_Inc
        UC07 -.->|&laquo;include&raquo;| UC07_Sec
        UC07 -.->|&laquo;include&raquo;| UC07_Save
        UC07 -.->|&laquo;include&raquo;| UC08
        UC11_Ext -.->|&laquo;extend&raquo;| UC11
    end

    %% ==========================================
    %% 3. AKTOR PENDUKUNG (SUPPORTING ACTORS - KANAN)
    %% ==========================================
    subgraph Supporting_Actors ["⚙️ Aktor Pendukung (Supporting)"]
        direction TB
        AI_LLM["🤖 Layanan AI LLM<br/>(Gemini / OpenAI API)"]:::supportingActor
        Edge_CV["👁️ Engine Client-Side Edge CV<br/>& Sensor Mobile (Kamera 1 & 2)"]:::supportingActor
        WS_Service["⚡ WebSocket Real-Time Gateway<br/>& Event Broker"]:::supportingActor
    end

    %% ==========================================
    %% ASOSIASI AKTOR UTAMA (KIRI -> USE CASE)
    %% ==========================================
    Admin --> UC01
    Admin --> UC02
    Admin --> UC13

    Guru --> UC01
    Guru --> UC03
    Guru --> UC04
    Guru --> UC05
    Guru --> UC09
    Guru --> UC11
    Guru --> UC13

    Siswa --> UC01
    Siswa --> UC06
    Siswa --> UC07
    Siswa --> UC10
    Siswa --> UC12

    %% ==========================================
    %% ASOSIASI USE CASE KE AKTOR PENDUKUNG (USE CASE -> KANAN)
    %% ==========================================
    UC04 -.->|Prompt & Schema Parsing| AI_LLM
    UC11 -.->|Asynchronous Rubric Scoring| AI_LLM
    UC12 -.->|Generasi Analisis Butir & Solusi| AI_LLM

    UC06 -.->|Verifikasi Orientasi Gyro & Stream| Edge_CV
    UC08 -.->|Inferensi Wajah, Tatapan & Motion| Edge_CV
    UC07_Sec -.->|Deteksi Window Blur / Tab Switch| Edge_CV

    UC08 -.->|Sinyal Anomali & Snapshot Bukti| WS_Service
    UC09 -.->|Broadcast Peringatan & Status| WS_Service
    UC07_Save -.->|Heartbeat Ping Status Peserta| WS_Service

    %% ==========================================
    %% STYLING
    %% ==========================================
    classDef primaryActor fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC,font-weight:bold;
    classDef supportingActor fill:#1E293B,stroke:#A855F7,stroke-width:2px,color:#F8FAFC,font-weight:bold;
    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1.5px,color:#0F172A;
```
---

### 1.2 Use Case Package: Rincian Hubungan `<<include>>` dan `<<extend>>`

```mermaid
graph TD
    subgraph Package_Guru["Paket Pengelolaan & Evaluasi Guru"]
        UC04([UC-04: Generate Soal Cerdas])
        UC04A([Generate Rubrik 4 Dimensi])
        UC04B([Kurasi & Analisis Distraktor])
        UC04 -.->|<<include>>| UC04A
        UC04 -.->|<<include>>| UC04B

        UC05([UC-05: Buat & Publikasikan Ujian])
        UC05A([Konfigurasi Acak Soal & Opsi])
        UC05B([Atur Aturan Dual-Camera])
        UC05 -.->|<<include>>| UC05A
        UC05 -.->|<<include>>| UC05B

        UC11([UC-11: Review Nilai Esai])
        UC11A([Manual Score Override])
        UC11B([Auto-Accept High Confidence])
        UC11A -.->|<<extend>>| UC11
        UC11B -.->|<<extend>>| UC11
    end

    subgraph Package_Siswa["Paket Pengerjaan & Pengawasan Siswa"]
        UC06([UC-06: Verifikasi Kamera])
        UC06A([Scan QR Code Pairing HP])
        UC06 -.->|<<include>>| UC06A

        UC07([UC-07: Kerjakan Ujian])
        UC07A([Autosave Lokal IndexedDB])
        UC07B([Heartbeat Sync ke Server])
        UC07C([Tandai Soal Ragu-ragu])
        UC07 -.->|<<include>>| UC07A
        UC07 -.->|<<include>>| UC07B
        UC07C -.->|<<extend>>| UC07

        UC08([UC-08: Pengawasan Cerdas])
        UC08A([Deteksi Wajah Hilang / Multi-Wajah])
        UC08B([Deteksi Sudut Tatapan Gaze Away])
        UC08C([Deteksi Tab Switch / Fullscreen Exit])
        UC08D([Simpan Snapshot Bukti Pelanggaran])
        UC08 -.->|<<include>>| UC08A
        UC08 -.->|<<include>>| UC08B
        UC08 -.->|<<include>>| UC08C
        UC08D -.->|<<extend>>| UC08
    end
```

---

### 1.3 Deskripsi Naratif Use Case Utama (Use Case Narratives)

#### Naratif UC-04: Generate Soal Cerdas & Rubrik via AI
- **Aktor**: Guru, Sistem AI (LLM Adapter).
- **Prasyarat**: Guru telah login dan memiliki hak akses aktif.
- **Alur Utama (Main Flow)**:
  1. Guru membuka menu AI Question Generator dan memasukkan topik/materi atau mengunggah dokumen PDF/DOCX.
  2. Guru memilih tingkat kesulitan, taksonomi Bloom (C1-C6), jumlah PG, dan jumlah Esai.
  3. Guru menekan tombol "Generate Soal".
  4. Backend memformat prompt terstruktur dan memanggil LLM Provider.
  5. AI menghasilkan butir soal PG (dengan distractor rationale) dan soal Esai (dengan Rubrik 4 Dimensi).
  6. Guru mereview hasil generate di Curation Workspace, mengedit teks yang diperlukan, dan mengklik "Simpan ke Bank Soal".
  7. Sistem menyimpan soal-soal tersebut ke database MySQL.
- **Alur Alternatif (Alternative Flow)**:
  - *4a. LLM API Rate Limit / Timeout*: Sistem menampilkan pesan error dan menawarkan opsi *Retry* atau beralih ke provider AI cadangan.

---

#### Naratif UC-06 & UC-08: Verifikasi Dual-Camera & Proctoring
- **Aktor**: Siswa, Smartphone Siswa, Guru Pengawas, Sistem AI (MediaPipe CV).
- **Prasyarat**: Siswa terdaftar pada ujian yang dijadwalkan dan berstatus `published`.
- **Alur Utama (Main Flow)**:
  1. Siswa login dan membuka ujian target di laptop.
  2. Laptop meminta izin webcam primer dan menampilkan QR Code pairing unik.
  3. Siswa memindai QR Code menggunakan browser kamera HP.
  4. HP terhubung ke WebSocket room ujian sebagai kamera sekunder yang mengawasi meja.
  5. Selama ujian, engine MediaPipe di laptop memantau wajah, tatapan, dan status fullscreen.
  6. Jika terjadi anomali (misal wajah hilang $>10$ detik), sistem mengambil snapshot terkompresi ($<50$ KB), mencatat log insiden, dan menyiarkannya ke grid guru.
- **Alur Alternatif (Alternative Flow)**:
  - *4a. HP terputus di tengah jalan*: Laptop menampilkan peringatan kuning `[⚠️ Cam 2 Disconnected]` dan memberi waktu toleransi 2 menit bagi siswa untuk me-refresh koneksi HP.

---

## 2. UML Activity Diagrams

---

### 2.1 Activity Diagram 1: AI Question Generation & Curation Flow

```mermaid
stateDiagram-v2
    direction TB
    
    state "Guru (Examiner)" as GuruRole {
        [*] --> InputMateri: Masukkan Topik / Upload Dokumen
        InputMateri --> AturParameter: Tentukan Taksonomi Bloom, Kesulitan, & Jumlah Soal
        AturParameter --> KlikGenerate: Klik 'Generate Soal'
        ReviewWorkspace --> EditInline: Perbaiki Teks Soal / Opsi (Opsional)
        EditInline --> KlikSimpan: Klik 'Simpan ke Bank Soal'
        ReviewWorkspace --> MintaRegenerasi: Klik 'Regenerate' Butir Tertentu
        MintaRegenerasi --> KlikGenerate
        ReviewWorkspace --> KlikSimpan: Setujui Semua
    }

    state "Backend API & AI Engine" as BackendRole {
        KlikGenerate --> EkstraksiTeks: Ekstraksi Dokumen & Susun Structured Prompt
        EkstraksiTeks --> PanggilLLM: Kirim Payload ke Adapter LLM (Gemini/OpenAI)
        PanggilLLM --> ValidasiSkema: Validasi Output JSON (Pydantic v2)
        
        state ValidasiSkema <<choice>>
        ValidasiSkema --> FormatGagal: Schema Invalid
        FormatGagal --> PanggilLLM: Auto-Correction Prompt
        ValidasiSkema --> KirimKeFrontend: Schema Valid (PG + Distractor + Rubrik 4D)
        
        KirimKeFrontend --> ReviewWorkspace
        KlikSimpan --> SimpanDatabase: INSERT ke question_banks & questions (MySQL)
        SimpanDatabase --> [*]: Tampilkan Notifikasi Sukses
    }
```

---

### 2.2 Activity Diagram 2: Dual-Camera Setup & QR Pairing Flow

```mermaid
stateDiagram-v2
    direction TB

    state "Laptop Siswa (Desktop Next.js)" as LaptopState {
        [*] --> AksesUjian: Buka Halaman Verifikasi Ujian
        AksesUjian --> IzinWebcam: Izinkan Akses Webcam Laptop
        IzinWebcam --> TampilQR: Tampilkan QR Code Pairing Unik
        TampilQR --> MenungguPairing: Tunggu Sinyal WebSocket
        TerimaSinyal --> KameraAktif: Status [Cam 1: OK] & [Cam 2: OK]
        KameraAktif --> KlikMulai: Tombol 'Mulai Ujian' Aktif
    }

    state "Smartphone Siswa (Companion Mobile Web)" as PhoneState {
        ScanQR --> BukaURL: Buka Web Companion via Browser HP
        BukaURL --> IzinKameraHP: Izinkan Akses Kamera Belakang HP
        IzinKameraHP --> PosisikanHP: Posisikan HP di Samping Meja (Sudut 45°)
        PosisikanHP --> KirimHandshake: Hubungkan WebSocket ke Server
    }

    state "Backend Server (FastAPI WebSocket Hub)" as ServerState {
        TampilQR --> BuatToken: POST /start -> Generate UUID Pairing Token (TTL 10m)
        KirimHandshake --> ValidasiToken: Verifikasi Token & Kaitkan ke session_id
        ValidasiToken --> BroadcastPairing: Broadcast Event `COMPANION_PAIRED_SUCCESS`
        BroadcastPairing --> TerimaSinyal
        KlikMulai --> MulaiSesiDB: UPDATE exam_sessions status = 'in_progress'
        MulaiSesiDB --> [*]: Masuk ke Exam Workspace
    }

    TampilQR --> ScanQR: Siswa scan QR pakai HP
```

---

### 2.3 Activity Diagram 3: Student Exam Taking, Offline Autosave & Reconnect Flow

```mermaid
stateDiagram-v2
    direction TB

    state "Siswa (Examinee)" as SiswaAction {
        [*] --> BacaSoal: Baca Soal di Layar Ujian
        BacaSoal --> JawabSoal: Pilih Opsi PG / Ketik Jawaban Esai
        JawabSoal --> SimpanLokal: Event Input Perubahan Teks
        JawabSoal --> TandaiRagu: Klik 'Tandai Ragu-ragu' (Opsional)
    }

    state "Browser Client (Next.js & IndexedDB)" as ClientEngine {
        SimpanLokal --> WriteIndexedDB: Simpan Instan ke Cache Lokal (< 5ms)
        WriteIndexedDB --> UpdateUIStatus: Label UI: 'Tersimpan di laptop'
        
        state CekJaringan <<choice>>
        UpdateUIStatus --> Timer30Detik: Timer Heartbeat 30 Detik Berjalan
        Timer30Detik --> CekJaringan: Cek Status Navigator Online
        
        CekJaringan --> KirimServer: Online (Jaringan Normal)
        CekJaringan --> ModeOffline: Offline (Jaringan Terputus)
        
        ModeOffline --> SiswaTetapNgetik: UI: 'Mode Offline (Jawaban Tetap Aman)'
        SiswaTetapNgetik --> JawabSoal
        
        ModeOffline --> EventReconnect: Event window 'online' Terpicu
        EventReconnect --> KirimServer: Sinkronkan Seluruh Cache Tertunda
    }

    state "Backend & Database (FastAPI + MySQL)" as ServerDB {
        KirimServer --> UpsertSnapshot: POST /student/exam/{id}/autosave
        UpsertSnapshot --> SimpanDB: UPSERT ke tabel autosave_snapshots
        SimpanDB --> ReturnOK: Return 200 OK { last_saved_at }
        ReturnOK --> UpdateUIServer: Label UI: 'Tersinkronisasi ke Server (12:30:15)'
        UpdateUIServer --> [*]
    }
```

---

### 2.4 Activity Diagram 4: Dual-Camera AI Proctoring & Flagging Flow

```mermaid
stateDiagram-v2
    direction TB

    state "Client Edge Vision Engine (MediaPipe)" as EdgeVision {
        [*] --> TangkapFrame: Capture Frame Video Webcam (3-5 FPS)
        TangkapFrame --> InferensiLandmark: Hitung 468 Landmark Wajah 3D
        InferensiLandmark --> HitungPose: Hitung Sudut Yaw, Pitch, Roll & EAR
        
        state EvaluasiKondisi <<choice>>
        HitungPose --> EvaluasiKondisi: Evaluasi Rule Anomali
        
        EvaluasiKondisi --> Normal: Tidak Ada Pelanggaran (Wajah & Tatapan OK)
        Normal --> TangkapFrame
        
        EvaluasiKondisi --> Anomali: Terdeteksi Anomali (Wajah Hilang / Multi / Gaze / Tab Blur)
        Anomali --> DebounceCheck: Apakah Anomali Berlangsung >= 10 Detik?
        
        state DebounceDecision <<choice>>
        DebounceCheck --> DebounceDecision
        DebounceDecision --> TangkapFrame: < 10 Detik (Fluktuasi Sesaat)
        DebounceDecision --> AmbilSnapshot: >= 10 Detik (Insiden Terkonfirmasi)
        
        AmbilSnapshot --> KompresiJPEG: Ambil Frame Canvas & Kompresi JPEG 60% (< 50 KB)
    }

    state "Backend & Database" as BackendProctor {
        KompresiJPEG --> KirimLogEvent: POST /api/v1/proctoring/log-event
        KirimLogEvent --> SimpanLogDB: INSERT ke proctoring_logs (event_type, severity, snap_url)
        SimpanLogDB --> KurangiIntegritas: Hitung Penalti Indeks Integritas (I_session)
        KurangiIntegritas --> BroadcastGuru: WebSocket Push `PROCTORING_FLAG_ALERT`
    }

    state "Guru (Live Monitoring Hub)" as GuruMonitor {
        BroadcastGuru --> UpdateGrid: Thumbnail Siswa Berubah Warna Menjadi 🔴 Flagged
        UpdateGrid --> ReviewSnapshot: Guru Buka Detail & Review Snapshot Bukti
        
        state TindakanGuru <<choice>>
        ReviewSnapshot --> TindakanGuru: Ambil Tindakan
        TindakanGuru --> Abaikan: Tandai 'False Positive' (Misal Batuk/Jatuh)
        TindakanGuru --> KirimPeringatan: Klik 'Kirim Pesan Peringatan Langsung'
        
        KirimPeringatan --> PushPeringatanSiswa: POST /proctoring/send-warning
        PushPeringatanSiswa --> MunculPopUp: Pop-Up Berkedip Muncul di Layar Siswa
        Abaikan --> [*]
        MunculPopUp --> [*]
    }
```

---

### 2.5 Activity Diagram 5: Exam Submission & Hybrid Async AI Grading Flow

```mermaid
stateDiagram-v2
    direction TB

    state "Siswa (Examinee)" as SiswaSubmit {
        [*] --> KlikKumpulkan: Klik 'Selesai & Kumpulkan Ujian'
        KlikKumpulkan --> ModalKonfirmasi: Muncul Dialog Ringkasan (Terjawab / Ragu)
        ModalKonfirmasi --> KonfirmasiFinal: Klik 'Ya, Kumpulkan Sekarang'
    }

    state "Backend FastAPI (Synchronous Layer)" as BackendSync {
        KonfirmasiFinal --> NilaiPGInstan: POST /student/exam/{id}/submit
        NilaiPGInstan --> UpdateStatusSession: Evaluasi PG (O(1)) & Update session = 'grading_in_progress'
        UpdateStatusSession --> TriggerWorker: Dispatch `BackgroundTasks.add_task(grade_essay_async)`
        UpdateStatusSession --> ResponSiswa: Return 200 OK (Siswa Bebas Keluar dari Ujian)
        ResponSiswa --> [*]: Siswa Selesai
    }

    state "Async Background Worker & LLM Adapter" as AsyncWorker {
        TriggerWorker --> AmbilJawabanEsai: Query `student_answers` bertipe esai untuk sesi tersebut
        
        state LoopEsai <<choice>>
        AmbilJawabanEsai --> LoopEsai: Iterasi setiap butir esai
        
        LoopEsai --> SusunPromptRubrik: Susun Prompt (Pertanyaan + Rubrik 4D + Jawaban Siswa)
        SusunPromptRubrik --> RequestLLM: Panggil Model LLM via JSON Structured Output
        RequestLLM --> ParseSubSkor: Ekstraksi Skor 4 Dimensi & Rasional Penilaian
        ParseSubSkor --> HitungConfidence: Hitung AI Confidence Index (C_ai: High/Med/Low)
        HitungConfidence --> UpdateAnswerDB: UPDATE student_answers (auto_score, confidence, rationale)
        
        UpdateAnswerDB --> LoopEsai: Butir berikutnya ada?
        LoopEsai --> AkumulasiTotal: Seluruh esai tuntas dinilai
        
        AkumulasiTotal --> UpdateSelesai: UPDATE exam_sessions status = 'graded', total_score = sum
        UpdateSelesai --> SelesaiWorker: Selesai (< 45 detik/kelas)
        SelesaiWorker --> [*]
    }
```

---

### 2.6 Activity Diagram 6: Teacher Grading Review, Score Override & Finalization Flow

```mermaid
stateDiagram-v2
    direction TB

    state "Guru (Examiner Workspace)" as GuruReview {
        [*] --> BukaReviewSuite: Buka Dashboard Grading Ujian
        BukaReviewSuite --> FilterSiswa: Pilih Siswa (Filter: Low Confidence / Semua)
        FilterSiswa --> BukaLembarJawaban: Buka Tampilan Side-by-Side Siswa
        BukaLembarJawaban --> EvaluasiNilaiAI: Periksa Jawaban vs Nilai 4 Dimensi AI
        
        state KeputusanGuru <<choice>>
        EvaluasiNilaiAI --> KeputusanGuru: Apakah Nilai AI Sesuai?
        
        KeputusanGuru --> SetujuiNilai: Ya (Nilai Sesuai)
        KeputusanGuru --> UbahNilai: Tidak (Perlu Penyesuaian Pedagogis)
        
        UbahNilai --> InputOverride: Masukkan `teacher_override_score` & `teacher_notes`
        InputOverride --> KlikSimpanNilai: Klik 'Simpan Nilai'
        SetujuiNilai --> KlikSimpanNilai: Klik 'Setujui Nilai AI'
        
        KlikSimpanNilai --> PeriksaSemuaSiswa: Ada siswa lain yang belum direview?
        
        state SelesaiSemua <<choice>>
        PeriksaSemuaSiswa --> SelesaiSemua
        SelesaiSemua --> FilterSiswa: Ya (Review Siswa Berikutnya)
        SelesaiSemua --> KlikFinalisasi: Tidak (Seluruh Siswa Tuntas)
        
        KlikFinalisasi --> KonfirmasiRilis: Klik 'Finalisasi & Rilis Nilai ke Kelas'
    }

    state "Backend & Database" as BackendFinal {
        KlikSimpanNilai --> UpdateScoreDB: UPDATE student_answers (final_score = override_score || auto_score)
        KonfirmasiFinal --> PublishResults: POST /api/v1/grading/exam/{id}/finalize
        PublishResults --> UpdateExamStatus: UPDATE exams status = 'completed', sessions = 'finalized'
        UpdateExamStatus --> BukaPembahasan: Aktifkan Akses Hasil & Pembahasan Siswa
    }

    state "Siswa (Examinee)" as SiswaResult {
        BukaPembahasan --> BukaHasilSiswa: Siswa Buka Menu Hasil Ujian
        BukaHasilSiswa --> LihatNilaiDanAI: Tampilkan Nilai Akhir, Sub-skor Rubrik, & Penjelasan Formatif AI
        LihatNilaiDanAI --> [*]: Proses Selesai
    }
```

---

## 3. Matriks Keterlacakan Use Case ke Kebutuhan Fungsional (Traceability)

| Kode Use Case | Nama Use Case | Kebutuhan SRS Terkait ([docs/SRS.md](./SRS.md)) | Tiket Terkait ([docs/tickets/](../tickets/)) |
|---|---|---|---|
| **UC-01** | Autentikasi Login & Logout | `REQ-F-AUTH-01`, `REQ-F-AUTH-02`, `REQ-F-AUTH-03` | `AUTH-001`, `AUTH-002`, `AUTH-003` |
| **UC-02** | Kelola Pengguna & Kelas | `REQ-F-AUTH-04` | `AUTH-004` |
| **UC-03** | Kelola Bank Soal | `REQ-F-QGEN-01` | `QGEN-001` |
| **UC-04** | Generate Soal & Rubrik via AI | `REQ-F-QGEN-02`, `REQ-F-QGEN-03`, `REQ-F-QGEN-04`, `REQ-F-QGEN-05` | `QGEN-002`, `QGEN-003`, `QGEN-004` |
| **UC-05** | Buat & Publikasikan Ujian | `REQ-F-EXAM-01`, `REQ-F-EXAM-02`, `REQ-F-EXAM-03`, `REQ-F-EXAM-04` | `EXAM-001`, `EXAM-002`, `EXAM-003` |
| **UC-06** | Verifikasi Dual-Camera & QR Pairing | `REQ-F-PROC-02` | `PROC-002` |
| **UC-07** | Kerjakan Ujian & Autosave | `REQ-F-TAKE-01`, `REQ-F-TAKE-02`, `REQ-F-TAKE-03`, `REQ-F-TAKE-04` | `TAKE-001`, `TAKE-002`, `TAKE-003` |
| **UC-08** | Pengawasan Cerdas & Flagging | `REQ-F-PROC-01`, `REQ-F-PROC-03`, `REQ-F-PROC-04`, `REQ-F-PROC-05` | `PROC-001`, `PROC-003` |
| **UC-09** | Live Monitor & Kirim Peringatan | `REQ-F-PROC-06` | `PROC-004` |
| **UC-10** | Kumpulkan Ujian & Auto-Grading | `REQ-F-TAKE-05`, `REQ-F-GRAD-01`, `REQ-F-GRAD-02` | `TAKE-004`, `GRAD-001`, `GRAD-002` |
| **UC-11** | Review & Override Nilai Esai | `REQ-F-GRAD-03`, `REQ-F-GRAD-04`, `REQ-F-GRAD-05` | `GRAD-003` |
| **UC-12** | Lihat Hasil & Pembahasan AI | `REQ-F-EXPL-01`, `REQ-F-EXPL-02` | `EXPL-001`, `EXPL-002` |
| **UC-13** | Analisis Butir Soal & Ekspor | `REQ-F-REP-01`, `REQ-F-REP-02`, `REQ-F-REP-03` | `REP-001`, `REP-002`, `REP-003` |
