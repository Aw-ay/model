from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Sequence, Tuple, Union

import numpy as np

from ..common.tables import FIR_DECIMATOR_FLOAT
from ..common.types import PulseRecord, RangeId
from ..common.fixed import round_array_ties_away_from_zero
from ..common.config import ModelConfig
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


@dataclass(frozen=True)
class AdcSampleBatch:
    """ADC samples plus an authoritative per-sample clipping sideband."""

    iq: np.ndarray
    clipped: np.ndarray

    def __post_init__(self) -> None:
        if self.iq.ndim != 1 or self.clipped.ndim != 1:
            raise ValueError("ADC IQ and clipping arrays must be one-dimensional")
        if self.iq.size != self.clipped.size:
            raise ValueError("ADC IQ and clipping arrays must have equal length")

    @property
    def any_clipped(self) -> bool:
        return bool(np.any(self.clipped))

    def __iter__(self) -> Iterator[object]:
        """Preserve the earlier ``iq, any_clipped = result`` convenience."""

        yield self.iq
        yield self.any_clipped


def apply_range_gain(iq: Sequence[complex], gain_db: float) -> AdcSampleBatch:
    """Apply ideal analogue gain followed by signed-16 ADC clipping."""

    samples = np.asarray(iq, dtype=np.complex128)
    scaled = samples * (10.0 ** (float(gain_db) / 20.0))
    rounded_i = round_array_ties_away_from_zero(scaled.real)
    rounded_q = round_array_ties_away_from_zero(scaled.imag)
    clipped = (
        (rounded_i > 32_767)
        | (rounded_i < -32_768)
        | (rounded_q > 32_767)
        | (rounded_q < -32_768)
    )
    return AdcSampleBatch(
        iq=(
            np.clip(rounded_i, -32_768, 32_767)
            + 1j * np.clip(rounded_q, -32_768, 32_767)
        ),
        clipped=np.asarray(clipped, dtype=np.bool_),
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
    adc_clipped: np.ndarray


class GoldenReceivePipeline:
    """Ideal 500-to-250 MSPS FIR/decimation followed by pulse detection."""

    filter_length = len(FIR_DECIMATOR_FLOAT)
    group_delay_input_samples = (filter_length - 1) // 2

    def __init__(
        self,
        config: Optional[Union[ModelConfig, DetectorConfig]] = None,
    ) -> None:
        if config is None:
            config = ModelConfig.load_default()
        if isinstance(config, ModelConfig):
            self.model_config: Optional[ModelConfig] = config
            detector_config = config.detector
            self.decimation = config.pl_decimation
            self.group_delay_input_samples = config.group_delay_input_samples
        else:
            self.model_config = None
            detector_config = config
            self.decimation = 2
        self.detector = GoldenPulseDetector(detector_config)

    def decimate(
        self,
        source_iq: Union[Sequence[complex], AdcSampleBatch],
    ) -> GoldenReceiveResult:
        if isinstance(source_iq, AdcSampleBatch):
            samples = np.asarray(source_iq.iq, dtype=np.complex128)
            source_clipped = np.asarray(source_iq.clipped, dtype=np.bool_)
        else:
            samples = np.asarray(source_iq, dtype=np.complex128)
            source_clipped = (
                (samples.real >= 32_767)
                | (samples.real <= -32_768)
                | (samples.imag >= 32_767)
                | (samples.imag <= -32_768)
            )
        if samples.ndim != 1:
            raise ValueError("source_iq must be one-dimensional")
        if samples.size < self.filter_length:
            return GoldenReceiveResult(
                iq=np.empty(0, dtype=np.complex128),
                source_sample_indices=np.empty(0, dtype=np.int64),
                adc_clipped=np.empty(0, dtype=np.bool_),
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
        select = (newest_indices % self.decimation) == 0
        clip_windows = np.convolve(
            source_clipped.astype(np.int64),
            np.ones(self.filter_length, dtype=np.int64),
            mode="valid",
        )
        return GoldenReceiveResult(
            iq=np.asarray(filtered[select], dtype=np.complex128),
            source_sample_indices=(
                newest_indices[select] - self.group_delay_input_samples
            ),
            adc_clipped=np.asarray(clip_windows[select] > 0, dtype=np.bool_),
        )

    def detect(
        self,
        source_iq: Union[Sequence[complex], AdcSampleBatch],
        *,
        channel: int = 0,
        range_id: RangeId = RangeId.ZERO_DB,
    ) -> list[PulseRecord]:
        result = self.decimate(source_iq)
        return self.detector.detect(
            result.iq,
            channel=channel,
            range_id=range_id,
            adc_clipped=result.adc_clipped,
        )
