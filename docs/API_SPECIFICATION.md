# EXAMIND — REST API & WebSocket Specifications

**Versi:** 1.0  
**Tanggal:** 31 Agustus 2026  
**Dokumen Induk:** [docs/PRD.md](./PRD.md) | [docs/ARCHITECTURE.md](./ARCHITECTURE.md)  

---

## 1. Konvensi & Standar Global API

- **Base URL**: `http://localhost:8000/api/v1` (Development)
- **Format Pertukaran Data**: `application/json` (UTF-8)
- **Header Autentikasi**: `Authorization: Bearer <JWT_TOKEN>`
- **Format Standar Response**:

```json
{
  "success": true,
  "data": { ... },
  "message": "Deskripsi status operasi",
  "error": null
}
```

- **Format Standar Error Response**:
```json
{
  "success": false,
  "data": null,
  "message": "Penjelasan error yang ramah pengguna",
  "error": {
    "code": "EXAM_ALREADY_SUBMITTED",
    "details": "Sesi ujian ini telah dikumpulkan dan tidak dapat diedit lagi."
  }
}
```

---

## 2. Modul Autentikasi (`/api/v1/auth`)

### 2.1 Login Pengguna
- **Method / Path**: `POST /api/v1/auth/login`
- **Akses**: Publik
- **Request Body**:
```json
{
  "identifier": "198507232010011005",
  "password": "PasswordGuru123!"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in_minutes": 1440,
    "user": {
      "id": 2,
      "identifier": "198507232010011005",
      "email": "guru.fisika@sekolah.sch.id",
      "full_name": "Budi Santoso, M.Pd.",
      "role": "teacher"
    }
  },
  "message": "Login berhasil",
  "error": null
}
```

---

## 3. Modul AI Question Generator (`/api/v1/ai`)

### 3.1 Generate Draft Soal Ujian
- **Method / Path**: `POST /api/v1/ai/generate-questions`
- **Akses**: Teacher
- **Request Body**:
```json
{
  "subject": "Fisika",
  "topic_content": "Teori Kuantum dan Efek Fotolistrik",
  "grade_level": "12",
  "mcq_count": 5,
  "essay_count": 2,
  "difficulty": "medium"
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "mcq_questions": [
      {
        "prompt": "Pada peristiwa efek fotolistrik, energi kinetik maksimum elektron yang terlepas bergantung pada...",
        "difficulty": "medium",
        "bloom_level": "C3",
        "options": [
          { "id": "A", "text": "Intensitas cahaya yang menyinari", "is_correct": false, "rationale": "Intensitas hanya mempengaruhi jumlah elektron, bukan energi kinetik." },
          { "id": "B", "text": "Frekuensi cahaya yang menyinari", "is_correct": true, "rationale": "Energi kinetik ditentukan oleh frekuensi foton sesuai persamaan Einstein: Ek = hf - W0." },
          { "id": "C", "text": "Luas permukaan logam", "is_correct": false, "rationale": "Luas permukaan tidak mengubah energi per foton." },
          { "id": "D", "text": "Lama penyinaran cahaya", "is_correct": false, "rationale": "Efek fotolistrik bersifat instan tanpa penundaan waktu." }
        ],
        "correct_option_id": "B",
        "explanation": "Berdasarkan teori foton Einstein, energi kinetik elektron hanya bergantung pada frekuensi foton dan fungsi kerja logam.",
        "points": 10.0
      }
    ],
    "essay_questions": [
      {
        "prompt": "Jelaskan bagaimana teori kuantum Einstein mampu menerangkan kelemahan teori gelombang klasik dalam menjelaskan efek fotolistrik!",
        "difficulty": "hard",
        "bloom_level": "C4",
        "rubric": {
          "dimension_1_concept": "Menjelaskan konsep paket energi foton (Maks 40 Poin)",
          "dimension_2_comparison": "Membandingkan dengan kegagalan teori gelombang klasik (Maks 30 Poin)",
          "dimension_3_terminology": "Penggunaan istilah frekuensi ambang dan fungsi kerja (Maks 15 Poin)",
          "dimension_4_clarity": "Runtutan logika dan bahasa (Maks 15 Poin)"
        },
        "points": 20.0
      }
    ]
  },
  "message": "Draft soal berhasil dibuat",
  "error": null
}
```

