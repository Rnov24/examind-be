# examind-be — EXAMIND Backend

> FastAPI + SQLAlchemy 2.0 backend for the EXAMIND AI-Powered Online Examination Platform (Sistem Ujian Online Berbasis AI).

Companion repo: [Rnov24/examind-fe](https://github.com/Rnov24/examind-fe) (Vue 3 frontend). Split from the original `Rnov24/examind` monorepo on 2026-10-16.

## Tech stack

- **FastAPI** + Pydantic v2, served by **uvicorn** on port **8000** (`/docs` → Swagger, `/redoc` → ReDoc)
- **SQLAlchemy 2.0** + **Alembic** migrations, **MySQL via XAMPP** (port 3306)
- **PyTorch** models for local CV/ML serving (proctoring), modular LLM adapters (Gemini/OpenAI) for question generation & essay grading
- **Secret Manager** (`app/core/secret_manager.py`) — Fernet-encrypted secrets in the DB
- WebSockets for realtime proctoring events; CORS configured for the Vue 3 frontend origin
- API modules: `auth`, `questions`, `ai` (question generator), `exams`, `student_exam`, `grading` (essay AI + teacher override), `proctoring` (+ WS), `analytics`, `admin`, `superadmin`, `academic`

## Requirements

- Python 3.10+
- MySQL running via XAMPP on port 3306

## Setup

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env      # edit DB credentials if needed (default XAMPP: root, no password)
```

## Database

```bash
# 1. Create schema
mysql -u root < database/schema.sql
# 2. Run migrations
mysql -u root examind < database/migrations/secret_manager_migration.sql
mysql -u root examind < database/migrations/saas_migration.sql
mysql -u root examind < database/migrations/email_verification_migration.sql
# 3. Seed initial data
mysql -u root examind < database/seeds/01_initial_seeds.sql
# (optional) python seed_data.py
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Tests & lint

```bash
pytest
ruff check .
```

## One-click launch (Windows)

`scripts/start_examind.bat` starts MySQL (XAMPP), this backend and the Vue dev server, assuming both repos are cloned side by side:

```
<parent>/
├── examind-fe/
└── examind-be/
```

`scripts/stop_examind.bat` stops everything.

## Docs

- Architecture & guardrails: [`GEMINI.md`](./GEMINI.md)
- API: [`docs/API_SPECIFICATION.md`](./docs/API_SPECIFICATION.md)
- AI features: [`docs/AI_SPECIFICATION.md`](./docs/AI_SPECIFICATION.md)
- Product/specs/tickets: [`docs/`](./docs)
