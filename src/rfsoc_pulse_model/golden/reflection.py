from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.config import ModelConfig
from ..common.reflection_types import (
    CompiledScatterer,
    PolarimetricWaveform,
    ReflectionScenario,
)
from ..common.types import SampleDomain
from .delay import (
    SPEED_OF_LIGHT_MPS,
    apply_causal_delay,
    compile_target_delay,
)
from .rcs import RcsCalibrationError, digital_gain_for_target


_REFERENCE_INDICES = {
    "HH": (0, 0),
    "HV": (0, 1),
    "VH": (1, 0),
    "VV": (1, 1),
}


class TargetCompiler:
    """Translate physical target requests into numerical scatterers."""

    def __init__(
        self,
        config: ModelConfig,
        calibration: CalibrationProfile,
    ) -> None:
        self.config = config
        self.calibration = calibration
        if (
            calibration.fixed_internal_delay.sample_rate_hz
            != config.reflection_sample_rate_hz
        ):
            raise ValueError(
                "fixed internal delay sample rate must equal reflection_sample_rate_hz"
            )
        self.last_absolute_rcs_calibrated = False

    def compile(
        self,
        scenario: ReflectionScenario,
    ) -> Tuple[CompiledScatterer, ...]:
        if len(scenario.targets) > self.config.maximum_targets:
            raise ValueError("target count exceeds maximum_targets")

        anchor = self.calibration.rcs_anchor
        anchor_invalid_reason = (
            "absolute RCS conversion requires a calibration anchor"
            if anchor is None
            else anchor.invalid_reason(
                frequency_hz=scenario.carrier_frequency_hz,
                temperature_c=scenario.temperature_c,
                physical_range_m=scenario.physical_range_m,
            )
        )
        profile_invalid_reason = None
        if (
            abs(scenario.carrier_frequency_hz - self.calibration.frequency_hz)
            > self.calibration.frequency_tolerance_hz
        ):
            profile_invalid_reason = (
                "RCS calibration profile frequency is out of tolerance"
            )
        elif (
            abs(scenario.temperature_c - self.calibration.temperature_c)
            > self.calibration.temperature_tolerance_c
        ):
            profile_invalid_reason = (
                "RCS calibration profile temperature is out of tolerance"
            )
        calibration_invalid_reason = (
            profile_invalid_reason
            if profile_invalid_reason is not None
            else anchor_invalid_reason
        )
        if (
            scenario.require_absolute_rcs
            and calibration_invalid_reason is not None
        ):
            raise RcsCalibrationError(calibration_invalid_reason)
        effective_anchor = (
            anchor if calibration_invalid_reason is None else None
        )
        anchor_valid = calibration_invalid_reason is None

        compiled = []
        absolute_flags = []
        for target in scenario.targets:
            integer_delay, fractional_delay = compile_target_delay(
                apparent_range_m=target.apparent_range_m,
                physical_range_m=scenario.physical_range_m,
                fixed_internal_delay_samples=(
                    self.calibration.fixed_internal_delay_samples
                ),
                sample_rate_hz=self.config.reflection_sample_rate_hz,
                maximum_delay_samples=self.config.maximum_delay_samples,
                taps=self.config.fractional_delay_taps,
            )
            doppler_hz = (
                -2.0
                * target.radial_velocity_mps
                * scenario.carrier_frequency_hz
                / SPEED_OF_LIGHT_MPS
            )
            device_delay_seconds = (
                2.0
                * (target.apparent_range_m - scenario.physical_range_m)
                / SPEED_OF_LIGHT_MPS
            )
            range_carrier_phase_rad = math.remainder(
                -2.0
                * math.pi
                * scenario.carrier_frequency_hz
                * device_delay_seconds,
                2.0 * math.pi,
            )
            reference_index = _REFERENCE_INDICES[target.rcs_reference_channel]
            reference_value = target.normalized_scattering_matrix[
                reference_index
            ]
            if abs(reference_value) == 0.0:
                raise ValueError("RCS reference scattering element cannot be zero")
            gain, calibrated = digital_gain_for_target(
                target_rcs_m2=target.target_rcs_m2,
                physical_range_m=scenario.physical_range_m,
                apparent_range_m=target.apparent_range_m,
                anchor=effective_anchor,
                require_absolute=scenario.require_absolute_rcs,
                operating_frequency_hz=scenario.carrier_frequency_hz,
                operating_temperature_c=scenario.temperature_c,
            )
            matrix = (
                target.normalized_scattering_matrix
                / abs(reference_value)
                * gain
                * np.exp(1j * target.initial_phase_rad)
            )
            compiled.append(
                CompiledScatterer(
                    integer_delay_samples=integer_delay,
                    fractional_delay=fractional_delay,
                    doppler_hz=doppler_hz,
                    complex_scattering_matrix=matrix,
                    range_carrier_phase_rad=range_carrier_phase_rad,
                )
            )
            absolute_flags.append(calibrated)

        self.last_absolute_rcs_calibrated = (
            all(absolute_flags)
            if absolute_flags
            else anchor_valid
        )
        return tuple(compiled)


class GoldenPolarimetricReflectionKernel:
    """Clock-free 2x2 delayed, Doppler-shifted multi-target reference."""

    def __init__(self, taps: int) -> None:
        if taps < 1 or taps % 2 == 0:
            raise ValueError("taps must be a positive odd value")
        self.taps = taps

    def process(
        self,
        incident: PolarimetricWaveform,
        scatterers: Sequence[CompiledScatterer],
    ) -> PolarimetricWaveform:
        if incident.sample_domain != SampleDomain.RFDC_COMPLEX_INPUT:
            raise ValueError("reflection kernel requires RFDC_COMPLEX_INPUT")
        if not all(
            isinstance(scatterer, CompiledScatterer)
            for scatterer in scatterers
        ):
            raise ValueError("scatterers must contain CompiledScatterer values")

        sample_count = incident.samples.shape[1]
        output = np.zeros((2, sample_count), dtype=np.complex128)
        absolute_samples = incident.start_sample + np.arange(
            sample_count,
            dtype=np.float64,
        )
        for scatterer in scatterers:
            delayed = apply_causal_delay(
                incident.samples,
                scatterer.integer_delay_samples,
                scatterer.fractional_delay,
                self.taps,
            )
            polarized = (
                np.exp(1j * scatterer.range_carrier_phase_rad)
                * (scatterer.complex_scattering_matrix @ delayed)
            )
            rotation = np.exp(
                2j
                * math.pi
                * scatterer.doppler_hz
                * absolute_samples
                / incident.sample_rate_hz
            )
            output += polarized * rotation[np.newaxis, :]

        return PolarimetricWaveform(
            samples=output,
            sample_domain=incident.sample_domain,
            sample_rate_hz=incident.sample_rate_hz,
            start_sample=incident.start_sample,
        )
