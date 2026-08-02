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


@dataclass(frozen=True)
class PulseRecord:
    """Normalized PDW plus the hit-only IQ window.

    ``toa_samples`` and ``pw_samples`` are always expressed in
    ``sample_domain`` at ``sample_rate_hz``. Golden detector records use the
    detector domain. ``freq_word`` is signed Q31 turns/sample in that same
    domain; Cycle and RTL later reproduce the same serialized representation.
    """

    channel: int
    range_id: RangeId
    sample_domain: SampleDomain
    sample_rate_hz: int
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
