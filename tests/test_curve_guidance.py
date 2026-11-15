import pytest
from fastapi import HTTPException

import rocket_planner as rp
from main import _validate_thrust_curve


def test_zero_thrust_at_curve_start_is_accepted():
    _validate_thrust_curve([(0.0, 0.0), (0.5, 3010.0), (1.0, 3200.0)], "P160C")


def test_zero_thrust_is_rejected_after_curve_start():
    with pytest.raises(HTTPException):
        _validate_thrust_curve([(0.0, 0.0), (0.5, 0.0)], "P160C")


def test_curve_time_must_strictly_increase():
    with pytest.raises(HTTPException):
        _validate_thrust_curve([(0.0, 0.0), (0.5, 3010.0), (0.4, 3200.0)], "P160C")


def test_closed_loop_guidance_adds_upward_component_below_target_radius():
    direction = rp._closed_loop_capture_direction(
        [1.0, 0.0, 0.0], [0.0, 7000.0, 0.0],
        rp.RE + 400_000.0, rp.RE + 200_000.0, 3.0
    )
    assert abs(float(direction @ direction) - 1.0) < 1e-12
    assert direction[0] > 0.0


def test_closed_loop_guidance_corrects_downward_velocity():
    up = [1.0, 0.0, 0.0]
    target_radius = rp.RE + 400_000.0
    current_radius = rp.RE + 200_000.0
    level = rp._closed_loop_capture_direction(
        up, [0.0, 7000.0, 0.0], target_radius, current_radius, 5.0
    )
    descending = rp._closed_loop_capture_direction(
        up, [-50.0, 7000.0, 0.0], target_radius, current_radius, 5.0
    )
    assert descending[0] > level[0]


def test_thrust_curve_accepts_275_points():
    points = [(i * 0.5, 0.0 if i == 0 else 3000.0 + i) for i in range(275)]
    _validate_thrust_curve(points, "P160C")


def test_thrust_curve_pressure_scaling_preserves_zero_ignition_point():
    stage = rp.Stage(
        name="P160C", thrust_sl=4400.0, thrust_vac=4775.0,
        isp_sl=245.0, isp_vac=278.5, prop_mass=155600.0,
        dry_mass=11700.0, burn_time=137.0, area=9.08,
        thrust_curve=[(0.0, 0.0), (0.5, 3010.0), (1.0, 4175.0)],
    )
    assert stage.thrust(rp.P0, 0.0) == pytest.approx(0.0)
    assert stage.thrust(rp.P0, 0.5) == pytest.approx(4400.0 * 1000.0 * 3010.0 / 4775.0)
    assert stage.thrust(0.0, 0.5) == pytest.approx(3010.0 * 1000.0)


def test_booster_phase_sea_level_curve_uses_ratio_not_constant_offset():
    from booster import build_boost_phases
    core = dict(name="LLPM", thrust_sl=1324.0, thrust_vac=1370.0,
                isp_sl=305.0, isp_vac=432.0, prop_mass=150000.0,
                dry_mass=23000.0, burn_time=468.0, area=22.902)
    group = dict(name="P160C", count=4, thrust_sl=4400.0, thrust_vac=4775.0,
                 isp_sl=245.0, isp_vac=278.5, prop_mass=155600.0,
                 dry_mass=11700.0, burn_time=137.0, area=9.08,
                 ignite_t=0.0, jettison_delay=4.0,
                 thrust_curve=[(0.0, 0.0), (0.5, 3010.0), (1.0, 4175.0)])
    phases, _ = build_boost_phases(core, [group])
    first = phases[0]
    assert first["thrust_sl"] > 0.0
    assert first["thrust_vac"] > 0.0
    assert first["thrust_sl"] <= first["thrust_vac"]
