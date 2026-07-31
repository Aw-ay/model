from __future__ import annotations

from typing import Iterable, List

from .types import PulseEvent, PulseRecord, RangeId


def associate_range_records(
    records: Iterable[PulseRecord],
    toa_tolerance: int,
    width_tolerance: int,
    config_version: int,
    first_event_id: int = 0,
) -> List[PulseEvent]:
    """Associate the three gain observations without mixing loopback data."""

    if toa_tolerance < 0 or width_tolerance < 0:
        raise ValueError("association tolerances cannot be negative")
    pending: List[List[PulseRecord]] = []
    for record in sorted(records, key=lambda item: item.toa_samples):
        if record.range_id == RangeId.LOOPBACK:
            pending.append([record])
            continue
        target = None
        for group in reversed(pending):
            reference = group[0]
            if reference.range_id == RangeId.LOOPBACK:
                continue
            if any(item.range_id == record.range_id for item in group):
                continue
            if abs(reference.toa_samples - record.toa_samples) > toa_tolerance:
                continue
            if abs(reference.pw_samples - record.pw_samples) > width_tolerance:
                continue
            target = group
            break
        if target is None:
            pending.append([record])
        else:
            target.append(record)
    pending.sort(key=lambda group: min(item.toa_samples for item in group))
    return [
        PulseEvent.from_records(
            event_id=first_event_id + offset,
            records=group,
            config_version=config_version,
        )
        for offset, group in enumerate(pending)
    ]

