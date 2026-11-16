"""Browser API for the Rocket Planner's original flight-dynamics engine.

All vehicle inputs are expressed in the same units as the original Streamlit UI:
thrust in kN, altitude in km for target/fairing, and SI metres for site heights.
"""
from datetime import datetime, timezone
from pathlib import Path
import math

import numpy as np
import pandas as pd
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
    # Stage 1 needs sea-level thrust for liftoff TWR; missing ISP SL is explicitly approximated.
    thrust_sl: float | None = Field(default=None, gt=0, description="Sea-level thrust, kN; required for Stage 1")
    thrust_vac: float = Field(gt=0, description="Vacuum thrust, kN")
    isp_sl: float | None = Field(default=None, gt=0, description="Sea-level ISP; optional, vacuum ISP fallback is warned")
    isp_vac: float = Field(gt=0)
    prop_mass: float = Field(gt=0, description="Propellant mass, kg")
    dry_mass: float = Field(ge=0, description="Dry mass, kg")
    burn_time: float = Field(gt=0, le=10000)
    area: float = Field(gt=0)
    ignition_delay: float = Field(default=0, ge=0, le=100000)
    # Vacuum thrust curve: [[powered_time_s, thrust_kN], ...]
    thrust_curve: list[tuple[float, float]] | None = Field(default=None, max_length=1000)


class BoosterInput(BaseModel):
    name: str = "SRB"
    count: int = Field(default=2, ge=1, le=12)
    # Optional for solid boosters when manufacturer sea-level data is unpublished.
    # If omitted, booster.py uses vacuum values as an explicit approximation and warns.
    thrust_sl: float | None = Field(default=None, gt=0)
    thrust_vac: float = Field(gt=0)
    isp_sl: float | None = Field(default=None, gt=0)
    isp_vac: float = Field(gt=0)
    prop_mass: float = Field(gt=0)
    dry_mass: float = Field(ge=0)
    burn_time: float = Field(gt=0, le=2000)
    area: float = Field(gt=0)
    ignite_t: float = Field(default=0, ge=0, le=100000)
    jettison_delay: float = Field(default=2, ge=0, le=300)
    thrust_curve: list[tuple[float, float]] | None = Field(default=None, max_length=1000)


class TimelineBurn(BaseModel):
    ignition_t: float = Field(ge=0, le=100000)
    cutoff_t: float = Field(gt=0, le=100000)


class TimelineStage(BaseModel):
    # Legacy single-burn fields remain accepted for existing saved timelines.
    ignition_t: float | None = Field(default=None, ge=0, le=100000)
    cutoff_t: float | None = Field(default=None, gt=0, le=100000)
    separation_t: float = Field(ge=0, le=100000)
    # Multiple ignition/cutoff pairs for restartable stages.
    burns: list[TimelineBurn] = Field(default_factory=list, max_length=10)


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
    target_alt: float = Field(default=550, ge=120, le=1000000,
                              description="Target orbit altitude or elliptical perigee, km")
    target_apogee_alt: float = Field(default=35786, ge=120, le=1000000)
    launch_azimuth_deg: float = Field(default=75.3, ge=0, le=360, description="Preferred Earth-fixed launch azimuth clockwise from true north")
    target_inclination_deg: float | None = Field(default=None, ge=0, le=180)
    target_raan_deg: float | None = Field(default=None, ge=0, lt=360)
    target_c3_km2_s2: float = Field(default=0.0, ge=0, le=1000,
                                    description="Required Earth-relative characteristic energy for escape")
    trajectory_duration_s: float = Field(default=86400, ge=3600, le=2592000)
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


