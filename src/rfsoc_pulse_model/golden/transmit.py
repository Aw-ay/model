from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..common.fixed import round_array_ties_away_from_zero


@dataclass(frozen=True)
class DacIq16Codes:
    """Clock-free signed-I16/Q16 representation at the RFDC PL boundary."""

    i: np.ndarray
    q: np.ndarray
    clipped: np.ndarray

    def __post_init__(self) -> None:
        i = np.asarray(self.i)
        q = np.asarray(self.q)
        clipped = np.asarray(self.clipped)
        if i.dtype != np.dtype(np.int16) or q.dtype != np.dtype(np.int16):
            raise ValueError("DAC I/Q code arrays must use int16 dtype")
        if clipped.dtype != np.dtype(np.bool_):
            raise ValueError("DAC clipping sideband must use bool dtype")
        if i.ndim != 2 or q.shape != i.shape or clipped.shape != i.shape:
            raise ValueError("DAC I/Q codes and clipping sideband must share a 2-D shape")
        immutable_i = np.array(i, copy=True)
        immutable_q = np.array(q, copy=True)
        immutable_clipped = np.array(clipped, copy=True)
        for array in (immutable_i, immutable_q, immutable_clipped):
            array.setflags(write=False)
        object.__setattr__(self, "i", immutable_i)
        object.__setattr__(self, "q", immutable_q)
        object.__setattr__(self, "clipped", immutable_clipped)


def quantize_complex_iq16(samples: np.ndarray) -> DacIq16Codes:
    """Round one complex envelope into independent saturated I16/Q16 codes."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 2:
        raise ValueError("complex DAC samples must be a 2-D channel/sample array")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("complex DAC samples must be finite")
    rounded_i = round_array_ties_away_from_zero(values.real)
    rounded_q = round_array_ties_away_from_zero(values.imag)
    clipped = (
        (rounded_i < -32_768)
        | (rounded_i > 32_767)
        | (rounded_q < -32_768)
        | (rounded_q > 32_767)
    )
    return DacIq16Codes(
        i=np.clip(rounded_i, -32_768, 32_767).astype(np.int16),
        q=np.clip(rounded_q, -32_768, 32_767).astype(np.int16),
        clipped=clipped,
    )


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
