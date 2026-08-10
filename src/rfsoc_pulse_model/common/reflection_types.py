from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Optional, Sequence, Tuple

import numpy as np

from .types import (
    AuxOutputMode,
    ChannelRole,
    GainRange,
    Polarization,
    SampleDomain,
)


def _immutable_array(
    values: object,
    *,
    dtype: np.dtype,
    shape: Optional[Tuple[Optional[int], ...]] = None,
    name: str,
) -> np.ndarray:
    array = np.array(values, dtype=dtype, copy=True)
    if shape is not None:
        if array.ndim != len(shape) or any(
            expected is not None and actual != expected
            for actual, expected in zip(array.shape, shape)
        ):
            rendered = "(" + ", ".join("N" if value is None else str(value) for value in shape) + ")"
            raise ValueError(f"{name} must have shape {rendered}")
    if not np.all(np.isfinite(array.real)) or not np.all(np.isfinite(array.imag)):
        raise ValueError(f"{name} must contain finite values")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class PhysicalChannelMapEntry:
    index: int
    rfdc_tile: int
    rfdc_slice: int
    package_bank: int
    board_net: str
    board_endpoint: str
    polarization: Polarization
    gain_range: GainRange
    allowed_roles: Tuple[ChannelRole, ...]
    nominal_gain_db: float
    digital_scale: float = 1.0
    enabled: bool = True

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "PhysicalChannelMapEntry":
        raw_roles = values.get("allowed_roles", ())
        if not isinstance(raw_roles, Sequence) or isinstance(raw_roles, (str, bytes)):
            raise ValueError("allowed_roles must be a sequence")
        return cls(
            index=int(values["index"]),
            rfdc_tile=int(values["rfdc_tile"]),
            rfdc_slice=int(values["rfdc_slice"]),
            package_bank=int(values["package_bank"]),
            board_net=str(values["board_net"]),
            board_endpoint=str(values["board_endpoint"]),
            polarization=Polarization(str(values["polarization"])),
            gain_range=GainRange(str(values["gain_range"])),
            allowed_roles=tuple(ChannelRole(str(value)) for value in raw_roles),
            nominal_gain_db=float(values["nominal_gain_db"]),
            digital_scale=float(values.get("digital_scale", 1.0)),
            enabled=bool(values.get("enabled", True)),
        )

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("physical channel index cannot be negative")
        if self.rfdc_tile < 0 or self.rfdc_slice < 0:
            raise ValueError("RFDC tile and slice cannot be negative")
        if self.package_bank < 1:
            raise ValueError("package_bank must be positive")
        if not self.board_net.strip() or not self.board_endpoint.strip():
            raise ValueError("physical channel requires board net and endpoint")
        if not self.allowed_roles:
            raise ValueError("physical channel requires at least one allowed role")
        if len(set(self.allowed_roles)) != len(self.allowed_roles):
            raise ValueError("physical channel roles cannot be duplicated")
        if not math.isfinite(self.nominal_gain_db):
            raise ValueError("nominal_gain_db must be finite")
        if not math.isfinite(self.digital_scale) or self.digital_scale < 0.0:
            raise ValueError("digital_scale must be finite and nonnegative")


@dataclass(frozen=True)
class PolarimetricWaveform:
    samples: np.ndarray
    sample_domain: SampleDomain
    sample_rate_hz: int
    start_sample: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples",
            _immutable_array(
                self.samples,
                dtype=np.complex128,
                shape=(2, None),
                name="samples",
            ),
        )
        if not isinstance(self.sample_domain, SampleDomain):
            raise ValueError("sample_domain must be a SampleDomain")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.start_sample < 0:
            raise ValueError("start_sample cannot be negative")


@dataclass(frozen=True)
class EightChannelAdcFrame:
    samples: np.ndarray
    clipped: np.ndarray
    sample_domain: SampleDomain
    sample_rate_hz: int
    start_sample: int = 0

    def __post_init__(self) -> None:
        samples = _immutable_array(
            self.samples,
            dtype=np.complex128,
            shape=(8, None),
            name="ADC samples",
        )
        clipped = np.array(self.clipped, dtype=np.bool_, copy=True)
        if clipped.shape != samples.shape:
            raise ValueError("ADC clipped must have shape (8, N) matching samples")
        clipped.setflags(write=False)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "clipped", clipped)
        if self.sample_domain != SampleDomain.RFDC_COMPLEX_INPUT:
            raise ValueError("ADC reflection frame must use RFDC_COMPLEX_INPUT")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.start_sample < 0:
            raise ValueError("start_sample cannot be negative")


@dataclass(frozen=True)
class EightChannelDacFrame:
    samples: np.ndarray
    sample_domain: SampleDomain
    sample_rate_hz: int
    representation: str
    start_sample: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples",
            _immutable_array(
                self.samples,
                dtype=np.complex128,
                shape=(8, None),
                name="DAC samples",
            ),
        )
        if not isinstance(self.sample_domain, SampleDomain):
            raise ValueError("sample_domain must be a SampleDomain")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.representation != "complex_baseband_reference":
            raise ValueError("unsupported DAC mathematical representation")
        if self.start_sample < 0:
            raise ValueError("start_sample cannot be negative")


