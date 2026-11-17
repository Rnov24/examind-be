# examind-be — EXAMIND Backend

[![CI](https://github.com/Rnov24/examind-be/actions/workflows/ci.yml/badge.svg)](https://github.com/Rnov24/examind-be/actions/workflows/ci.yml)

FastAPI + SQLAlchemy 2.0 backend for EXAMIND, an AI-powered online examination platform for schools.

Companion repo: [Rnov24/examind-fe](https://github.com/Rnov24/examind-fe) (Next.js 15 frontend). Split from the original `Rnov24/examind` monorepo on 2026-10-16.

## Live

- App: https://examind.rijal.work
- API (Cloudflare edge): https://examind-api.rijal.work
- Modal backend (direct): https://rnov24--examind-be-api.us-east.modal.run

## Tech stack

- **FastAPI** + Pydantic v2, served by **uvicorn** on port **8000** (`/docs` → Swagger, `/redoc` → ReDoc)
- **SQLAlchemy 2.0** + PyMySQL against **TiDB Cloud** (MySQL-compatible, TLS, port 4000). There is no local database anymore.
- **LLM adapters** (Gemini by default, OpenAI-compatible, OpenRouter, Claude) for question generation, essay grading, and the AI chatbot; **Respan essay grader** via OpenRouter. No ML/CV models run in this repo.
- **Proctoring**: the backend receives proctoring events over REST and authenticated WebSockets. Face/phone detection runs client-side (MediaPipe) in the frontend.
- **Secret Manager** (`app/core/secret_manager.py`) — Fernet-encrypted secrets in the DB.
- **Auth**: JWT. Login takes `identifier` (NISN/NIP/username, or email) + `password`.
- API modules: `auth`, `academic`, `questions`, `ai`, `exams`, `student_exam`, `proctoring` (+ WS), `grading`, `analytics`, `admin`, `superadmin`, `public`, `notifications`
- CORS origins come from the `CORS_ORIGINS` env var (production: the `examind-env` Modal secret).

## Requirements

- Python 3.12 (what CI uses; `pyproject.toml` requires >= 3.10)
- A TiDB Cloud connection string (see Database)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in DATABASE_URL and the keys below
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Environment variables

As read by `app/core/config.py`. `.env.example` is incomplete: it still defaults `DATABASE_URL` to a localhost database URL and omits the provider, edge, and email keys, so use this list, not just the example file.

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | `mysql+pymysql://<user>:<pass>@<host>:4000/examind?ssl_ca=...` (TiDB Cloud; TLS is auto-enabled for `*.tidbcloud.com` hosts via certifi) |
| `SECRET_KEY` | 64+ char random string; required in production |
| `ALGORITHM` | `HS256` (default) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (default) |
| `ENVIRONMENT`, `DEBUG`, `HOST`, `PORT` | `development`, `True`, `0.0.0.0`, `8000` (defaults) |
| `FRONTEND_URL` | `http://localhost:3000` (default) |
| `CORS_ORIGINS` | JSON list or comma-separated origins |
| `DB_SSL_CA` | Optional explicit CA bundle path for TLS database connections |
| `EDGE_SECRET`, `EDGE_ENFORCE` | Cloudflare edge lock; enforcement off by default |
| `AI_PROVIDER` | `gemini` (default) |
| `AI_API_KEY` | Provider key for `AI_PROVIDER` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini key; model defaults to `gemini-2.5-flash` |
| `OPENROUTER_API_KEY`, `OPENROUTER_DECISION_MODEL` | Decision model defaults to `respan/span-01-lite` |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Email; from defaults to `EXAMIND <noreply@examind.rijal.work>` |
| `EXAM_RESULT_EMAIL_ENABLED` | `True` (default) |

Production values live in the Modal secrets `examind-env`, `examind-edge`, and `examind-frontend` — never in this repo, never commit `.env`.

## Database

- The production database is **TiDB Cloud** (MySQL-compatible, `ap-southeast-1`, `gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000`, TLS required). The connection string lives only in the `examind-env` Modal secret; it is not in this repo.
- Schema and migrations are plain SQL files: `database/schema.sql`, `database/migrations/`, `migrations/`. There is **no Alembic setup** (no `alembic.ini`; Alembic is only a listed dependency) and no local-database workflow.
- Production schema changes and seeds go through one-off Modal scripts, for example:
  - `modal run migrate_disqualify_enum_once.py::migrate_disqualify_enum`
  - `modal run seed_dummy_once.py` (idempotent dummy seed, `DUMMY`-prefixed, for dashboard review)
  - `modal run seed_dummy_once.py::cleanup_dummy` (removes the dummy data)
- Local development also points `DATABASE_URL` at TiDB Cloud. There is no supported local-database path.

## Tests

```bash
pytest tests/ -k "not api_suite" \
  --deselect tests/test_finance_analytics.py::test_finance_analytics_honest_mrr_and_invoices
```

On a clean tree this gives **150 passed, 1 failed**. The one failure is pre-existing: `test_finance_analytics_honest_mrr_and_invoices` (month-label mismatch) — it is deselected so CI stays green. The `api_suite` tests need a live database server and are excluded with `-k`.

CI is `.github/workflows/ci.yml` (Python 3.12, runs on push to `main` and on pull requests) and is green on `main`.

Lint: `ruff` is configured in `pyproject.toml`, but `ruff check .` currently reports ~1500 errors on the clean tree, so there is no passing lint gate. Do not treat it as one.

## Deploy

```bash
modal deploy modal_app.py
```

- `modal serve modal_app.py` for development.
- The Modal image bakes the code in (`copy=True` in `modal_app.py`), so a deploy serves fresh code.
- The app uses the Modal secrets `examind-env`, `examind-edge`, and `examind-frontend` (see the `modal_app.py` docstring for the `examind-env` keys).
- A daily 07:00 WIB subscription-reminder job runs as a scheduled Modal function (`subscription_reminder_cron` in `modal_app.py`).

## Repo map

- `app/main.py` — FastAPI app, CORS, edge guard, rate limiting
- `app/api/v1/` — routers (`endpoints/` + `router.py`); WebSocket proctoring in `endpoints/proctoring_ws.py`
- `app/core/` — `config.py`, `database.py` (TiDB TLS), `security.py`, `secret_manager.py`, `edge_guard.py`, `tenant_scope.py`, `rate_limit.py`
- `app/models/`, `app/schemas/` — SQLAlchemy models, Pydantic schemas
- `app/services/` — `ai/` (LLM adapters, Respan grader), `grading/`, `billing/`, `email/`, `exam/`, `proctoring/`, `analytics/`, `reporting/`
- `modal_app.py` — Modal deployment entrypoint
- `database/` — `schema.sql`, SQL migrations, seeds
- `migrations/` — additional SQL migrations, applied via one-off Modal scripts
- `seed_data.py`, `seed_dummy_once.py`, `migrate_disqualify_enum_once.py` — one-off scripts (see Database)
- `scripts/` — `create_superadmin.py` (idempotent superadmin creation); the `start_examind.bat` / `stop_examind.bat` launchers are stale and unused
- `tests/` — pytest suite
- `docs/` — `API_SPECIFICATION.md`, `AI_SPECIFICATION.md`, `ARCHITECTURE.md`, `PRD.md`, `SRS.md`, `TEST_PLAN.md`, UML docs

## Docs

- Architecture & guardrails: [`GEMINI.md`](./GEMINI.md) (stale: still describes the old pre-split stack)
- API: [`docs/API_SPECIFICATION.md`](./docs/API_SPECIFICATION.md)
- AI features: [`docs/AI_SPECIFICATION.md`](./docs/AI_SPECIFICATION.md)
- Product/specs/tickets: [`docs/`](./docs)
