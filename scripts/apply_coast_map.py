#!/usr/bin/env python3
"""Apply coast trajectory map support (idempotent)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
INDEX = ROOT / "static" / "index.html"

def patch_main(text: str) -> str:
    if "_sample_coast_arc" in text and '"coast": records(coast' in text:
        return text
    old_vis = (
        "def _visibility_trajectory(ascent, orbit):\n"
        '    """Join ascent and propagated orbit states on the same launch-relative time axis."""\n'
        "    frames = [frame for frame in (ascent, orbit) if frame is not None and not frame.empty]\n"
        "    if not frames:\n"
        "        return pd.DataFrame()\n"
        "    return (pd.concat(frames, ignore_index=True)\n"
        '            .sort_values("t")\n'
        '            .drop_duplicates(subset=["t"], keep="last")\n'
        "            .reset_index(drop=True))\n"
    )
    new_vis = '''def _visibility_trajectory(*frames):
    """Join ascent, coast and orbit states on the same launch-relative time axis."""
    valid = [frame for frame in frames if frame is not None and not getattr(frame, "empty", True)]
    if not valid:
        return pd.DataFrame()
    return (pd.concat(valid, ignore_index=True)
            .sort_values("t")
            .drop_duplicates(subset=["t"], keep="last")
            .reset_index(drop=True))


def _sample_coast_arc(state, t_start, t_end, theta0, sample_dt=5.0):
    """Propagate a ballistic coast arc for map display (no thrust)."""
    import numpy as np
    y = np.array(state, dtype=float)
    rows = []
    t = float(t_start)
    end = float(t_end)
    dt = max(float(sample_dt), 1.0)
    if end <= t + 1e-9:
        lat, lon, alt = rp.eci_to_geodetic(y[0:3], theta0 + rp.OMEGA_E * t)
        return pd.DataFrame([dict(t=t, lat=lat, lon=lon, alt_km=alt/1000.0,
                                 v_inertial=float(np.linalg.norm(y[3:6])))])
    while t <= end + 1e-9:
        lat, lon, alt = rp.eci_to_geodetic(y[0:3], theta0 + rp.OMEGA_E * t)
        rows.append(dict(t=t, lat=lat, lon=lon, alt_km=alt/1000.0,
                         v_inertial=float(np.linalg.norm(y[3:6]))))
        if t >= end - 1e-9:
            break
        step = min(dt, end - t)
        k1 = rp._two_body_j2(y)
        k2 = rp._two_body_j2(y + 0.5 * step * k1)
        k3 = rp._two_body_j2(y + 0.5 * step * k2)
        k4 = rp._two_body_j2(y + step * k3)
        y = y + (step / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        t += step
    return pd.DataFrame(rows)
'''
    if old_vis not in text:
        raise SystemExit("unexpected main.py: visibility helper not found")
    text = text.replace(old_vis, new_vis, 1)
    needle = (
        "            orbit_state, t_insert, delta_v = rp.coast_and_circularize(\n"
        "                state, t_end, mission.target_alt,\n"
        "                mission_type=data.mission_type,\n"
        "                max_coast=circular_coast_limit_s,\n"
        "                verbose=False\n"
        "            )\n"
    )
    insert = needle + "            coast = _sample_coast_arc(state, t_end, t_insert, theta0, sample_dt=5.0)\n"
    if needle not in text:
        raise SystemExit("unexpected main.py: coast_and_circularize call not found")
    if "coast = _sample_coast_arc" not in text:
        text = text.replace(needle, insert, 1)
    text = text.replace(
        "visibility_trajectory = _visibility_trajectory(ascent, orbit)",
        "visibility_trajectory = _visibility_trajectory(ascent, coast, orbit)",
        1,
    )
    old_payload = (
        '            "ascent": records(ascent, ["t","lat","lon","alt_km","v_inertial",\n'
        '                "v_relative","mach","q_kPa","fpa_deg","mass","thrust_kN","acc_g","stage"]),\n'
        '            "orbit": records(orbit, ["t","lat","lon","alt_km"]),'
    )
    new_payload = (
        '            "ascent": records(ascent, ["t","lat","lon","alt_km","v_inertial",\n'
        '                "v_relative","mach","q_kPa","fpa_deg","mass","thrust_kN","acc_g","stage"]),\n'
        '            "coast": records(coast, ["t","lat","lon","alt_km","v_inertial"]),\n'
        '            "orbit": records(orbit, ["t","lat","lon","alt_km"]),'
    )
    if old_payload not in text:
        raise SystemExit("unexpected main.py: response payload not found")
    return text.replace(old_payload, new_payload, 1)

def patch_index(text: str) -> str:
    if "coast_map_overlay.js" in text and "coast-dot" in text:
        return text
    text = text.replace(
        '<span><i class="ascent-dot"></i> Ascent</span><span><i class="orbit-dot"></i> Orbit</span>',
        '<span><i class="ascent-dot"></i> Ascent</span><span><i class="coast-dot"></i> Coast</span><span><i class="orbit-dot"></i> Orbit</span>',
    )
    if "coast_map_overlay.js" not in text:
        text2, n = re.subn(
            r'(<script src="/static/app\.js[^"]*"></script>)',
            r'\1\n<script src="/static/coast_map_overlay.js"></script>',
            text,
            count=1,
        )
        if n == 0:
            raise SystemExit("unexpected index.html: app.js script tag not found")
        text = text2
    return text

changed = False
main_text = MAIN.read_text()
new_main = patch_main(main_text)
if new_main != main_text:
    MAIN.write_text(new_main)
    print("patched", MAIN)
    changed = True
else:
    print("main.py already patched")

index_text = INDEX.read_text()
new_index = patch_index(index_text)
if new_index != index_text:
    INDEX.write_text(new_index)
    print("patched", INDEX)
    changed = True
else:
    print("index.html already patched")

if not changed:
    print("already applied")
