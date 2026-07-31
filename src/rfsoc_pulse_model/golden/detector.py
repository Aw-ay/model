from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

import numpy as np

from ..common.types import IQSample, PulseRecord, RangeId


@dataclass(frozen=True)
class DetectorConfig:
    noise_boot_samples: int = 16_384
    threshold_scale: float = 13.815510557964274
    noise_update_shift: int = 8
    moving_average: int = 8
    vote_window: int = 5
    vote_required: int = 3
    pre_samples: int = 16
    post_samples: int = 16
    min_pulse_samples: int = 1
    max_pulse_samples: int = 65_535
    full_scale: int = 32_767

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "DetectorConfig":
        names = (
            "noise_boot_samples",
            "threshold_scale",
            "noise_update_shift",
            "moving_average",
            "vote_window",
            "vote_required",
            "pre_samples",
            "post_samples",
            "min_pulse_samples",
            "max_pulse_samples",
            "full_scale",
        )
        return cls(**{name: values[name] for name in names if name in values})

    def __post_init__(self) -> None:
        if self.noise_boot_samples < 1:
            raise ValueError("noise_boot_samples must be positive")
        if self.threshold_scale <= 0.0:
            raise ValueError("threshold_scale must be positive")
        if not 1 <= self.noise_update_shift <= 31:
            raise ValueError("noise_update_shift must be between one and 31")
        if self.moving_average < 1:
            raise ValueError("moving_average must be positive")
        if not 1 <= self.vote_required <= self.vote_window:
            raise ValueError("vote_required must be within vote_window")
        if self.pre_samples < 0 or self.post_samples < 0:
            raise ValueError("guard sample counts cannot be negative")
        if self.min_pulse_samples < 1:
            raise ValueError("min_pulse_samples must be positive")
        if self.max_pulse_samples < self.min_pulse_samples:
            raise ValueError("max_pulse_samples must cover min_pulse_samples")


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
    value = int(round(turns_per_sample * (1 << 31)))
    return max(-(1 << 31), min((1 << 31) - 1, value))


def _payload(samples: np.ndarray) -> Tuple[IQSample, ...]:
    i_values = np.clip(np.rint(samples.real), -32_768, 32_767).astype(np.int64)
    q_values = np.clip(np.rint(samples.imag), -32_768, 32_767).astype(np.int64)
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
    ) -> List[PulseRecord]:
        samples = _as_complex_array(iq)
        if samples.size == 0:
            self.last_thresholds = np.empty(0, dtype=np.float64)
            return []

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
            above_half = np.flatnonzero(window_power >= refine_threshold)
            if above_half.size == 0:
                continue
            refined_start = search_start + int(above_half[0])
            refined_end = search_start + int(above_half[-1])
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
                    toa_samples=start_index + refined_start,
                    pw_samples=width,
                    peak_power=min(0xFFFF_FFFF, int(round(float(np.max(pulse_powers))))),
                    mean_power=min(0xFFFF_FFFF, int(round(float(np.mean(pulse_powers))))),
                    freq_word=_frequency_word(frequency),
                    iq=_payload(samples[payload_start:payload_end]),
                    saturated=bool(
                        np.any(np.abs(pulse_samples.real) >= self.config.full_scale)
                        or np.any(np.abs(pulse_samples.imag) >= self.config.full_scale)
                    ),
                    truncated=truncated,
                )
            )
        return records
