from __future__ import annotations

import math
from typing import Optional, Tuple

from ..common.calibration_types import RcsCalibrationAnchor


class RcsCalibrationError(ValueError):
    """Absolute RCS conversion was requested without a valid anchor."""


def digital_gain_for_target(
    target_rcs_m2: float,
    physical_range_m: float,
    apparent_range_m: float,
    anchor: Optional[RcsCalibrationAnchor],
    require_absolute: bool,
) -> Tuple[float, bool]:
    """Convert target RCS and range into a digital voltage gain."""

    for name, value in (
        ("target_rcs_m2", target_rcs_m2),
        ("physical_range_m", physical_range_m),
        ("apparent_range_m", apparent_range_m),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")

    equivalent_rcs = target_rcs_m2 * (
        physical_range_m / apparent_range_m
    ) ** 4
    if anchor is None:
        if require_absolute:
            raise RcsCalibrationError(
                "absolute RCS conversion requires a calibration anchor"
            )
        return math.sqrt(target_rcs_m2) * (
            physical_range_m / apparent_range_m
        ) ** 2, False

    gain = anchor.digital_voltage_gain * math.sqrt(
        equivalent_rcs / anchor.equivalent_rcs_m2
    )
    return float(gain), True
