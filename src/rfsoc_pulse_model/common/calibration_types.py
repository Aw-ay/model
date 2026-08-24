from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple

import numpy as np

from .types import SampleDomain


class CalibrationConditionError(ValueError):
    """A measured polarization matrix cannot be inverted reliably."""


@dataclass(frozen=True)
class FixedInternalDelay:
    """Measured common device delay on the public RFDC complex time axis.

    The boundary is the mathematical RFDC ADC complex input to the
    mathematical DAC baseband output. The measurement includes common Cycle
    pipeline/RAM/filter latency. It excludes both the programmed target delay
    and the symmetric Golden fractional-delay kernel center, whose group delay
    is removed inside the Golden implementation.
    """

    samples: float
    sample_rate_hz: int
    sample_domain: SampleDomain = SampleDomain.RFDC_COMPLEX_INPUT
    reference_boundary: str = "rfdc_adc_complex_input_to_dac_baseband_output"

    def __post_init__(self) -> None:
        if not math.isfinite(self.samples) or self.samples < 0.0:
            raise ValueError("fixed internal delay samples must be finite and nonnegative")
        if self.sample_rate_hz <= 0:
            raise ValueError("fixed internal delay sample rate must be positive")
        if self.sample_domain != SampleDomain.RFDC_COMPLEX_INPUT:
            raise ValueError("fixed internal delay must use RFDC_COMPLEX_INPUT")
        if self.reference_boundary != "rfdc_adc_complex_input_to_dac_baseband_output":
            raise ValueError("unsupported fixed internal delay reference boundary")

    @property
    def includes_common_hardware_latency(self) -> bool:
        return True

    @property
    def includes_programmable_target_delay(self) -> bool:
        return False

    @property
    def includes_golden_fractional_kernel_center(self) -> bool:
        return False

    def normalized_to_physical_sample(self, sample_index: float) -> float:
        """Add measured common latency to one Golden-normalized index."""

        value = float(sample_index)
        if not math.isfinite(value):
            raise ValueError("normalized sample index must be finite")
        return value + self.samples

    def physical_to_normalized_sample(self, sample_index: float) -> float:
        """Remove measured common latency from one physical output index."""

        value = float(sample_index)
        if not math.isfinite(value):
            raise ValueError("physical sample index must be finite")
        return value - self.samples


@dataclass(frozen=True)
class ComplexChannelCalibration:
    """Residual complex response after nominal channel gain is removed."""

    response_gain: complex = 1.0 + 0.0j
    response_delay_samples: float = 0.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.response_gain.real)
            or not math.isfinite(self.response_gain.imag)
            or self.response_gain == 0.0
        ):
            raise ValueError("response_gain must be finite and nonzero")
        if not math.isfinite(self.response_delay_samples) or self.response_delay_samples < 0.0:
            raise ValueError("response_delay_samples must be finite and nonnegative")


