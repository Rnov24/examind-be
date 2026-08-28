# EXAMIND Backend (`backend/`)

FastAPI backend service for the EXAMIND AI Examination Platform.

## Requirements
- Python 3.10+
- MySQL (running via XAMPP on port 3306)

## Setup

1. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env to verify your MySQL connection (default XAMPP: root with no password)
   ```

4. **Run the development server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

   Interactive API docs:
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
