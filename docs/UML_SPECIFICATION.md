# EXAMIND — UML Structural & Behavioral Specifications

**Versi:** 1.2 (Tech Stack Migration: Vue 3 + FastAPI + PyTorch)  
**Tanggal:** 2 September 2026  
**Dokumen Induk:** [docs/PRD.md](./PRD.md) | [docs/SRS.md](./SRS.md) | [docs/ARCHITECTURE.md](./ARCHITECTURE.md)  

---

## DAFTAR ISI
1. [BAGIAN I: UML STRUCTURAL DIAGRAMS (DIAGRAM STRUKTURAL)](#bagian-i-uml-structural-diagrams)
   - 1.1 Class Diagram (Domain Model & Service Architecture)
   - 1.2 Component Diagram (Komponen Perangkat Lunak Monorepo)
   - 1.3 Deployment Diagram (Topologi & Node Distribusi Fisik)
   - 1.4 Package Diagram (Dekomposisi Paket Backend & Frontend)
2. [BAGIAN II: UML BEHAVIORAL DIAGRAMS (DIAGRAM PERILAKU)](#bagian-ii-uml-behavioral-diagrams)
   - 2.1 Use Case Diagram & Naratif
   - 2.2 Sequence Diagrams (Alur Transaksi Sistem Kunci)
   - 2.3 State Machine Diagrams (Siklus Hidup Entitas Kunci)
   - 2.4 Activity Diagrams (Alur Kerja Operasional dengan Swimlanes)

---

# BAGIAN I: UML STRUCTURAL DIAGRAMS

## 1.1 Class Diagram (Domain Model & Service Architecture)

```mermaid
classDiagram
    %% Domain Entities
    class User {
        +int id
        +string identifier
        +string email
        +string password_hash
        +string full_name
        +UserRole role
        +string avatar_url
        +bool is_active
        +datetime created_at
        +authenticate(password: string) bool
        +update_profile(data: dict) bool
    }

    class UserRole {
        <<enumeration>>
        ADMIN
        TEACHER
        STUDENT
    }

    class AcademicClass {
        +int id
        +string name
        +string grade_level
        +string academic_year
        +int created_by
        +add_member(user_id: int, role: string) bool
        +get_roster() List~User~
    }

    class ClassMember {
        +int id
        +int class_id
        +int user_id
        +string role
        +datetime joined_at
    }

    class QuestionBank {
        +int id
        +int teacher_id
        +string title
        +string subject
        +string description
        +datetime created_at
        +get_questions(filter: dict) List~Question~
    }

    class Question {
        +int id
        +int bank_id
        +QuestionType question_type
        +string prompt
        +json options_json
        +string correct_answer
        +json rubric_json
        +string explanation
        +DifficultyLevel difficulty
        +float default_points
        +validate_schema() bool
    }

    class Exam {
        +int id
        +int teacher_id
        +int class_id
        +string title
        +string description
        +int duration_minutes
        +datetime start_time
        +datetime end_time
        +bool randomize_questions
        +bool randomize_options
        +ProctoringLevel proctoring_level
        +ExplanationPolicy explanation_policy
        +ExamStatus status
        +publish() bool
        +is_active_now() bool
    }

    class ExamQuestion {
        +int id
        +int exam_id
        +int question_id
        +int order_index
        +float allocated_points
    }

    class ExamSession {
        +int id
        +int exam_id
        +int student_id
        +datetime start_time
        +datetime submit_time
        +SessionStatus status
        +float total_score
        +int integrity_score
        +bool companion_paired
        +string client_ip
        +calculate_integrity() int
        +finalize_score() float
    }

    class StudentAnswer {
        +int id
        +int session_id
        +int question_id
        +string student_response
        +bool is_correct
        +float auto_score
        +float teacher_override_score
        +float final_score
        +ConfidenceLevel ai_confidence_level
        +string ai_grading_rationale
        +string ai_explanation
        +string teacher_notes
        +apply_override(score: float, notes: string) void
    }

    class AutosaveSnapshot {
        +int id
        +int session_id
        +json answers_payload
        +datetime last_saved_at
        +restore_to_session() dict
    }

    class ProctoringLog {
        +int id
        +int session_id
        +EventType event_type
        +CameraSource camera_source
        +SeverityLevel severity
        +int duration_seconds
        +string snapshot_url
        +datetime event_timestamp
        +bool reviewed_by_teacher
        +VerdictStatus teacher_verdict
        +apply_verdict(verdict: string) void
    }

    %% Service Layer & Model Serving
    class ModelServingEngine {
        -PyTorchModel face_model
        -PyTorchModel object_model
        +load_weights(weights_path: str) void
        +predict_face_anomaly(frame_bytes: bytes) dict
        +predict_desk_objects(frame_bytes: bytes) dict
    }

    class MLGradingPipeline {
        -AIServiceInterface llm_adapter
        +extract_semantic_features(response: str) Vector
        +calculate_confidence_score(subscores: dict) float
        +evaluate_rubric_async(session_id: int) void
    }

    %% Relationships
    User "1" --> "*" AcademicClass : creates
    AcademicClass "1" --> "*" ClassMember : contains
    User "1" --> "*" ClassMember : belongs_to
    User "1" --> "*" QuestionBank : owns
    QuestionBank "1" --> "*" Question : contains
    User "1" --> "*" Exam : manages
    AcademicClass "1" --> "*" Exam : targeted_to
    Exam "1" --> "*" ExamQuestion : defines
    Question "1" --> "*" ExamQuestion : assigned_to
    Exam "1" --> "*" ExamSession : instantiates
    User "1" --> "*" ExamSession : participates_in
    ExamSession "1" --> "*" StudentAnswer : records
    Question "1" --> "*" StudentAnswer : evaluated_against
    ExamSession "1" --> "1" AutosaveSnapshot : backups
    ExamSession "1" --> "*" ProctoringLog : monitors
```

---

## 1.2 Component Diagram (Komponen Perangkat Lunak Monorepo)

```mermaid
graph TD
    subgraph Frontend_App["💻 Frontend Application (Vue 3 + Vite + TypeScript)"]
        UI_Exam["Exam Workspace (Vue SFC)"]
        UI_Monitor["Teacher Live Monitoring Grid (Vue SFC)"]
        UI_Grading["Grading & Override Suite (Vue SFC)"]
        UI_Curation["Question Curation Workspace (Vue SFC)"]
        Pinia_Store["Pinia Stores (Auth, Exam, Proctoring)"]
        Vue_Router["Vue Router (Auth Navigation Guards)"]
        EdgeCV["MediaPipe WASM Engine (Client Edge Vision)"]
        IDBCache["IndexedDB Local Storage Cache"]
        APIClient["Axios API Client (JWT Interceptor)"]
        WSSClient["WebSocket Client Manager"]
    end

    subgraph Backend_App["⚡ Backend Application (FastAPI / Python 3.10+)"]
        Gateway["API Gateway & CORS / RBAC Middleware"]
        AuthModule["Authentication (JWT + Bcrypt)"]
        ExamService["Business Logic: Exam Session Service"]
        AutosaveHub["Autosave & Snapshot Hub"]
        ProctoringHub["Proctoring WebSocket & Flagging Hub"]
        GradingQueue["Async Background Grading Worker"]
        ModelServing["PyTorch Model Serving Engine"]
        ML_Pipeline["ML Pipeline & Feature Extraction"]
        AI_Adapter["Modular LLM Adapters (Gemini/OpenAI)"]
        AnalyticsEngine["Item Analysis & Report Exporter"]
    end

    subgraph Database_Layer["🗄️ Database & Storage Layer (XAMPP MySQL)"]
        MySQL_DB[("MySQL Database (Port 3306)")]
        FileStorage[("Snapshot JPEG Storage")]
        PyTorchWeights[("PyTorch Model Weights (.pt / .pth)")]
    end

    subgraph External_Cloud["☁️ External Cloud Services"]
        LLM_API["Google Gemini / OpenAI API"]
    end

    %% Wiring connections
    UI_Exam --> Pinia_Store
    Pinia_Store --> IDBCache
    UI_Exam --> EdgeCV
    EdgeCV --> WSSClient
    UI_Exam --> APIClient
    UI_Monitor --> WSSClient
    UI_Grading --> APIClient
    UI_Curation --> APIClient

    APIClient -->|HTTPS REST| Gateway
    WSSClient -->|WSS Protocol| Gateway

    Gateway --> AuthModule
    Gateway --> ExamService
    Gateway --> AutosaveHub
    Gateway --> ProctoringHub
    Gateway --> AnalyticsEngine

    ProctoringHub --> ModelServing
    ModelServing --> PyTorchWeights

    ExamService --> GradingQueue
    GradingQueue --> ML_Pipeline
    ML_Pipeline --> AI_Adapter
    AI_Adapter -->|HTTPS REST| LLM_API

    AuthModule --> MySQL_DB
    ExamService --> MySQL_DB
    AutosaveHub --> MySQL_DB
    ProctoringHub --> MySQL_DB
    ProctoringHub --> FileStorage
    AnalyticsEngine --> MySQL_DB
```

---

## 1.3 Deployment Diagram (Topologi & Node Distribusi Fisik)

```mermaid
graph TB
    subgraph Client_Laptop["🖥️ Node: Examinee Laptop / Desktop"]
        Browser_Desktop["Peramban Web (Chrome / Edge / Firefox)"]
        subgraph Exec_Desktop["Vue 3 SPA (Vite Bundle)"]
            WASM_CV["MediaPipe Face Mesh (WASM)"]
            IndexedDB_Local["IndexedDB Storage Cache"]
            Pinia_Engine["Pinia State Engine"]
        end
        Webcam_Device["📷 Hardware: HD Webcam (720p)"]
        Webcam_Device --> Browser_Desktop
    end

    subgraph Client_Phone["📱 Node: Examinee Smartphone (Companion)"]
        Browser_Mobile["Mobile Browser (Safari / Chrome)"]
        Mobile_Cam["📷 Hardware: Rear Camera (45° Meja)"]
        Mobile_Cam --> Browser_Mobile
    end

    subgraph Server_Host["🖥️ Node: Local Application Server (Host Machine)"]
        subgraph Process_FastAPI["Python 3.10+ Runtime Environment"]
            Uvicorn["ASGI Server: Uvicorn (Port 8000)"]
            FastAPI_App["FastAPI Application Instance"]
            Background_Worker["BackgroundTasks ThreadPool"]
            PyTorch_Runtime["PyTorch Inference Runtime (CPU/CUDA)"]
        end

        subgraph Process_XAMPP["XAMPP Server Environment"]
            MySQL_Server["MySQL 8.0+ Service (Port 3306)"]
            Apache_Admin["Apache (phpMyAdmin Port 80)"]
        end

        LocalStorage_Disk[("📁 Local Disk: /storage/snapshots/")]
        Model_Disk[("🧠 Model Weights: /models/*.pt")]
    end

    subgraph Cloud_AI["☁️ Node: AI Cloud Infrastructure"]
        Gemini_Cloud["Google AI Studio / Gemini Pro 1.5 Endpoint"]
    end

    %% Network Connections
    Browser_Desktop -->|HTTPS (Port 8000)| Uvicorn
    Browser_Desktop -->|WSS (Port 8000)| Uvicorn
    Browser_Mobile -->|WSS (Port 8000)| Uvicorn
    Uvicorn --> FastAPI_App
    FastAPI_App --> Background_Worker
    FastAPI_App --> PyTorch_Runtime
    PyTorch_Runtime --> Model_Disk
    FastAPI_App -->|TCP Connection Pool (Port 3306)| MySQL_Server
    FastAPI_App -->|Local I/O File Write| LocalStorage_Disk
    Background_Worker -->|TLS HTTPS Outbound| Gemini_Cloud
```

---

## 1.4 Package Diagram (Dekomposisi Paket Backend & Frontend)

```mermaid
graph TD
    subgraph Monorepo["📁 EXAMIND MONOREPO"]
        subgraph Backend_Pkg["backend/app"]
            Pkg_Core["core (config, security, database, deps)"]
            Pkg_Models["models (user, exam, question, session, proctoring)"]
            Pkg_Schemas["schemas (auth, exam, question, grading, proctoring)"]
            Pkg_API["api.v1 (endpoints: auth, exams, questions, student, grading, proctoring)"]
            Pkg_ML["ml (model_serving, pipeline, feature_extractor)"]
            Pkg_Services["services (ai_adapters, grading, proctoring, analytics, reporting)"]
            
            Pkg_API --> Pkg_Schemas
            Pkg_API --> Pkg_Services
            Pkg_Services --> Pkg_ML
            Pkg_Services --> Pkg_Models
            Pkg_Services --> Pkg_Core
            Pkg_Models --> Pkg_Core
        end

        subgraph Frontend_Pkg["frontend/src"]
            Pkg_Views["views (LoginView, DashboardView, ExamWorkspaceView, CompanionView)"]
            Pkg_Components["components (ui, exam, monitor, grading)"]
            Pkg_Router["router (index.ts, navigation guards)"]
            Pkg_Stores["stores (authStore, examStore, proctoringStore)"]
            Pkg_Lib["lib (apiClient, utils, indexedDB, faceMeshEngine)"]

            Pkg_Views --> Pkg_Components
            Pkg_Views --> Pkg_Stores
            Pkg_Views --> Pkg_Router
            Pkg_Stores --> Pkg_Lib
        end
    end
```

---

# BAGIAN II: UML BEHAVIORAL DIAGRAMS

## 2.1 Sequence Diagram: Ujian Siswa, Autosave Vue 3 & Model Verification

```mermaid
sequenceDiagram
    autonumber
    actor Siswa as 👨‍🎓 Siswa (Laptop Vue 3)
    participant Pinia as 🍍 Pinia Exam Store
    participant IDB as 💾 IndexedDB
    participant API as ⚡ FastAPI Backend
    participant PyTorch as 🔬 PyTorch Model Serving
    participant DB as 🗄️ MySQL Database

    Siswa->>Pinia: Mengetik Jawaban Esai
    Pinia->>IDB: Simpan instan ke local cache (< 5ms)
    
    loop Heartbeat Tiap 30 Detik
        Pinia->>API: POST /api/v1/student/exam/{id}/autosave
        API->>DB: UPSERT autosave_snapshots
        API-->>Pinia: 200 OK (Sync Acknowledged)
    end

    opt Terdeteksi Anomali Kamera HP
        Siswa->>API: POST /api/v1/proctoring/log-event (Snapshot JPEG)
        API->>PyTorch: model.predict_desk_objects(snapshot)
        PyTorch-->>API: Return { is_anomaly: true, confidence: 0.92 }
        API->>DB: INSERT INTO proctoring_logs
        API->>DB: UPDATE exam_sessions SET integrity_score = integrity_score - 10
    end
```

---

## 2.2 Sequence Diagram: Submit & Async ML Grading Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Siswa as 👨‍🎓 Siswa
    participant API as ⚡ FastAPI Backend
    participant DB as 🗄️ MySQL Database
    participant Worker as ⚙️ Async Background Worker
    participant ML as 🔬 ML Pipeline & LLM

    Siswa->>API: POST /api/v1/student/exam/{id}/submit
    API->>DB: Hitung Nilai Pilihan Ganda Instan (O(1))
    API->>DB: UPDATE exam_sessions SET status = 'grading_in_progress'
    API->>Worker: Dispatch BackgroundTasks(grade_session_async)
    API-->>Siswa: Response 200 OK (Ujian Dikumpulkan)

    Note over Worker,ML: Penilaian Esai Asinkron (< 45s)
    Worker->>DB: SELECT student_answers WHERE type = 'essay'
    loop Setiap Soal Esai
        Worker->>ML: evaluate_essay(rubric_4d, student_response)
        ML-->>Worker: Return { subscores, confidence_score, rationale, explanation }
        Worker->>DB: UPDATE student_answers SET auto_score, ai_confidence, explanation
    end
    Worker->>DB: UPDATE exam_sessions SET status = 'graded'
```
