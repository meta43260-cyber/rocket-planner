"""Browser API for the Rocket Planner's original flight-dynamics engine.

All vehicle inputs are expressed in the same units as the original Streamlit UI:
thrust in kN, altitude in km for target/fairing, and SI metres for site heights.
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
import booster as bst
import supabase_api

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Rocket Planner API", version="2.0.0",
              description="Rocket ascent, orbital mechanics, booster and observer-visibility simulator")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.include_router(supabase_api.router)


class StageInput(BaseModel):
    name: str = "Stage"
    # Sea-level values are optional only for upper stages that ignite in near-vacuum.
    thrust_sl: float | None = Field(default=None, gt=0, description="Sea-level thrust, kN; required for Stage 1")
    thrust_vac: float = Field(gt=0, description="Vacuum thrust, kN")
    isp_sl: float | None = Field(default=None, gt=0, description="Sea-level ISP; required for Stage 1")
    isp_vac: float = Field(gt=0)
    prop_mass: float = Field(gt=0, description="Propellant mass, kg")
    dry_mass: float = Field(ge=0, description="Dry mass, kg")
    burn_time: float = Field(gt=0, le=10000)
    area: float = Field(gt=0)
    ignition_delay: float = Field(default=0, ge=0, le=100000)


class BoosterInput(BaseModel):
    name: str = "SRB"
    count: int = Field(default=2, ge=1, le=12)
    thrust_sl: float = Field(gt=0)
    thrust_vac: float = Field(gt=0)
    isp_sl: float = Field(gt=0)
    isp_vac: float = Field(gt=0)
    prop_mass: float = Field(gt=0)
    dry_mass: float = Field(ge=0)
    burn_time: float = Field(gt=0, le=2000)
    area: float = Field(gt=0)
    ignite_t: float = Field(default=0, ge=0, le=100000)
    jettison_delay: float = Field(default=2, ge=0, le=300)


class TimelineStage(BaseModel):
    ignition_t: float = Field(ge=0, le=100000)
    cutoff_t: float = Field(gt=0, le=100000)
    separation_t: float = Field(ge=0, le=100000)


class TimelineInput(BaseModel):
    stages: list[TimelineStage] = Field(default_factory=list, max_length=5)
    fairing_t: float | None = Field(default=None, ge=0, le=100000)
    payload_t: float | None = Field(default=None, ge=0, le=100000)


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
    launch_azimuth_deg: float = Field(default=90, ge=0, le=360, description="Earth-fixed launch azimuth clockwise from true north")
    mission_type: str = "circular"
    launch_utc: datetime
    auto_profile: bool = True
    vertical_time: float = Field(default=10, ge=0, le=30)
    kick_angle: float = Field(default=6, ge=0, le=20)
    kick_duration: float = Field(default=12, ge=1, le=40)
    timestep: float = Field(default=0.05, ge=0.02, le=0.2)
    orbit_count: int = Field(default=3, ge=1, le=6)
    min_elevation: float = Field(default=5, ge=0, le=30)
    use_boost: bool = False
    boost_groups: list[BoosterInput] = Field(default_factory=list, max_length=4)
    boost_throttle: float = Field(default=100, ge=20, le=100)
    solo_throttle: float = Field(default=100, ge=50, le=100)
    boost_auto_burn: bool = True
    use_timeline: bool = False
    timeline: TimelineInput | None = None


def jd_from_datetime(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    fraction = (dt.hour + dt.minute / 60 + dt.second / 3600
                + dt.microsecond / 3.6e9) / 24
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + dt.day + b - 1524.5 + fraction


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
    view = df.iloc[::max(1, stride)]
    if columns:
        view = view[columns]
    return clean(view.to_dict(orient="records"))


def event_rows(ascent, fairing_t=None, payload_t=None, fairing_alt=110):
    events = []
    names = [n for n in ascent["stage"].dropna().unique() if n != "coast"]
    first = names[0] if names else None
    for name in names:
        subset = ascent[ascent["stage"] == name]
        powered = subset[subset["thrust_kN"] > 0.1]
        if name != first and not subset.empty:
            row = subset.iloc[0]
            events.append({"event": f"{name} — separation", "t": float(row.t),
                           "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
        if not powered.empty:
            row = powered.iloc[0]
            events.append({"event": f"{name} — ignition", "t": float(row.t),
                           "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
            row = powered.iloc[-1]
            events.append({"event": f"{name} — cutoff", "t": float(row.t),
                           "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
    if fairing_t is not None:
        row = ascent.iloc[(ascent["t"] - fairing_t).abs().idxmin()]
        events.append({"event": "Fairing jettison (timeline)", "t": float(row.t),
                       "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
    else:
        subset = ascent[ascent["alt_km"] >= fairing_alt]
        if not subset.empty:
            row = subset.iloc[0]
            events.append({"event": "Fairing jettison (altitude)", "t": float(row.t),
                           "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
    if payload_t is not None:
        row = ascent.iloc[(ascent["t"] - payload_t).abs().idxmin()]
        events.append({"event": "Payload deployment", "t": float(row.t),
                       "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
    row = ascent.loc[ascent["q_kPa"].idxmax()]
    events.append({"event": "Max-Q", "t": float(row.t),
                   "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
    return clean(sorted(events, key=lambda x: x["t"]))


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/admin")
def admin_home():
    return FileResponse(STATIC / "admin.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "rocket_planner", "version": app.version,
            "features": ["ascent", "orbit", "observer", "boosters", "timeline", "exports"]}


@app.post("/api/simulate")
def simulate(data: SimulationInput):
    if data.mission_type not in ("circular", "elliptical", "escape"):
        raise HTTPException(422, "mission_type must be circular, elliptical or escape")
    if data.use_boost and not data.boost_groups:
        raise HTTPException(422, "Add at least one booster group or disable Side Booster.")
    # Stage 1 starts at the launch site and therefore needs both sea-level values
    # for the initial TWR estimate. Upper stages may omit both only when they
    # ignite in near-vacuum; supplying just one is an inconsistent engine model.
    if data.stages[0].thrust_sl is None or data.stages[0].isp_sl is None:
        raise HTTPException(422, "Stage 1 requires both sea-level thrust and sea-level ISP.")
    for i, stage in enumerate(data.stages[1:], start=2):
        if (stage.thrust_sl is None) != (stage.isp_sl is None):
            raise HTTPException(422, f"Stage {i}: enter both sea-level thrust and ISP, or leave both blank.")
    if data.use_timeline:
        if not data.timeline or len(data.timeline.stages) != len(data.stages):
            raise HTTPException(422, "Timeline must contain one event row for every original core stage.")
        previous_sep = -1.0
        for i, row in enumerate(data.timeline.stages):
            if row.cutoff_t <= row.ignition_t or row.separation_t < row.cutoff_t:
                raise HTTPException(422, f"Invalid ignition/cutoff/separation times for stage {i + 1}.")
            if i and row.ignition_t < previous_sep and not (data.use_boost and i == 0):
                raise HTTPException(422, f"Stage {i + 1} ignition precedes previous stage separation.")
            previous_sep = row.separation_t
    try:
        launch_jd = jd_from_datetime(data.launch_utc)
        original = [s.model_dump() if hasattr(s, "model_dump") else s.dict() for s in data.stages]
        stages_cfg = [dict(s) for s in original]
        boost_log = []
        boost_warnings = []
        if data.use_boost:
            core = stages_cfg[0]
            groups = [bst.make_group(g.name, g.count, g.thrust_sl, g.thrust_vac,
                      g.isp_sl, g.isp_vac, g.prop_mass, g.dry_mass, g.burn_time,
                      g.area, g.ignite_t, g.jettison_delay) for g in data.boost_groups]
            phases, boost_log = bst.build_boost_phases(
                core, groups, data.boost_throttle, data.solo_throttle, data.boost_auto_burn)
            boost_warnings = bst.validate(core, groups, phases)
            stages_cfg = phases + stages_cfg[1:]

        fair_t = payload_t = None
        max_time = 2500.0
        if data.use_timeline and data.timeline:
            rows = data.timeline.stages
            for i, row in enumerate(rows):
                if data.use_boost and i == 0:
                    continue
                index = len(stages_cfg) - len(original) + i if data.use_boost else i
                if index < 0 or index >= len(stages_cfg):
                    continue
                stage = stages_cfg[index]
                stage["burn_time"] = max(row.cutoff_t - row.ignition_t, 0.1)
                if i > 0:
                    prev_sep = rows[i - 1].separation_t
                    stage["ignition_delay"] = max(row.ignition_t - prev_sep, 0.0)
            fair_t = data.timeline.fairing_t
            payload_t = data.timeline.payload_t
            if payload_t is not None:
                max_time = max(max_time, payload_t + 1800.0)

        stages = [rp.Stage(
            s.get("name", f"Stage {i + 1}"),
            s["thrust_sl"] * 1000 if s.get("thrust_sl") is not None else None,
            s["thrust_vac"] * 1000,
            s.get("isp_sl"), s["isp_vac"],
            s["prop_mass"], s["dry_mass"], s["burn_time"], s["area"],
            float(s.get("ignition_delay", 0.0))
        ) for i, s in enumerate(stages_cfg)]
        vehicle = rp.Vehicle(
            stages=stages, payload=data.payload, fairing_mass=data.fairing_mass,
            fairing_jettison_alt=data.fairing_alt * 1000,
            fairing_jettison_t=fair_t, payload_deploy_t=payload_t
        )
        mission = rp.Mission(
            site_lat=data.site_lat, site_lon=data.site_lon, site_alt=data.site_alt,
            target_alt=data.target_alt * 1000, launch_azimuth_deg=data.launch_azimuth_deg,
            launch_jd=launch_jd, vertical_time=data.vertical_time,
            kick_angle=data.kick_angle, kick_duration=data.kick_duration,
            mission_type=data.mission_type,
            target_apogee_alt=(data.target_apogee_alt if data.mission_type != "circular"
                               else data.target_alt) * 1000,
            auto_profile=data.auto_profile
        )
        ascent, state, t_end, theta0, azimuth = rp.simulate_ascent(
            vehicle, mission, dt=data.timestep, dt_out=0.5,
            max_time=max_time, verbose=False
        )
        if ascent.empty:
            raise ValueError("The ascent simulation returned no trajectory points.")
        orbit_state, t_insert, delta_v = rp.coast_and_circularize(
            state, t_end, mission.target_alt,
            mission_type=data.mission_type, verbose=False
        )
        elements = rp.orbital_elements(orbit_state[0:3], orbit_state[3:6])
        if elements["e"] >= 1.0 or not math.isfinite(elements["period_min"]):
            duration = 6 * 3600.0
        else:
            duration = data.orbit_count * elements["period_min"] * 60.0
        orbit = rp.propagate_orbit(orbit_state, t_insert, theta0, duration=duration, dt=15)
        look = rp.look_angles(ascent, data.obs_lat, data.obs_lon, data.obs_alt,
                              launch_jd, theta0)
        visible = look[look["el_deg"] > data.min_elevation]
        first = visible.iloc[0].to_dict() if not visible.empty else None
        peak = visible.loc[visible["el_deg"].idxmax()].to_dict() if not visible.empty else None
        closest = visible.loc[visible["range_km"].idxmin()].to_dict() if not visible.empty else None
        last = visible.iloc[-1].to_dict() if not visible.empty else None
        profile = rp.auto_ascent_profile(vehicle, mission) if data.auto_profile else (
            data.vertical_time, data.kick_angle, data.kick_duration)
        summary = {
            "gross_mass_kg": vehicle.gross_mass(), "meco_s": t_end,
            "max_q_kpa": float(ascent["q_kPa"].max()),
            "max_q_time_s": float(ascent.loc[ascent["q_kPa"].idxmax(), "t"]),
            "max_g": float(ascent["acc_g"].max()),
            "azimuth_rotating_deg": azimuth[0], "azimuth_inertial_deg": azimuth[1],
            "earth_rotation_bonus_mps": azimuth[2], "delta_v_mps": delta_v,
            "visible_duration_s": float(last["t"] - first["t"]) if first and last else 0.0,
            "sunlit_percent": float(visible["rocket_sunlit"].mean() * 100) if not visible.empty else 0.0,
            "photo_window_percent": float(visible["photo_window"].mean() * 100) if not visible.empty else 0.0,
            "visible_count": int(len(visible)),
        }
        return clean({
            "summary": summary, "elements": elements, "profile": profile,
            "visibility": {"first": first, "peak": peak, "closest": closest,
                           "last": last, "count": len(visible)},
            "ascent": records(ascent, ["t","lat","lon","alt_km","v_inertial",
                "v_relative","mach","q_kPa","fpa_deg","mass","thrust_kN","acc_g","stage"]),
            "orbit": records(orbit, ["t","lat","lon","alt_km"]),
            "look": records(look, ["t","az_deg","el_deg","range_km","alt_km",
                "sun_el_deg","rocket_sunlit","photo_window","angular_rate"]),
            "events": event_rows(ascent, fair_t, payload_t, data.fairing_alt),
            "boost_log": boost_log, "boost_warnings": boost_warnings,
            "report": rp.photo_report(look, data.min_elevation),
            "launch_utc": data.launch_utc.isoformat(),
            "parameters": {"site_lat": data.site_lat, "site_lon": data.site_lon,
                "site_alt": data.site_alt, "obs_lat": data.obs_lat,
                "obs_lon": data.obs_lon, "obs_alt": data.obs_alt,
                "mission_type": data.mission_type, "target_alt_km": data.target_alt,
                "target_apogee_alt_km": data.target_apogee_alt,
                "launch_azimuth_deg": data.launch_azimuth_deg}
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Simulation failed: {exc}") from exc
