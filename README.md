# Rocket Planner

Rocket Ascent & Observation Planner: a browser-based interface backed by the existing Python flight-dynamics engine.

## Run locally

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000. API health: http://localhost:8000/api/health.

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, choose **New + → Blueprint**.
3. Select this repository and deploy the detected `render.yaml`.
4. Open the generated `onrender.com` URL.

The Dockerfile starts FastAPI; Streamlit is no longer required for the web version.

## API

- `GET /api/health` — service health.
- `POST /api/simulate` — run ascent, orbit propagation and observer look-angle analysis.

## Model limitations

This is a simplified numerical mission-design model, not a launch-provider trajectory feed. Default stage data are illustrative presets. Real launch predictions require confirmed vehicle performance, flight events, guidance profile, launch epoch and trajectory/orbit data. Visibility and sunlight estimates inherit the assumptions and approximations of the underlying engine.

## Legacy Streamlit interface

The original `app.py` is retained for reference. The browser version is started with Uvicorn and does not import or require Streamlit.
