# Rocket Planner

A browser-based rocket ascent, orbital mechanics and observer-visibility planner, powered by the repository's original Python numerical engine.

## Features

- Multi-stage vehicle configuration (1–5 stages) and editable JSON presets
- Falcon 9, Electron, GSLV Mk II and custom launcher example presets
- Side/strap-on booster groups, staggered ignition and delayed jettison
- Automatic ascent profile or manually specified vertical/kick profile
- Circular, elliptical and escape trajectory modes
- Mission timeline input for stage ignition, cutoff, separation, fairing jettison and payload deployment
- Numerical ascent profile: altitude, velocity, Mach, dynamic pressure, flight-path angle and acceleration
- J2 orbital propagation and interactive Leaflet ground track
- Observer azimuth/elevation, range, angular rate, rocket illumination and twilight photo-window estimate
- Sky polar plot, flight event table, look-angle table
- CSV, KML, orbital-elements JSON, observation-report TXT and preset JSON export/import
- Responsive Thai/English interface for Android and desktop

## Run locally

Python 3.10+:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000. API documentation is available at http://localhost:8000/docs and health at http://localhost:8000/api/health.

## Deploy on Render

1. Push/merge the web-app branch to the repository's default branch.
2. In Render, choose **New + → Blueprint**.
3. Select this GitHub repository and deploy the detected `render.yaml`.
4. Open the generated `onrender.com` URL.

The Dockerfile runs FastAPI/Uvicorn. Streamlit is not required to run the browser app. The original `app.py` remains in the repository as a legacy interface/reference.

## API

- `GET /api/health` — service health and feature list.
- `POST /api/simulate` — ascent, orbit, booster, mission-timeline and observer calculations.

The API request uses kN for thrust, kg for masses, km for target/fairing altitudes, metres for site/observer elevations, seconds for event times, degrees for angular values, and an ISO-8601 UTC launch epoch. See the browser form or OpenAPI schema for the full request shape.

## Important scientific limitations

This is a numerical planning/educational model, not a launch-provider trajectory feed or operational flight dynamics system. Vehicle preset data are illustrative and simplified; they are not certified current performance specifications. Actual plume visibility and rocket-body visibility depend on confirmed vehicle configuration, guidance, launch epoch, event timing, attitude, trajectory, atmospheric conditions, terrain/horizon obstruction and solar geometry. The illumination/photo-window calculation inherits the assumptions and approximations of the underlying engine. Validate results against authoritative mission data before using them to plan an observation.
