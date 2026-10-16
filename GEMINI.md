# EXAMIND — Project Guidelines & Architecture Rules

## 1. Project Overview & Scope
- **Product**: EXAMIND is an AI-powered online examination platform designed for schools and educational institutions.
- **Core Capabilities**:
  - AI Question Generator (Multiple choice, short essay, long essay from topics/materials).
  - Automated Grading (Instant for multiple choice; AI LLM-based for essay with rubrics, confidence scores, and teacher override).
  - Detailed Answer Explanations (Explaining why answers are correct/incorrect and referencing concepts).
  - AI Dual-Camera Proctoring (Face detection & presence on primary camera; secondary device/camera for desk/environment monitoring; flagging system with snapshot/timestamp for teacher review).
  - School & Teacher Dashboard (Question bank, class/student management, exam scheduling, proctoring log review, and analytics).
- **Non-Goals (Out of Scope for v1)**:
  - DO NOT implement full LMS features (course materials, lessons, discussion forums).
  - DO NOT implement School Information System (SIS) features (academic administration, tuition fees).
  - DO NOT implement scanned paper exam grading in initial versions.

## 2. Tech Stack & Architectural Constraints
- **Frontend**: Vue 3 + TypeScript.
  - Build Tool: Vite (runs on port 3000 or 5173).
  - Styling & UI Components: Tailwind CSS + shadcn-vue (Radix Vue).
  - State Management: Pinia.
  - Routing: Vue Router with navigation auth guards.
- **Backend**: FastAPI (Python 3.10+) + Pydantic v2.
  - Modules: Authentication (JWT + Bcrypt), Business Logic, Model Serving, ML Pipeline.
  - AI & Computer Vision: PyTorch Models for local CV/ML model serving, plus modular LLM adapters (Gemini/OpenAI) for generation and grading.
- **Database**: MySQL served via XAMPP (strict requirement for university project).
  - FastAPI runs as a standalone Python process and connects to MySQL hosted on XAMPP (default port 3306).
  - Database schema managed cleanly with SQLAlchemy 2.0 and Alembic migrations.
- **CORS & Realtime**:
  - FastAPI must include CORS middleware configured for the Vue 3 frontend origin.
  - Realtime exam status and proctoring events communicate via WebSockets (native FastAPI).

## 3. Core Behavioral Invariants & Guardrails
- **Human-in-the-Loop Proctoring**: The AI proctoring system must NEVER automatically disqualify a student. It only flags suspicious events with timestamps and snapshots for human (teacher/admin) review.
- **Reliability & Autosave**: The exam taking interface must autosave student answers periodically (IndexedDB local edge cache + 30s server heartbeat sync) to prevent data loss on network disconnects.
- **Async AI Grading**: Essay auto-grading should run asynchronously in the background so that submission flows remain fast and responsive.
- **Privacy & UU PDP Compliance**: Student video, face, and audio data are sensitive. Ensure explicit camera consent flows and secure data handling (auto-pruning snapshots after 60 days).
- **Teacher Control**: Teachers always have the authority to override AI-generated scores and customize grading rubrics.
