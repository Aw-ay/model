from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.config import ModelConfig
from ..common.reflection_types import (
    CompiledScatterer,
    DacAuxRequest,
    EightChannelAdcFrame,
    EightChannelDacFrame,
    PolarimetricWaveform,
    ReflectionScenario,
    ReflectionStatus,
)
from ..common.types import (
    AuxOutputMode,
    ChannelRole,
    GainRange,
    Polarization,
    PulseRecord,
    RangeId,
    RangeSelectionMode,
)
from .adc_frontend import GoldenEightChannelAdcFrontend
from .calibration import GoldenTxPredistorter
from .dac_router import GoldenEightChannelDacRouter
from .receive import AdcSampleBatch, GoldenReceivePipeline
from .reflection import (
    GoldenPolarimetricReflectionKernel,
    TargetCompiler,
)


_LEGACY_RANGE = {
    GainRange.HIGH: RangeId.PLUS_20_DB,
    GainRange.MID: RangeId.ZERO_DB,
    GainRange.LOW: RangeId.MINUS_20_DB,
}


@dataclass(frozen=True)
class ReflectionSourceResult:
    incident: PolarimetricWaveform
    desired_reflection: PolarimetricWaveform
    actual_uncompensated: PolarimetricWaveform
    predistorted_reflection: PolarimetricWaveform
    dac_frame: EightChannelDacFrame
    pulse_records: Tuple[PulseRecord, ...]
    compiled_targets: Tuple[CompiledScatterer, ...]
    status: ReflectionStatus


class GoldenReflectionSource:
    """End-to-end clock-free continuous polarimetric reflection reference."""

    def __init__(
        self,
        config: ModelConfig,
        calibration: CalibrationProfile,
        *,
        range_selection_mode: RangeSelectionMode = RangeSelectionMode.FIXED,
        fixed_ranges: Optional[Mapping[Polarization, GainRange]] = None,
    ) -> None:
        self.config = config
        self.calibration = calibration
        self.range_selection_mode = range_selection_mode
        self.fixed_ranges = dict(
            fixed_ranges
            if fixed_ranges is not None
            else {
                Polarization.H: GainRange.HIGH,
                Polarization.V: GainRange.HIGH,
            }
        )
        self.adc_frontend = GoldenEightChannelAdcFrontend(
            config,
            calibration,
        )
        self.target_compiler = TargetCompiler(config, calibration)
        self.kernel = GoldenPolarimetricReflectionKernel(
            config.fractional_delay_taps
        )
        self.predistorter = GoldenTxPredistorter(calibration)
        self.dac_router = GoldenEightChannelDacRouter(config, calibration)

    def _validate_run(
        self,
        adc_frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
    ) -> None:
        if adc_frame.samples.shape[1] != scenario.length:
            raise ValueError("ADC frame length must match scenario length")
        if adc_frame.start_sample != scenario.start_sample:
            raise ValueError("ADC frame start_sample must match scenario")
        if adc_frame.sample_rate_hz != self.config.reflection_sample_rate_hz:
            raise ValueError("ADC frame rate must match reflection configuration")
        if len(scenario.targets) > self.config.maximum_targets:
            raise ValueError("target count exceeds maximum_targets")

    def _run_monitor(
        self,
        adc_frame: EightChannelAdcFrame,
    ) -> Tuple[PulseRecord, ...]:
        records = []
        for entry in self.config.adc_channel_map:
            if (
                not entry.enabled
                or ChannelRole.ECHO not in entry.allowed_roles
                or entry.gain_range not in _LEGACY_RANGE
            ):
                continue
            batch = AdcSampleBatch(
                iq=adc_frame.samples[entry.index],
                clipped=adc_frame.clipped[entry.index],
            )
            records.extend(
                GoldenReceivePipeline(self.config).detect(
                    batch,
                    channel=entry.index,
                    range_id=_LEGACY_RANGE[entry.gain_range],
                )
            )
        return tuple(
            sorted(
                records,
                key=lambda record: (record.toa_samples, record.channel),
            )
        )

    def _status(
        self,
        adc_frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
        selected_ranges: np.ndarray,
        auxiliary: DacAuxRequest,
        pulse_records: Tuple[PulseRecord, ...],
    ) -> ReflectionStatus:
        clipped_by_polarization = []
        for polarization in (Polarization.H, Polarization.V):
            indices = [
                entry.index
                for entry in self.config.adc_channel_map
                if entry.polarization == polarization
                and ChannelRole.ECHO in entry.allowed_roles
            ]
            clipped_by_polarization.append(
                bool(np.any(adc_frame.clipped[indices]))
            )
        if selected_ranges.shape[1]:
            final_ranges = (
                selected_ranges[0, -1],
                selected_ranges[1, -1],
            )
        else:
            final_ranges = (
                self.fixed_ranges[Polarization.H],
                self.fixed_ranges[Polarization.V],
            )
        calibration_out_of_range = (
            abs(scenario.carrier_frequency_hz - self.calibration.frequency_hz)
            > self.calibration.frequency_tolerance_hz
            or abs(scenario.temperature_c - self.calibration.temperature_c)
            > self.calibration.temperature_tolerance_c
        )
        return ReflectionStatus(
            adc_clipped=(
                clipped_by_polarization[0],
                clipped_by_polarization[1],
            ),
            selected_ranges=final_ranges,
            absolute_rcs_calibrated=(
                self.target_compiler.last_absolute_rcs_calibrated
                and not calibration_out_of_range
            ),
            calibration_out_of_range=calibration_out_of_range,
            calibration_outputs_enabled=(
                auxiliary.mode == AuxOutputMode.CALIBRATION
            ),
            cancellation_outputs_enabled=(
                auxiliary.mode == AuxOutputMode.CANCELLATION
            ),
            monitor_pulse_count=len(pulse_records),
        )

    def run(
        self,
        adc_frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
        auxiliary: Optional[DacAuxRequest] = None,
    ) -> ReflectionSourceResult:
        self._validate_run(adc_frame, scenario)
        auxiliary_request = (
            auxiliary
            if auxiliary is not None
            else DacAuxRequest(AuxOutputMode.OFF, None)
        )

        frontend = self.adc_frontend.reconstruct(
            adc_frame,
            mode=self.range_selection_mode,
            fixed_ranges=self.fixed_ranges,
        )
        scatterers = self.target_compiler.compile(scenario)
        desired = self.kernel.process(frontend.incident, scatterers)
        uncompensated_reflection = self.kernel.process(
            frontend.measured_incident,
            scatterers,
        )
        actual_uncompensated = self.predistorter.forward(
            uncompensated_reflection
        )
        predistorted = self.predistorter.predistort(desired)
        dac_frame = self.dac_router.route(predistorted, auxiliary_request)

        pulse_records = self._run_monitor(adc_frame)
        status = self._status(
            adc_frame,
            scenario,
            frontend.selected_ranges,
            auxiliary_request,
            pulse_records,
        )
        return ReflectionSourceResult(
            incident=frontend.incident,
            desired_reflection=desired,
            actual_uncompensated=actual_uncompensated,
            predistorted_reflection=predistorted,
            dac_frame=dac_frame,
            pulse_records=pulse_records,
            compiled_targets=scatterers,
            status=status,
        )
