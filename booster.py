"""
booster.py — แปลง strap-on booster (ขนาน) เป็นสเตจเสมือน (อนุกรม)
รองรับ: หลายกลุ่ม, จุดต่างเวลา, สลัดหน่วงเวลา, core throttle
"""
G0 = 9.80665
EPS = 1e-6

def mdot(thrust_kN, isp_s):
    return thrust_kN * 1e3 / (G0 * isp_s)

def make_group(name, count, thrust_sl, thrust_vac, isp_sl, isp_vac,
               prop_mass, dry_mass, burn_time, area,
               ignite_t=0.0, jettison_delay=2.0, thrust_curve=None):
    return dict(name=name, count=int(count),
                thrust_sl=thrust_sl, thrust_vac=thrust_vac,
                isp_sl=isp_sl, isp_vac=isp_vac,
                prop_mass=prop_mass, dry_mass=dry_mass,
                burn_time=burn_time, area=area,
                ignite_t=ignite_t, jettison_delay=jettison_delay, thrust_curve=thrust_curve)

def _is_burning(g, t):
    return g["ignite_t"] - EPS <= t < g["ignite_t"] + g["burn_time"] - EPS

def _is_attached(g, t):
    return t < g["ignite_t"] + g["burn_time"] + g["jettison_delay"] - EPS

def _core_throttle(groups, t, tau_boost, tau_solo=1.0):
    return tau_boost if any(_is_burning(g, t) for g in groups) else tau_solo

def core_depletion_time(core, groups, tau_boost, tau_solo=1.0, t_max=2000.0):
    bounds = sorted({0.0} | {g["ignite_t"] for g in groups}
                    | {g["ignite_t"] + g["burn_time"] for g in groups})
    bounds = [b for b in bounds if 0 <= b <= t_max] + [t_max]
    used, t_prev = 0.0, 0.0
    for b in bounds[1:]:
        dt = b - t_prev
        if dt <= EPS:
            continue
        tau = _core_throttle(groups, 0.5 * (t_prev + b), tau_boost, tau_solo)
        rate = mdot(tau * core["thrust_vac"], core["isp_vac"])
        if used + rate * dt >= core["prop_mass"]:
            return t_prev + (core["prop_mass"] - used) / rate
        used += rate * dt
        t_prev = b
    return t_prev

