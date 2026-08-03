from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Sequence, Tuple


IQSample = Tuple[int, int]


class RangeId(IntEnum):
    """Physical receive/transmit path identity shared by all layers."""

    PLUS_20_DB = 0
    ZERO_DB = 1
    MINUS_20_DB = 2
    LOOPBACK = 3


class SampleDomain(str, Enum):
    """Timebase in which sample-index fields are expressed."""

    RFDC_COMPLEX_INPUT = "rfdc_complex_input"
    DETECTOR = "detector"
    DAC_BASEBAND = "dac_baseband"


class IQUnit(str, Enum):
    """Physical meaning of one decoded I or Q component."""

    ADC_CODE = "adc_code"


class PowerUnit(str, Enum):
    """Physical meaning of a PulseRecord power code."""

    ADC_CODE_SQUARED = "adc_code_squared"


@dataclass(frozen=True)
class PulseRecord:
    """Normalized PDW plus the hit-only IQ window.

    ``toa_samples`` and ``pw_samples`` are expressed in ``sample_domain`` at
    ``sample_rate_hz``. IQ codes and power statistics carry their width,
    fixed-point and unit metadata directly. ``freq_word`` is signed Q31
    turns/sample in that same domain; Cycle and RTL later reproduce the same
    serialized representation.
    """

    channel: int
    range_id: RangeId
    sample_domain: SampleDomain
    sample_rate_hz: int
    iq_width_bits: int
    iq_fraction_bits: int
    iq_signed: bool
    iq_unit: IQUnit
    power_width_bits: int
    power_fraction_bits: int
    power_unit: PowerUnit
    toa_samples: int
    pw_samples: int
    peak_power: int
    mean_power: int
    freq_word: int
    iq: Tuple[IQSample, ...]
    saturated: bool = False
    truncated: bool = False
    overflow: bool = False

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.toa_samples < 0:
            raise ValueError("toa_samples cannot be negative")
        if self.pw_samples < 1:
            raise ValueError("pw_samples must be positive")
        if self.iq_width_bits < 1:
            raise ValueError("iq_width_bits must be positive")
        if not 0 <= self.iq_fraction_bits < self.iq_width_bits:
            raise ValueError("iq_fraction_bits must be within iq_width_bits")
        if not isinstance(self.iq_unit, IQUnit):
            raise ValueError("iq_unit must be an IQUnit")
        if self.power_width_bits < 1:
            raise ValueError("power_width_bits must be positive")
        if not 0 <= self.power_fraction_bits < self.power_width_bits:
            raise ValueError("power_fraction_bits must be within power_width_bits")
        if not isinstance(self.power_unit, PowerUnit):
            raise ValueError("power_unit must be a PowerUnit")
        if (
            self.power_unit == PowerUnit.ADC_CODE_SQUARED
            and self.power_fraction_bits != 2 * self.iq_fraction_bits
        ):
            raise ValueError(
                "power_fraction_bits must be twice iq_fraction_bits for ADC-code-squared power"
            )
        iq_min = -(1 << (self.iq_width_bits - 1)) if self.iq_signed else 0
        iq_max = (
            (1 << (self.iq_width_bits - 1)) - 1
            if self.iq_signed
            else (1 << self.iq_width_bits) - 1
        )
        for i_value, q_value in self.iq:
            if not iq_min <= i_value <= iq_max or not iq_min <= q_value <= iq_max:
                raise ValueError(
                    f"IQ sample must fit the declared {self.iq_width_bits}-bit format"
                )
        power_max = (1 << self.power_width_bits) - 1
        for field_name, value in (
            ("peak_power", self.peak_power),
            ("mean_power", self.mean_power),
        ):
            if not 0 <= value <= power_max:
                raise ValueError(
                    f"{field_name} must fit the declared unsigned "
                    f"{self.power_width_bits}-bit power format"
                )

    @property
    def power_definition(self) -> str:
        """Power statistic represented by peak_power and mean_power."""

        return "I^2+Q^2"

    @property
    def physical_format(self) -> tuple:
        """Hashable contract used to prevent mixed-format event association."""

        return (
            self.iq_width_bits,
            self.iq_fraction_bits,
            self.iq_signed,
            self.iq_unit,
            self.power_width_bits,
            self.power_fraction_bits,
            self.power_unit,
            self.power_definition,
        )

    @property
    def frequency_turns_per_sample(self) -> float:
        return self.freq_word / float(1 << 31)

    @property
    def toa_seconds(self) -> float:
        return self.toa_samples / float(self.sample_rate_hz)

    @property
    def pw_seconds(self) -> float:
        return self.pw_samples / float(self.sample_rate_hz)


@dataclass(frozen=True)
class PulseEvent:
    """Records associated across +20/0/-20 dB or the loopback path."""

    event_id: int
    records: Tuple[PulseRecord, ...]
    selected_range: RangeId
    channel_mask: int
    toa_samples: int
    config_version: int

    @property
    def sample_domain(self) -> SampleDomain:
        return self.records[0].sample_domain

    @property
    def sample_rate_hz(self) -> int:
        return self.records[0].sample_rate_hz

    @classmethod
    def from_records(
        cls,
        event_id: int,
        records: Sequence[PulseRecord],
        config_version: int,
    ) -> "PulseEvent":
        if not records:
            raise ValueError("a pulse event requires at least one record")
        ordered = tuple(sorted(records, key=lambda record: record.channel))
        clocks = {
            (record.sample_domain, record.sample_rate_hz) for record in ordered
        }
        if len(clocks) != 1:
            raise ValueError("event records must share one sample domain and rate")
        physical_formats = {record.physical_format for record in ordered}
        if len(physical_formats) != 1:
            raise ValueError("event records must share one IQ and power physical format")
        selected = next(
            (
                record
                for range_id in (
                    RangeId.PLUS_20_DB,
                    RangeId.ZERO_DB,
                    RangeId.MINUS_20_DB,
                    RangeId.LOOPBACK,
                )
                for record in ordered
                if record.range_id == range_id and not record.saturated
            ),
            ordered[-1],
        )
        channel_mask = 0
        for record in ordered:
            channel_mask |= 1 << record.channel
        return cls(
            event_id=event_id,
            records=ordered,
            selected_range=selected.range_id,
            channel_mask=channel_mask,
            toa_samples=min(record.toa_samples for record in ordered),
            config_version=config_version,
        )
