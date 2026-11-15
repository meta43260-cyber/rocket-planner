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


def test_boost_mode_applies_core_shutdown_and_separation_timeline():
    from main import TimelineStage, TimelineBurn, _apply_boost_core_timeline
    phases = [
        {"name": "boost+core", "burn_time": 137.0, "prop_mass": 100000.0},
        {"name": "core-only", "burn_time": 323.0, "prop_mass": 50000.0},
    ]
    log = [
        {"t0": 0.0, "t1": 137.0},
        {"t0": 137.0, "t1": 464.0},
    ]
    row = TimelineStage(
        burns=[TimelineBurn(ignition_t=0.0, cutoff_t=460.0)],
        separation_t=466.0,
    )
    _apply_boost_core_timeline(phases, log, row)
    assert phases[-1]["burn_windows"] == [(137.0, 460.0)]
    assert phases[-1]["burn_time"] == pytest.approx(323.0)
    assert phases[-1]["separation_t"] == pytest.approx(466.0)


def test_boost_core_timeline_rejects_cutoff_outside_generated_phase():
    from fastapi import HTTPException
    from main import TimelineStage, TimelineBurn, _apply_boost_core_timeline
    phases = [{"name": "core-only", "burn_time": 300.0}]
    log = [{"t0": 137.0, "t1": 437.0}]
    row = TimelineStage(
        burns=[TimelineBurn(ignition_t=0.0, cutoff_t=460.0)],
        separation_t=466.0,
    )
    with pytest.raises(HTTPException):
        _apply_boost_core_timeline(phases, log, row)


def test_capture_guidance_engages_early_for_heavy_payload_ascent():
    target_radius = rp.RE + 450_000.0
    threshold = rp._capture_guidance_threshold(target_radius)
    assert threshold == pytest.approx(rp.RE + 157_500.0)
    assert threshold < rp.RE + 212_840.0
    assert threshold < target_radius


def test_capture_guidance_has_minimum_altitude_for_low_orbits():
    target_radius = rp.RE + 40_000.0
    threshold = rp._capture_guidance_threshold(target_radius)
    assert threshold == pytest.approx(rp.RE + 50_000.0)


def test_capture_guidance_threshold_is_below_heavy_flight_peak():
    target_radius = rp.RE + 450_000.0
    observed_peak_altitude = 212_840.0
    threshold = rp._capture_guidance_threshold(target_radius)
    assert threshold - rp.RE < observed_peak_altitude


