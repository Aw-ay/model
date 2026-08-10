from __future__ import annotations

from typing import Iterable, List

from .types import (
    ChannelRole,
    GainRange,
    Polarization,
    PulseEvent,
    PulseRecord,
    RangeId,
)


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


def associate_polarimetric_range_records(
    records: Iterable[PulseRecord],
    toa_tolerance: int,
    width_tolerance: int,
    config_version: int,
    first_event_id: int = 0,
) -> List[PulseEvent]:
    """Associate H and V three-range observations without cross-polarization mixing."""

    expected_range = {
        GainRange.HIGH: RangeId.PLUS_20_DB,
        GainRange.MID: RangeId.ZERO_DB,
        GainRange.LOW: RangeId.MINUS_20_DB,
    }
    by_polarization = {Polarization.H: [], Polarization.V: []}
    for record in records:
        identity = record.channel_identity
        if identity is None:
            raise ValueError("polarimetric association requires channel_identity")
        if (
            identity.role != ChannelRole.ECHO
            or identity.gain_range not in expected_range
        ):
            raise ValueError("polarimetric association accepts only echo gain paths")
        if record.range_id != expected_range[identity.gain_range]:
            raise ValueError("record range_id does not match channel_identity")
        by_polarization[identity.polarization].append(record)

    groups = []
    for polarization in (Polarization.H, Polarization.V):
        events = associate_range_records(
            by_polarization[polarization],
            toa_tolerance,
            width_tolerance,
            config_version,
        )
        groups.extend(event.records for event in events)
    groups.sort(
        key=lambda group: (
            min(record.toa_samples for record in group),
            group[0].channel_identity.polarization.value,
        )
    )
    return [
        PulseEvent.from_records(
            first_event_id + offset,
            group,
            config_version,
        )
        for offset, group in enumerate(groups)
    ]
