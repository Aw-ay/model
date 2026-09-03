"""Non-backpressuring, whole-event 128-bit AXI Stream queue model."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from ...common.network_protocol import encode_pdw_payload
from ...common.types import PulseEvent


@dataclass(frozen=True)
class Axis128Beat:
    tdata: int
    tkeep: int
    tlast: bool
    event_id: int

    def __post_init__(self) -> None:
        if not 0 <= self.tdata < (1 << 128):
            raise ValueError("tdata must fit 128 bits")
        if not 0 <= self.tkeep <= 0xFFFF:
            raise ValueError("tkeep must fit 16 bits")


class EventDmaQueue:
    """Accept complete events or drop them; the sample producer is never stalled."""

    ERROR_FIFO_FULL = 1 << 0
    ERROR_DUPLICATE_EVENT = 1 << 1

    def __init__(self, *, capacity_beats: int) -> None:
        if not isinstance(capacity_beats, int) or isinstance(capacity_beats, bool) or capacity_beats < 1:
            raise ValueError("capacity_beats must be positive")
        self.capacity_beats = capacity_beats
        self._beats: list[Axis128Beat] = []
        self._seen_event_ids: set[int] = set()
        self.event_count = 0
        self.drop_count = 0
        self.sticky_errors = 0

    @property
    def queued_beats(self) -> int:
        return len(self._beats)

    def submit_event(self, event: PulseEvent) -> bool:
        if not isinstance(event, PulseEvent):
            raise ValueError("event must be a PulseEvent")
        if event.event_id in self._seen_event_ids:
            self.drop_count += 1
            self.sticky_errors |= self.ERROR_DUPLICATE_EVENT
            return False
        payload = _encode_dma_event(event)
        beats = _axis_beats(payload, event.event_id)
        if len(self._beats) + len(beats) > self.capacity_beats:
            self.drop_count += 1
            self.sticky_errors |= self.ERROR_FIFO_FULL
            return False
        self._beats.extend(beats)
        self._seen_event_ids.add(event.event_id)
        self.event_count += 1
        return True

    def submit_events(self, events: tuple[PulseEvent, ...] | list[PulseEvent]) -> int:
        ordered = sorted(
            events,
            key=lambda event: (
                event.toa_samples,
                min(record.channel for record in event.records),
            ),
        )
        return sum(1 for event in ordered if self.submit_event(event))

    def drain(self, maximum_beats: int | None = None) -> tuple[Axis128Beat, ...]:
        if maximum_beats is None:
            maximum_beats = len(self._beats)
        if not isinstance(maximum_beats, int) or isinstance(maximum_beats, bool) or maximum_beats < 0:
            raise ValueError("maximum_beats must be nonnegative")
        count = min(maximum_beats, len(self._beats))
        result = tuple(self._beats[:count])
        del self._beats[:count]
        return result

    def clear_errors(self, mask: int = 0xFFFFFFFF) -> None:
        self.sticky_errors &= ~mask


def _axis_beats(payload: bytes, event_id: int) -> tuple[Axis128Beat, ...]:
    result: list[Axis128Beat] = []
    for offset in range(0, len(payload), 16):
        chunk = payload[offset : offset + 16]
        result.append(
            Axis128Beat(
                tdata=int.from_bytes(chunk, "little"),
                tkeep=(1 << len(chunk)) - 1,
                tlast=offset + len(chunk) == len(payload),
                event_id=event_id,
            )
        )
    return tuple(result)


_DMA_MAGIC = int.from_bytes(b"DMA1", "little")
_DMA_HEADER = struct.Struct("<IIIIQIHH")


def _encode_dma_event(event: PulseEvent) -> bytes:
    pdws = b"".join(encode_pdw_payload(record) for record in event.records)
    total_length = _DMA_HEADER.size + len(pdws)
    header = _DMA_HEADER.pack(
        _DMA_MAGIC,
        total_length,
        event.event_id,
        event.config_version,
        event.toa_samples,
        event.channel_mask,
        len(event.records),
        0,
    )
    return header + pdws
