"""
app.py — Streamlit UI สำหรับ rocket_planner
รัน: streamlit run app.py
"""
import io
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

import rocket_planner as rp

st.set_page_config(page_title="Rocket Planner", page_icon="🚀", layout="wide")

# ============================================================
# PRESETS
# ============================================================
PRESETS = {
    "Falcon 9 (LEO)": dict(
        stages=[
            dict(name="Stage 1", thrust_sl=7607.0, thrust_vac=8227.0, isp_sl=283.0,
                 isp_vac=312.0, prop_mass=411000.0, dry_mass=25600.0,
                 burn_time=162.0, area=10.52),
            dict(name="Stage 2", thrust_sl=934.0, thrust_vac=934.0, isp_sl=348.0,
                 isp_vac=348.0, prop_mass=107500.0, dry_mass=4000.0,
                 burn_time=397.0, area=10.52),
        ],
        payload=15000.0, fairing_mass=1900.0, fairing_alt=110.0,
        site_lat=28.5619, site_lon=-80.5772, site_alt=10.0,
        target_alt=550.0, target_inc=53.0,
        vertical_time=10.0, kick_angle=6.5, kick_duration=14.0),

    "Electron (SSO)": dict(
        stages=[
            dict(name="Stage 1", thrust_sl=162.0, thrust_vac=192.0, isp_sl=303.0,
                 isp_vac=311.0, prop_mass=9250.0, dry_mass=950.0,
                 burn_time=154.0, area=1.13),
            dict(name="Stage 2", thrust_sl=25.8, thrust_vac=25.8, isp_sl=343.0,
                 isp_vac=343.0, prop_mass=2050.0, dry_mass=250.0,
                 burn_time=320.0, area=1.13),
        ],
        payload=200.0, fairing_mass=50.0, fairing_alt=80.0,
        site_lat=-39.2617, site_lon=177.8649, site_alt=20.0,
        target_alt=500.0, target_inc=97.4,
        vertical_time=8.0, kick_angle=7.0, kick_duration=12.0),

    "Small launcher (custom)": dict(
        stages=[
            dict(name="Stage 1", thrust_sl=500.0, thrust_vac=560.0, isp_sl=270.0,
                 isp_vac=295.0, prop_mass=28000.0, dry_mass=2200.0,
                 burn_time=150.0, area=3.5),
            dict(name="Stage 2", thrust_sl=70.0, thrust_vac=70.0, isp_sl=330.0,
                 isp_vac=330.0, prop_mass=6000.0, dry_mass=600.0,
                 burn_time=300.0, area=3.5),
        ],
        payload=500.0, fairing_mass=120.0, fairing_alt=100.0,
        site_lat=12.5, site_lon=99.9, site_alt=5.0,
        target_alt=450.0, target_inc=30.0,
        vertical_time=10.0, kick_angle=6.0, kick_duration=15.0),
}


def jd_from_date(y, mo, d, hh, mm, ss):
    """ปฏิทินสากล → Julian Date (UTC)"""
    if mo <= 2:
        y, mo = y - 1, mo + 12
    A = y // 100
    B = 2 - A + A // 4
    jd = int(365.25*(y + 4716)) + int(30.6001*(mo + 1)) + d + B - 1524.5
    return jd + (hh + mm/60.0 + ss/3600.0)/24.0


def make_kml(df, name="Trajectory", color="ff00aaff"):
    pts = "\n".join(f"{r.lon:.6f},{r.lat:.6f},{r.alt_km*1000:.1f}"
                    for r in df.itertuples())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<name>{name}</name>
