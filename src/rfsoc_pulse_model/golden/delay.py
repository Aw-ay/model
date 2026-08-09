from __future__ import annotations

import math
from typing import Tuple

import numpy as np


SPEED_OF_LIGHT_MPS = 299_792_458.0


class CausalityError(ValueError):
    """The requested apparent range requires a noncausal response."""


def _validate_taps(taps: int) -> int:
    if taps < 1 or taps % 2 == 0:
        raise ValueError("taps must be a positive odd value")
    return (taps - 1) // 2


def compile_target_delay(
    apparent_range_m: float,
    physical_range_m: float,
    fixed_internal_delay_samples: float,
    sample_rate_hz: int,
    maximum_delay_samples: int,
    taps: int,
) -> Tuple[int, float]:
    """Compile apparent range into a realizable causal sample delay."""

    center = _validate_taps(taps)
    for name, value in (
        ("apparent_range_m", apparent_range_m),
        ("physical_range_m", physical_range_m),
        ("fixed_internal_delay_samples", fixed_internal_delay_samples),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if apparent_range_m <= 0.0 or physical_range_m <= 0.0:
        raise ValueError("ranges must be positive")
    if fixed_internal_delay_samples < 0.0:
        raise ValueError("fixed_internal_delay_samples cannot be negative")
    if sample_rate_hz <= 0 or maximum_delay_samples < 1:
        raise ValueError("sample rate and maximum delay must be positive")

    programmable_samples = (
        2.0
        * (apparent_range_m - physical_range_m)
        / SPEED_OF_LIGHT_MPS
        * sample_rate_hz
        - fixed_internal_delay_samples
    )
    if not math.isfinite(programmable_samples) or programmable_samples < center:
        raise CausalityError(
            "requested apparent range cannot cover fixed and fractional-delay latency"
        )
    if programmable_samples > maximum_delay_samples:
        raise ValueError("requested programmable delay exceeds maximum_delay_samples")

    integer_delay = math.floor(programmable_samples)
    fractional_delay = programmable_samples - integer_delay
    return int(integer_delay), float(fractional_delay)


def fractional_delay_kernel(fractional_delay: float, taps: int) -> np.ndarray:
    """Return a normalized causal Blackman-windowed sinc reference."""

    center = _validate_taps(taps)
    if not math.isfinite(fractional_delay) or not 0.0 <= fractional_delay < 1.0:
        raise ValueError("fractional_delay must be within [0, 1)")
    positions = np.arange(taps, dtype=np.float64)
    kernel = (
        np.sinc(positions - center - fractional_delay)
        * np.blackman(taps)
    )
    scale = float(np.sum(kernel))
    if not math.isfinite(scale) or abs(scale) < np.finfo(np.float64).eps:
        raise ValueError("fractional-delay kernel cannot be normalized")
    return np.asarray(kernel / scale, dtype=np.float64)


def apply_causal_delay(
    samples: np.ndarray,
    integer_delay_samples: int,
    fractional_delay: float,
    taps: int,
) -> np.ndarray:
    """Apply one zero-filled causal delay to H/V arrays without wraparound."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 2 or values.shape[0] != 2:
        raise ValueError("samples must have shape (2, N)")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("samples must contain finite values")
    center = _validate_taps(taps)
    if integer_delay_samples < center:
        raise CausalityError("integer delay cannot cover fractional-filter support")
    kernel = fractional_delay_kernel(fractional_delay, taps)
    sample_count = values.shape[1]
    if sample_count == 0:
        return np.empty((2, 0), dtype=np.complex128)

    coarse_delay = integer_delay_samples - center
    coarse = np.zeros_like(values)
    if coarse_delay == 0:
        coarse[:] = values
    elif coarse_delay < sample_count:
        coarse[:, coarse_delay:] = values[:, : sample_count - coarse_delay]

    result = np.empty_like(values)
    for polarization in range(2):
        result[polarization] = np.convolve(
            coarse[polarization],
            kernel,
            mode="full",
        )[:sample_count]
    return result


def apply_relative_delay(
    samples: np.ndarray,
    delay_samples: float,
    taps: int,
) -> np.ndarray:
    """Apply a Golden-only relative delay without exposing FIR group delay.

    This helper aligns calibrated channels on one mathematical time axis.  It
    deliberately removes the symmetric fractional-delay kernel's center delay;
    hardware implementations must account for their common pipeline latency
    separately from the relative channel correction.
    """

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 2 or values.shape[0] != 2:
        raise ValueError("samples must have shape (2, N)")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("samples must contain finite values")
    if not math.isfinite(delay_samples) or delay_samples < 0.0:
        raise ValueError("relative delay must be finite and nonnegative")
    center = _validate_taps(taps)
    sample_count = values.shape[1]
    if sample_count == 0:
        return np.empty((2, 0), dtype=np.complex128)

    integer_delay = math.floor(delay_samples)
    fractional_delay = delay_samples - integer_delay
    coarse = np.zeros_like(values)
    if integer_delay == 0:
        coarse[:] = values
    elif integer_delay < sample_count:
        coarse[:, integer_delay:] = values[:, : sample_count - integer_delay]
    if fractional_delay <= 1e-15:
        return coarse

    kernel = fractional_delay_kernel(fractional_delay, taps)
    result = np.empty_like(values)
    for polarization in range(2):
        full = np.convolve(coarse[polarization], kernel, mode="full")
        result[polarization] = full[center : center + sample_count]
    return result
