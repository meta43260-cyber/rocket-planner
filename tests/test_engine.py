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