<Style id="tr"><LineStyle><color>{color}</color><width>3</width></LineStyle></Style>
<Placemark><name>{name}</name><styleUrl>#tr</styleUrl>
<LineString><altitudeMode>absolute</altitudeMode><extrude>1</extrude>
<coordinates>
{pts}
</coordinates></LineString></Placemark>
</Document></kml>"""


def split_dateline(lat, lon):
    """ตัดเส้นเมื่อข้ามเส้นแบ่งวัน ±180° เพื่อไม่ให้กราฟลากพาดจอ"""
    segs, s_lat, s_lon = [], [lat[0]], [lon[0]]
    for i in range(1, len(lon)):
        if abs(lon[i] - lon[i-1]) > 180:
            segs.append((s_lat, s_lon))
            s_lat, s_lon = [], []
        s_lat.append(lat[i]); s_lon.append(lon[i])
    segs.append((s_lat, s_lon))
    return segs


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("🚀 ตั้งค่าภารกิจ")

up = st.sidebar.file_uploader("โหลด preset (.json)", type="json")
if up is not None and not st.session_state.get("_loaded"):
    try:
        st.session_state["cfg"] = json.load(up)
        st.session_state["_loaded"] = True
        st.sidebar.success("โหลด preset สำเร็จ")
    except Exception as e:
        st.sidebar.error(f"ไฟล์ไม่ถูกต้อง: {e}")

pname = st.sidebar.selectbox("จรวดต้นแบบ", list(PRESETS.keys()))
base = st.session_state.get("cfg") or PRESETS[pname]

with st.sidebar.expander("📍 ฐานปล่อย", expanded=True):
    site_lat = st.number_input("ละติจูด (°)", -90.0, 90.0,
                               float(base["site_lat"]), 0.0001, format="%.4f")
    site_lon = st.number_input("ลองจิจูด (°)", -180.0, 180.0,
                               float(base["site_lon"]), 0.0001, format="%.4f")
    site_alt = st.number_input("ความสูงฐาน (m)", -500.0, 5000.0,
                               float(base["site_alt"]), 1.0)

with st.sidebar.expander("🎯 วงโคจรเป้าหมาย", expanded=True):
    target_alt = st.number_input("ความสูงวงโคจร (km)", 120.0, 2000.0,
                                 float(base["target_alt"]), 10.0)
    target_inc = st.number_input("ความเอียง (°)", 0.0, 180.0,
                                 float(base["target_inc"]), 0.1)
    east = st.checkbox("ยิงไปทางตะวันออก (ascending)", value=True)

with st.sidebar.expander("🕐 เวลาปล่อย (UTC)"):
    c1, c2, c3 = st.columns(3)
    yy = c1.number_input("ปี", 2020, 2100, 2026)
    mo = c2.number_input("เดือน", 1, 12, 9)
    dd = c3.number_input("วัน", 1, 31, 15)
    c4, c5 = st.columns(2)
    hh = c4.number_input("ชม.", 0, 23, 22)
    mi = c5.number_input("นาที", 0, 59, 30)
    jd = jd_from_date(int(yy), int(mo), int(dd), int(hh), int(mi), 0)
    st.caption(f"JD = {jd:.5f}")

with st.sidebar.expander("🛩️ โปรไฟล์การไต่"):
    vt = st.slider("ไต่ตรง (s)", 0.0, 30.0, float(base["vertical_time"]), 0.5)
    ka = st.slider("มุม pitch kick (°)", 0.0, 20.0, float(base["kick_angle"]), 0.1)
    kd = st.slider("ระยะเวลา kick (s)", 1.0, 40.0, float(base["kick_duration"]), 0.5)

with st.sidebar.expander("🛰️ ยานพาหนะ", expanded=False):
    payload = st.number_input("Payload (kg)", 0.0, 100000.0,
                              float(base["payload"]), 10.0)
    fmass = st.number_input("Fairing (kg)", 0.0, 10000.0,
                            float(base["fairing_mass"]), 10.0)
    falt = st.number_input("ปลด fairing ที่ (km)", 40.0, 200.0,
                           float(base["fairing_alt"]), 5.0)
    nstage = st.radio("จำนวนสเตจ", [1, 2], index=1, horizontal=True)

    stages_cfg = []
    for i in range(nstage):
        d = base["stages"][i] if i < len(base["stages"]) else base["stages"][-1]
        st.markdown(f"**สเตจ {i+1}**")
        t_sl = st.number_input(f"แรงขับ SL (kN) #{i+1}", 1.0, 20000.0,
                               float(d["thrust_sl"]), 1.0, key=f"tsl{i}")
        t_vc = st.number_input(f"แรงขับ Vac (kN) #{i+1}", 1.0, 20000.0,
                               float(d["thrust_vac"]), 1.0, key=f"tvc{i}")
        i_sl = st.number_input(f"Isp SL (s) #{i+1}", 100.0, 500.0,
                               float(d["isp_sl"]), 1.0, key=f"isl{i}")
        i_vc = st.number_input(f"Isp Vac (s) #{i+1}", 100.0, 500.0,
                               float(d["isp_vac"]), 1.0, key=f"ivc{i}")
        m_p = st.number_input(f"เชื้อเพลิง (kg) #{i+1}", 10.0, 1e6,
                              float(d["prop_mass"]), 100.0, key=f"mp{i}")
        m_d = st.number_input(f"มวลแห้ง (kg) #{i+1}", 10.0, 2e5,
                              float(d["dry_mass"]), 10.0, key=f"md{i}")
        b_t = st.number_input(f"เวลาเผาสูงสุด (s) #{i+1}", 5.0, 1000.0,
                              float(d["burn_time"]), 1.0, key=f"bt{i}")
        ar = st.number_input(f"พื้นที่หน้าตัด (m²) #{i+1}", 0.1, 100.0,
                             float(d["area"]), 0.01, key=f"ar{i}")
        stages_cfg.append(dict(name=f"Stage {i+1}", thrust_sl=t_sl, thrust_vac=t_vc,
                               isp_sl=i_sl, isp_vac=i_vc, prop_mass=m_p,
                               dry_mass=m_d, burn_time=b_t, area=ar))

with st.sidebar.expander("📷 จุดสังเกตการณ์", expanded=True):
    same = st.checkbox("ใช้พิกัดเดียวกับฐานปล่อย", value=False)
    if same:
        obs_lat, obs_lon, obs_alt = site_lat, site_lon, site_alt
    else:
        obs_lat = st.number_input("ละติจูดผู้ชม (°)", -90.0, 90.0,
                                  float(site_lat) - 0.15, 0.0001, format="%.4f")
        obs_lon = st.number_input("ลองจิจูดผู้ชม (°)", -180.0, 180.0,
                                  float(site_lon) - 0.05, 0.0001, format="%.4f")
        obs_alt = st.number_input("ความสูงผู้ชม (m)", -500.0, 5000.0, 5.0, 1.0)
    min_el = st.slider("มุมเงยต่ำสุดที่มองเห็น (°)", 0.0, 30.0, 5.0, 0.5)

with st.sidebar.expander("⚙️ ความละเอียด"):
    dt = st.select_slider("timestep (s)", [0.02, 0.05, 0.1, 0.2], value=0.05)
    n_orbit = st.slider("จำนวนรอบวงโคจรที่พล็อต", 1, 6, 3)

run = st.sidebar.button("▶️ คำนวณ", type="primary", use_container_width=True)

cfg = dict(stages=stages_cfg, payload=payload, fairing_mass=fmass,
           fairing_alt=falt, site_lat=site_lat, site_lon=site_lon,
           site_alt=site_alt, target_alt=target_alt, target_inc=target_inc,
           vertical_time=vt, kick_angle=ka, kick_duration=kd)
st.sidebar.download_button("💾 บันทึก preset",
                           json.dumps(cfg, indent=2, ensure_ascii=False),
                           "preset.json", "application/json",
                           use_container_width=True)

# ============================================================
# คำนวณ
# ============================================================
st.title("🚀 Rocket Ascent & Observation Planner")

if run:
    with st.spinner("กำลังจำลองการไต่..."):
        veh = rp.Vehicle(
            stages=[rp.Stage(s["name"], s["thrust_sl"]*1e3, s["thrust_vac"]*1e3,
                             s["isp_sl"], s["isp_vac"], s["prop_mass"],
                             s["dry_mass"], s["burn_time"], s["area"])
                    for s in stages_cfg],
            payload=payload, fairing_mass=fmass, fairing_jettison_alt=falt*1e3)
        mis = rp.Mission(site_lat=site_lat, site_lon=site_lon, site_alt=site_alt,
                         target_alt=target_alt*1e3, target_inc=target_inc,
                         launch_jd=jd, vertical_time=vt, kick_angle=ka,
                         kick_duration=kd, ascend_east=east)
        try:
            asc, st6, t_end, th0, azi = rp.simulate_ascent(
                veh, mis, dt=dt, dt_out=0.5, verbose=False)
            orb6, t_ins, dv = rp.coast_and_circularize(
                st6, t_end, mis.target_alt, verbose=False)
            el = rp.orbital_elements(orb6[0:3], orb6[3:6])
            orb = rp.propagate_orbit(orb6, t_ins, th0,
                                     duration=n_orbit*el["period_min"]*60, dt=15)
            look = rp.look_angles(asc, obs_lat, obs_lon, obs_alt, jd, th0)
            st.session_state["res"] = dict(asc=asc, orb=orb, look=look, el=el,
                                           azi=azi, dv=dv, t_end=t_end,
                                           gross=veh.gross_mass(), jd=jd)
        except Exception as e:
            st.error(f"คำนวณไม่สำเร็จ: {e}")

if "res" not in st.session_state:
    st.info("👈 ตั้งค่าในเมนูด้านซ้าย แล้วกด **คำนวณ**  \n"
            "บนมือถือ: แตะไอคอน **»** มุมซ้ายบนเพื่อเปิดเมนู")
    st.stop()

R = st.session_state["res"]
asc, orb, look, el = R["asc"], R["orb"], R["look"], R["el"]

# ============================================================
# TABS
# ============================================================
t1, t2, t3, t4, t5 = st.tabs(
    ["📊 ภาพรวม", "📈 กราฟไต่", "🌍 Ground track", "📷 สำหรับช่างภาพ", "💾 ส่งออก"])

with t1:
    c = st.columns(4)
    c[0].metric("มวลรวมตอนปล่อย", f"{R['gross']/1000:,.1f} t")
    c[1].metric("MECO", f"T+{R['t_end']:.0f} s")
    c[2].metric("Max-Q", f"{asc['q_kPa'].max():.1f} kPa",
                f"T+{asc.loc[asc['q_kPa'].idxmax(),'t']:.0f}s")
    c[3].metric("G สูงสุด", f"{asc['acc_g'].max():.2f} g")

    c = st.columns(4)
    c[0].metric("Perigee", f"{el['perigee_km']:.1f} km")
    c[1].metric("Apogee", f"{el['apogee_km']:.1f} km")
    c[2].metric("ความเอียง", f"{el['inc_deg']:.2f}°")
    c[3].metric("คาบโคจร", f"{el['period_min']:.1f} min")

    c = st.columns(4)
    c[0].metric("Azimuth (หมุนตามโลก)", f"{R['azi'][0]:.1f}°")
    c[1].metric("Azimuth (เฉื่อย)", f"{R['azi'][1]:.1f}°")
    c[2].metric("โบนัสจากโลกหมุน", f"{R['azi'][2]:.0f} m/s")
    c[3].metric("Δv วงกลม", f"{R['dv']:.0f} m/s")

    st.markdown("### ลำดับเหตุการณ์")
    ev = []
    for s in asc["stage"].unique():
        sub = asc[asc["stage"] == s]
        ev.append(dict(เหตุการณ์=f"{s} จุดติด", **{
            "T+ (s)": round(sub['t'].iloc[0], 1),
            "alt (km)": round(sub['alt_km'].iloc[0], 1),
            "v (m/s)": round(sub['v_relative'].iloc[0], 0)}))
        ev.append(dict(เหตุการณ์=f"{s} ดับ", **{
            "T+ (s)": round(sub['t'].iloc[-1], 1),
            "alt (km)": round(sub['alt_km'].iloc[-1], 1),
            "v (m/s)": round(sub['v_relative'].iloc[-1], 0)}))
    mq = asc.loc[asc["q_kPa"].idxmax()]
    ev.append({"เหตุการณ์": "Max-Q", "T+ (s)": round(mq.t, 1),
               "alt (km)": round(mq.alt_km, 1), "v (m/s)": round(mq.v_relative, 0)})
    st.dataframe(pd.DataFrame(ev).sort_values("T+ (s)"),
                 use_container_width=True, hide_index=True)

with t2:
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    ax[0, 0].plot(asc["t"], asc["alt_km"], lw=2)
    ax[0, 0].set_title("ความสูง"); ax[0, 0].set_ylabel("km")
    ax[0, 1].plot(asc["t"], asc["v_inertial"], lw=2, label="เฉื่อย")
    ax[0, 1].plot(asc["t"], asc["v_relative"], lw=2, ls="--", label="สัมพัทธ์")
    ax[0, 1].set_title("ความเร็ว"); ax[0, 1].set_ylabel("m/s"); ax[0, 1].legend()
    ax[1, 0].plot(asc["t"], asc["q_kPa"], lw=2, color="crimson")
    ax[1, 0].set_title("แรงดันพลศาสตร์"); ax[1, 0].set_ylabel("kPa")
    ax[1, 1].plot(asc["t"], asc["fpa_deg"], lw=2, color="green")
    ax[1, 1].axhline(0, color="gray", lw=0.8)
    ax[1, 1].set_title("Flight path angle"); ax[1, 1].set_ylabel("°")
    for a in ax.flat:
        a.grid(alpha=0.3); a.set_xlabel("T+ (s)")
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)

    fig2, a2 = plt.subplots(figsize=(11, 3))
    a2.plot(asc["t"], asc["mach"], lw=2, color="purple")
    a2.axhline(1, color="red", ls="--", lw=1, label="Mach 1")
    a2.set_xlabel("T+ (s)"); a2.set_ylabel("Mach"); a2.grid(alpha=0.3); a2.legend()
    st.pyplot(fig2, use_container_width=True)

with t3:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for la, lo in split_dateline(orb["lat"].values, orb["lon"].values):
        ax.plot(lo, la, lw=1.2, color="tab:blue", alpha=0.85)
    ax.plot(asc["lon"], asc["lat"], lw=3, color="orangered", label="ช่วงไต่")
    ax.plot(site_lon, site_lat, "^", ms=11, color="black", label="ฐานปล่อย")
    ax.plot(obs_lon, obs_lat, "*", ms=14, color="gold",
            mec="black", label="จุดสังเกต")
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
    ax.grid(alpha=0.3); ax.legend(loc="upper right", fontsize=8)
    ax.set_xlabel("ลองจิจูด (°)"); ax.set_ylabel("ละติจูด (°)")
    ax.set_title(f"Ground track — {n_orbit} รอบ")
    st.pyplot(fig, use_container_width=True)

    st.markdown("### เส้นทางช่วงไต่ (ซูม)")
    fig3, a3 = plt.subplots(figsize=(11, 4))
    sc = a3.scatter(asc["lon"], asc["lat"], c=asc["alt_km"], cmap="plasma", s=8)
    a3.plot(site_lon, site_lat, "^", ms=11, color="black")
    plt.colorbar(sc, ax=a3, label="ความสูง (km)")
    a3.grid(alpha=0.3); a3.set_xlabel("ลองจิจูด"); a3.set_ylabel("ละติจูด")
    st.pyplot(fig3, use_container_width=True)

with t4:
    st.code(rp.photo_report(look, min_el), language=None)
    vis = look[look["el_deg"] > min_el]
    if vis.empty:
        st.warning("จรวดไม่ขึ้นเหนือมุมเงยที่กำหนดจากจุดนี้ — ลองลดค่ามุมเงยต่ำสุด")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].plot(vis["t"], vis["el_deg"], lw=2)
        ax[0].set_title("มุมเงย"); ax[0].set_ylabel("°")
        ax[1].plot(vis["t"], vis["az_deg"], lw=2, color="teal")
        ax[1].set_title("ทิศ (azimuth)"); ax[1].set_ylabel("°")
        for a in ax:
            a.grid(alpha=0.3); a.set_xlabel("T+ (s)")
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)

        st.markdown("### แผนผังท้องฟ้า (polar)")
        figp = plt.figure(figsize=(5.5, 5.5))
        ap = figp.add_subplot(111, projection="polar")
        ap.set_theta_zero_location("N"); ap.set_theta_direction(-1)
        ap.plot(np.radians(vis["az_deg"]), 90 - vis["el_deg"], lw=2.5,
                color="orangered")
        ap.set_rmax(90); ap.set_rticks([0, 30, 60, 90])
        ap.set_yticklabels(["90°", "60°", "30°", "0°"])
        ap.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"])
        ap.grid(alpha=0.4)
        st.pyplot(figp, use_container_width=False)

        st.markdown("### ตารางมุมเล็ง (ทุก 10 วินาที)")
        tb = vis[vis["t"] % 10 < 0.6][
            ["t", "az_deg", "el_deg", "range_km", "alt_km", "angular_rate"]].copy()
        tb.columns = ["T+ (s)", "ทิศ (°)", "มุมเงย (°)", "ระยะ (km)",
                      "สูง (km)", "°/s"]
        st.dataframe(tb.round(2), use_container_width=True, hide_index=True)

with t5:
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ ascent.csv", asc.to_csv(index=False).encode(),
                       "ascent.csv", "text/csv", use_container_width=True)
    c2.download_button("⬇️ look_angles.csv", look.to_csv(index=False).encode(),
                       "look_angles.csv", "text/csv", use_container_width=True)
    c1.download_button("⬇️ orbit.csv", orb.to_csv(index=False).encode(),
                       "orbit.csv", "text/csv", use_container_width=True)
    c2.download_button("⬇️ trajectory.kml",
                       make_kml(asc, "Ascent").encode(),
                       "trajectory.kml",
                       "application/vnd.google-earth.kml+xml",
                       use_container_width=True)
    st.download_button("⬇️ elements.json",
                       json.dumps(el, indent=2).encode(),
                       "elements.json", "application/json",
                       use_container_width=True)
    st.caption("เปิด trajectory.kml ด้วย Google Earth เพื่อดูเส้นทางลอยเหนือแผนที่จริง")