---

## 4. Modul Pengerjaan Ujian Siswa (`/api/v1/student`)

### 4.1 Memulai Sesi Ujian (Start Exam)
- **Method / Path**: `POST /api/v1/student/exam/{exam_id}/start`
- **Akses**: Student
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "session_id": 108,
    "exam": {
      "id": 1,
      "title": "Ujian Akhir Semester Fisika Kuantum",
      "duration_minutes": 90,
      "start_time": "2026-08-31T08:00:00Z",
      "end_time": "2026-08-31T10:00:00Z",
      "proctoring_level": "dual_camera",
      "total_questions": 40
    },
    "pairing_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "companion_qr_url": "https://examind.sch.id/companion/pair?token=a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "questions": [
      {
        "id": 101,
        "order_index": 1,
        "question_type": "multiple_choice",
        "prompt": "Pada peristiwa efek fotolistrik...",
        "options": [
          { "id": "A", "text": "Intensitas cahaya" },
          { "id": "B", "text": "Frekuensi cahaya" },
          { "id": "C", "text": "Luas permukaan" },
          { "id": "D", "text": "Lama penyinaran" }
        ],
        "points": 10.0
      }
    ]
  },
  "message": "Sesi ujian dimulai",
  "error": null
}
```

---

### 4.2 Autosave Snapshot Jawaban
- **Method / Path**: `POST /api/v1/student/exam/{exam_id}/autosave`
- **Akses**: Student
- **Request Body**:
```json
{
  "session_id": 108,
  "answers": [
    { "question_id": 101, "response": "B" },
    { "question_id": 102, "response": "Efek fotolistrik terjadi karena..." }
  ]
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "saved_items_count": 2,
    "last_saved_at": "2026-08-31T08:15:30Z"
  },
  "message": "Jawaban berhasil diautosave",
  "error": null
}
```

---

### 4.3 Submit Final Ujian
- **Method / Path**: `POST /api/v1/student/exam/{exam_id}/submit`
- **Akses**: Student
- **Request Body**:
```json
{
  "session_id": 108
}
```
- **Response (200 OK)**:
```json
{
  "success": true,
  "data": {
    "session_id": 108,
    "status": "grading_in_progress",
    "submitted_at": "2026-08-31T09:25:10Z",
    "message": "Ujian telah selesai. Penilaian esai sedang diproses secara asinkron."
  },
  "message": "Submit berhasil",
  "error": null
}
```

---

## 5. Modul Pengawasan & Protokol WebSocket (`/ws`)

### 5.1 WebSocket Live Monitoring Guru
- **Protokol / Path**: `WS /ws/exam/{exam_id}/live-monitor`
- **Aktor**: Guru / Pengawas Ujian
- **Format Pesan Masuk dari Server (Broadcast Event)**:
```json
{
  "event": "PROCTORING_FLAG_ALERT",
  "payload": {
    "session_id": 108,
    "student_name": "Budi Santoso",
    "event_type": "face_absent",
    "camera_source": "primary_camera",
    "severity": "medium",
    "duration_seconds": 12,
    "timestamp": "2026-08-31T08:35:40Z",
    "snapshot_url": "https://storage.examind.sch.id/snapshots/108_flag_1.jpg",
    "current_integrity_score": 90
  }
}
```

---

### 5.2 Pengiriman Peringatan Langsung dari Guru ke Siswa
- **Method / Path**: `POST /api/v1/proctoring/send-warning`
- **Akses**: Teacher
- **Request Body**:
```json
{
  "session_id": 108,
  "message_text": "Peringatan: Pastikan wajah Anda selalu menghadap layar monitor!",
  "urgency": "high"
}
```
- **Efek Real-Time**: Siswa langsung menerima dialog modal peringatan berkedip di layar ujian mereka tanpa perlu me-refresh browser.
