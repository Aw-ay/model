"""Cycle-exact 2SPC reference for calibration and H/V auto-ranging."""

from __future__ import annotations

from functools import lru_cache
import math


CHANNEL_COUNT = 8
FRACTIONAL_DELAY_TAPS = 63
FRACTIONAL_COEFFICIENT_BITS = 17
GAIN_FRACTION_BITS = 20
S24_MIN = -(1 << 23)
S24_MAX = (1 << 23) - 1

IQ = tuple[int, int]
Lane = tuple[IQ, ...]


class CalibratorChannelParameters:
    """One channel's shadow/active calibration register values."""

    __slots__ = ("integer_delay", "fractional_delay_q20", "gain_real", "gain_imag", "enabled")

    def __init__(
        self,
        integer_delay: int = 0,
        fractional_delay_q20: int = 0,
        gain_real: int = 1 << GAIN_FRACTION_BITS,
        gain_imag: int = 0,
        enabled: bool = True,
    ) -> None:
        if not isinstance(integer_delay, int) or isinstance(integer_delay, bool) or not 0 <= integer_delay <= 2047:
            raise ValueError("integer_delay must be in 0..2047")
        if (
            not isinstance(fractional_delay_q20, int)
            or isinstance(fractional_delay_q20, bool)
            or not 0 <= fractional_delay_q20 < (1 << 20)
        ):
            raise ValueError("fractional_delay_q20 must be in 0..1048575")
        for name, value in (("gain_real", gain_real), ("gain_imag", gain_imag)):
            if not isinstance(value, int) or isinstance(value, bool) or not S24_MIN <= value <= S24_MAX:
                raise ValueError(f"{name} must be a signed 24-bit s24.Q20 value")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        self.integer_delay = integer_delay
        self.fractional_delay_q20 = fractional_delay_q20
        self.gain_real = gain_real
        self.gain_imag = gain_imag
        self.enabled = enabled

    def copy(self) -> "CalibratorChannelParameters":
        return CalibratorChannelParameters(
            integer_delay=self.integer_delay,
            fractional_delay_q20=self.fractional_delay_q20,
            gain_real=self.gain_real,
            gain_imag=self.gain_imag,
            enabled=self.enabled,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CalibratorChannelParameters) and all(
            getattr(self, name) == getattr(other, name) for name in self.__slots__
        )


class ActiveCalibrationBank:
    """Eight-channel shadow bank with acquisition-safe atomic commit."""

    def __init__(self) -> None:
        self._active = tuple(CalibratorChannelParameters() for _ in range(CHANNEL_COUNT))
        self._shadow = [parameters.copy() for parameters in self._active]
        self._config_version = 0

    @property
    def active(self) -> tuple[CalibratorChannelParameters, ...]:
        return tuple(parameters.copy() for parameters in self._active)

    @property
    def shadow(self) -> tuple[CalibratorChannelParameters, ...]:
        return tuple(parameters.copy() for parameters in self._shadow)

    @property
    def config_version(self) -> int:
        return self._config_version

    def write_shadow(self, channel: int, parameters: CalibratorChannelParameters) -> None:
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel < CHANNEL_COUNT:
            raise ValueError("channel must be in 0..7")
        if not isinstance(parameters, CalibratorChannelParameters):
            raise ValueError("parameters must be CalibratorChannelParameters")
        self._shadow[channel] = parameters.copy()

    def commit(self, *, acquisition_enabled: bool) -> int:
        if acquisition_enabled:
            raise RuntimeError("calibration commit requires acquisition is stopped")
        self._active = tuple(parameters.copy() for parameters in self._shadow)
        self._config_version = (self._config_version + 1) & 0xFFFFFFFF
        return self._config_version


def _round_shift_ties_away(value: int, shift: int) -> int:
    if shift < 0:
        raise ValueError("shift cannot be negative")
    if shift == 0:
        return value
    magnitude = abs(value)
    rounded = (magnitude + (1 << (shift - 1))) >> shift
    return -rounded if value < 0 else rounded


def _saturate_s24(value: int) -> int:
    return max(S24_MIN, min(S24_MAX, value))


def apply_complex_gain(sample: IQ, gain_real: int, gain_imag: int) -> IQ:
    """Apply one s24.Q20 complex coefficient with project rounding."""

    i_value, q_value = sample
    real = _round_shift_ties_away(i_value * gain_real - q_value * gain_imag, GAIN_FRACTION_BITS)
    imag = _round_shift_ties_away(i_value * gain_imag + q_value * gain_real, GAIN_FRACTION_BITS)
    return (_saturate_s24(real), _saturate_s24(imag))


@lru_cache(maxsize=256)
def fractional_delay_coefficients_q17(fractional_delay_q20: int) -> tuple[int, ...]:
    """Build the normalized 63-tap Blackman-windowed sinc coefficient row."""

    if not 0 <= fractional_delay_q20 < (1 << 20):
        raise ValueError("fractional_delay_q20 must be in 0..1048575")
    fractional = fractional_delay_q20 / float(1 << 20)
    center = (FRACTIONAL_DELAY_TAPS - 1) // 2
    values: list[float] = []
    for tap in range(FRACTIONAL_DELAY_TAPS):
        distance = tap - center - fractional
        sinc = 1.0 if abs(distance) < 1e-15 else math.sin(math.pi * distance) / (math.pi * distance)
        window = 0.42 - 0.5 * math.cos(2.0 * math.pi * tap / (FRACTIONAL_DELAY_TAPS - 1)) + 0.08 * math.cos(4.0 * math.pi * tap / (FRACTIONAL_DELAY_TAPS - 1))
        values.append(sinc * window)
    scale = sum(values)
    quantized = [int(math.floor(abs(value / scale) * (1 << FRACTIONAL_COEFFICIENT_BITS) + 0.5)) * (-1 if value < 0 else 1) for value in values]
    quantized[center] += (1 << FRACTIONAL_COEFFICIENT_BITS) - sum(quantized)
    return tuple(quantized)


