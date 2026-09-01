"""
rocket_planner.py — Rocket Ascent, Orbit & Observation Engine
3-DOF ascent (ECI) + J2 orbit propagation + look angles + airspace check

หน่วย: SI ทั้งหมด (m, kg, s, rad ภายใน / deg ที่ interface)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd

# ============================================================
# ค่าคงที่
# ============================================================
MU      = 3.986004418e14      # m^3/s^2
RE      = 6378137.0           # m (WGS84 equatorial)
FLAT    = 1/298.257223563
E2      = FLAT*(2-FLAT)
OMEGA_E = 7.2921159e-5        # rad/s
J2      = 1.08262668e-3
G0      = 9.80665
P0      = 101325.0
R_AIR   = 287.053
GAMMA   = 1.4
Z_AXIS  = np.array([0.0, 0.0, 1.0])

D2R = np.pi/180.0
R2D = 180.0/np.pi


# ============================================================
# บรรยากาศมาตรฐาน US-1976 (ถึง 86 km) + exponential ด้านบน
# ============================================================
_LAYERS = [
    (0.0,     288.15, -0.0065, 101325.0),
    (11000.0, 216.65,  0.0,     22632.10),
    (20000.0, 216.65,  0.0010,   5474.89),
    (32000.0, 228.65,  0.0028,    868.019),
    (47000.0, 270.65,  0.0,       110.906),
    (51000.0, 270.65, -0.0028,     66.9389),
    (71000.0, 214.65, -0.0020,      3.95642),
]
_H_TOP, _T_TOP, _P_TOP, _HS = 84852.0, 186.946, 0.37287, 6500.0


def atmosphere(h: float):
    """คืน (rho, p, T, a) ที่ความสูง geometric h เมตร"""
    if h <= 0:
        h = 0.0
    if h >= _H_TOP:
        T = _T_TOP
        p = _P_TOP*np.exp(-(h-_H_TOP)/_HS)
    else:
        hb, Tb, L, pb = _LAYERS[0]
        for lay in _LAYERS:
            if h >= lay[0]:
                hb, Tb, L, pb = lay
            else:
                break
        if abs(L) < 1e-12:
            T = Tb
            p = pb*np.exp(-G0*(h-hb)/(R_AIR*Tb))
        else:
            T = Tb + L*(h-hb)
            T = max(T, 1.0)
            p = pb*(T/Tb)**(-G0/(L*R_AIR))
    rho = p/(R_AIR*T)
    a = np.sqrt(GAMMA*R_AIR*T)
    return rho, p, T, a


_MACH = np.array([0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0, 25.0])
_CD   = np.array([0.30, 0.30, 0.34, 0.58, 0.62, 0.55, 0.45, 0.33, 0.28, 0.26, 0.25])


def drag_coefficient(mach: float) -> float:
    return float(np.interp(mach, _MACH, _CD))


# ============================================================
# Dataclasses
# ============================================================
@dataclass
class Stage:
    name: str
    thrust_sl: float      # N
    thrust_vac: float     # N
    isp_sl: float         # s
    isp_vac: float        # s
    prop_mass: float      # kg
    dry_mass: float       # kg
    burn_time: float      # s (ใช้เป็นเพดานเวลาเผา)
    area: float           # m^2

    def thrust(self, p: float) -> float:
        f = min(max(p/P0, 0.0), 1.0)
        return self.thrust_vac + (self.thrust_sl - self.thrust_vac)*f

    def isp(self, p: float) -> float:
        f = min(max(p/P0, 0.0), 1.0)
        return self.isp_vac + (self.isp_sl - self.isp_vac)*f


@dataclass
class Vehicle:
    stages: List[Stage]
    payload: float = 0.0
    fairing_mass: float = 0.0
    fairing_jettison_alt: float = 110000.0

    def gross_mass(self) -> float:
        return sum(s.prop_mass + s.dry_mass for s in self.stages) \
               + self.payload + self.fairing_mass


@dataclass
class Mission:
    site_lat: float          # deg
    site_lon: float          # deg
    site_alt: float = 0.0    # m
    target_alt: float = 500e3
    target_inc: float = 51.6
    launch_jd: float = 2451545.0
    vertical_time: float = 10.0
    kick_angle: float = 6.5
    kick_duration: float = 14.0
    ascend_east: bool = True


# ============================================================
# เวลา / พิกัด
# ============================================================
def gmst(jd: float) -> float:
    """Greenwich Mean Sidereal Time (rad)"""
    d = jd - 2451545.0
    T = d/36525.0
    g = 280.46061837 + 360.98564736629*d + 0.000387933*T*T - T*T*T/38710000.0
    return (g % 360.0)*D2R


def geodetic_to_ecef(lat_d, lon_d, h):
    lat, lon = lat_d*D2R, lon_d*D2R
    N = RE/np.sqrt(1 - E2*np.sin(lat)**2)
    return np.array([(N+h)*np.cos(lat)*np.cos(lon),
                     (N+h)*np.cos(lat)*np.sin(lon),
                     (N*(1-E2)+h)*np.sin(lat)])


def ecef_to_geodetic(r):
    """Bowring — คืน (lat_deg, lon_deg, alt_m)"""
    x, y, z = r
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    if p < 1e-9:
        return (90.0 if z > 0 else -90.0), lon*R2D, abs(z) - RE*(1-FLAT)
    b = RE*(1-FLAT)
    ep2 = (RE**2 - b**2)/b**2
    th = np.arctan2(z*RE, p*b)
    lat = np.arctan2(z + ep2*b*np.sin(th)**3, p - E2*RE*np.cos(th)**3)
    N = RE/np.sqrt(1 - E2*np.sin(lat)**2)
    alt = p/np.cos(lat) - N
    return lat*R2D, lon*R2D, alt


def eci_to_geodetic(r_eci, theta):
    c, s = np.cos(-theta), np.sin(-theta)
    r_ecef = np.array([c*r_eci[0] - s*r_eci[1],
                       s*r_eci[0] + c*r_eci[1],
                       r_eci[2]])
    return ecef_to_geodetic(r_ecef)


def enu_basis(r_eci):
    up = r_eci/np.linalg.norm(r_eci)
    e = np.cross(Z_AXIS, up)
    n_e = np.linalg.norm(e)
    e = np.array([1.0, 0.0, 0.0]) if n_e < 1e-9 else e/n_e
    n = np.cross(up, e)
    return e, n, up


def sun_unit_eci(jd: float):
    """ตำแหน่งดวงอาทิตย์แบบ low-precision (unit vector, ECI)"""
    n = jd - 2451545.0
    L = np.radians((280.460 + 0.9856474*n) % 360.0)
    g = np.radians((357.528 + 0.9856003*n) % 360.0)
    lam = L + np.radians(1.915*np.sin(g) + 0.020*np.sin(2*g))
    eps = np.radians(23.439 - 4.0e-7*n)
    return np.array([np.cos(lam),
                     np.cos(eps)*np.sin(lam),
                     np.sin(eps)*np.sin(lam)])


# ============================================================
# Launch azimuth
# ============================================================
def launch_azimuth(site_lat_deg, inc_deg, target_alt, ascend_east=True):
    """คืน (az_rotating_deg, az_inertial_deg, earth_rotation_bonus_mps)"""
    lat = site_lat_deg*D2R
    inc = abs(inc_deg)*D2R
    c = np.cos(inc)/max(np.cos(lat), 1e-9)
    c = float(np.clip(c, -1.0, 1.0))
    az_i = np.arcsin(c)                      # วัดจากทิศเหนือ
    if not ascend_east:
        az_i = np.pi - az_i
    v_orb = np.sqrt(MU/(RE + target_alt))
    ve = v_orb*np.sin(az_i)
    vn = v_orb*np.cos(az_i)
    v_earth = OMEGA_E*RE*np.cos(lat)
    az_r = np.arctan2(ve - v_earth, vn)
    return (az_r*R2D) % 360.0, (az_i*R2D) % 360.0, v_earth*np.sin(az_i)


# ============================================================
# ASCENT SIMULATION
# ============================================================
def simulate_ascent(vehicle: Vehicle, mission: Mission,
                    dt: float = 0.05, dt_out: float = 0.5,
                    max_time: float = 2000.0, verbose: bool = True):
    """
    คืน (df_ascent, state6_final, t_end, theta0, (az_rot, az_inert, v_bonus))
    """
    theta0 = gmst(mission.launch_jd)
    az_r, az_i, v_bonus = launch_azimuth(mission.site_lat, mission.target_inc,
                                         mission.target_alt, mission.ascend_east)
    az = az_r*D2R

    # --- สภาวะเริ่มต้น ---
    r_ecef = geodetic_to_ecef(mission.site_lat, mission.site_lon, mission.site_alt)
    c, s = np.cos(theta0), np.sin(theta0)
    r = np.array([c*r_ecef[0] - s*r_ecef[1], s*r_ecef[0] + c*r_ecef[1], r_ecef[2]])
    v = np.cross(np.array([0, 0, OMEGA_E]), r)
    state = np.concatenate([r, v])

    stages = vehicle.stages
    prop_left = [st.prop_mass for st in stages]
    stage_time = [0.0 for _ in stages]
    idx = 0
    fairing_on = True
    t = 0.0
    t_sep = None
    fpa_sep = None
    target_r = RE + mission.target_alt

    rows, next_out = [], 0.0

    def current_mass():
        m = vehicle.payload + (vehicle.fairing_mass if fairing_on else 0.0)
        for i in range(idx, len(stages)):
            m += stages[i].dry_mass + (prop_left[i] if i >= idx else 0.0)
        return m

    def steering(rv, tt, alt, burning):
        rr, vv = rv[0:3], rv[3:6]
        e, n, up = enu_basis(rr)
        horiz = np.sin(az)*e + np.cos(az)*n
        v_rel = vv - np.cross(np.array([0, 0, OMEGA_E]), rr)
        if not burning:
            return v_rel/max(np.linalg.norm(v_rel), 1e-6)
        # เฟส 1: ไต่ตรง
        if tt < mission.vertical_time:
            return up
        # เฟส 2: pitch kick
        if tt < mission.vertical_time + mission.kick_duration:
            f = (tt - mission.vertical_time)/max(mission.kick_duration, 1e-6)
            p = mission.kick_angle*D2R*f
            return np.cos(p)*up + np.sin(p)*horiz
        # เฟส 3: gravity turn (สเตจ 1)
        if idx == 0:
            nv = np.linalg.norm(v_rel)
            return v_rel/nv if nv > 1.0 else up
        # เฟส 4: สเตจบน — ลด pitch เชิงเส้นสู่แนวระนาบ
        vh = vv - np.dot(vv, up)*up
        nvh = np.linalg.norm(vh)
        vh = vh/nvh if nvh > 1.0 else horiz
        Tref = max(0.55*stages[idx].burn_time, 40.0)
        tau = np.clip((tt - t_sep)/Tref, 0.0, 1.0) if t_sep else 0.0
        g_cmd = max(fpa_sep*(1.0 - tau), 0.0) if fpa_sep else 0.0
        return np.cos(g_cmd)*vh + np.sin(g_cmd)*up

    def deriv(rv, mass, thr_vec, alt):
        rr, vv = rv[0:3], rv[3:6]
        rn = np.linalg.norm(rr)
        # แรงโน้มถ่วง + J2
        k = -MU/rn**3
        zr = rr[2]/rn
        j = 1.5*J2*MU*RE**2/rn**5
        ag = k*rr + np.array([j*rr[0]*(5*zr**2-1),
                              j*rr[1]*(5*zr**2-1),
                              j*rr[2]*(5*zr**2-3)])
        # แรงต้าน
        rho, _, _, _ = atmosphere(alt)
        v_rel = vv - np.cross(np.array([0, 0, OMEGA_E]), rr)
        vr = np.linalg.norm(v_rel)
        ad = np.zeros(3)
        if rho > 1e-12 and vr > 1.0:
            _, _, _, a_snd = atmosphere(alt)
            cd = drag_coefficient(vr/a_snd)
            area = stages[idx].area if idx < len(stages) else stages[-1].area
            ad = -0.5*rho*vr*cd*area/mass*v_rel
        return np.concatenate([vv, ag + thr_vec/mass + ad])

    while t < max_time:
        rn = np.linalg.norm(state[0:3])
        lat_d, lon_d, alt = eci_to_geodetic(state[0:3], theta0 + OMEGA_E*t)
        if alt < -500:
            break
        if fairing_on and alt >= vehicle.fairing_jettison_alt:
            fairing_on = False

        burning = idx < len(stages) and prop_left[idx] > 0.0 \
                  and stage_time[idx] < stages[idx].burn_time
        if idx < len(stages) and not burning and prop_left[idx] <= 0.0:
            if idx + 1 < len(stages):
                idx += 1
                t_sep = t
                vv = state[3:6]
                up = state[0:3]/rn
                fpa_sep = np.arcsin(np.clip(np.dot(vv, up)/max(np.linalg.norm(vv), 1e-6),
                                            -1, 1))
                continue
            else:
                break

        rho, p, T, a_snd = atmosphere(alt)
        mass = current_mass()
        u = steering(state, t, alt, burning)
        u = u/np.linalg.norm(u)

        if burning:
            st = stages[idx]
            thr = st.thrust(p)
            isp = st.isp(p)
            mdot = thr/(G0*isp)
            thr_vec = thr*u
        else:
            thr, mdot, thr_vec = 0.0, 0.0, np.zeros(3)

        # ---- บันทึกข้อมูล ----
        if t >= next_out - 1e-9:
            v_rel = state[3:6] - np.cross(np.array([0, 0, OMEGA_E]), state[0:3])
            vr = np.linalg.norm(v_rel)
            up = state[0:3]/rn
            fpa = np.degrees(np.arcsin(np.clip(np.dot(v_rel, up)/max(vr, 1e-6), -1, 1)))
            rows.append(dict(
                t=t, x=state[0], y=state[1], z=state[2],
                vx=state[3], vy=state[4], vz=state[5],
                lat=lat_d, lon=lon_d, alt_km=alt/1000.0,
                v_inertial=np.linalg.norm(state[3:6]), v_relative=vr,
                mach=vr/a_snd, q_kPa=0.5*rho*vr*vr/1000.0,
                fpa_deg=fpa, mass=mass, thrust_kN=thr/1000.0,
                acc_g=np.linalg.norm(thr_vec)/mass/G0,
                stage=stages[idx].name if idx < len(stages) else "coast"))
            next_out += dt_out

        # ---- ตัดเครื่องเมื่อ apogee ถึงเป้าหมาย ----
        if idx >= 1 and alt > 60000:
            if apoapsis_radius(state[0:3], state[3:6]) >= target_r:
                break

        # ---- RK4 ----
        f = lambda y: deriv(y, mass, thr_vec, alt)
        k1 = f(state)
        k2 = f(state + 0.5*dt*k1)
        k3 = f(state + 0.5*dt*k2)
        k4 = f(state + dt*k3)
        state = state + (dt/6.0)*(k1 + 2*k2 + 2*k3 + k4)

        if burning:
            prop_left[idx] -= mdot*dt
            stage_time[idx] += dt
        t += dt

    df = pd.DataFrame(rows)
    if verbose:
        print(f"MECO t={t:.1f}s  alt={df['alt_km'].iloc[-1]:.1f} km  "
              f"v_i={df['v_inertial'].iloc[-1]:.0f} m/s  "
              f"Max-Q={df['q_kPa'].max():.1f} kPa")
    return df, state, t, theta0, (az_r, az_i, v_bonus)


def apoapsis_radius(r, v):
    rn = np.linalg.norm(r)
    vn2 = float(np.dot(v, v))
    energy = vn2/2 - MU/rn
    if energy >= 0:
        return 1e12
    a = -MU/(2*energy)
    h = np.cross(r, v)
    e_vec = np.cross(v, h)/MU - r/rn
    return a*(1 + np.linalg.norm(e_vec))


# ============================================================
# COAST + CIRCULARIZE
# ============================================================
def _two_body_j2(rv):
    r, v = rv[0:3], rv[3:6]
    rn = np.linalg.norm(r)
    zr = r[2]/rn
    j = 1.5*J2*MU*RE**2/rn**5
    a = -MU/rn**3*r + np.array([j*r[0]*(5*zr**2-1),
                                j*r[1]*(5*zr**2-1),
                                j*r[2]*(5*zr**2-3)])
    return np.concatenate([v, a])


def coast_and_circularize(state, t_end, target_alt, dt=1.0,
                          max_coast=7200.0, verbose=True):
    """ปล่อยไหลถึง apogee แล้วเผาเป็นวงกลม — คืน (state6, t_insertion, dv)"""
    y = np.array(state, dtype=float)
    t = 0.0
    target_r = RE + target_alt
    prev_vr = float(np.dot(y[0:3], y[3:6])/np.linalg.norm(y[0:3]))
    while t < max_coast:
        rn = np.linalg.norm(y[0:3])
        if rn >= target_r:
            break
        k1 = _two_body_j2(y)
        k2 = _two_body_j2(y + 0.5*dt*k1)
        k3 = _two_body_j2(y + 0.5*dt*k2)
        k4 = _two_body_j2(y + dt*k3)
        y = y + (dt/6.0)*(k1 + 2*k2 + 2*k3 + k4)
        t += dt
        vr = float(np.dot(y[0:3], y[3:6])/np.linalg.norm(y[0:3]))
        if prev_vr > 0 and vr <= 0:
            break
        prev_vr = vr

    r, v = y[0:3], y[3:6]
    rn = np.linalg.norm(r)
    up = r/rn
    v_h = v - np.dot(v, up)*up
    nh = np.linalg.norm(v_h)
    h_hat = v_h/nh if nh > 1e-6 else v/np.linalg.norm(v)
    v_circ = np.sqrt(MU/rn)
    v_new = v_circ*h_hat
    dv = float(np.linalg.norm(v_new - v))
    st6 = np.concatenate([r, v_new])
    if verbose:
        print(f"Circularize @ {(rn-RE)/1000:.1f} km  Δv={dv:.0f} m/s  coast={t:.0f}s")
    return st6, t_end + t, dv


# ============================================================
# ORBITAL ELEMENTS
# ============================================================
def orbital_elements(r, v) -> Dict[str, float]:
    r = np.asarray(r, float); v = np.asarray(v, float)
    rn = np.linalg.norm(r); vn = np.linalg.norm(v)
    h = np.cross(r, v); hn = np.linalg.norm(h)
    n = np.cross(Z_AXIS, h); nn = np.linalg.norm(n)
    e_vec = (np.cross(v, h)/MU) - r/rn
    e = float(np.linalg.norm(e_vec))
    energy = vn*vn/2 - MU/rn
    a = -MU/(2*energy)
    inc = np.arccos(np.clip(h[2]/hn, -1, 1))
    raan = np.arctan2(n[1], n[0]) if nn > 1e-9 else 0.0
    if nn > 1e-9 and e > 1e-9:
        argp = np.arccos(np.clip(np.dot(n, e_vec)/(nn*e), -1, 1))
        if e_vec[2] < 0: argp = 2*np.pi - argp
    else:
        argp = 0.0
    if e > 1e-9:
        ta = np.arccos(np.clip(np.dot(e_vec, r)/(e*rn), -1, 1))
        if np.dot(r, v) < 0: ta = 2*np.pi - ta
    else:
        ta = np.arctan2(np.dot(r, np.cross(h, n))/hn, np.dot(r, n)) if nn > 1e-9 else 0.0
    period = 2*np.pi*np.sqrt(a**3/MU)
    return dict(
        a_km=a/1000.0, e=e, inc_deg=float(inc*R2D),
        raan_deg=float(raan*R2D % 360.0), argp_deg=float(argp*R2D % 360.0),
        ta_deg=float(ta*R2D % 360.0),
        perigee_km=(a*(1-e)-RE)/1000.0, apogee_km=(a*(1+e)-RE)/1000.0,
        period_min=period/60.0, v_now_mps=float(vn),
        alt_now_km=(rn-RE)/1000.0)


# ============================================================
# ORBIT PROPAGATION (ground track)
# ============================================================
def propagate_orbit(state6, t0, theta0, duration=6000.0, dt=15.0):
    y = np.array(state6, dtype=float)
    rows, t = [], 0.0
    n_steps = int(duration/dt) + 1
    for _ in range(n_steps):
        lat, lon, alt = eci_to_geodetic(y[0:3], theta0 + OMEGA_E*(t0 + t))
        rows.append(dict(t=t0+t, x=y[0], y=y[1], z=y[2],
                         vx=y[3], vy=y[4], vz=y[5],
                         lat=lat, lon=lon, alt_km=alt/1000.0,
                         v_inertial=float(np.linalg.norm(y[3:6]))))
        k1 = _two_body_j2(y)
        k2 = _two_body_j2(y + 0.5*dt*k1)
        k3 = _two_body_j2(y + 0.5*dt*k2)
        k4 = _two_body_j2(y + dt*k3)
        y = y + (dt/6.0)*(k1 + 2*k2 + 2*k3 + k4)
        t += dt
    return pd.DataFrame(rows)


# ============================================================
# LOOK ANGLES (สำหรับผู้สังเกต / ช่างภาพ)
# ============================================================
def look_angles(df, obs_lat, obs_lon, obs_alt, launch_jd, theta0):
    obs_ecef = geodetic_to_ecef(obs_lat, obs_lon, obs_alt)
    rows = []
    for row in df.itertuples():
        t = row.t
        th = theta0 + OMEGA_E*t
        c, s = np.cos(th), np.sin(th)
        obs = np.array([c*obs_ecef[0] - s*obs_ecef[1],
                        s*obs_ecef[0] + c*obs_ecef[1], obs_ecef[2]])
        rk = np.array([row.x, row.y, row.z])
        d = rk - obs
        rng = np.linalg.norm(d)
        e, n, up = enu_basis(obs)
        de, dn, du = np.dot(d, e), np.dot(d, n), np.dot(d, up)
        az = np.degrees(np.arctan2(de, dn)) % 360.0
        el = np.degrees(np.arcsin(np.clip(du/max(rng, 1e-6), -1, 1)))

        jd = launch_jd + t/86400.0
        sun = sun_unit_eci(jd)
        proj = float(np.dot(rk, sun))
        perp = np.linalg.norm(rk - proj*sun)
        sunlit = bool(proj > 0 or perp > RE)
        sun_el = np.degrees(np.arcsin(np.clip(np.dot(sun, obs/np.linalg.norm(obs)),
                                              -1, 1)))
        rows.append(dict(t=t, az_deg=az, el_deg=el, range_km=rng/1000.0,
                         alt_km=row.alt_km, sun_el_deg=sun_el,
                         rocket_sunlit=sunlit,
                         photo_window=bool(sunlit and sun_el < -4.0)))
    out = pd.DataFrame(rows)
    if len(out) > 1:
        du_ = np.gradient(np.unwrap(np.radians(out['az_deg'].values)))
        de_ = np.gradient(np.radians(out['el_deg'].values))
        dt_ = np.gradient(out['t'].values)
        cs = np.cos(np.radians(out['el_deg'].values))
        out['angular_rate'] = np.degrees(np.sqrt((du_*cs)**2 + de_**2))/np.maximum(dt_, 1e-6)
    else:
        out['angular_rate'] = 0.0
    return out


def photo_report(look: pd.DataFrame, min_elev: float = 5.0) -> str:
    vis = look[look['el_deg'] > min_elev]
    L = []
    L.append("=" * 58)
    L.append("  รายงานสำหรับการถ่ายภาพ / สังเกตการณ์")
    L.append("=" * 58)
    if vis.empty:
        L.append(f"  ❌ จรวดไม่ขึ้นเหนือมุมเงย {min_elev}° จากจุดนี้")
        return "\n".join(L)
    a = vis.iloc[0]; b = vis.iloc[-1]
    pk = vis.loc[vis['el_deg'].idxmax()]
    cl = vis.loc[vis['range_km'].idxmin()]
    L.append(f"  เห็นครั้งแรก   T+{a.t:7.1f} s   az {a.az_deg:6.1f}°  el {a.el_deg:5.1f}°")
    L.append(f"  มุมเงยสูงสุด   T+{pk.t:7.1f} s   az {pk.az_deg:6.1f}°  el {pk.el_deg:5.1f}°")
    L.append(f"  ระยะใกล้สุด    T+{cl.t:7.1f} s   {cl.range_km:6.1f} km  el {cl.el_deg:5.1f}°")
    L.append(f"  เห็นครั้งสุดท้าย T+{b.t:7.1f} s   az {b.az_deg:6.1f}°  el {b.el_deg:5.1f}°")
    L.append(f"  ระยะเวลาที่เห็น  {b.t - a.t:.0f} s")

    L.append("-" * 58)

    L.append(f"  ช่วง azimuth   {vis['az_deg'].min():.1f}° → {vis['az_deg'].max():.1f}°")

    L.append(f"  อัตราเคลื่อนที่สูงสุด {vis['angular_rate'].max():.2f} °/s")

    lit = vis['rocket_sunlit'].mean()*100

    win = vis['photo_window'].mean()*100

    L.append(f"  จรวดโดนแสงแดด  {lit:.0f}% ของเวลาที่เห็น")

    L.append(f"  ช่วง twilight สวย {win:.0f}% ของเวลาที่เห็น"

             + ("  ⭐ เงื่อนไขดีมาก" if win > 40 else ""))

    L.append("=" * 58)

    return "\n".join(L)


# ============================================================

# AIRSPACE CROSSINGS

# ============================================================

def _in_poly(lat, lon, poly):

    inside = False

    n = len(poly)

    for i in range(n):

        y1, x1 = poly[i]

        y2, x2 = poly[(i+1) % n]

        if (x1 > lon) != (x2 > lon):

            yi = (y2-y1)*(lon-x1)/(x2-x1) + y1

            if lat < yi:

                inside = not inside

    return inside

def airspace_crossings(df, regions: Dict[str, list],

                       max_alt_km: Optional[float] = None) -> pd.DataFrame:

    d = df.sort_values('t').reset_index(drop=True)

    out = []

    for name, poly in regions.items():

        inside = False

        seg = []

        for row in d.itertuples():

            if max_alt_km and row.alt_km > max_alt_km:

                hit = False

            else:

                hit = _in_poly(row.lat, row.lon, poly)

            if hit and not inside:

                inside = True

                seg = [row]

            elif hit and inside:

                seg.append(row)

            elif not hit and inside:

                inside = False

                if seg:

                    out.append(_seg_row(name, seg))

                seg = []

        if inside and seg:

            out.append(_seg_row(name, seg))

    return pd.DataFrame(out)



def _seg_row(name, seg):

    alts = [s.alt_km for s in seg]

    return dict(region=name, t_enter=seg[0].t, t_exit=seg[-1].t,

                duration_s=seg[-1].t - seg[0].t,

                lat_enter=seg[0].lat, lon_enter=seg[0].lon,

                lat_exit=seg[-1].lat, lon_exit=seg[-1].lon,

                alt_min_km=min(alts), alt_max_km=max(alts))


# ============================================================

# DEMO

# ============================================================

if __name__ == "__main__":

    f9 = Vehicle(

        stages=[

            Stage("Stage 1", 7607e3, 8227e3, 283, 312, 411000, 25600, 162, 10.52),

            Stage("Stage 2", 934e3, 934e3, 348, 348, 107500, 4000, 397, 10.52),

        ], payload=15000, fairing_mass=1900, fairing_jettison_alt=110e3)


    m = Mission(site_lat=28.5619, site_lon=-80.5772, site_alt=10,

                target_alt=550e3, target_inc=53.0, launch_jd=2460600.5,

                vertical_time=10, kick_angle=6.5, kick_duration=14)


    asc, st, te, th0, az = simulate_ascent(f9, m)

    print(f"Azimuth  rot={az[0]:.1f}°  inert={az[1]:.1f}°  bonus={az[2]:.0f} m/s")

    st6, ti, dv = coast_and_circularize(st, te, m.target_alt)

    el = orbital_elements(st6[0:3], st6[3:6])

    print({k: round(v, 2) for k, v in el.items()})

    orb = propagate_orbit(st6, ti, th0, duration=3*el['period_min']*60, dt=15)

    look = look_angles(asc, 28.40, -80.60, 5, m.launch_jd, th0)

    print(photo_report(look, 5.0))
