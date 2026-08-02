from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..common.fixed import round_array_ties_away_from_zero


@dataclass(frozen=True)
class GoldenLfmConfig:
    """Clock-free numerical form of the later DAC-domain phase accumulator."""

    phase_inc_0: int
    phase_inc_step: int
    pulse_samples: int
    amplitude_q15: int

    def __post_init__(self) -> None:
        if self.pulse_samples < 1:
            raise ValueError("pulse_samples must be positive")
        if not 0 <= self.amplitude_q15 <= 32_767:
            raise ValueError("amplitude_q15 must be between zero and 32767")


def generate_lfm_waveform(config: GoldenLfmConfig) -> np.ndarray:
    """Return unquantized real LFM samples using the exact phase-word law."""

    phase = 0
    increment = int(config.phase_inc_0) & 0xFFFF_FFFF
    step = int(config.phase_inc_step) & 0xFFFF_FFFF
    phases = np.empty(config.pulse_samples, dtype=np.float64)
    for index in range(config.pulse_samples):
        phases[index] = phase / float(1 << 32)
        phase = (phase + increment) & 0xFFFF_FFFF
        increment = (increment + step) & 0xFFFF_FFFF
    return config.amplitude_q15 * np.sin(2.0 * np.pi * phases)


def generate_lfm_samples(config: GoldenLfmConfig) -> np.ndarray:
    """Quantize the ideal waveform to the signed-16 DAC sample contract."""

    waveform = generate_lfm_waveform(config)
    rounded = round_array_ties_away_from_zero(waveform)
    return np.clip(rounded, -32_768, 32_767).astype(np.int16)