@dataclass(frozen=True)
class TargetRequest:
    apparent_range_m: float
    radial_velocity_mps: float
    target_rcs_m2: float
    normalized_scattering_matrix: np.ndarray
    rcs_reference_channel: str = "HH"
    initial_phase_rad: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("apparent_range_m", self.apparent_range_m),
            ("radial_velocity_mps", self.radial_velocity_mps),
            ("target_rcs_m2", self.target_rcs_m2),
            ("initial_phase_rad", self.initial_phase_rad),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.apparent_range_m <= 0.0 or self.target_rcs_m2 <= 0.0:
            raise ValueError("target range and RCS must be positive")
        if self.rcs_reference_channel not in ("HH", "HV", "VH", "VV"):
            raise ValueError("rcs_reference_channel must be HH, HV, VH, or VV")
        object.__setattr__(
            self,
            "normalized_scattering_matrix",
            _immutable_array(
                self.normalized_scattering_matrix,
                dtype=np.complex128,
                shape=(2, 2),
                name="normalized_scattering_matrix",
            ),
        )


@dataclass(frozen=True)
class CompiledScatterer:
    integer_delay_samples: int
    fractional_delay: float
    doppler_hz: float
    complex_scattering_matrix: np.ndarray
    range_carrier_phase_rad: float = 0.0

    def __post_init__(self) -> None:
        if self.integer_delay_samples < 0:
            raise ValueError("integer_delay_samples cannot be negative")
        if not 0.0 <= self.fractional_delay < 1.0:
            raise ValueError("fractional_delay must be within [0, 1)")
        if not math.isfinite(self.doppler_hz):
            raise ValueError("doppler_hz must be finite")
        if not math.isfinite(self.range_carrier_phase_rad):
            raise ValueError("range_carrier_phase_rad must be finite")
        object.__setattr__(
            self,
            "complex_scattering_matrix",
            _immutable_array(
                self.complex_scattering_matrix,
                dtype=np.complex128,
                shape=(2, 2),
                name="complex_scattering_matrix",
            ),
        )


@dataclass(frozen=True)
class ReflectionScenario:
    physical_range_m: float
    carrier_frequency_hz: float
    targets: Tuple[TargetRequest, ...]
    temperature_c: float
    start_sample: int
    length: int
    require_absolute_rcs: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.physical_range_m) or self.physical_range_m <= 0.0:
            raise ValueError("physical_range_m must be finite and positive")
        if not math.isfinite(self.carrier_frequency_hz) or self.carrier_frequency_hz <= 0.0:
            raise ValueError("carrier_frequency_hz must be finite and positive")
        if not math.isfinite(self.temperature_c):
            raise ValueError("temperature_c must be finite")
        if self.start_sample < 0 or self.length < 0:
            raise ValueError("scenario start and length cannot be negative")
        if not all(isinstance(target, TargetRequest) for target in self.targets):
            raise ValueError("targets must contain TargetRequest values")


@dataclass(frozen=True)
class DacAuxRequest:
    mode: AuxOutputMode
    waveform: Optional[PolarimetricWaveform]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, AuxOutputMode):
            raise ValueError("mode must be an AuxOutputMode")
        if self.mode == AuxOutputMode.OFF and self.waveform is not None:
            raise ValueError("OFF auxiliary mode requires no waveform")
        if self.mode != AuxOutputMode.OFF and self.waveform is None:
            raise ValueError("enabled auxiliary mode requires a waveform")


@dataclass(frozen=True)
class ReflectionStatus:
    adc_clipped: Tuple[bool, bool]
    selected_ranges: Tuple[GainRange, GainRange]
    absolute_rcs_calibrated: bool
    calibration_out_of_range: bool
    calibration_outputs_enabled: bool
    cancellation_outputs_enabled: bool
    monitor_pulse_count: int
    monitor_pulse_count_total: int
    processed_stop_sample: int
    emitted_stop_sample: int
    stream_final: bool

    def __post_init__(self) -> None:
        if len(self.adc_clipped) != 2 or len(self.selected_ranges) != 2:
            raise ValueError("reflection status requires H and V values")
        if self.monitor_pulse_count < 0 or self.monitor_pulse_count_total < 0:
            raise ValueError("monitor pulse counts cannot be negative")
        if self.monitor_pulse_count > self.monitor_pulse_count_total:
            raise ValueError("per-result monitor count cannot exceed cumulative count")
        if self.processed_stop_sample < 0 or self.emitted_stop_sample < 0:
            raise ValueError("status sample stops cannot be negative")
        if self.emitted_stop_sample > self.processed_stop_sample:
            raise ValueError("emitted_stop_sample cannot exceed processed_stop_sample")
        if not isinstance(self.stream_final, bool):
            raise ValueError("stream_final must be boolean")