def test_closed_loop_guidance_does_not_over_brake_early_ascent():
    up = [1.0, 0.0, 0.0]
    direction = rp._closed_loop_capture_direction(
        up, [1000.0, 7000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 112_000.0, 5.0
    )
    # With a large remaining altitude gap, guidance should make only a
    # modest correction rather than commanding the old -0.65 radial limit.
    assert direction[0] > -0.20


def test_closed_loop_guidance_reduces_radial_target_near_orbit():
    up = [1.0, 0.0, 0.0]
    far = rp._closed_loop_capture_direction(
        up, [1000.0, 7000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 112_000.0, 5.0
    )
    near = rp._closed_loop_capture_direction(
        up, [1000.0, 7000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 430_000.0, 5.0
    )
    assert near[0] < far[0]

def test_inertial_capture_velocity_projection_stays_in_launch_plane():
    velocity = [120.0, 7000.0, 450.0]
    plane_normal = [0.0, 0.0, 1.0]
    projected = rp._project_velocity_to_plane(velocity, plane_normal)
    assert projected == pytest.approx([120.0, 7000.0, 0.0])
    assert float(projected @ plane_normal) == pytest.approx(0.0)


def test_radial_environment_includes_tangential_curvature():
    radius = rp.RE + 450_000.0
    circular_speed = (rp.MU / radius) ** 0.5
    assert rp._radial_environment_accel(radius, circular_speed) == pytest.approx(0.0, abs=1e-12)
    assert rp._radial_environment_accel(radius, 7000.0) < 0.0
    assert rp._radial_environment_accel(radius, 8000.0) > 0.0


def test_capture_guidance_uses_net_radial_environment_at_circular_speed():
    up = [1.0, 0.0, 0.0]
    radius = rp.RE + 450_000.0
    circular_speed = (rp.MU / radius) ** 0.5
    direction = rp._closed_loop_capture_direction(
        up, [0.0, circular_speed, 0.0],
        radius, radius, 10.0,
        radial_environment_accel=rp._radial_environment_accel(radius, circular_speed)
    )
    assert direction[0] == pytest.approx(0.0, abs=1e-10)
    assert direction[1] == pytest.approx(1.0, abs=1e-10)


def test_capture_guidance_radial_command_respects_thrust_limit():
    direction = rp._closed_loop_capture_direction(
        [1.0, 0.0, 0.0], [0.0, 7000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 100_000.0, 2.0,
        radial_environment_accel=-9.7
    )
    assert direction[0] == pytest.approx(0.65)
    assert direction[1] == pytest.approx((1.0 - 0.65 ** 2) ** 0.5)



def test_timeline_events_remain_pending_until_restart_and_separation():
    stages = [
        rp.Stage(
            name="ULPM", thrust_sl=None, thrust_vac=180_000.0,
            isp_sl=None, isp_vac=457.0, prop_mass=30_000.0,
            dry_mass=6_000.0, burn_time=696.0, area=22.902,
            burn_windows=[(474.0, 1152.0), (4281.0, 4299.0)],
            separation_t=6844.0,
        )
    ]
    assert rp._has_pending_timeline_events(stages, 0, 1200.0)
    assert rp._has_pending_timeline_events(stages, 0, 4300.0)
    assert not rp._has_pending_timeline_events(stages, 0, 6844.0)


def test_periapsis_diagnostic_identifies_suborbital_peak():
    radius = rp.RE + 569_170.0
    speed = 6_436.4
    state_r = [radius, 0.0, 0.0]
    state_v = [0.0, speed, 0.0]
    periapsis_alt = rp.periapsis_radius(state_r, state_v) - rp.RE
    assert periapsis_alt / 1000.0 == pytest.approx(-2453.0, abs=2.0)



def test_capture_guidance_limits_radial_thrust_when_tangential_speed_is_low():
    direction = rp._closed_loop_capture_direction(
        [1.0, 0.0, 0.0], [0.0, 5000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 450_000.0, 4.0,
        radial_environment_accel=-5.0,
        max_radial_fraction=0.08
    )
    assert direction[0] <= 0.08 + 1e-12
    assert direction[1] >= (1.0 - 0.08 ** 2) ** 0.5 - 1e-12


def test_capture_guidance_can_use_more_radial_thrust_near_circular_speed():
    direction = rp._closed_loop_capture_direction(
        [1.0, 0.0, 0.0], [0.0, 7600.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 450_000.0, 4.0,
        radial_environment_accel=-0.1,
        max_radial_fraction=0.65
    )
    assert direction[0] <= 0.65 + 1e-12
    assert direction[1] > 0.0


def test_capture_radial_authority_prioritizes_tangential_speed_below_82_percent():
    assert rp._capture_radial_authority_limit(0.50) == pytest.approx(0.15)
    assert rp._capture_radial_authority_limit(0.65) == pytest.approx(0.15)
    assert rp._capture_radial_authority_limit(0.80) == pytest.approx(0.15)
    assert rp._capture_radial_authority_limit(0.82) == pytest.approx(0.15)
    assert rp._capture_radial_authority_limit(0.87) == pytest.approx(0.325)
    assert rp._capture_radial_authority_limit(0.92) == pytest.approx(0.50)
    assert rp._capture_radial_authority_limit(0.96) == pytest.approx(0.575)
    assert rp._capture_radial_authority_limit(1.00) == pytest.approx(0.65)


def test_capture_guidance_uses_low_radial_authority_before_circular_speed():
    limit = rp._capture_radial_authority_limit(0.65)
    direction = rp._closed_loop_capture_direction(
        [1.0, 0.0, 0.0], [0.0, 5000.0, 0.0],
        rp.RE + 450_000.0, rp.RE + 450_000.0, 4.0,
        radial_environment_accel=-5.0,
        max_radial_fraction=limit
    )
    assert direction[0] == pytest.approx(0.15)
    assert direction[1] == pytest.approx((1.0 - 0.15 ** 2) ** 0.5)


def test_ascent_guidance_mode_labels_vertical_pitch_gravity_turn_and_capture():
    mode = rp._ascent_guidance_mode
    assert mode(2.0, 5.0, 8.0, False, True) == "vertical"
    assert mode(8.0, 5.0, 8.0, False, True) == "pitch_kick"
    assert mode(20.0, 5.0, 8.0, False, True) == "gravity_turn"
    assert mode(20.0, 5.0, 8.0, True, True) == "orbital_capture"
    assert mode(20.0, 5.0, 8.0, False, False) == "coast"



def test_orbital_energy_diagnostics_reports_speed_ratio_and_remaining_stage_dv():
    radius = rp.RE + 400_000.0
    circular_speed = (rp.MU / radius) ** 0.5
    mass = 50_000.0
    propellant = 10_000.0
    isp = 450.0
    diag = rp.orbital_energy_diagnostics(
        [radius, 0.0, 0.0], [0.0, circular_speed * 0.9, 0.0],
        mass=mass, remaining_propellant=propellant, isp_s=isp
    )
    assert diag["tangential_speed_ratio"] == pytest.approx(0.9)
    assert diag["circular_speed_mps"] == pytest.approx(circular_speed)
    assert diag["remaining_stage_dv_mps"] == pytest.approx(
        rp.G0 * isp * __import__("math").log(mass / (mass - propellant))
    )
    assert diag["specific_energy_mj_kg"] < 0.0
    assert diag["apoapsis_circularization_dv_mps"] >= 0.0


def test_orbital_energy_diagnostics_returns_nan_circularization_for_escape():
    diag = rp.orbital_energy_diagnostics(
        [rp.RE + 200_000.0, 0.0, 0.0], [0.0, 12_000.0, 0.0]
    )
    assert diag["specific_energy_mj_kg"] > 0.0
    assert rp.np.isnan(diag["apoapsis_circularization_dv_mps"])
    assert rp.np.isnan(diag["remaining_stage_dv_mps"])
