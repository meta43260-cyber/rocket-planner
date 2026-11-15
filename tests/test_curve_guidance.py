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
        up, [0.0, 7000.0, 0.0], target_radius, current_radius, 3.0
    )
    descending = rp._closed_loop_capture_direction(
        up, [-250.0, 7000.0, 0.0], target_radius, current_radius, 3.0
    )
    assert descending[0] > level[0]
