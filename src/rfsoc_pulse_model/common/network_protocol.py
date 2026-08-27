"""Version-1 little-endian UDP event protocol shared by board and host."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

from .types import Polarization, PulseEvent, PulseRecord, RangeId


MAGIC = int.from_bytes(b"CAL1", "little")
VERSION = 1
TYPE_EVENT = 1
HEADER = struct.Struct("<IHHHHIQIIQHHI")
PDW_HEADER = struct.Struct("<BBBBQIIIiHH")
EVENT_PREFIX = struct.Struct("<HHI")
IQ_SAMPLE = struct.Struct("<hh")
HEADER_SIZE = HEADER.size
PDW_HEADER_SIZE = PDW_HEADER.size
_CRC_OFFSET = HEADER_SIZE - 4


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedPdw:
    channel: int
    range_id: RangeId
    polarization: Polarization | None
    toa_samples: int
    pw_samples: int
    peak_power: int
    mean_power: int
    freq_word: int
    iq: tuple[tuple[int, int], ...]
    saturated: bool
    truncated: bool
    overflow: bool


@dataclass(frozen=True)
class DecodedEvent:
    sequence: int
    event_id: int
    config_version: int
    toa_samples: int
    channel_mask: int
    pdws: tuple[DecodedPdw, ...]


@dataclass(frozen=True)
class DatagramFragment:
    sequence: int
    event_id: int
    config_version: int
    toa_samples: int
    fragment_index: int
    fragment_count: int
    payload: bytes


def encode_event_datagrams(
    event: PulseEvent,
    *,
    sequence: int,
    mtu: int = 1500,
) -> tuple[bytes, ...]:
    if not isinstance(event, PulseEvent):
        raise ProtocolError("event must be a PulseEvent")
    if not 0 <= sequence <= 0xFFFFFFFFFFFFFFFF:
        raise ProtocolError("sequence must fit uint64")
    if mtu <= HEADER_SIZE:
        raise ProtocolError("MTU must exceed the 48-byte header")
    payload = _encode_event_payload(event)
    fragment_size = mtu - HEADER_SIZE
    fragments = tuple(
        payload[offset : offset + fragment_size]
        for offset in range(0, len(payload), fragment_size)
    ) or (b"",)
    if len(fragments) > 0xFFFF:
        raise ProtocolError("event requires too many fragments")
    return tuple(
        _encode_datagram(
            fragment,
            sequence=sequence + index,
            event_id=event.event_id,
            config_version=event.config_version,
            toa_samples=event.toa_samples,
            fragment_index=index,
            fragment_count=len(fragments),
        )
        for index, fragment in enumerate(fragments)
    )


def encode_event_payload(event: PulseEvent) -> bytes:
    """Encode the event body used both by UDP and the 128-bit DMA stream."""

    if not isinstance(event, PulseEvent):
        raise ProtocolError("event must be a PulseEvent")
    return _encode_event_payload(event)


def encode_pdw_payload(record: PulseRecord) -> bytes:
    """Encode one fixed 32-byte PDW header and its 32 IQ16 samples."""

    if not isinstance(record, PulseRecord):
        raise ProtocolError("record must be a PulseRecord")
    return _encode_pdw(record)


def decode_event_datagrams(datagrams: tuple[bytes, ...] | list[bytes]) -> DecodedEvent:
    if not datagrams:
        raise ProtocolError("missing fragment 0")
    headers = tuple(_decode_datagram(datagram) for datagram in datagrams)
    first = min(headers, key=lambda header: header.fragment_index)
    expected_count = first.fragment_count
    if len(headers) != expected_count:
        raise ProtocolError("missing fragment")
    by_index = {header.fragment_index: header for header in headers}
    if set(by_index) != set(range(expected_count)):
        raise ProtocolError("missing fragment or duplicate fragment index")
    for index, header in by_index.items():
        if (
            header.fragment_count != expected_count
            or header.event_id != first.event_id
            or header.config_version != first.config_version
            or header.toa_samples != first.toa_samples
            or header.sequence != first.sequence + index
        ):
            raise ProtocolError("inconsistent event fragments")
    payload = b"".join(by_index[index].payload for index in range(expected_count))
    channel_mask, pdws = _decode_event_payload(payload)
    return DecodedEvent(
        sequence=first.sequence,
        event_id=first.event_id,
        config_version=first.config_version,
        toa_samples=first.toa_samples,
        channel_mask=channel_mask,
        pdws=pdws,
    )


def decode_datagram_fragment(datagram: bytes) -> DatagramFragment:
    """Validate one UDP datagram and expose its fragment metadata."""

    return _decode_datagram(datagram)


def _encode_event_payload(event: PulseEvent) -> bytes:
    if len(event.records) > 0xFFFF:
        raise ProtocolError("too many PDWs in event")
    parts = [EVENT_PREFIX.pack(len(event.records), 0, event.channel_mask)]
    for record in event.records:
        parts.append(_encode_pdw(record))
    return b"".join(parts)


def _encode_pdw(record: PulseRecord) -> bytes:
    if len(record.iq) != 32:
        raise ProtocolError("each PDW must contain exactly 32 IQ samples")
    if record.iq_width_bits != 16 or record.iq_fraction_bits != 0 or not record.iq_signed:
        raise ProtocolError("network IQ must be signed IQ16")
    flags = int(record.saturated) | (int(record.truncated) << 1) | (int(record.overflow) << 2)
    polarization = 0xFF
    if record.channel_identity is not None:
        polarization = 0 if record.channel_identity.polarization == Polarization.H else 1
    header = PDW_HEADER.pack(
        record.channel,
        int(record.range_id),
        polarization,
        flags,
        record.toa_samples,
        record.pw_samples,
        record.peak_power,
        record.mean_power,
        record.freq_word,
        len(record.iq),
        0,
    )
    try:
        iq = b"".join(IQ_SAMPLE.pack(i_value, q_value) for i_value, q_value in record.iq)
    except struct.error as error:
        raise ProtocolError("IQ sample does not fit signed 16 bits") from error
    return header + iq


def _encode_datagram(
    payload: bytes,
    *,
    sequence: int,
    event_id: int,
    config_version: int,
    toa_samples: int,
    fragment_index: int,
    fragment_count: int,
) -> bytes:
    fields = (
        MAGIC, VERSION, TYPE_EVENT, HEADER_SIZE, 0, len(payload), sequence,
        event_id, config_version, toa_samples, fragment_index, fragment_count, 0,
    )
    header = HEADER.pack(*fields)
    crc = zlib.crc32(header + payload) & 0xFFFFFFFF
    return HEADER.pack(*fields[:-1], crc) + payload


def _decode_datagram(datagram: bytes) -> DatagramFragment:
    if len(datagram) < HEADER_SIZE:
        raise ProtocolError("datagram shorter than header")
    fields = HEADER.unpack_from(datagram)
    (
        magic, version, message_type, header_len, _flags, payload_len, sequence,
        event_id, config_version, toa_samples, fragment_index, fragment_count, crc,
    ) = fields
    if magic != MAGIC:
        raise ProtocolError("unknown magic")
    if version != VERSION:
        raise ProtocolError("unknown protocol version")
    if message_type != TYPE_EVENT:
        raise ProtocolError("unknown message type")
    if header_len != HEADER_SIZE or len(datagram) != HEADER_SIZE + payload_len:
        raise ProtocolError("invalid protocol length")
    if fragment_count < 1 or fragment_index >= fragment_count:
        raise ProtocolError("invalid fragment metadata")
    zero_crc_header = bytearray(datagram[:HEADER_SIZE])
    zero_crc_header[_CRC_OFFSET:] = b"\0\0\0\0"
    payload = datagram[HEADER_SIZE:]
    expected = zlib.crc32(bytes(zero_crc_header) + payload) & 0xFFFFFFFF
    if expected != crc:
        raise ProtocolError("CRC mismatch")
    return DatagramFragment(
        sequence=sequence, event_id=event_id, config_version=config_version,
        toa_samples=toa_samples, fragment_index=fragment_index,
        fragment_count=fragment_count, payload=payload,
    )


def _decode_event_payload(payload: bytes) -> tuple[int, tuple[DecodedPdw, ...]]:
    if len(payload) < EVENT_PREFIX.size:
        raise ProtocolError("event payload is truncated")
    pdw_count, reserved, channel_mask = EVENT_PREFIX.unpack_from(payload)
    if reserved:
        raise ProtocolError("event reserved field must be zero")
    expected = EVENT_PREFIX.size + pdw_count * (PDW_HEADER_SIZE + 32 * IQ_SAMPLE.size)
    if len(payload) != expected:
        raise ProtocolError("event payload length does not match PDW count")
    pdws: list[DecodedPdw] = []
    offset = EVENT_PREFIX.size
    for _ in range(pdw_count):
        values = PDW_HEADER.unpack_from(payload, offset)
        offset += PDW_HEADER_SIZE
        channel, range_value, polarization_value, flags, toa, width, peak, mean, frequency, iq_count, reserved = values
        if iq_count != 32 or reserved:
            raise ProtocolError("PDW must declare exactly 32 IQ samples")
        try:
            range_id = RangeId(range_value)
        except ValueError as error:
            raise ProtocolError("unknown range id") from error
        if polarization_value == 0xFF:
            polarization = None
        elif polarization_value in (0, 1):
            polarization = Polarization.H if polarization_value == 0 else Polarization.V
        else:
            raise ProtocolError("unknown polarization")
        iq = tuple(
            IQ_SAMPLE.unpack_from(payload, offset + index * IQ_SAMPLE.size)
            for index in range(32)
        )
        offset += 32 * IQ_SAMPLE.size
        pdws.append(
            DecodedPdw(
                channel=channel, range_id=range_id, polarization=polarization,
                toa_samples=toa, pw_samples=width, peak_power=peak,
                mean_power=mean, freq_word=frequency, iq=iq,
                saturated=bool(flags & 1), truncated=bool(flags & 2),
                overflow=bool(flags & 4),
            )
        )
    return channel_mask, tuple(pdws)
