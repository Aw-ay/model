from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..common.config import DetectorConfig
from ..common.fixed import round_array_ties_away_from_zero, round_ties_away_from_zero
from ..common.types import ChannelIdentity, IQSample, PulseRecord, RangeId


def _as_complex_array(iq: Sequence[complex]) -> np.ndarray:
    values = np.asarray(iq)
    if values.ndim == 1:
        return np.asarray(values, dtype=np.complex128)
    if values.ndim == 2 and values.shape[1] == 2:
        return np.asarray(values[:, 0], dtype=np.float64) + 1j * np.asarray(
            values[:, 1], dtype=np.float64
        )
    raise ValueError("iq must be a one-dimensional complex array or an Nx2 array")


def _regions(bits: np.ndarray) -> List[Tuple[int, int]]:
    padded = np.concatenate(([False], np.asarray(bits, dtype=np.bool_), [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1) - 1
    return list(zip(starts.tolist(), stops.tolist()))


def _frequency_turns(iq: np.ndarray) -> float:
    nonzero = iq[np.abs(iq) > 0.0]
    if nonzero.size < 2:
        return 0.0
    deltas = np.angle(nonzero[1:] * np.conjugate(nonzero[:-1]))
    return float(np.mean(deltas) / (2.0 * np.pi))


def _frequency_word(turns_per_sample: float) -> int:
    value = round_ties_away_from_zero(turns_per_sample * (1 << 31))
    return max(-(1 << 31), min((1 << 31) - 1, value))


def _payload(samples: np.ndarray, config: DetectorConfig) -> Tuple[IQSample, ...]:
    i_values = np.clip(
        round_array_ties_away_from_zero(samples.real),
        config.iq_min_code,
        config.iq_max_code,
    ).astype(np.int64)
    q_values = np.clip(
        round_array_ties_away_from_zero(samples.imag),
        config.iq_min_code,
        config.iq_max_code,
    ).astype(np.int64)
    return tuple((int(i_value), int(q_value)) for i_value, q_value in zip(i_values, q_values))


class GoldenPulseDetector:
    """Array-oriented ideal detector without clocks, RAM, FIFO, or AXI."""

    def __init__(self, config: DetectorConfig) -> None:
        self.config = config
        self.last_thresholds = np.empty(0, dtype=np.float64)

    def detect(
        self,
        iq: Sequence[complex],
        *,
        channel: int = 0,
        range_id: RangeId = RangeId.ZERO_DB,
        start_index: int = 0,
        adc_clipped: Optional[Sequence[bool]] = None,
        channel_identity: Optional[ChannelIdentity] = None,
    ) -> List[PulseRecord]:
        samples = _as_complex_array(iq)
        if samples.size == 0:
            self.last_thresholds = np.empty(0, dtype=np.float64)
            return []

        if adc_clipped is None:
            clipped = (
                (samples.real >= self.config.iq_max_code)
                | (samples.real <= self.config.iq_min_code)
                | (samples.imag >= self.config.iq_max_code)
                | (samples.imag <= self.config.iq_min_code)
            )
        else:
            clipped = np.asarray(adc_clipped, dtype=np.bool_)
            if clipped.ndim != 1 or clipped.size != samples.size:
                raise ValueError("adc_clipped must contain one flag per IQ sample")

        powers = np.square(samples.real) + np.square(samples.imag)
        boot_count = min(self.config.noise_boot_samples, powers.size)
        noise = float(np.mean(powers[:boot_count]))
        threshold = max(1.0, noise * self.config.threshold_scale)
        thresholds = np.full(powers.size, threshold, dtype=np.float64)
        raw = np.zeros(powers.size, dtype=np.bool_)
        detected = np.zeros(powers.size, dtype=np.bool_)
        power_history: List[float] = []
        vote_history: List[bool] = []
        active = False

        for index in range(boot_count, powers.size):
            thresholds[index] = threshold
            power_history.append(float(powers[index]))
            if len(power_history) > self.config.moving_average:
                del power_history[0]
            raw[index] = (
                len(power_history) == self.config.moving_average
                and sum(power_history)
                > threshold * self.config.moving_average
            )
            freeze = bool(raw[index]) or any(vote_history) or active
            if not freeze:
                alpha = 1.0 / float(1 << self.config.noise_update_shift)
                noise += (float(powers[index]) - noise) * alpha
                threshold = max(1.0, noise * self.config.threshold_scale)
            vote_history.append(bool(raw[index]))
            if len(vote_history) > self.config.vote_window:
                del vote_history[0]
            active = (
                len(vote_history) == self.config.vote_window
                and sum(vote_history) >= self.config.vote_required
            )
            detected[index] = active

        self.last_thresholds = thresholds
        latency = self.config.moving_average + self.config.vote_window - 2
        records: List[PulseRecord] = []
        for coarse_start, coarse_end in _regions(detected):
            search_start = max(boot_count, coarse_start - latency)
            search_end = min(powers.size - 1, coarse_end + latency)
            window_power = powers[search_start : search_end + 1]
            if window_power.size == 0:
                continue
            peak = float(np.max(window_power))
            refine_threshold = max(float(thresholds[coarse_start]), peak / 2.0)
            peak_offset = int(np.argmax(window_power))
            left_offset = peak_offset
            while (
                left_offset > 0
                and window_power[left_offset - 1] >= refine_threshold
            ):
                left_offset -= 1
            right_offset = peak_offset
            while (
                right_offset + 1 < window_power.size
                and window_power[right_offset + 1] >= refine_threshold
            ):
                right_offset += 1
            refined_start = search_start + left_offset
            refined_end = search_start + right_offset
            width = refined_end - refined_start + 1
            if width < self.config.min_pulse_samples:
                continue
            truncated = width > self.config.max_pulse_samples
            if truncated:
                refined_end = refined_start + self.config.max_pulse_samples - 1
                width = self.config.max_pulse_samples
            payload_start = max(0, refined_start - self.config.pre_samples)
            payload_end = min(
                samples.size,
                refined_end + self.config.post_samples + 1,
            )
            pulse_samples = samples[refined_start : refined_end + 1]
            pulse_powers = powers[refined_start : refined_end + 1]
            frequency = _frequency_turns(pulse_samples)
            records.append(
                PulseRecord(
                    channel=channel,
                    range_id=range_id,
                    sample_domain=self.config.sample_domain,
                    sample_rate_hz=self.config.sample_rate_hz,
                    iq_width_bits=self.config.iq_width_bits,
                    iq_fraction_bits=self.config.iq_fraction_bits,
                    iq_signed=self.config.iq_signed,
                    iq_unit=self.config.iq_unit,
                    power_width_bits=self.config.power_width_bits,
                    power_fraction_bits=self.config.power_fraction_bits,
                    power_unit=self.config.power_unit,
                    toa_samples=start_index + refined_start,
                    pw_samples=width,
                    peak_power=min(
                        self.config.power_max_code,
                        round_ties_away_from_zero(float(np.max(pulse_powers))),
                    ),
                    mean_power=min(
                        self.config.power_max_code,
                        round_ties_away_from_zero(float(np.mean(pulse_powers))),
                    ),
                    freq_word=_frequency_word(frequency),
                    iq=_payload(samples[payload_start:payload_end], self.config),
                    saturated=bool(np.any(clipped[refined_start : refined_end + 1])),
                    truncated=truncated,
                    channel_identity=channel_identity,
                )
            )
        return records
