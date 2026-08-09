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
from .rcs import digital_gain_for_target


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
        self.last_absolute_rcs_calibrated = False

    def compile(
        self,
        scenario: ReflectionScenario,
    ) -> Tuple[CompiledScatterer, ...]:
        if len(scenario.targets) > self.config.maximum_targets:
            raise ValueError("target count exceeds maximum_targets")

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
                anchor=self.calibration.rcs_anchor,
                require_absolute=scenario.require_absolute_rcs,
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
                )
            )
            absolute_flags.append(calibrated)

        self.last_absolute_rcs_calibrated = (
            all(absolute_flags)
            if absolute_flags
            else self.calibration.rcs_anchor is not None
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
            polarized = scatterer.complex_scattering_matrix @ delayed
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