def _apply_boost_core_timeline(phases, boost_log, timeline_stage):
    """Apply the original core-stage cutoff/separation to the final core-only boost phase."""
    windows = timeline_stage.burns or [
        TimelineBurn(ignition_t=timeline_stage.ignition_t,
                     cutoff_t=timeline_stage.cutoff_t)
    ]
    if len(windows) != 1:
        raise HTTPException(
            422, "With Side Booster enabled, the LLPM timeline must contain one continuous burn."
        )
    if not phases or len(phases) != len(boost_log):
        raise HTTPException(422, "Unable to map LLPM timeline to booster phases.")
    final_phase = phases[-1]
    phase_info = boost_log[-1]
    phase_start = float(phase_info["t0"])
    phase_end = float(phase_info["t1"])
    cutoff = float(windows[0].cutoff_t)
    separation = float(timeline_stage.separation_t)
    if cutoff <= phase_start or cutoff > phase_end + 1e-6:
        raise HTTPException(
            422,
            f"LLPM cutoff T+{cutoff:g}s is outside the final core phase "
            f"(T+{phase_start:g} to T+{phase_end:g}s)."
        )
    if separation < cutoff:
        raise HTTPException(422, "LLPM separation cannot precede its cutoff.")
    # burn_windows are absolute T+ times. Propellant allocated to the full
    # phase remains aboard until separation; any unburned remainder is dropped
    # with the core stage at separation_t.
    final_phase["burn_windows"] = [(phase_start, cutoff)]
    final_phase["burn_time"] = cutoff - phase_start
    final_phase["separation_t"] = separation


def _curve_points(value):
    """Normalize an optional thrust curve from API input for the engine."""
    return [(float(point[0]), float(point[1])) for point in (value or [])] or None


def _validate_thrust_curve(points, label):
    """Allow a zero-thrust ignition point only at t=0; later points must be positive."""
    if len(points) < 2 or points[0][0] != 0:
        raise HTTPException(422, f"{label}: thrust curve needs at least two points and must start at 0 seconds.")
    if any(t < 0 or thrust < 0 or (i > 0 and thrust <= 0)
           for i, (t, thrust) in enumerate(points)):
        raise HTTPException(422, f"{label}: only the first thrust-curve point may be zero; times must be non-negative.")
    if any(points[i][0] >= points[i + 1][0] for i in range(len(points) - 1)):
        raise HTTPException(422, f"{label}: thrust-curve times must be strictly increasing.")


