"""
booster.py — แปลง strap-on booster (ขนาน) เป็นสเตจเสมือน (อนุกรม)
รองรับ: หลายกลุ่ม, จุดต่างเวลา, สลัดหน่วงเวลา, core throttle
"""

G0 = 9.80665
EPS = 1e-6


def mdot(thrust_kN, isp_s):
    """อัตราการไหลเชื้อเพลิง (kg/s) จากแรงขับ kN และ Isp วินาที"""
    return thrust_kN * 1e3 / (G0 * isp_s)


def make_group(name, count, thrust_sl, thrust_vac, isp_sl, isp_vac,
               prop_mass, dry_mass, burn_time, area,
               ignite_t=0.0, jettison_delay=2.0):
    """สร้าง booster หนึ่งกลุ่ม (ค่ามวล/แรงขับเป็น 'ต่อ 1 ตัว')"""
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
    """core ลดแรงขับเฉพาะช่วงที่ยังมี booster ทำงาน"""
    return tau_boost if any(_is_burning(g, t) for g in groups) else tau_solo


def core_depletion_time(core, groups, tau_boost, tau_solo=1.0, t_max=2000.0):
    """
    หาเวลาที่ core เผาเชื้อเพลิงหมดจริง เมื่อมีการ throttle
    (throttle ต่ำ = core อยู่ได้นานกว่า burn_time ที่ระบุใน spec)
    """
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
    """
    คืนค่า: (phases, timeline_log)
    phases = list ของ dict สเตจเสมือน พร้อมส่งเข้า simulator
    """
    if not groups:
        return [dict(core)], []

    tau_b = throttle_pct / 100.0
    tau_s = solo_throttle_pct / 100.0

    # --- เวลาเผาจริงของ core ---
    T_core = (core_depletion_time(core, groups, tau_b, tau_s)
              if auto_burn else core["burn_time"])

    # --- รวบรวมจุดเหตุการณ์ทั้งหมด ---
    ev = {0.0, T_core}
    for g in groups:
        ev.add(g["ignite_t"])
        ev.add(g["ignite_t"] + g["burn_time"])
        ev.add(g["ignite_t"] + g["burn_time"] + g["jettison_delay"])
    times = sorted(t for t in ev if -EPS <= t <= T_core + EPS)
    if times[-1] < T_core - EPS:
        times.append(T_core)

    phases, log = [], []
    for k in range(len(times) - 1):
        t0, t1 = times[k], times[k + 1]
        dt = t1 - t0
        if dt <= 1e-3:
            continue
        tm = 0.5 * (t0 + t1)

        burning = [g for g in groups if _is_burning(g, tm)]
        attached = [g for g in groups if _is_attached(g, tm)]
        tau = _core_throttle(groups, tm, tau_b, tau_s)

        # --- แรงขับรวม ---
        F_sl = tau * core["thrust_sl"] + sum(g["count"] * g["thrust_sl"] for g in burning)
        F_vac = tau * core["thrust_vac"] + sum(g["count"] * g["thrust_vac"] for g in burning)

        # --- Isp ประสิทธิผล (ถ่วงน้ำหนักด้วย mass flow) ---
        w_sl = (tau * core["thrust_sl"] / core["isp_sl"]
                + sum(g["count"] * g["thrust_sl"] / g["isp_sl"] for g in burning))
        w_vac = (tau * core["thrust_vac"] / core["isp_vac"]
                 + sum(g["count"] * g["thrust_vac"] / g["isp_vac"] for g in burning))
        isp_sl = F_sl / w_sl if w_sl > 0 else core["isp_sl"]
        isp_vac = F_vac / w_vac if w_vac > 0 else core["isp_vac"]

        # --- เชื้อเพลิงที่ใช้ในเฟสนี้ ---
        p_core = mdot(tau * core["thrust_vac"], core["isp_vac"]) * dt
        p_boost = sum(g["count"] * mdot(g["thrust_vac"], g["isp_vac"]) * dt
                      for g in burning)

        # --- มวลที่สลัดทิ้งตอนจบเฟส ---
        jett = [g for g in groups
                if abs(g["ignite_t"] + g["burn_time"] + g["jettison_delay"] - t1) < 1e-3]
        m_jett = sum(g["count"] * g["dry_mass"] for g in jett)

        area = core["area"] + sum(g["count"] * g["area"] for g in attached)

        if burning:
            tag = "+".join(f"{g['count']}×{g['name']}" for g in burning)
            name = f"เฟส {k+1}: core+{tag}"
        else:
            name = f"เฟส {k+1}: core เดี่ยว"

        phases.append(dict(
            name=name, thrust_sl=F_sl, thrust_vac=F_vac,
            isp_sl=isp_sl, isp_vac=isp_vac,
            prop_mass=p_core + p_boost, dry_mass=m_jett,
            burn_time=dt, area=area))

        log.append(dict(t0=t0, t1=t1, name=name, F_sl=F_sl, isp_vac=isp_vac,
                        prop=p_core + p_boost, jett=m_jett,
                        twr_note=f"{tau*100:.0f}%"))

    # มวลแห้ง core ทิ้งตอนจบเฟสสุดท้าย
    phases[-1]["dry_mass"] += core["dry_mass"]
    return phases, log


def validate(core, groups, phases):
    """ตรวจความสมเหตุสมผล คืน list ของข้อความเตือน"""
    warn = []
    total_p = sum(p["prop_mass"] for p in phases)
    avail = core["prop_mass"] + sum(g["count"] * g["prop_mass"] for g in groups)
    err = abs(total_p - avail) / avail * 100
    if err > 2.0:
        warn.append(f"เชื้อเพลิงคลาดเคลื่อน {err:.1f}% "
                    f"(ใช้ {total_p:,.0f} / มี {avail:,.0f} kg)")
    for g in groups:
        implied = g["count"] * mdot(g["thrust_vac"], g["isp_vac"]) * g["burn_time"]
        e = abs(implied - g["count"] * g["prop_mass"]) / (g["count"] * g["prop_mass"]) * 100
        if e > 15:
            warn.append(f"{g['name']}: thrust×burn ไม่ตรงกับ prop mass ({e:.0f}%)")
    if phases[0]["thrust_sl"] <= 0:
        warn.append("แรงขับเริ่มต้นเป็นศูนย์ — ตรวจ ignite_t ของ booster")
    return warn