@dataclass(frozen=True)
class RcsCalibrationAnchor:
    calibration_id: str
    valid: bool
    frequency_hz: float
    frequency_tolerance_hz: float
    temperature_c: float
    temperature_tolerance_c: float
    physical_range_m: float
    physical_range_tolerance_m: float
    equivalent_rcs_m2: float
    digital_voltage_gain: float

    def __post_init__(self) -> None:
        for name, value in (
            ("frequency_hz", self.frequency_hz),
            ("frequency_tolerance_hz", self.frequency_tolerance_hz),
            ("temperature_tolerance_c", self.temperature_tolerance_c),
            ("physical_range_m", self.physical_range_m),
            ("physical_range_tolerance_m", self.physical_range_tolerance_m),
            ("equivalent_rcs_m2", self.equivalent_rcs_m2),
            ("digital_voltage_gain", self.digital_voltage_gain),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not self.calibration_id.strip():
            raise ValueError("calibration_id must be nonempty")
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be boolean")
        if not math.isfinite(self.temperature_c):
            raise ValueError("temperature_c must be finite")

    def invalid_reason(
        self,
        *,
        frequency_hz: float,
        temperature_c: float,
        physical_range_m: float,
    ) -> Optional[str]:
        if not self.valid:
            return "RCS calibration anchor is marked invalid"
        if abs(frequency_hz - self.frequency_hz) > self.frequency_tolerance_hz:
            return "RCS calibration anchor frequency is out of tolerance"
        if abs(temperature_c - self.temperature_c) > self.temperature_tolerance_c:
            return "RCS calibration anchor temperature is out of tolerance"
        if (
            abs(physical_range_m - self.physical_range_m)
            > self.physical_range_tolerance_m
        ):
            return "RCS calibration anchor physical range is out of tolerance"
        return None


def _matrix(values: object, name: str) -> np.ndarray:
    matrix = np.array(values, dtype=np.complex128, copy=True)
    if matrix.shape != (2, 2):
        raise ValueError(f"{name} must have shape (2, 2)")
    if not np.all(np.isfinite(matrix.real)) or not np.all(np.isfinite(matrix.imag)):
        raise ValueError(f"{name} must contain finite values")
    matrix.setflags(write=False)
    return matrix


@dataclass(frozen=True)
class CalibrationProfile:
    frequency_hz: float
    temperature_c: float
    frequency_tolerance_hz: float
    temperature_tolerance_c: float
    fixed_internal_delay: FixedInternalDelay
    adc_channels: Tuple[ComplexChannelCalibration, ...]
    dac_channels: Tuple[ComplexChannelCalibration, ...]
    rx_polarization_matrix: np.ndarray
    tx_polarization_matrix: np.ndarray
    rcs_anchor: Optional[RcsCalibrationAnchor]
    maximum_condition_number: float = 1.0e6

    def __post_init__(self) -> None:
        for name, value in (
            ("frequency_hz", self.frequency_hz),
            ("frequency_tolerance_hz", self.frequency_tolerance_hz),
            ("temperature_tolerance_c", self.temperature_tolerance_c),
            ("maximum_condition_number", self.maximum_condition_number),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.temperature_c):
            raise ValueError("temperature_c must be finite")
        if not isinstance(self.fixed_internal_delay, FixedInternalDelay):
            raise ValueError("fixed_internal_delay has the wrong type")
        if len(self.adc_channels) != 8 or len(self.dac_channels) != 8:
            raise ValueError("calibration profile requires eight ADC and eight DAC channels")
        if not all(isinstance(value, ComplexChannelCalibration) for value in self.adc_channels + self.dac_channels):
            raise ValueError("channel calibration entries have the wrong type")
        if self.rcs_anchor is not None and not isinstance(
            self.rcs_anchor, RcsCalibrationAnchor
        ):
            raise ValueError("rcs_anchor has the wrong type")
        rx_matrix = _matrix(self.rx_polarization_matrix, "rx_polarization_matrix")
        tx_matrix = _matrix(self.tx_polarization_matrix, "tx_polarization_matrix")
        for name, matrix in (
            ("rx_polarization_matrix", rx_matrix),
            ("tx_polarization_matrix", tx_matrix),
        ):
            condition = float(np.linalg.cond(matrix))
            if not math.isfinite(condition) or condition > self.maximum_condition_number:
                raise CalibrationConditionError(f"{name} is singular or ill-conditioned")
        object.__setattr__(self, "rx_polarization_matrix", rx_matrix)
        object.__setattr__(self, "tx_polarization_matrix", tx_matrix)

    @classmethod
    def identity(
        cls,
        frequency_hz: float,
        temperature_c: float,
        fixed_internal_delay_samples: float,
        rcs_anchor: Optional[RcsCalibrationAnchor],
        fixed_internal_delay_sample_rate_hz: int = 500_000_000,
    ) -> "CalibrationProfile":
        channels = tuple(ComplexChannelCalibration() for _ in range(8))
        return cls(
            frequency_hz=frequency_hz,
            temperature_c=temperature_c,
            frequency_tolerance_hz=1_000_000.0,
            temperature_tolerance_c=5.0,
            fixed_internal_delay=FixedInternalDelay(
                samples=fixed_internal_delay_samples,
                sample_rate_hz=fixed_internal_delay_sample_rate_hz,
            ),
            adc_channels=channels,
            dac_channels=channels,
            rx_polarization_matrix=np.eye(2, dtype=np.complex128),
            tx_polarization_matrix=np.eye(2, dtype=np.complex128),
            rcs_anchor=rcs_anchor,
            maximum_condition_number=1.0e6,
        )

    @property
    def fixed_internal_delay_samples(self) -> float:
        """Compatibility accessor for the explicitly qualified delay value."""

        return self.fixed_internal_delay.samples
