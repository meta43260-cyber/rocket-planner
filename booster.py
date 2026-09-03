"""
booster.py — แปลง strap-on booster (ขนาน) เป็นสเตจเสมือน (อนุกรม)
รองรับ: หลายกลุ่ม, จุดต่างเวลา, สลัดหน่วงเวลา, core throttle
[FIX] core ดับแล้วแรงขับ/เชื้อเพลิง core = 0, booster เผาต่อจนหมดแล้วสลัด
"""
G0 = 9.80665
EPS = 1e-6

def mdot(thrust_kN, isp_s):
    return thrust_kN * 1e3 / (G0 * isp_s)

def make_group(name, count, thrust_sl, thrust_vac, isp_sl, isp_vac,
               prop_mass, dry_mass, burn_time, area,
               ignite_t=0.0, jettison_delay=2.0):
    return dict(name=name, count=int(count),
                thrust_sl=thrust_sl, thrust_vac=thrust_vac,
                isp_sl=isp_sl, isp_vac=isp_vac,
                prop_mass=prop_mass, dry_mass=dry_mass,
                burn_time=burn_time, area=area,
                ignite_t=ignite_t, jettison_delay=jettison_delay)

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
    t_last = T_core
    ev = {0.0, T_core}
    for g in groups:
        ev.add(g["ignite_t"])
        ev.add(g["ignite_t"] + g["burn_time"])
        ev.add(g["ignite_t"] + g["burn_time"] + g["jettison_delay"])
        t_last = max(t_last, g["ignite_t"] + g["burn_time"] + g["jettison_delay"])
    t_last = max([T_core] + [g["ignite_t"] + g["burn_time"] + g["jettison_delay"] for g in groups])
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
        core_on = tm < T_core - EPS
        tau = _core_throttle(groups, tm, tau_b, tau_s) if core_on else 0.0
        F_sl = tau * core["thrust_sl"] + sum(g["count"] * g["thrust_sl"] for g in burning)
        F_vac = tau * core["thrust_vac"] + sum(g["count"] * g["thrust_vac"] for g in burning)
        w_sl = (tau * core["thrust_sl"] / core["isp_sl"]
                + sum(g["count"] * g["thrust_sl"] / g["isp_sl"] for g in burning))
        w_vac = (tau * core["thrust_vac"] / core["isp_vac"]
                 + sum(g["count"] * g["thrust_vac"] / g["isp_vac"] for g in burning))
        isp_sl = F_sl / w_sl if w_sl > 0 else core["isp_sl"]
        isp_vac = F_vac / w_vac if w_vac > 0 else core["isp_vac"]
        want = sum(g["count"] * mdot(g["thrust_vac"], g["isp_vac"]) * dt
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
                           burn_time=dt, area=area))
        log.append(dict(t0=t0, t1=t1, name=name, F_sl=F_sl, isp_vac=isp_vac,
                        prop=p_core + p_boost, jett=m_jett,
                        twr_note=f"{tau*100:.0f}%"))
    phases[-1]["dry_mass"] += core["dry_mass"]
    return phases, log

def validate(core, groups, phases):
    warn = []
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