def _visibility_trajectory(ascent, orbit):
    """Join ascent and propagated orbit states on the same launch-relative time axis."""
    frames = [frame for frame in (ascent, orbit) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    return (pd.concat(frames, ignore_index=True)
            .sort_values("t")
            .drop_duplicates(subset=["t"], keep="last")
            .reset_index(drop=True))


def _sampled_visible_duration(look, min_elevation):
    """Sum adjacent sampled intervals that are both above the visibility threshold."""
    if look is None or len(look) < 2:
        return 0.0
    times = look["t"].to_numpy(dtype=float)
    visible = look["el_deg"].to_numpy(dtype=float) > float(min_elevation)
    intervals = np.diff(times)
    return float(intervals[visible[:-1] & visible[1:]].sum())


def event_rows(ascent, fairing_t=None, payload_t=None, fairing_alt=110,
               timeline_stages=None, timeline_has_boosters=False):
    events = []
    names = [n for n in ascent["stage"].dropna().unique() if n != "coast"]
    first = names[0] if names else None

    def add_event(label, t_event):
        if float(t_event) > float(ascent["t"].iloc[-1]) + 1e-9:
            return
        row = ascent.iloc[(ascent["t"] - float(t_event)).abs().idxmin()]
        events.append({"event": label, "t": float(t_event),
                       "alt_km": float(row.alt_km),
                       "velocity_mps": float(row.v_relative)})

    for name in names:
        subset = ascent[ascent["stage"] == name]
        if timeline_stages is None:
            powered = subset[subset["thrust_kN"] > 0.1].copy()
            if name != first and not subset.empty:
                row = subset.iloc[0]
                events.append({"event": f"{name} — separation", "t": float(row.t),
                               "alt_km": float(row.alt_km), "velocity_mps": float(row.v_relative)})
            if not powered.empty:
                # A gap in powered samples marks a cutoff/coast/restart sequence.
                powered = powered.sort_values("t")
                segment_ids = powered["t"].diff().fillna(0).gt(0.75).cumsum()
                segments = list(powered.groupby(segment_ids))
                for number, (_, segment) in enumerate(segments, start=1):
                    first_row, last_row = segment.iloc[0], segment.iloc[-1]
                    suffix = "" if len(segments) == 1 else f" #{number}"
                    events.append({"event": f"{name} — ignition{suffix}",
                                   "t": float(first_row.t), "alt_km": float(first_row.alt_km),
                                   "velocity_mps": float(first_row.v_relative)})
                    events.append({"event": f"{name} — cutoff{suffix}",
                                   "t": float(last_row.t), "alt_km": float(last_row.alt_km),
                                   "velocity_mps": float(last_row.v_relative)})

    if timeline_stages is not None:
        for i, timeline_stage in enumerate(timeline_stages):
            if timeline_has_boosters and i == 0:
                continue
            burns = timeline_stage.burns or [
                TimelineBurn(ignition_t=timeline_stage.ignition_t,
                             cutoff_t=timeline_stage.cutoff_t)
            ]
            for number, burn in enumerate(burns, start=1):
                suffix = f" #{number}" if len(burns) > 1 else ""
                add_event(f"Stage {i + 1} — ignition{suffix}", burn.ignition_t)
                add_event(f"Stage {i + 1} — cutoff{suffix}", burn.cutoff_t)
            add_event(f"Stage {i + 1} — separation (timeline)",
                      timeline_stage.separation_t)
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
    if data.mission_type == "elliptical" and data.target_apogee_alt <= data.target_alt:
        raise HTTPException(422, "Elliptical orbit requires apogee altitude greater than perigee altitude.")
    if data.target_raan_deg is not None and data.target_inclination_deg is None:
        raise HTTPException(422, "Set target inclination when specifying a target RAAN.")
    if data.use_boost and not data.boost_groups:
        raise HTTPException(422, "Add at least one booster group or disable Side Booster.")
    # Liftoff TWR needs a sea-level thrust datum. ISP SL may be omitted,
    # but vacuum ISP is then used as an explicit approximation.
    if data.stages[0].thrust_sl is None:
        raise HTTPException(422, "Stage 1 requires sea-level thrust for liftoff TWR.")
    for i, stage in enumerate(data.stages, start=1):
        if stage.thrust_curve:
            _validate_thrust_curve(stage.thrust_curve, f"Stage {i}")
    if data.use_boost:
        for i, booster in enumerate(data.boost_groups, start=1):
            if booster.thrust_curve:
                _validate_thrust_curve(booster.thrust_curve, f"Booster {i}")
    if data.use_timeline:
        if not data.timeline or len(data.timeline.stages) != len(data.stages):
            raise HTTPException(422, "Timeline must contain one event row for every original core stage.")
        previous_sep = -1.0
        for i, row in enumerate(data.timeline.stages):
            windows = row.burns or (
                [TimelineBurn(ignition_t=row.ignition_t, cutoff_t=row.cutoff_t)]
                if row.ignition_t is not None and row.cutoff_t is not None else []
            )
            if not windows:
                raise HTTPException(422, f"Stage {i + 1}: provide ignition_t/cutoff_t or a non-empty burns array.")
            previous_cut = -1.0
            for burn in windows:
                if burn.cutoff_t <= burn.ignition_t:
                    raise HTTPException(422, f"Stage {i + 1}: each cutoff must be after its ignition.")
                if burn.ignition_t < previous_cut:
                    raise HTTPException(422, f"Stage {i + 1}: burn windows must be ordered and must not overlap.")
                previous_cut = burn.cutoff_t
            if row.separation_t < previous_cut:
                raise HTTPException(422, f"Stage {i + 1}: separation cannot occur before the final cutoff.")
            first_ignition = windows[0].ignition_t
            if i and first_ignition < previous_sep and not (data.use_boost and i == 0):
                raise HTTPException(422, f"Stage {i + 1} ignition precedes previous stage separation.")
            previous_sep = row.separation_t
        if (data.timeline.payload_t is not None
                and data.timeline.payload_t < windows[-1].cutoff_t):
            raise HTTPException(422, "Payload deployment cannot precede the final stage's last engine cutoff.")
    try:
        launch_jd = jd_from_datetime(data.launch_utc)
        effective_launch_azimuth = data.launch_azimuth_deg
        if data.target_raan_deg is not None:
            effective_launch_azimuth = rp.launch_azimuth_for_plane(
                data.site_lat, data.site_lon, data.site_alt, launch_jd,
                data.target_inclination_deg, data.target_raan_deg
            )
        elif data.target_inclination_deg is not None:
            effective_launch_azimuth = rp.launch_azimuth_for_inclination(
                data.site_lat, data.launch_azimuth_deg,
                data.target_inclination_deg
            )
        original = [s.model_dump() if hasattr(s, "model_dump") else s.dict() for s in data.stages]
        stages_cfg = [dict(s) for s in original]
        boost_log = []
        boost_warnings = []
        if data.use_boost:
            core = stages_cfg[0]
            groups = [bst.make_group(g.name, g.count, g.thrust_sl, g.thrust_vac,
                      g.isp_sl, g.isp_vac, g.prop_mass, g.dry_mass, g.burn_time,
                      g.area, g.ignite_t, g.jettison_delay, g.thrust_curve) for g in data.boost_groups]
            phases, boost_log = bst.build_boost_phases(
                core, groups, data.boost_throttle, data.solo_throttle, data.boost_auto_burn)
            boost_warnings = bst.validate(core, groups, phases)
            if data.use_timeline and data.timeline:
                _apply_boost_core_timeline(phases, boost_log, data.timeline.stages[0])
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
                windows = row.burns or [
                    TimelineBurn(ignition_t=row.ignition_t, cutoff_t=row.cutoff_t)
                ]
                stage["burn_windows"] = [
                    (float(burn.ignition_t), float(burn.cutoff_t))
                    for burn in windows
                ]
                stage["burn_time"] = sum(
                    cutoff - ignition for ignition, cutoff in stage["burn_windows"]
                )
                stage["separation_t"] = float(row.separation_t)
                if i > 0:
                    prev_sep = rows[i - 1].separation_t
                    stage["ignition_delay"] = max(windows[0].ignition_t - prev_sep, 0.0)
            fair_t = data.timeline.fairing_t
            payload_t = data.timeline.payload_t
            timeline_end = max(row.separation_t for row in rows)
            max_time = max(max_time, timeline_end + 2.0)
            if payload_t is not None:
                max_time = max(max_time, payload_t + 2.0)

        stages = [rp.Stage(
            s.get("name", f"Stage {i + 1}"),
            s["thrust_sl"] * 1000 if s.get("thrust_sl") is not None else None,
            s["thrust_vac"] * 1000,
            s.get("isp_sl"), s["isp_vac"],
            s["prop_mass"], s["dry_mass"], s["burn_time"], s["area"],
            float(s.get("ignition_delay", 0.0)),
            s.get("burn_windows"),
            s.get("separation_t"),
            _curve_points(s.get("thrust_curve"))
        ) for i, s in enumerate(stages_cfg)]
        vehicle = rp.Vehicle(
            stages=stages, payload=data.payload, fairing_mass=data.fairing_mass,
            fairing_jettison_alt=data.fairing_alt * 1000,
            fairing_jettison_t=fair_t, payload_deploy_t=payload_t
        )
        mission = rp.Mission(
            site_lat=data.site_lat, site_lon=data.site_lon, site_alt=data.site_alt,
            target_alt=data.target_alt * 1000, launch_azimuth_deg=effective_launch_azimuth,
            launch_jd=launch_jd, vertical_time=data.vertical_time,
            kick_angle=data.kick_angle, kick_duration=data.kick_duration,
            mission_type=data.mission_type,
            target_apogee_alt=(data.target_apogee_alt if data.mission_type != "circular"
                               else data.target_alt) * 1000,
            target_c3_km2_s2=data.target_c3_km2_s2,
            auto_profile=data.auto_profile
        )
        ascent, state, t_end, theta0, azimuth = rp.simulate_ascent(
            vehicle, mission, dt=data.timestep, dt_out=0.5,
            max_time=max_time, verbose=False
        )
        if ascent.empty:
            raise ValueError("The ascent simulation returned no trajectory points.")
        try:
            orbit_state, t_insert, delta_v = rp.coast_and_circularize(
                state, t_end, mission.target_alt,
                mission_type=data.mission_type, verbose=False
            )
        except ValueError as exc:
            if "apoapsis ต่ำกว่า" not in str(exc):
                raise
            last = ascent.iloc[-1]
            peak = ascent.loc[ascent["alt_km"].idxmax()]
            def ascent_sample_diagnostics(sample):
                return (
                    f"stage={sample.get('stage', 'unknown')}, "
                    f"t=+{float(sample.get('t', 0.0)):.1f}s, "
                    f"alt={float(sample.get('alt_km', 0.0)):.2f}km, "
                    f"FPA={float(sample.get('fpa_deg', 0.0)):.2f}deg, "
                    f"v_radial={float(sample.get('radial_velocity_mps', 0.0)):.1f}m/s, "
                    f"v_tangential={float(sample.get('tangential_velocity_mps', 0.0)):.1f}m/s, "
                    f"thrust={float(sample.get('thrust_kN', 0.0)):.1f}kN, "
                    f"mass={float(sample.get('mass', 0.0)):.1f}kg, "
                    f"thrust_radial_fraction={float(sample.get('thrust_radial_fraction', 0.0)):.3f}, "
                    f"thrust_radial_accel={float(sample.get('thrust_radial_accel_mps2', 0.0)):.2f}m/s2, "
                    f"thrust_tangential_accel={float(sample.get('thrust_tangential_accel_mps2', 0.0)):.2f}m/s2, "
                    f"burn_elapsed={float(sample.get('stage_burn_elapsed_s', 0.0)):.1f}s, "
                    f"prop_remaining={float(sample.get('stage_propellant_remaining_kg', 0.0)):.1f}kg"
                )
            detail = (
                f"; capture_guidance_start=+{float(peak.get('capture_guidance_start_t_s') or 0.0):.1f}s, "
                f"capture_guidance_active_at_peak={bool(peak.get('capture_guidance_active', False))}, "
                f"capture_threshold={float(peak.get('capture_threshold_alt_km', 0.0)):.1f}km, "
                f"predicted_apoapsis_at_peak={float(peak.get('predicted_apoapsis_alt_km', 0.0)):.1f}km; "
                f"peak sample: {ascent_sample_diagnostics(peak)}; "
                f"last sample: {ascent_sample_diagnostics(last)}"
            )
            raise ValueError(f"{exc}{detail}") from exc
        elements = rp.orbital_elements(orbit_state[0:3], orbit_state[3:6])
        target_orbit_met = True
        if data.mission_type == "escape":
            actual_c3 = float(elements["c3_km2_s2"])
            if actual_c3 + 1e-6 < data.target_c3_km2_s2:
                raise ValueError(
                    "Escape target not reached: "
                    f"actual C3={actual_c3:.4f} km²/s², "
                    f"required C3={data.target_c3_km2_s2:.4f} km²/s²."
                )
            target_orbit_met = actual_c3 + 1e-6 >= data.target_c3_km2_s2
            if data.target_inclination_deg is not None:
                target_orbit_met = target_orbit_met and (
                    abs(elements["inc_deg"] - data.target_inclination_deg) <= 0.5
                )
            if data.target_raan_deg is not None:
                raan_error = abs((elements["raan_deg"] - data.target_raan_deg + 180.0) % 360.0 - 180.0)
                target_orbit_met = target_orbit_met and raan_error <= 0.5
            duration = data.trajectory_duration_s
        elif elements["e"] >= 1.0 or not math.isfinite(elements["period_min"]):
            raise ValueError(
                "Requested bound orbit was not achieved: the final trajectory is not elliptic."
            )
        else:
            if elements["perigee_km"] < 120.0:
                raise ValueError(
                    f"Final orbit intersects the protected low-altitude limit "
                    f"(perigee {elements['perigee_km']:.1f} km)."
                )
            if data.mission_type == "elliptical":
                perigee_tolerance = max(10.0, data.target_alt * 0.01)
                apogee_tolerance = max(10.0, data.target_apogee_alt * 0.01)
                target_orbit_met = (
                    abs(elements["perigee_km"] - data.target_alt) <= perigee_tolerance
                    and abs(elements["apogee_km"] - data.target_apogee_alt) <= apogee_tolerance
                )
            if data.target_inclination_deg is not None:
                target_orbit_met = target_orbit_met and (
                    abs(elements["inc_deg"] - data.target_inclination_deg) <= 0.5
                )
            if data.target_raan_deg is not None:
                raan_error = abs((elements["raan_deg"] - data.target_raan_deg + 180.0) % 360.0 - 180.0)
                target_orbit_met = target_orbit_met and raan_error <= 0.5
            duration = data.orbit_count * elements["period_min"] * 60.0
        orbit = rp.propagate_orbit(orbit_state, t_insert, theta0, duration=duration, dt=15)
        # Visibility must cover the powered ascent AND the propagated orbital
        # ground track. The map displays both; previously only ascent was tested.
        visibility_trajectory = _visibility_trajectory(ascent, orbit)
        look = rp.look_angles(visibility_trajectory, data.obs_lat, data.obs_lon,
                              data.obs_alt, launch_jd, theta0)
        visible = look[look["el_deg"] > data.min_elevation]
        visible_duration_s = _sampled_visible_duration(look, data.min_elevation)
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
            "target_orbit_met": bool(target_orbit_met),
            "target_c3_km2_s2": data.target_c3_km2_s2,
            "actual_c3_km2_s2": elements["c3_km2_s2"],
            "visible_duration_s": visible_duration_s,
            "sunlit_percent": float(visible["rocket_sunlit"].mean() * 100) if not visible.empty else 0.0,
            "photo_window_percent": float(visible["photo_window"].mean() * 100) if not visible.empty else 0.0,
            "visible_count": int(len(visible)),
        }
        model_warnings = ["Ambient-pressure interpolation is a two-point approximation; no nozzle performance map is available."]
        for i, stage in enumerate(data.stages, start=1):
            if stage.isp_sl is None:
                model_warnings.append(f"Stage {i}: ไม่มี ISP sea-level; ใช้ ISP vacuum เป็นค่าประมาณในบรรยากาศ")
            if stage.thrust_sl is None:
                model_warnings.append(f"Stage {i}: ไม่มี Thrust sea-level; ใช้ค่า vacuum เป็นค่าประมาณ")
            if not stage.thrust_curve:
                model_warnings.append(f"Stage {i}: ไม่มี Thrust-Time Curve; สมมติแรงขับ vacuum คงที่")
        return clean({
            "model_warnings": model_warnings,
            "summary": summary, "elements": elements, "profile": profile,
            "visibility": {"first": first, "peak": peak, "closest": closest,
                           "last": last, "count": len(visible)},
            "ascent": records(ascent, ["t","lat","lon","alt_km","v_inertial",
                "v_relative","mach","q_kPa","fpa_deg","mass","thrust_kN","acc_g","stage"]),
            "orbit": records(orbit, ["t","lat","lon","alt_km"]),
            "look": records(look, ["t","az_deg","el_deg","range_km","alt_km",
                "sun_el_deg","rocket_sunlit","photo_window","angular_rate"]),
            "events": event_rows(
                ascent, fair_t, payload_t, data.fairing_alt,
                data.timeline.stages if data.use_timeline and data.timeline else None,
                data.use_boost
            ),
            "boost_log": boost_log, "boost_warnings": boost_warnings,
            "report": rp.photo_report(look, data.min_elevation),
            "launch_utc": data.launch_utc.isoformat(),
            "parameters": {"site_lat": data.site_lat, "site_lon": data.site_lon,
                "site_alt": data.site_alt, "obs_lat": data.obs_lat,
                "obs_lon": data.obs_lon, "obs_alt": data.obs_alt,
                "mission_type": data.mission_type, "target_alt_km": data.target_alt,
                "target_apogee_alt_km": data.target_apogee_alt,
                "launch_azimuth_deg": effective_launch_azimuth,
                "preferred_launch_azimuth_deg": data.launch_azimuth_deg,
                "target_inclination_deg": data.target_inclination_deg,
                "target_raan_deg": data.target_raan_deg,
                "target_c3_km2_s2": data.target_c3_km2_s2,
                "trajectory_duration_s": data.trajectory_duration_s}
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Simulation failed: {exc}") from exc
