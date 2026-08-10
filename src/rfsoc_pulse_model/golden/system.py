from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional, Tuple

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.config import ModelConfig
from ..common.events import associate_polarimetric_range_records
from ..common.reflection_types import (
    CompiledScatterer,
    DacAuxRequest,
    EightChannelAdcFrame,
    EightChannelDacFrame,
    PolarimetricWaveform,
    ReflectionScenario,
    ReflectionStatus,
    TargetRequest,
)
from ..common.types import (
    AuxOutputMode,
    ChannelIdentity,
    ChannelRole,
    GainRange,
    Polarization,
    PulseRecord,
    PulseEvent,
    RangeId,
    RangeSelectionMode,
    SampleDomain,
)
from .adc_frontend import GoldenEightChannelAdcFrontend
from .calibration import GoldenTxPredistorter
from .dac_router import GoldenEightChannelDacRouter
from .delay import fractional_delay_center_samples
from .receive import AdcSampleBatch, GoldenReceivePipeline
from .reflection import (
    GoldenPolarimetricReflectionKernel,
    TargetCompiler,
)
from .transmit import DacIq16Codes, quantize_complex_iq16


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
    dac_iq_codes: DacIq16Codes
    pulse_records: Tuple[PulseRecord, ...]
    pulse_events: Tuple[PulseEvent, ...]
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
                    source_start_sample=adc_frame.start_sample,
                    channel_identity=ChannelIdentity(
                        entry.polarization,
                        entry.gain_range,
                        ChannelRole.ECHO,
                        entry.index,
                    ),
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
            monitor_pulse_count_total=len(pulse_records),
            processed_stop_sample=(
                adc_frame.start_sample + adc_frame.samples.shape[1]
            ),
            emitted_stop_sample=(
                adc_frame.start_sample + adc_frame.samples.shape[1]
            ),
            stream_final=True,
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
        dac_iq_codes = quantize_complex_iq16(dac_frame.samples)

        pulse_records = self._run_monitor(adc_frame)
        pulse_events = tuple(
            associate_polarimetric_range_records(
                pulse_records,
                toa_tolerance=self.config.toa_tolerance,
                width_tolerance=self.config.width_tolerance,
                config_version=self.config.config_version,
            )
        )
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
            dac_iq_codes=dac_iq_codes,
            pulse_records=pulse_records,
            pulse_events=pulse_events,
            compiled_targets=scatterers,
            status=status,
        )


