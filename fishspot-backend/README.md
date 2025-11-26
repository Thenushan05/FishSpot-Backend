# FishSpot Backend (scaffold)

This folder contains a minimal scaffold of a FastAPI backend for the Fish Hotspot Prediction project.

Quick start (Windows PowerShell)

1. Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and edit values if needed

```powershell
cp .env.example .env
```

4. Start development server (FastAPI + Swagger UI)

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger UI at: `http://127.0.0.1:8000/docs`

Notes:

- Installing `xgboost` can take time on Windows; it is optional if you use mock predictions.
- The scaffold includes `app/api/v1/agent.py` and services; extend other endpoints (auth, trips, hotspots) as needed.
