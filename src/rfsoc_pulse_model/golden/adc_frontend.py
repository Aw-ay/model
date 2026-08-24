from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.config import ModelConfig
from ..common.reflection_types import (
    EightChannelAdcFrame,
    PolarimetricWaveform,
)
from ..common.types import (
    ChannelRole,
    GainRange,
    Polarization,
    RangeSelectionMode,
)
from .delay import apply_relative_delay


_POLARIZATIONS = (Polarization.H, Polarization.V)
_GAIN_ORDER = (GainRange.HIGH, GainRange.MID, GainRange.LOW)


@dataclass(frozen=True)
class AdcFrontendResult:
    measured_incident: PolarimetricWaveform
    incident: PolarimetricWaveform
    selected_ranges: np.ndarray
    aligned_raw_channels: np.ndarray
    corrected_channels: np.ndarray
    corrected_clipped: np.ndarray


@dataclass(frozen=True)
class AutoHoldState:
    current_ranges: Tuple[GainRange, GainRange]
    last_switch_samples: Tuple[int, int]
    next_sample: int


class GoldenEightChannelAdcFrontend:
    """Calibrate eight ADC paths and reconstruct H/V continuous waveforms."""

    def __init__(
        self,
        config: ModelConfig,
        calibration: CalibrationProfile,
    ) -> None:
        self.config = config
        self.calibration = calibration
        self._echo_indices = {
            (entry.polarization, entry.gain_range): entry.index
            for entry in config.adc_channel_map
            if entry.enabled and ChannelRole.ECHO in entry.allowed_roles
        }
        self._channel_entries = {
            entry.index: entry for entry in config.adc_channel_map
        }
        self._auto_hold_state: Optional[AutoHoldState] = None

    @property
    def auto_hold_state(self) -> Optional[AutoHoldState]:
        return self._auto_hold_state

    def reset_auto_hold(self) -> None:
        """Begin a new AUTO_HOLD acquisition at the next frame's start."""

        self._auto_hold_state = None

    def _correct_channels(
        self,
        frame: EightChannelAdcFrame,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        response_delays = np.array(
            [
                channel.response_delay_samples
                for channel in self.calibration.adc_channels
            ],
            dtype=np.float64,
        )
        if np.max(response_delays) - np.min(response_delays) <= 1e-15:
            aligned_raw = np.array(frame.samples, copy=True)
            aligned_clipped = np.array(frame.clipped, copy=True)
        else:
            taps = self.config.fractional_delay_taps
            center = (taps - 1) // 2
            maximum_delay = float(np.max(response_delays))
            aligned_raw = np.empty_like(frame.samples)
            aligned_clipped = np.empty_like(frame.clipped)
            sample_count = frame.samples.shape[1]
            for index, response_delay in enumerate(response_delays):
                compensation = maximum_delay - float(response_delay)
                integer_delay = int(np.floor(compensation))
                fractional_delay = compensation - integer_delay
                pair = np.vstack(
                    (
                        frame.samples[index],
                        np.zeros(sample_count, dtype=np.complex128),
                    )
                )
                aligned_raw[index] = apply_relative_delay(
                    pair,
                    compensation,
                    taps,
                )[0]

                coarse_clip = np.zeros(sample_count, dtype=np.int64)
                if integer_delay == 0:
                    coarse_clip[:] = frame.clipped[index]
                elif integer_delay < sample_count:
                    coarse_clip[integer_delay:] = frame.clipped[
                        index, : sample_count - integer_delay
                    ]
                if fractional_delay <= 1e-15:
                    aligned_clipped[index] = coarse_clip > 0
                else:
                    full_clip = np.convolve(
                        coarse_clip,
                        np.ones(taps, dtype=np.int64),
                        mode="full",
                    )
                    aligned_clipped[index] = (
                        full_clip[center : center + sample_count] > 0
                    )

        corrected = np.empty_like(aligned_raw)
        for index, channel in enumerate(self.calibration.adc_channels):
            nominal_voltage_gain = 10.0 ** (
                self._channel_entries[index].nominal_gain_db / 20.0
            )
            corrected[index] = aligned_raw[index] / (
                nominal_voltage_gain * channel.response_gain
            )
        return corrected, aligned_raw, aligned_clipped

    @staticmethod
    def _component_magnitude(samples: np.ndarray, index: int) -> float:
        return max(abs(samples[index].real), abs(samples[index].imag))

    def _fixed_selection(
        self,
        corrected: np.ndarray,
        fixed_ranges: Optional[Mapping[Polarization, GainRange]],
    ) -> Tuple[np.ndarray, np.ndarray]:
        if fixed_ranges is None or set(fixed_ranges) != set(_POLARIZATIONS):
            raise ValueError("FIXED mode requires one H and one V gain range")
        sample_count = corrected.shape[1]
        selected = np.empty((2, sample_count), dtype=object)
        measured = np.empty((2, sample_count), dtype=np.complex128)
        for row, polarization in enumerate(_POLARIZATIONS):
            gain_range = fixed_ranges[polarization]
            if gain_range not in _GAIN_ORDER:
                raise ValueError("FIXED mode accepts only HIGH, MID, or LOW")
            channel_index = self._echo_indices[(polarization, gain_range)]
            selected[row, :] = gain_range
            measured[row] = corrected[channel_index]
        return measured, selected

    def _auto_hold_selection(
        self,
        aligned_raw: np.ndarray,
        aligned_clipped: np.ndarray,
        corrected: np.ndarray,
        start_sample: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        sample_count = corrected.shape[1]
        selected = np.empty((2, sample_count), dtype=object)
        measured = np.empty((2, sample_count), dtype=np.complex128)
        high_water = self.config.auto_range_high_water_fraction * 32_767.0
        low_water = self.config.auto_range_low_water_fraction * 32_767.0

        if self._auto_hold_state is None:
            current_ranges = (GainRange.HIGH, GainRange.HIGH)
            last_switch_samples = (
                start_sample - self.config.auto_range_hold_samples,
                start_sample - self.config.auto_range_hold_samples,
            )
        else:
            if start_sample != self._auto_hold_state.next_sample:
                raise ValueError(
                    "AUTO_HOLD frames must use contiguous absolute samples; "
                    "call reset_auto_hold() to begin a new acquisition"
                )
            current_ranges = self._auto_hold_state.current_ranges
            last_switch_samples = self._auto_hold_state.last_switch_samples

        final_ranges = []
        final_switch_samples = []
        for row, polarization in enumerate(_POLARIZATIONS):
            range_index = _GAIN_ORDER.index(current_ranges[row])
            last_switch = last_switch_samples[row]
            for sample_index in range(sample_count):
                absolute_sample = start_sample + sample_index
                current_range = _GAIN_ORDER[range_index]
                channel_index = self._echo_indices[(polarization, current_range)]
                overloaded = bool(aligned_clipped[channel_index, sample_index]) or (
                    self._component_magnitude(
                        aligned_raw[channel_index], sample_index
                    )
                    >= high_water
                )
                if overloaded and range_index < len(_GAIN_ORDER) - 1:
                    while overloaded and range_index < len(_GAIN_ORDER) - 1:
                        range_index += 1
                        current_range = _GAIN_ORDER[range_index]
                        channel_index = self._echo_indices[
                            (polarization, current_range)
                        ]
                        overloaded = bool(
                            aligned_clipped[channel_index, sample_index]
                        ) or (
                            self._component_magnitude(
                                aligned_raw[channel_index], sample_index
                            )
                            >= high_water
                        )
                    last_switch = absolute_sample
                elif (
                    range_index > 0
                    and absolute_sample - last_switch
                    >= self.config.auto_range_hold_samples
                ):
                    candidate_range = _GAIN_ORDER[range_index - 1]
                    candidate_index = self._echo_indices[
                        (polarization, candidate_range)
                    ]
                    candidate_safe = not bool(
                        aligned_clipped[candidate_index, sample_index]
                    ) and (
                        self._component_magnitude(
                            aligned_raw[candidate_index], sample_index
                        )
                        < low_water
                    )
                    if candidate_safe:
                        range_index -= 1
                        last_switch = absolute_sample

                current_range = _GAIN_ORDER[range_index]
                channel_index = self._echo_indices[
                    (polarization, current_range)
                ]
                selected[row, sample_index] = current_range
                measured[row, sample_index] = corrected[
                    channel_index, sample_index
                ]
            final_ranges.append(_GAIN_ORDER[range_index])
            final_switch_samples.append(last_switch)
        self._auto_hold_state = AutoHoldState(
            current_ranges=(final_ranges[0], final_ranges[1]),
            last_switch_samples=(
                final_switch_samples[0],
                final_switch_samples[1],
            ),
            next_sample=start_sample + sample_count,
        )
        return measured, selected

    def reconstruct(
        self,
        frame: EightChannelAdcFrame,
        *,
        mode: RangeSelectionMode,
        fixed_ranges: Optional[Mapping[Polarization, GainRange]] = None,
    ) -> AdcFrontendResult:
        if frame.sample_rate_hz != self.config.reflection_sample_rate_hz:
            raise ValueError("ADC frame rate does not match reflection_sample_rate_hz")
        if mode == RangeSelectionMode.FUSED:
            raise ValueError("FUSED range selection is not implemented")
        if not isinstance(mode, RangeSelectionMode):
            raise ValueError("mode must be a RangeSelectionMode")

        corrected, aligned_raw, corrected_clipped = self._correct_channels(frame)
        if mode == RangeSelectionMode.FIXED:
            measured, selected = self._fixed_selection(
                corrected,
                fixed_ranges,
            )
        else:
            measured, selected = self._auto_hold_selection(
                aligned_raw,
                corrected_clipped,
                corrected,
                frame.start_sample,
            )

        incident_samples = (
            np.linalg.inv(self.calibration.rx_polarization_matrix) @ measured
        )
        measured_waveform = PolarimetricWaveform(
            measured,
            frame.sample_domain,
            frame.sample_rate_hz,
            frame.start_sample,
        )
        incident = PolarimetricWaveform(
            incident_samples,
            frame.sample_domain,
            frame.sample_rate_hz,
            frame.start_sample,
        )
        selected.setflags(write=False)
        aligned_raw.setflags(write=False)
        corrected.setflags(write=False)
        corrected_clipped.setflags(write=False)
        return AdcFrontendResult(
            measured_incident=measured_waveform,
            incident=incident,
            selected_ranges=selected,
            aligned_raw_channels=aligned_raw,
            corrected_channels=corrected,
            corrected_clipped=corrected_clipped,
        )