class GoldenReflectionStream:
    """Stateful chunk-invariant Golden oracle for one continuous acquisition.

    The implementation intentionally buffers the accumulated mathematical
    input and re-evaluates the stateless Golden reference.  It emits only the
    prefix that cannot depend on future samples, so arbitrary software chunk
    boundaries cannot change the observable result.  This is an oracle
    contract, not the finite-memory structure that the Cycle layer must use.
    """

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
        self._samples = np.empty((8, 0), dtype=np.complex128)
        self._clipped = np.empty((8, 0), dtype=np.bool_)
        self._initial_start: Optional[int] = None
        self._next_start: Optional[int] = None
        self._scenario: Optional[ReflectionScenario] = None
        self._emitted_samples = 0
        self._emitted_records: set[PulseRecord] = set()
        self._emitted_events: set[tuple[PulseRecord, ...]] = set()
        self._finalized = False
        self._lookahead = self._relative_lookahead()

    def _relative_lookahead(self) -> int:
        center = fractional_delay_center_samples(self.config.fractional_delay_taps)

        def needs_fractional_alignment(channels: tuple) -> bool:
            delays = [channel.response_delay_samples for channel in channels]
            maximum = max(delays)
            if maximum - min(delays) <= 1e-15:
                return False
            return any(
                abs((maximum - delay) - round(maximum - delay)) > 1e-15
                for delay in delays
            )

        return center * (
            int(needs_fractional_alignment(self.calibration.adc_channels))
            + int(needs_fractional_alignment(self.calibration.dac_channels))
        )

    @staticmethod
    def _targets_equal(
        left: Tuple[TargetRequest, ...],
        right: Tuple[TargetRequest, ...],
    ) -> bool:
        if len(left) != len(right):
            return False
        for first, second in zip(left, right):
            if (
                first.apparent_range_m != second.apparent_range_m
                or first.radial_velocity_mps != second.radial_velocity_mps
                or first.target_rcs_m2 != second.target_rcs_m2
                or first.rcs_reference_channel != second.rcs_reference_channel
                or first.initial_phase_rad != second.initial_phase_rad
                or not np.array_equal(
                    first.normalized_scattering_matrix,
                    second.normalized_scattering_matrix,
                )
            ):
                return False
        return True

    def _validate_chunk(
        self,
        frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
    ) -> None:
        if self._finalized:
            raise ValueError("stream is already finalized")
        if frame.start_sample != scenario.start_sample:
            raise ValueError("ADC frame and scenario start_sample must match")
        if frame.samples.shape[1] != scenario.length:
            raise ValueError("ADC frame and scenario length must match")
        if self._next_start is not None and frame.start_sample != self._next_start:
            raise ValueError("stream chunks must use contiguous absolute samples")
        if self._scenario is None:
            return
        reference = self._scenario
        if (
            scenario.physical_range_m != reference.physical_range_m
            or scenario.carrier_frequency_hz != reference.carrier_frequency_hz
            or scenario.temperature_c != reference.temperature_c
            or scenario.require_absolute_rcs != reference.require_absolute_rcs
            or not self._targets_equal(scenario.targets, reference.targets)
        ):
            raise ValueError("stream scenario physics must remain constant")

    def _combined_run(self) -> ReflectionSourceResult:
        assert self._initial_start is not None
        assert self._scenario is not None
        frame = EightChannelAdcFrame(
            self._samples,
            self._clipped,
            SampleDomain.RFDC_COMPLEX_INPUT,
            self.config.reflection_sample_rate_hz,
            self._initial_start,
        )
        scenario = ReflectionScenario(
            physical_range_m=self._scenario.physical_range_m,
            carrier_frequency_hz=self._scenario.carrier_frequency_hz,
            targets=self._scenario.targets,
            temperature_c=self._scenario.temperature_c,
            start_sample=self._initial_start,
            length=self._samples.shape[1],
            require_absolute_rcs=self._scenario.require_absolute_rcs,
        )
        return GoldenReflectionSource(
            self.config,
            self.calibration,
            range_selection_mode=self.range_selection_mode,
            fixed_ranges=self.fixed_ranges,
        ).run(frame, scenario)

    @staticmethod
    def _slice_result(
        result: ReflectionSourceResult,
        start: int,
        stop: int,
        *,
        pulse_records: Tuple[PulseRecord, ...],
        pulse_events: Tuple[PulseEvent, ...],
        status: ReflectionStatus,
    ) -> ReflectionSourceResult:
        def waveform_slice(waveform: PolarimetricWaveform) -> PolarimetricWaveform:
            return PolarimetricWaveform(
                waveform.samples[:, start:stop],
                waveform.sample_domain,
                waveform.sample_rate_hz,
                waveform.start_sample + start,
            )

        dac_frame = EightChannelDacFrame(
            samples=result.dac_frame.samples[:, start:stop],
            sample_domain=result.dac_frame.sample_domain,
            sample_rate_hz=result.dac_frame.sample_rate_hz,
            representation=result.dac_frame.representation,
            fixed_internal_delay=result.dac_frame.fixed_internal_delay,
            time_reference=result.dac_frame.time_reference,
            start_sample=result.dac_frame.start_sample + start,
        )
        dac_iq_codes = DacIq16Codes(
            i=result.dac_iq_codes.i[:, start:stop],
            q=result.dac_iq_codes.q[:, start:stop],
            clipped=result.dac_iq_codes.clipped[:, start:stop],
        )
        return ReflectionSourceResult(
            incident=waveform_slice(result.incident),
            desired_reflection=waveform_slice(result.desired_reflection),
            actual_uncompensated=waveform_slice(result.actual_uncompensated),
            predistorted_reflection=waveform_slice(
                result.predistorted_reflection
            ),
            dac_frame=dac_frame,
            dac_iq_codes=dac_iq_codes,
            pulse_records=pulse_records,
            pulse_events=pulse_events,
            compiled_targets=result.compiled_targets,
            status=status,
        )

    def _monitor_detector_stop_sample(self) -> int:
        assert self._initial_start is not None
        entry = next(
            entry
            for entry in self.config.adc_channel_map
            if entry.enabled and ChannelRole.ECHO in entry.allowed_roles
        )
        decimated = GoldenReceivePipeline(self.config).decimate(
            AdcSampleBatch(
                iq=self._samples[entry.index],
                clipped=self._clipped[entry.index],
            ),
            source_start_sample=self._initial_start,
        )
        if not decimated.source_sample_indices.size:
            return 0
        first_detector_sample = int(
            (
                decimated.source_sample_indices[0]
                - self.config.group_delay_input_samples
            )
            // self.config.pl_decimation
        )
        return first_detector_sample + int(decimated.iq.size)

    def _new_stable_monitor_outputs(
        self,
        result: ReflectionSourceResult,
        *,
        final: bool,
    ) -> Tuple[Tuple[PulseRecord, ...], Tuple[PulseEvent, ...]]:
        detector_stop = self._monitor_detector_stop_sample()
        detector_latency = (
            self.config.detector.moving_average
            + self.config.detector.vote_window
            - 2
        )
        association_guard = self.config.toa_tolerance + self.config.width_tolerance
        stable_guard = (
            detector_latency
            + self.config.detector.post_samples
            + association_guard
        )
        stable_record_prefix = []
        for record in result.pulse_records:
            stable = final or (
                record.toa_samples
                + record.pw_samples
                - 1
                + stable_guard
                < detector_stop
            )
            if not stable:
                break
            stable_record_prefix.append(record)
        stable_records = tuple(stable_record_prefix)
        stable_record_set = set(stable_records)
        new_records = tuple(
            record
            for record in stable_records
            if record not in self._emitted_records
        )
        stable_event_prefix = []
        for event in result.pulse_events:
            if not all(record in stable_record_set for record in event.records):
                break
            stable_event_prefix.append(event)
        stable_events = tuple(stable_event_prefix)
        new_events = tuple(
            event
            for event in stable_events
            if event.records not in self._emitted_events
        )
        self._emitted_records.update(new_records)
        self._emitted_events.update(event.records for event in new_events)
        return new_records, new_events

    def process_chunk(
        self,
        frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
        *,
        final: bool = False,
    ) -> ReflectionSourceResult:
        """Append one contiguous chunk and return the newly stable prefix."""

        self._validate_chunk(frame, scenario)
        if self._initial_start is None:
            self._initial_start = frame.start_sample
            self._scenario = scenario
        self._samples = np.concatenate((self._samples, frame.samples), axis=1)
        self._clipped = np.concatenate((self._clipped, frame.clipped), axis=1)
        self._next_start = frame.start_sample + frame.samples.shape[1]

        result = self._combined_run()
        stable_stop = (
            self._samples.shape[1]
            if final
            else max(0, self._samples.shape[1] - self._lookahead)
        )
        pulse_records, pulse_events = self._new_stable_monitor_outputs(
            result,
            final=final,
        )
        assert self._initial_start is not None
        status = replace(
            result.status,
            monitor_pulse_count=len(pulse_records),
            monitor_pulse_count_total=len(self._emitted_records),
            processed_stop_sample=self._next_start,
            emitted_stop_sample=self._initial_start + stable_stop,
            stream_final=final,
        )
        emitted = self._slice_result(
            result,
            self._emitted_samples,
            stable_stop,
            pulse_records=pulse_records,
            pulse_events=pulse_events,
            status=status,
        )
        self._emitted_samples = stable_stop
        self._finalized = final
        return emitted
