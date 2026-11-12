"""FastAPI web backend for Rocket Planner.

The original Streamlit UI remains available as a legacy entry point, while this
module exposes the existing orbital/flight mechanics engine to a browser UI.
"""
from datetime import datetime, timezone
from pathlib import Path
import math

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import rocket_planner as rp

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Rocket Planner API", version="1.0.0",
              description="Rocket ascent, orbit and observer-visibility simulator")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class StageInput(BaseModel):
    name: str = "Stage"
    thrust_sl: float = Field(gt=0, description="Sea-level thrust, kN")
    thrust_vac: float = Field(gt=0, description="Vacuum thrust, kN")
    isp_sl: float = Field(gt=0)
    isp_vac: float = Field(gt=0)
    prop_mass: float = Field(gt=0, description="Propellant mass, kg")
    dry_mass: float = Field(ge=0, description="Dry mass, kg")
    burn_time: float = Field(gt=0, le=2000)
    area: float = Field(gt=0)
    ignition_delay: float = Field(default=0, ge=0, le=7200)


class SimulationInput(BaseModel):
    stages: list[StageInput] = Field(min_length=1, max_length=5)
    payload: float = Field(default=0, ge=0)
    fairing_mass: float = Field(default=0, ge=0)
    fairing_alt: float = Field(default=110, ge=40, le=200)
    site_lat: float = Field(ge=-90, le=90)
    site_lon: float = Field(ge=-180, le=180)
    site_alt: float = Field(default=0, ge=-500, le=5000)
    obs_lat: float = Field(ge=-90, le=90)
    obs_lon: float = Field(ge=-180, le=180)
    obs_alt: float = Field(default=0, ge=-500, le=5000)
    target_alt: float = Field(default=550, ge=120, le=2000)
    target_apogee_alt: float = Field(default=35786, ge=120, le=1000000)
    target_inc: float = Field(default=53, ge=0, le=180)
    mission_type: str = "circular"
    launch_utc: datetime
    ascend_east: bool = True
    auto_profile: bool = True
    vertical_time: float = Field(default=10, ge=0, le=30)
    kick_angle: float = Field(default=6, ge=0, le=20)
    kick_duration: float = Field(default=12, ge=1, le=40)
    min_elevation: float = Field(default=5, ge=0, le=30)
    timestep: float = Field(default=0.1, ge=0.02, le=0.2)
    orbit_count: int = Field(default=2, ge=1, le=6)


def jd_from_datetime(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    day_fraction = (dt.hour + dt.minute / 60 + dt.second / 3600
                    + dt.microsecond / 3.6e9) / 24
    return (int(365.25 * (y + 4716)) + int(30.6001 * (m + 1))
            + dt.day + b - 1524.5 + day_fraction)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    return value


def records(df, columns=None, stride=1):
    if df is None or df.empty:
        return []
    view = df.iloc[::stride]
    if columns:
        view = view[columns]
    return clean(view.replace({np.nan: None}).to_dict(orient="records"))


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "rocket_planner", "version": app.version}


@app.post("/api/simulate")
def simulate(data: SimulationInput):
    if data.mission_type not in ("circular", "elliptical", "escape"):
        raise HTTPException(422, "mission_type must be circular, elliptical or escape")
    try:
        launch_jd = jd_from_datetime(data.launch_utc)
        stages = [rp.Stage(
            s.name, s.thrust_sl * 1000, s.thrust_vac * 1000,
            s.isp_sl, s.isp_vac, s.prop_mass, s.dry_mass,
            s.burn_time, s.area, s.ignition_delay
        ) for s in data.stages]
        vehicle = rp.Vehicle(
            stages=stages, payload=data.payload, fairing_mass=data.fairing_mass,
            fairing_jettison_alt=data.fairing_alt * 1000
        )
        mission = rp.Mission(
            site_lat=data.site_lat, site_lon=data.site_lon, site_alt=data.site_alt,
            target_alt=data.target_alt * 1000, target_inc=data.target_inc,
            launch_jd=launch_jd, vertical_time=data.vertical_time,
            kick_angle=data.kick_angle, kick_duration=data.kick_duration,
            ascend_east=data.ascend_east, mission_type=data.mission_type,
            target_apogee_alt=(data.target_apogee_alt if data.mission_type != "circular"
                               else data.target_alt) * 1000,
            auto_profile=data.auto_profile
        )
        ascent, state, t_end, theta0, azimuth = rp.simulate_ascent(
            vehicle, mission, dt=data.timestep, dt_out=1.0,
            max_time=2500.0, verbose=False
        )
        if ascent.empty:
            raise ValueError("The ascent simulation returned no trajectory points.")
        orbit_state, t_insert, delta_v = rp.coast_and_circularize(
            state, t_end, mission.target_alt,
            mission_type=data.mission_type, verbose=False
        )
        elements = rp.orbital_elements(orbit_state[0:3], orbit_state[3:6])
        duration = (6 * 3600 if elements["e"] >= 1 else
                    data.orbit_count * elements["period_min"] * 60)
        orbit = rp.propagate_orbit(orbit_state, t_insert, theta0,
                                   duration=duration, dt=30)
        look = rp.look_angles(ascent, data.obs_lat, data.obs_lon,
                              data.obs_alt, launch_jd, theta0)
        visible = look[look["el_deg"] >= data.min_elevation]
        first = visible.iloc[0].to_dict() if not visible.empty else None
        peak = visible.loc[visible["el_deg"].idxmax()].to_dict() if not visible.empty else None
        closest = visible.loc[visible["range_km"].idxmin()].to_dict() if not visible.empty else None
        last = visible.iloc[-1].to_dict() if not visible.empty else None
        return clean({
            "summary": {
                "gross_mass_kg": vehicle.gross_mass(),
                "meco_s": t_end,
                "max_q_kpa": float(ascent["q_kPa"].max()),
                "max_q_time_s": float(ascent.loc[ascent["q_kPa"].idxmax(), "t"]),
                "max_g": float(ascent["acc_g"].max()),
                "azimuth_rotating_deg": azimuth[0],
                "azimuth_inertial_deg": azimuth[1],
                "earth_rotation_bonus_mps": azimuth[2],
                "delta_v_mps": delta_v,
                "visible_duration_s": (float(last["t"] - first["t"])
                                       if first and last else 0),
                "photo_window_percent": (float(visible["photo_window"].mean() * 100)
                                         if not visible.empty else 0),
            },
            "elements": elements,
            "visibility": {"first": first, "peak": peak, "closest": closest,
                           "last": last, "count": len(visible)},
            "ascent": records(ascent, ["t","lat","lon","alt_km","v_inertial",
                "v_relative","mach","q_kPa","fpa_deg","mass","thrust_kN","acc_g","stage"], 2),
            "orbit": records(orbit, ["t","lat","lon","alt_km"], 2),
            "look": records(look, ["t","az_deg","el_deg","range_km","alt_km",
                "sun_el_deg","rocket_sunlit","photo_window","angular_rate"], 2),
            "report": rp.photo_report(look, data.min_elevation),
            "launch_utc": data.launch_utc.isoformat()
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Simulation failed: {exc}") from exc
