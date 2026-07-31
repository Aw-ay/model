from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence, Tuple


IQSample = Tuple[int, int]


class RangeId(IntEnum):
    """Physical receive/transmit path identity shared by all layers."""

    PLUS_20_DB = 0
    ZERO_DB = 1
    MINUS_20_DB = 2
    LOOPBACK = 3


@dataclass(frozen=True)
class PulseRecord:
    """Normalized PDW plus the hit-only IQ window.

    ``freq_word`` is signed Q31 turns/sample. Golden computes it from the
    ideal phase slope; Cycle and RTL later reproduce the same serialized
    representation.
    """

    channel: int
    range_id: RangeId
    toa_samples: int
    pw_samples: int
    peak_power: int
    mean_power: int
    freq_word: int
    iq: Tuple[IQSample, ...]
    saturated: bool = False
    truncated: bool = False
    overflow: bool = False

    @property
    def frequency_turns_per_sample(self) -> float:
        return self.freq_word / float(1 << 31)


@dataclass(frozen=True)
class PulseEvent:
    """Records associated across +20/0/-20 dB or the loopback path."""

    event_id: int
    records: Tuple[PulseRecord, ...]
    selected_range: RangeId
    channel_mask: int
    toa_samples: int
    config_version: int

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

