from datetime import datetime, timezone
import math

import rocket_planner as rp
import booster as bst
from main import clean, health, jd_from_datetime


def test_j2000_epoch_conversion():
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert jd_from_datetime(epoch) == 2451545.0


def test_circular_orbit_elements_are_finite():
    radius = rp.RE + 400_000.0
    velocity = math.sqrt(rp.MU / radius)
    elements = rp.orbital_elements([radius, 0, 0], [0, velocity, 0])
    assert abs(elements["e"]) < 1e-8
    assert abs(elements["perigee_km"] - 400.0) < 1e-5
    assert abs(elements["apogee_km"] - 400.0) < 1e-5
    assert elements["period_min"] > 90


def test_booster_phase_builder_returns_mass_and_phases():
    core = dict(name="Core", thrust_sl=1000.0, thrust_vac=1100.0,
                isp_sl=270.0, isp_vac=300.0, prop_mass=10000.0,
                dry_mass=1000.0, burn_time=100.0, area=3.0)
    group = bst.make_group("SRB", 2, 300.0, 330.0, 250.0, 265.0,
                           2000.0, 250.0, 60.0, 1.0, 0.0, 2.0)
    phases, log = bst.build_boost_phases(core, [group])
    assert phases
    assert log
    assert all(p["burn_time"] > 0 for p in phases)
    assert phases[-1]["dry_mass"] >= core["dry_mass"]


def test_api_health_and_json_cleaning():
    assert health()["status"] == "ok"
    assert clean(float("inf")) is None
    assert clean(float("nan")) is None


def test_launch_azimuth_uses_entered_compass_heading():
    azimuth, inertial_azimuth, earth_bonus = rp.launch_azimuth(
        13.72, 270.0, 170_000.0
    )
    assert azimuth == 270.0
    assert 0.0 <= inertial_azimuth < 360.0
    assert earth_bonus < 0.0

    wrapped_azimuth, _, _ = rp.launch_azimuth(13.72, 360.0, 170_000.0)
    assert wrapped_azimuth == 0.0



def test_timeline_supports_restart_after_coast_without_resetting_propellant():
    stage = rp.Stage(
        "Restartable upper stage", 100_000.0, 100_000.0, 300.0, 300.0,
        1000.0, 200.0, 4.0, 1.0,
        burn_windows=[(0.0, 2.0), (4.0, 6.0)],
        separation_t=8.0,
    )
    vehicle = rp.Vehicle(
        stages=[stage], payload=100.0, payload_deploy_t=8.0
    )
    mission = rp.Mission(
        site_lat=0.0, site_lon=0.0, site_alt=0.0,
        target_alt=200_000.0, auto_profile=False,
        vertical_time=0.0, kick_angle=0.0, kick_duration=1.0,
    )
    ascent, state, t_end, _, _ = rp.simulate_ascent(
        vehicle, mission, dt=0.05, dt_out=0.1, max_time=10.0, verbose=False
    )
    at_coast = ascent[(ascent["t"] >= 2.5) & (ascent["t"] < 3.5)]
    after_restart = ascent[(ascent["t"] >= 4.5) & (ascent["t"] < 5.5)]
    assert not at_coast.empty and (at_coast["thrust_kN"] == 0).all()
    assert not after_restart.empty and (after_restart["thrust_kN"] > 0).all()
    assert after_restart["mass"].iloc[-1] < at_coast["mass"].iloc[0]
    assert t_end >= 7.9



def test_stage_ambient_pressure_endpoints_and_vacuum_curve():
    stage = rp.Stage(
        "Curve engine", 500_000.0, 1_000_000.0, 250.0, 300.0,
        1000.0, 100.0, 100.0, 1.0,
        thrust_curve=[(0.0, 1000.0), (10.0, 800.0)],
    )
    assert abs(stage.thrust(rp.P0, 0.0) - 500_000.0) < 1e-6
    assert abs(stage.thrust(0.0, 0.0) - 1_000_000.0) < 1e-6
    assert abs(stage.thrust(0.0, 5.0) - 900_000.0) < 1e-6



def test_booster_thrust_curve_is_preserved_in_virtual_phases():
    core = dict(name="Core", thrust_sl=1000.0, thrust_vac=1100.0,
                isp_sl=270.0, isp_vac=300.0, prop_mass=10000.0,
                dry_mass=1000.0, burn_time=100.0, area=3.0)
    group = bst.make_group(
        "P160C", 2, None, 4775.0, None, 278.5,
        156000.0, 12000.0, 60.0, 9.0, 0.0, 2.0,
        thrust_curve=[(0.0, 4775.0), (30.0, 4300.0), (60.0, 3500.0)],
    )
    phases, _ = bst.build_boost_phases(core, [group])
    assert len(phases) >= 3
    assert all(len(phase["thrust_curve"]) == 2 for phase in phases)
    assert phases[0]["thrust_curve"][0][1] > phases[-2]["thrust_curve"][-1][1]
