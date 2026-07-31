from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np

from ..common.tables import FIR_DECIMATOR_FLOAT
from ..common.types import PulseRecord, RangeId
from .detector import DetectorConfig, GoldenPulseDetector


def _signed_16_word(value: int) -> int:
    raw = int(value) & 0xFFFF
    return raw - 0x10000 if raw & 0x8000 else raw


def unpack_dual_iq_words(i_word: int, q_word: int) -> np.ndarray:
    """Return the early and late complex samples from aligned RFDC I/Q words."""

    return np.array(
        [
            complex(_signed_16_word(i_word), _signed_16_word(q_word)),
            complex(_signed_16_word(i_word >> 16), _signed_16_word(q_word >> 16)),
        ],
        dtype=np.complex128,
    )


def apply_range_gain(iq: Sequence[complex], gain_db: float) -> Tuple[np.ndarray, bool]:
    """Apply ideal analogue gain followed by signed-16 ADC clipping."""

    samples = np.asarray(iq, dtype=np.complex128)
    scaled = samples * (10.0 ** (float(gain_db) / 20.0))
    rounded_i = np.rint(scaled.real)
    rounded_q = np.rint(scaled.imag)
    clipped = bool(
        np.any(rounded_i > 32_767)
        or np.any(rounded_i < -32_768)
        or np.any(rounded_q > 32_767)
        or np.any(rounded_q < -32_768)
    )
    return (
        np.clip(rounded_i, -32_768, 32_767)
        + 1j * np.clip(rounded_q, -32_768, 32_767),
        clipped,
    )


@dataclass(frozen=True)
class PulseSpec:
    toa: int
    width: int
    amplitude: float
    frequency_turns_per_sample: float = 0.0
    chirp_turns_per_sample2: float = 0.0
    phase_turns: float = 0.0

    def __post_init__(self) -> None:
        if self.toa < 0:
            raise ValueError("pulse toa cannot be negative")
        if self.width < 1:
            raise ValueError("pulse width must be positive")
        if self.amplitude < 0.0:
            raise ValueError("pulse amplitude cannot be negative")


@dataclass(frozen=True)
class SignalScenario:
    length: int
    pulses: Tuple[PulseSpec, ...]
    noise_sigma: float = 0.0
    seed: int = 1

    def __post_init__(self) -> None:
        if self.length < 0:
            raise ValueError("scenario length cannot be negative")
        if self.noise_sigma < 0.0:
            raise ValueError("noise_sigma cannot be negative")


def generate_iq(scenario: SignalScenario) -> np.ndarray:
    """Generate a reproducible ideal complex test scenario as one NumPy array."""

    rng = np.random.default_rng(scenario.seed)
    samples = rng.normal(0.0, scenario.noise_sigma, scenario.length) + 1j * rng.normal(
        0.0, scenario.noise_sigma, scenario.length
    )
    for pulse in scenario.pulses:
        start = pulse.toa
        stop = min(scenario.length, pulse.toa + pulse.width)
        if start >= scenario.length:
            continue
        relative = np.arange(stop - start, dtype=np.float64)
        phase_turns = (
            pulse.phase_turns
            + relative * pulse.frequency_turns_per_sample
            + 0.5 * np.square(relative) * pulse.chirp_turns_per_sample2
        )
        samples[start:stop] += pulse.amplitude * np.exp(2j * np.pi * phase_turns)
    return np.asarray(samples, dtype=np.complex128)


@dataclass(frozen=True)
class GoldenReceiveResult:
    iq: np.ndarray
    source_sample_indices: np.ndarray


class GoldenReceivePipeline:
    """Ideal 500-to-250 MSPS FIR/decimation followed by pulse detection."""

    filter_length = len(FIR_DECIMATOR_FLOAT)
    group_delay_input_samples = (filter_length - 1) // 2

    def __init__(self, detector_config: DetectorConfig = DetectorConfig()) -> None:
        self.detector = GoldenPulseDetector(detector_config)

    def decimate(self, source_iq: Sequence[complex]) -> GoldenReceiveResult:
        samples = np.asarray(source_iq, dtype=np.complex128)
        if samples.ndim != 1:
            raise ValueError("source_iq must be one-dimensional")
        if samples.size < self.filter_length:
            return GoldenReceiveResult(
                iq=np.empty(0, dtype=np.complex128),
                source_sample_indices=np.empty(0, dtype=np.int64),
            )
        filtered = np.convolve(
            samples,
            np.asarray(FIR_DECIMATOR_FLOAT, dtype=np.float64),
            mode="valid",
        )
        newest_indices = np.arange(
            self.filter_length - 1,
            samples.size,
            dtype=np.int64,
        )
        select = (newest_indices & 1) == 0
        return GoldenReceiveResult(
            iq=np.asarray(filtered[select], dtype=np.complex128),
            source_sample_indices=(
                newest_indices[select] - self.group_delay_input_samples
            ),
        )

    def detect(
        self,
        source_iq: Sequence[complex],
        *,
        channel: int = 0,
        range_id: RangeId = RangeId.ZERO_DB,
    ) -> list[PulseRecord]:
        result = self.decimate(source_iq)
        return self.detector.detect(
            result.iq,
            channel=channel,
            range_id=range_id,
        )