class EightChannelCalibrationPipeline2Spc:
    """Stateful integer-delay, 63-tap FIR, and complex-gain pipeline model."""

    latency_excluding_programmed_delay_samples = (FRACTIONAL_DELAY_TAPS - 1) // 2
    samples_per_cycle = 2

    def __init__(self, parameters: tuple[CalibratorChannelParameters, ...]) -> None:
        if len(parameters) != CHANNEL_COUNT or not all(
            isinstance(item, CalibratorChannelParameters) for item in parameters
        ):
            raise ValueError("pipeline requires eight channel parameter sets")
        self.parameters = tuple(item.copy() for item in parameters)
        self._history: list[list[IQ]] = [[] for _ in range(CHANNEL_COUNT)]

    def reset(self) -> None:
        self._history = [[] for _ in range(CHANNEL_COUNT)]

    def process_beat(self, lane0: Lane, lane1: Lane) -> tuple[Lane, Lane]:
        _validate_lane(lane0)
        _validate_lane(lane1)
        return (self._process_lane(lane0), self._process_lane(lane1))

    def _process_lane(self, lane: Lane) -> Lane:
        output: list[IQ] = []
        for channel, sample in enumerate(lane):
            history = self._history[channel]
            history.append(sample)
            parameters = self.parameters[channel]
            if not parameters.enabled:
                output.append((0, 0))
                continue
            coefficients = fractional_delay_coefficients_q17(parameters.fractional_delay_q20)
            i_accumulator = 0
            q_accumulator = 0
            newest = len(history) - 1
            for tap, coefficient in enumerate(coefficients):
                source_index = newest - parameters.integer_delay - tap
                if source_index >= 0:
                    i_sample, q_sample = history[source_index]
                    i_accumulator += i_sample * coefficient
                    q_accumulator += q_sample * coefficient
            filtered = (
                _round_shift_ties_away(i_accumulator, FRACTIONAL_COEFFICIENT_BITS),
                _round_shift_ties_away(q_accumulator, FRACTIONAL_COEFFICIENT_BITS),
            )
            output.append(apply_complex_gain(filtered, parameters.gain_real, parameters.gain_imag))
        return tuple(output)


class AutoRangeSelector2Spc:
    """Independent H/V high-mid-low selector; ADC3/7 are never candidates."""

    _CHANNELS = ((0, 1, 2), (4, 5, 6))

    def __init__(self, *, high_water: int, low_water: int, hold_samples: int) -> None:
        if not 0 < low_water < high_water <= 32767:
            raise ValueError("water marks must satisfy 0 < low < high <= 32767")
        if hold_samples < 1:
            raise ValueError("hold_samples must be positive")
        self.high_water = high_water
        self.low_water = low_water
        self.hold_samples = hold_samples
        self.current_ranges = (0, 0)
        self._last_switch = (-hold_samples, -hold_samples)
        self._sample_index = 0

    def reset(self) -> None:
        self.current_ranges = (0, 0)
        self._last_switch = (-self.hold_samples, -self.hold_samples)
        self._sample_index = 0

    def process_beat(
        self,
        lane0: Lane,
        lane1: Lane,
        clipped0: tuple[bool, ...] | None = None,
        clipped1: tuple[bool, ...] | None = None,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        _validate_lane(lane0)
        _validate_lane(lane1)
        clipping0 = clipped0 or (False,) * CHANNEL_COUNT
        clipping1 = clipped1 or (False,) * CHANNEL_COUNT
        if len(clipping0) != CHANNEL_COUNT or len(clipping1) != CHANNEL_COUNT:
            raise ValueError("clipping lanes must contain eight flags")
        return (
            self._process_sample(lane0, clipping0),
            self._process_sample(lane1, clipping1),
        )

    def _process_sample(self, samples: Lane, clipped: tuple[bool, ...]) -> tuple[int, int]:
        next_ranges = list(self.current_ranges)
        last_switch = list(self._last_switch)
        for polarization, channel_indices in enumerate(self._CHANNELS):
            selected = next_ranges[polarization]
            channel = channel_indices[selected]
            overloaded = clipped[channel] or _magnitude(samples[channel]) >= self.high_water
            if overloaded and selected < 2:
                while overloaded and selected < 2:
                    selected += 1
                    channel = channel_indices[selected]
                    overloaded = clipped[channel] or _magnitude(samples[channel]) >= self.high_water
                last_switch[polarization] = self._sample_index
            elif selected > 0 and self._sample_index - last_switch[polarization] >= self.hold_samples:
                candidate = channel_indices[selected - 1]
                if not clipped[candidate] and _magnitude(samples[candidate]) < self.low_water:
                    selected -= 1
                    last_switch[polarization] = self._sample_index
            next_ranges[polarization] = selected
        self.current_ranges = (next_ranges[0], next_ranges[1])
        self._last_switch = (last_switch[0], last_switch[1])
        self._sample_index += 1
        return self.current_ranges


def _magnitude(sample: IQ) -> int:
    return max(abs(sample[0]), abs(sample[1]))


def _validate_lane(lane: Lane) -> None:
    if len(lane) != CHANNEL_COUNT:
        raise ValueError("each 2SPC lane must contain eight channels")
    for sample in lane:
        if len(sample) != 2 or not all(isinstance(value, int) and not isinstance(value, bool) for value in sample):
            raise ValueError("each channel sample must be an integer (I, Q) pair")
