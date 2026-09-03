"""
app.py — Streamlit UI สำหรับ rocket_planner
รัน: streamlit run app.py
[FIX] ฟอนต์ไทยในกราฟ matplotlib + ป้ายอังกฤษอัตโนมัติเมื่อไม่มีฟอนต์
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import streamlit as st

import rocket_planner as rp
import booster as bst

# ============================================================
# ฟอนต์ไทยสำหรับ matplotlib (แก้ป้าย "ททททท")
# ============================================================
def _setup_thai_font():
    names = {f.name for f in fm.fontManager.ttflist}
    for n in ["Noto Sans Thai", "Noto Sans Thai UI", "Noto Sans Thai Looped",
              "Sarabun", "TH Sarabun New", "TH Sarabun", "Garuda", "Loma",
              "Sawasdee", "Waree", "Umpush", "Norasi", "Kinnari",
              "Leelawadee UI", "DokChampa", "Angsana New", "Cordia New", "Tahoma"]:
        if n in names:
            return n
    d = os.path.join(os.path.expanduser("~"), ".cache", "rp_fonts")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    p = os.path.join(d, "NotoSansThai.ttf")
    if not os.path.exists(p):
        urls = ["https://raw.githubusercontent.com/google/fonts/main/ofl/notosansthai/NotoSansThai%5Bwdth%2Cwght%5D.ttf",
                "https://github.com/google/fonts/raw/main/ofl/notosansthai/NotoSansThai%5Bwdth%2Cwght%5D.ttf"]
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    with open(p, "wb") as f:
                        f.write(r.read())
                break
            except Exception:
                continue
    if os.path.exists(p):
        try:
            fm.fontManager.addfont(p)
            return fm.FontProperties(fname=p).get_name()
        except Exception:
            return None
    return None

THAI_FONT = _setup_thai_font()
THAI_OK = THAI_FONT is not None
if THAI_OK:
    plt.rcParams["font.family"] = THAI_FONT
plt.rcParams["axes.unicode_minus"] = False

def T(thai, eng):
    return thai if THAI_OK else eng

st.set_page_config(page_title="Rocket Planner", page_icon="🚀", layout="wide")

# ============================================================
# PRESETS
# ============================================================
PRESETS = {
    "GSLV Mk II (GTO-ish)": dict(
        stages=[
            dict(name="S139", thrust_sl=4000.0, thrust_vac=4700.0, isp_sl=240.0,
                 isp_vac=269.0, prop_mass=139000.0, dry_mass=28000.0,
                 burn_time=100.0, area=6.15),
            dict(name="GS2", thrust_sl=750.0, thrust_vac=846.0, isp_sl=280.0,
                 isp_vac=295.0, prop_mass=42000.0, dry_mass=5600.0,
                 burn_time=143.0, area=6.15),
            dict(name="CUS", thrust_sl=60.0, thrust_vac=73.6, isp_sl=450.0,
                 isp_vac=454.0, prop_mass=12500.0, dry_mass=2500.0,
                 burn_time=720.0, area=6.15),
        ],
        payload=2367.0, fairing_mass=1200.0, fairing_alt=115.0,
        site_lat=13.72, site_lon=80.23, site_alt=10.0,
        target_alt=170.0, target_inc=19.35,
        vertical_time=10.0, kick_angle=3.0, kick_duration=12.0,
        use_boost=True,
        boost=dict(cnt=4, tsl=680.0, tvc=762.0, isl=250.0, ivc=262.0,
                   mp=42000.0, md=5600.0, bt=150.0, ig=0.0, jd=2.0, ar=3.46)),
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
st.sidebar.title("🚀 ภารกิจและวงโคจร")
if not THAI_OK:
    st.sidebar.info("ไม่พบฟอนต์ไทย → กราฟจะแสดงป้ายภาษาอังกฤษ (UI ยังเป็นไทย)")

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
stages_base = base.get("stages") or PRESETS["Small launcher (custom)"]["stages"]

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
    launch_jd = jd_from_date(int(yy), int(mo), int(dd), int(hh), int(mi), 0)
    st.caption(f"JD = {launch_jd:.5f}")

with st.sidebar.expander("🛩️ โปรไฟล์การไต่"):
    vt = st.slider("ไต่ตรง (s)", 0.0, 30.0, float(base["vertical_time"]), 0.5)
    ka = st.slider("มุม pitch kick (°)", 0.0, 20.0, float(base["kick_angle"]), 0.1)
    kd = st.slider("ระยะเวลา kick (s)", 1.0, 40.0, float(base["kick_duration"]), 0.5)

with st.sidebar.expander("⚙️ ความละเอียด"):
    dt = st.select_slider("timestep (s)", [0.02, 0.05, 0.1, 0.2], value=0.05)
    n_orbit = st.slider("จำนวนรอบวงโคจรที่พล็อต", 1, 6, 3)

# ============================================================
# MAIN PAGE
# ============================================================
st.title("🚀 Rocket Ascent & Observation Planner")
col_veh, col_obs = st.columns([2, 1])

with col_veh:
    with st.expander("🛰️ ยานพาหนะและสเตจ (Vehicle Setup)", expanded=True):
        c_p, c_f, c_a = st.columns(3)
        payload = c_p.number_input("Payload (kg)", 0.0, 100000.0, float(base["payload"]), 10.0)
        fmass = c_f.number_input("Fairing (kg)", 0.0, 10000.0, float(base["fairing_mass"]), 10.0)
        falt = c_a.number_input("ปลด fairing ที่ (km)", 40.0, 200.0, float(base["fairing_alt"]), 5.0)
        nstage = st.number_input("จำนวนสเตจ", min_value=1, max_value=5,
                                 value=len(stages_base), step=1)
        stages_cfg = []
        for i in range(int(nstage)):
            d = stages_base[i] if i < len(stages_base) else stages_base[-1]
            st.markdown(f"**สเตจ {i+1}**")
            c1, c2, c3, c4 = st.columns(4)
            t_sl = c1.number_input("แรงขับ SL (kN)", 1.0, 20000.0, float(d["thrust_sl"]), 1.0, key=f"tsl{i}")
            t_vc = c2.number_input("แรงขับ Vac (kN)", 1.0, 20000.0, float(d["thrust_vac"]), 1.0, key=f"tvc{i}")
            i_sl = c3.number_input("Isp SL (s)", 100.0, 500.0, float(d["isp_sl"]), 1.0, key=f"isl{i}")
            i_vc = c4.number_input("Isp Vac (s)", 100.0, 500.0, float(d["isp_vac"]), 1.0, key=f"ivc{i}")
            c5, c6, c7, c8 = st.columns(4)
            m_p = c5.number_input("เชื้อเพลิง (kg)", 10.0, 1e6, float(d["prop_mass"]), 100.0, key=f"mp{i}")
            m_d = c6.number_input("มวลแห้ง (kg)", 10.0, 2e5, float(d["dry_mass"]), 10.0, key=f"md{i}")
            b_t = c7.number_input("เวลาเผาสูงสุด (s)", 5.0, 1000.0, float(d["burn_time"]), 1.0, key=f"bt{i}")
            ar = c8.number_input("พื้นที่หน้าตัด (m²)", 0.1, 100.0, float(d["area"]), 0.01, key=f"ar{i}")
            stages_cfg.append(dict(name=f"Stage {i+1}", thrust_sl=t_sl, thrust_vac=t_vc,
                                   isp_sl=i_sl, isp_vac=i_vc, prop_mass=m_p,
                                   dry_mass=m_d, burn_time=b_t, area=ar))
    with st.expander("🧨 Side booster (strap-on)", expanded=False):
        bb = base.get("boost", {})
        use_b = st.checkbox("ติด booster ข้าง", value=bool(base.get("use_boost", False)))
        groups = []
        if use_b:
            ng = st.number_input("จำนวนกลุ่ม booster", 1, 4, int(bb.get("cnt", 1)), 1)
            for i in range(int(ng)):
                st.markdown(f"**— กลุ่มที่ {i+1} —**")
                c1, c2 = st.columns(2)
                nm = c1.text_input("ชื่อ", f"SRB-{i+1}", key=f"bn{i}")
                cnt = c2.number_input("จำนวนตัว", 1, 12, int(bb.get("cnt", 2)), key=f"bc{i}")
                c1, c2 = st.columns(2)
                tsl = c1.number_input("แรงขับ SL (kN/ตัว)", 1.0, 20000.0, float(bb.get("tsl", 1663.0)), key=f"bs{i}")
                tvc = c2.number_input("แรงขับ Vac (kN/ตัว)", 1.0, 20000.0, float(bb.get("tvc", 1850.0)), key=f"bv{i}")
                c1, c2 = st.columns(2)
                isl = c1.number_input("Isp SL (s)", 100.0, 500.0, float(bb.get("isl", 274.0)), key=f"bi{i}")
                ivc = c2.number_input("Isp Vac (s)", 100.0, 500.0, float(bb.get("ivc", 279.0)), key=f"bj{i}")
                c1, c2 = st.columns(2)
                mp = c1.number_input("เชื้อเพลิง (kg/ตัว)", 10.0, 6e5, float(bb.get("mp", 44200.0)), key=f"bp{i}")
                md = c2.number_input("มวลแห้ง (kg/ตัว)", 10.0, 1e5, float(bb.get("md", 4000.0)), key=f"bd{i}")
                c1, c2, c3, c4 = st.columns(4)
                b_bt = c1.number_input("เวลาเผา (s)", 5.0, 400.0, float(bb.get("bt", 94.0)), key=f"b_bt{i}")
                b_ig = c2.number_input("จุดที่ t= (s)", 0.0, 300.0, float(bb.get("ig", 0.0)), key=f"bg{i}")
                b_jd = c3.number_input("หน่วงสลัด (s)", 0.0, 30.0, float(bb.get("jd", 2.0)), key=f"bx{i}")
                b_ar = c4.number_input("หน้าตัด (m²)", 0.05, 50.0, float(bb.get("ar", 1.77)), key=f"ba{i}")
                groups.append(bst.make_group(nm, cnt, tsl, tvc, isl, ivc,
                                             mp, md, b_bt, b_ar, b_ig, b_jd))
            st.divider()
            thr_b = st.slider("Core throttle ขณะมี booster (%)", 20, 100, 100, 5)
            thr_s = st.slider("Core throttle หลังสลัด (%)", 50, 100, 100, 5)
            auto = st.checkbox("คำนวณเวลาเผา core ใหม่อัตโนมัติ", True)
            phases, tlog = bst.build_boost_phases(stages_cfg[0], groups, thr_b, thr_s, auto)
            for w in bst.validate(stages_cfg[0], groups, phases):
                st.warning(w)
            stages_cfg = phases + stages_cfg[1:]
            st.success(f"สร้าง {len(phases)} เฟสจาก core 1 ท่อน")
            st.dataframe([{
                "ช่วง (s)": f"{r['t0']:.0f}–{r['t1']:.0f}",
                "เฟส": r["name"].split(": ")[-1],
                "F_SL (kN)": f"{r['F_sl']:,.0f}",
                "Isp_vac": f"{r['isp_vac']:.0f}",
                "เชื้อเพลิง (t)": f"{r['prop']/1000:.1f}",
                "สลัด (t)": f"{r['jett']/1000:.1f}",
                "Core": r["twr_note"],
            } for r in tlog], use_container_width=True, hide_index=True)

with col_obs:
    with st.expander("📷 จุดสังเกตการณ์", expanded=True):
        same = st.checkbox("ใช้พิกัดเดียวกับฐานปล่อย", value=False)
        if same:
            obs_lat, obs_lon, obs_alt = site_lat, site_lon, site_alt
        else:
            obs_lat = st.number_input("ละติจูดผู้ชม (°)", -90.0, 90.0, 13.6904, 0.0001, format="%.4f")
            obs_lon = st.number_input("ลองจิจูดผู้ชม (°)", -180.0, 180.0, 101.0779, 0.0001, format="%.4f")
            obs_alt = st.number_input("ความสูงผู้ชม (m)", -500.0, 5000.0, 5.0, 1.0)
        min_el = st.slider("มุมเงยต่ำสุดที่มองเห็น (°)", 0.0, 30.0, 5.0, 0.5)

cfg = dict(stages=stages_cfg, payload=payload, fairing_mass=fmass,
           fairing_alt=falt, site_lat=site_lat, site_lon=site_lon,
           site_alt=site_alt, target_alt=target_alt, target_inc=target_inc,
           vertical_time=vt, kick_angle=ka, kick_duration=kd)
st.sidebar.download_button("💾 บันทึก preset",
                           json.dumps(cfg, indent=2, ensure_ascii=False),
                           "preset.json", "application/json",
                           use_container_width=True)
run = st.sidebar.button("▶️ คำนวณจำลองการไต่", type="primary", use_container_width=True)

# ============================================================
# คำนวณ
# ============================================================
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
                         launch_jd=launch_jd, vertical_time=vt, kick_angle=ka,
                         kick_duration=kd, ascend_east=east)
        try:
            asc, st6, t_end, th0, azi = rp.simulate_ascent(
                veh, mis, dt=dt, dt_out=0.5, verbose=False)
            orb6, t_ins, dv = rp.coast_and_circularize(
                st6, t_end, mis.target_alt, verbose=False)
            el = rp.orbital_elements(orb6[0:3], orb6[3:6])
            orb = rp.propagate_orbit(orb6, t_ins, th0,
                                     duration=n_orbit*el["period_min"]*60, dt=15)
            look = rp.look_angles(asc, obs_lat, obs_lon, obs_alt, launch_jd, th0)
            st.session_state["res"] = dict(asc=asc, orb=orb, look=look, el=el,
                                           azi=azi, dv=dv, t_end=t_end,
                                           gross=veh.gross_mass(), jd=launch_jd)
        except Exception as e:
            st.error(f"คำนวณไม่สำเร็จ: {e}")

if "res" not in st.session_state:
    st.info("👈 ปรับแต่งจรวดและพิกัด จากนั้นกด คำนวณจำลองการไต่ ในเมนูด้านซ้าย")
    st.stop()

R = st.session_state["res"]
asc, orb, look, el = R["asc"], R["orb"], R["look"], R["el"]

if abs(el["apogee_km"] - target_alt) > 0.25*target_alt or el["perigee_km"] < 0:
    st.warning(f"⚠️ วงโคจรลัพธ์ (perigee {el['perigee_km']:.0f} × apogee {el['apogee_km']:.0f} km) "
               f" ห่างจากเป้า {target_alt:.0f} km มาก — ตรวจการตั้งค่า")

# ============================================================
# TABS
# ============================================================
st.divider()
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
    ax[0, 0].set_title(T("ความสูง", "Altitude")); ax[0, 0].set_ylabel(T("km", "km"))
    ax[0, 1].plot(asc["t"], asc["v_inertial"], lw=2, label=T("เฉื่อย", "inertial"))
    ax[0, 1].plot(asc["t"], asc["v_relative"], lw=2, ls="--", label=T("สัมพัทธ์", "relative"))
    ax[0, 1].set_title(T("ความเร็ว", "Velocity")); ax[0, 1].set_ylabel(T("m/s", "m/s"))
    ax[0, 1].legend()
    ax[1, 0].plot(asc["t"], asc["q_kPa"], lw=2, color="crimson")
    ax[1, 0].set_title(T("แรงดันพลศาสตร์", "Dynamic pressure"))
    ax[1, 0].set_ylabel(T("kPa", "kPa"))
    ax[1, 1].plot(asc["t"], asc["fpa_deg"], lw=2, color="green")
    ax[1, 1].axhline(0, color="gray", lw=0.8)
    ax[1, 1].set_title(T("มุมวิถีบิน (Flight path angle)", "Flight path angle"))
    ax[1, 1].set_ylabel(T("°", "deg"))
    for a in ax.flat:
        a.grid(alpha=0.3); a.set_xlabel(T("T+ (s)", "T+ (s)"))
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)
    fig2, a2 = plt.subplots(figsize=(11, 3))
    a2.plot(asc["t"], asc["mach"], lw=2, color="purple")
    a2.axhline(1, color="red", ls="--", lw=1, label=T("Mach 1", "Mach 1"))
    a2.set_xlabel(T("T+ (s)", "T+ (s)")); a2.set_ylabel(T("Mach", "Mach"))
    a2.grid(alpha=0.3); a2.legend()
    st.pyplot(fig2, use_container_width=True)

with t3:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for la, lo in split_dateline(orb["lat"].values, orb["lon"].values):
        ax.plot(lo, la, lw=1.2, color="tab:blue", alpha=0.85)
    ax.plot(asc["lon"], asc["lat"], lw=3, color="orangered", label=T("ช่วงไต่", "ascent"))
    ax.plot(site_lon, site_lat, "^", ms=11, color="black", label=T("ฐานปล่อย", "launch site"))
    ax.plot(obs_lon, obs_lat, "*", ms=14, color="gold",
            mec="black", label=T("จุดสังเกต", "observer"))
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
    ax.grid(alpha=0.3); ax.legend(loc="upper right", fontsize=8)
    ax.set_xlabel(T("ลองจิจูด (°)", "Longitude (deg)"))
    ax.set_ylabel(T("ละติจูด (°)", "Latitude (deg)"))
    ax.set_title(T(f"Ground track — {n_orbit} รอบ", f"Ground track — {n_orbit} orbits"))
    st.pyplot(fig, use_container_width=True)
    st.markdown(T("### เส้นทางช่วงไต่ (ซูม)", "### Ascent track (zoom)"))
    fig3, a3 = plt.subplots(figsize=(11, 4))
    sc = a3.scatter(asc["lon"], asc["lat"], c=asc["alt_km"], cmap="plasma", s=8)
    a3.plot(site_lon, site_lat, "^", ms=11, color="black")
    plt.colorbar(sc, ax=a3, label=T("ความสูง (km)", "Altitude (km)"))
    a3.grid(alpha=0.3)
    a3.set_xlabel(T("ลองจิจูด", "Longitude")); a3.set_ylabel(T("ละติจูด", "Latitude"))
    st.pyplot(fig3, use_container_width=True)

with t4:
    st.code(rp.photo_report(look, min_el), language=None)
    vis = look[look["el_deg"] > min_el]
    if vis.empty:
        st.warning("จรวดไม่ขึ้นเหนือมุมเงยที่กำหนดจากจุดนี้ — ลองลดค่ามุมเงยต่ำสุด")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].plot(vis["t"], vis["el_deg"], lw=2)
        ax[0].set_title(T("มุมเงย", "Elevation")); ax[0].set_ylabel(T("°", "deg"))
        ax[1].plot(vis["t"], vis["az_deg"], lw=2, color="teal")
        ax[1].set_title(T("ทิศ (azimuth)", "Azimuth")); ax[1].set_ylabel(T("°", "deg"))
        for a in ax:
            a.grid(alpha=0.3); a.set_xlabel(T("T+ (s)", "T+ (s)"))
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)
        st.markdown(T("### แผนผังท้องฟ้า (polar)", "### Sky map (polar)"))
        figp = plt.figure(figsize=(5.5, 5.5))
        ap = figp.add_subplot(111, projection="polar")
        ap.set_theta_zero_location("N"); ap.set_theta_direction(-1)
        ap.plot(np.radians(vis["az_deg"]), 90 - vis["el_deg"], lw=2.5, color="orangered")
        ap.set_rmax(90); ap.set_rticks([0, 30, 60, 90])
        ap.set_yticklabels(["90°", "60°", "30°", "0°"])
        ap.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"])
        ap.grid(alpha=0.4)
        st.pyplot(figp, use_container_width=False)
        st.markdown(T("### ตารางมุมเล็ง (ทุก 10 วินาที)", "### Look angles (every 10 s)"))
        tb = vis[vis["t"] % 10 < 0.6][
            ["t", "az_deg", "el_deg", "range_km", "alt_km", "angular_rate"]].copy()
        tb.columns = ["T+ (s)", T("ทิศ (°)", "Az (deg)"), T("มุมเงย (°)", "El (deg)"),
                      T("ระยะ (km)", "Range (km)"), T("สูง (km)", "Alt (km)"), "°/s"]
        st.dataframe(tb.round(2), use_container_width=True, hide_index=True)

with t5:
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ ascent.csv", asc.to_csv(index=False).encode(),
                       "ascent.csv", "text/csv", use_container_width=True)
    c2.download_button("⬇️ look_angles.csv", look.to_csv(index=False).encode(),
                       "look_angles.csv", "text/csv", use_container_width=True)
    c1.download_button("⬇️ orbit.csv", orb.to_csv(index=False).encode(),
                       "orbit.csv", "text/csv", use_container_width=True)
    c2.download_button("⬇️ trajectory.kml", make_kml(asc, "Ascent").encode(),
                       "trajectory.kml", "application/vnd.google-earth.kml+xml",
                       use_container_width=True)
    st.download_button("⬇️ elements.json", json.dumps(el, indent=2).encode(),
                       "elements.json", "application/json", use_container_width=True)
    st.caption("เปิด trajectory.kml ด้วย Google Earth เพื่อดูเส้นทางลอยเหนือแผนที่จริง")  