def build_boost_phases(core, groups, throttle_pct=100.0,
                       solo_throttle_pct=100.0, auto_burn=True):
    if not groups:
        return [dict(core)], []
    tau_b = throttle_pct / 100.0
    tau_s = solo_throttle_pct / 100.0
    T_core = (core_depletion_time(core, groups, tau_b, tau_s)
              if auto_burn else core["burn_time"])
    ev = {0.0, T_core}
    for g in groups:
        ev.add(g["ignite_t"])
        ev.add(g["ignite_t"] + g["burn_time"])
        ev.add(g["ignite_t"] + g["burn_time"] + g["jettison_delay"])
    t_last = max([T_core] + [g["ignite_t"] + g["burn_time"] + g["jettison_delay"]
                             for g in groups])
    for g in groups:
        for point in (g.get("thrust_curve") or []):
            curve_t = g["ignite_t"] + float(point[0])
            if g["ignite_t"] < curve_t < g["ignite_t"] + g["burn_time"]:
                ev.add(curve_t)
    times = sorted(t for t in ev if -EPS <= t <= t_last + EPS)
    rem_boost = sum(g["count"] * g["prop_mass"] for g in groups)
    phases, log = [], []
    for k in range(len(times) - 1):
        t0, t1 = times[k], times[k + 1]
        dt = t1 - t0
        if dt <= 1e-3:
            continue
        tm = 0.5 * (t0 + t1)
        core_on = tm < T_core - EPS
        burning = [g for g in groups if _is_burning(g, tm)]
        attached = [g for g in groups if _is_attached(g, tm)]
        tau = _core_throttle(groups, tm, tau_b, tau_s) if core_on else 0.0
        # Missing booster sea-level data must not block a run. In that case use
        # the vacuum rating as a clearly warned upper-bound approximation; never
        # silently substitute a P120C value or invent a P160C sea-level datum.
        def booster_vac(g, when):
            curve = g.get("thrust_curve") or []
            if not curve:
                return g["thrust_vac"]
            elapsed = max(0.0, when - g["ignite_t"])
            if elapsed <= curve[0][0]: return curve[0][1]
            for left, right in zip(curve, curve[1:]):
                if left[0] <= elapsed <= right[0]:
                    f = (elapsed-left[0]) / max(right[0]-left[0], EPS)
                    return left[1] + f * (right[1]-left[1])
            return curve[-1][1]
        F_sl = tau * core["thrust_sl"] + sum(
            g["count"] * (booster_vac(g, tm) + ((g["thrust_sl"] - g["thrust_vac"])
            if g["thrust_sl"] is not None else 0.0)) for g in burning
        )
        F_vac = tau * core["thrust_vac"] + sum(g["count"] * booster_vac(g, tm) for g in burning)
        phase_curve = [[0.0, tau * core["thrust_vac"] + sum(g["count"] * booster_vac(g, t0) for g in burning)]]
        phase_curve.append([dt, tau * core["thrust_vac"] + sum(g["count"] * booster_vac(g, t1 - 1e-7) for g in burning)])
        w_sl = (tau * core["thrust_sl"] / core["isp_sl"]
                + sum(
                    g["count"] * (g["thrust_sl"] if g["thrust_sl"] is not None else g["thrust_vac"])
                    / (g["isp_sl"] if g["isp_sl"] is not None else g["isp_vac"])
                    for g in burning
                ))
        w_vac = (tau * core["thrust_vac"] / core["isp_vac"]
                 + sum(g["count"] * g["thrust_vac"] / g["isp_vac"] for g in burning))
        isp_sl = F_sl / w_sl if w_sl > 0 else core["isp_sl"]
        isp_vac = F_vac / w_vac if w_vac > 0 else core["isp_vac"]
        want = sum(g["count"] * mdot(booster_vac(g, tm), g["isp_vac"]) * dt
                   for g in burning)
        p_boost = min(want, rem_boost)
        rem_boost -= p_boost
        p_core = mdot(tau * core["thrust_vac"], core["isp_vac"]) * dt if core_on else 0.0
        jett = [g for g in groups
                if abs(g["ignite_t"] + g["burn_time"] + g["jettison_delay"] - t1) < 1e-3]
        m_jett = sum(g["count"] * g["dry_mass"] for g in jett)
        area = core["area"] + sum(g["count"] * g["area"] for g in attached)
        tag = "+".join(f"{g['count']}x{g['name']}" for g in burning)
        if burning and core_on:
            name = f"เฟส {k+1}: core+{tag}"
        elif burning:
            name = f"เฟส {k+1}: {tag} (core ดับ)"
        else:
            name = f"เฟส {k+1}: สลัด booster"
        phases.append(dict(name=name, thrust_sl=F_sl, thrust_vac=F_vac,
                           isp_sl=isp_sl, isp_vac=isp_vac,
                           prop_mass=p_core + p_boost, dry_mass=m_jett,
                           burn_time=dt, area=area, thrust_curve=phase_curve))
        log.append(dict(t0=t0, t1=t1, name=name, F_sl=F_sl, isp_vac=isp_vac,
                        prop=p_core + p_boost, jett=m_jett,
                        twr_note=f"{tau*100:.0f}%"))
    phases[-1]["dry_mass"] += core["dry_mass"]
    return phases, log

def validate(core, groups, phases):
    warn = []
    for g in groups:
        if g["thrust_sl"] is None and g["isp_sl"] is None:
            warn.append(
                f'{g["name"]}: ไม่มีข้อมูล Thrust SL — ใช้ค่า Vacuum เป็นค่าประมาณ '
                'ผลช่วงใกล้พื้นโลกอาจสูงเกินจริง'
            )
    total_p = sum(p["prop_mass"] for p in phases)
    avail = core["prop_mass"] + sum(
        min(g["count"] * g["prop_mass"],
            g["count"] * mdot(g["thrust_vac"], g["isp_vac"]) * g["burn_time"])
        for g in groups)
    err = abs(total_p - avail) / avail * 100
    if err > 2.0:
        warn.append(f"เชื้อเพลิงคลาดเคลื่อน {err:.1f}%")
    if phases[0]["thrust_sl"] <= 0:
        warn.append("แรงขับเริ่มต้นเป็นศูนย์ — ตรวจ ignite_t ของ booster")
    return warn
