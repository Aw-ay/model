"""Strict TCP control and UDP event reception for the calibrator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import socket
from typing import Any

from rfsoc_pulse_model.common.network_protocol import (
    DecodedEvent,
    ProtocolError,
    decode_datagram_fragment,
    decode_event_datagrams,
)


SUPPORTED_COMMANDS = frozenset(
    {
        "get_status", "start", "stop", "set_threshold", "set_calibration",
        "commit_calibration", "run_mts", "clear_errors", "shutdown",
    }
)


class ControlProtocolError(ValueError):
    """The TCP peer or caller violated the version-1 control protocol."""


@dataclass
class SequenceTracker:
    """Account for wire loss, duplicates and reordering over uint64 wrap."""

    received: int = 0
    lost: int = 0
    duplicates: int = 0
    reordered: int = 0
    _highest: int | None = None
    _recent: set[int] = field(default_factory=set, repr=False)
    _recent_order: list[int] = field(default_factory=list, repr=False)

    def observe(self, sequence: int) -> None:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or not 0 <= sequence <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("sequence must fit uint64")
        self.received += 1
        if sequence in self._recent:
            self.duplicates += 1
            return
        self._remember(sequence)
        if self._highest is None:
            self._highest = sequence
            return
        forward = (sequence - self._highest) & 0xFFFFFFFFFFFFFFFF
        if 0 < forward < (1 << 63):
            if forward > 1:
                self.lost += forward - 1
            self._highest = sequence
        else:
            self.reordered += 1

    def _remember(self, sequence: int) -> None:
        self._recent.add(sequence)
        self._recent_order.append(sequence)
        if len(self._recent_order) > 4096:
            expired = self._recent_order.pop(0)
            self._recent.discard(expired)


@dataclass
class _PendingEvent:
    fragment_count: int
    datagrams: dict[int, bytes] = field(default_factory=dict)


class EventReassembler:
    """Validate and reassemble bounded, possibly out-of-order UDP events."""

    def __init__(self, *, max_pending_events: int = 256) -> None:
        if max_pending_events < 1:
            raise ValueError("max_pending_events must be positive")
        self.sequence = SequenceTracker()
        self.duplicate_fragments = 0
        self.evicted_events = 0
        self._max_pending_events = max_pending_events
        self._pending: dict[tuple[int, int, int], _PendingEvent] = {}

    @property
    def pending_events(self) -> int:
        return len(self._pending)

    def push(self, datagram: bytes) -> DecodedEvent | None:
        fragment = decode_datagram_fragment(datagram)
        self.sequence.observe(fragment.sequence)
        key = (fragment.event_id, fragment.config_version, fragment.toa_samples)
        pending = self._pending.get(key)
        if pending is None:
            self._evict_if_full()
            pending = _PendingEvent(fragment.fragment_count)
            self._pending[key] = pending
        elif pending.fragment_count != fragment.fragment_count:
            del self._pending[key]
            raise ProtocolError("fragment count changed within an event")
        if fragment.fragment_index in pending.datagrams:
            self.duplicate_fragments += 1
            return None
        pending.datagrams[fragment.fragment_index] = bytes(datagram)
        if len(pending.datagrams) != pending.fragment_count:
            return None
        ordered = tuple(pending.datagrams[index] for index in range(pending.fragment_count))
        del self._pending[key]
        return decode_event_datagrams(ordered)

    def _evict_if_full(self) -> None:
        if len(self._pending) < self._max_pending_events:
            return
        oldest = next(iter(self._pending))
        del self._pending[oldest]
        self.evicted_events += 1


def encode_control_request(command: str, **parameters: Any) -> bytes:
    if command not in SUPPORTED_COMMANDS:
        raise ControlProtocolError(f"unsupported command: {command}")
    request = {"command": command, **parameters}
    try:
        encoded = json.dumps(request, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ControlProtocolError("control request is not valid JSON") from error
    return encoded.encode("utf-8") + b"\n"


def decode_control_response(line: bytes) -> dict[str, Any]:
    if not line.endswith(b"\n"):
        raise ControlProtocolError("control response is not newline terminated")
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlProtocolError("malformed control response") from error
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise ControlProtocolError("control response must be an object with boolean ok")
    if not value["ok"]:
        raise ControlProtocolError(str(value.get("error", "control command failed")))
    return value


class ControlClient:
    """One-request/one-response TCP JSON-lines client."""

    def __init__(self, host: str, *, port: int = 47001, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def request(self, command: str, **parameters: Any) -> dict[str, Any]:
        request = encode_control_request(command, **parameters)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
            connection.sendall(request)
            connection.settimeout(self.timeout)
            chunks = bytearray()
            while not chunks.endswith(b"\n"):
                chunk = connection.recv(4096)
                if not chunk:
                    raise ControlProtocolError("control connection closed before response")
                chunks.extend(chunk)
                if len(chunks) > 65536:
                    raise ControlProtocolError("control response exceeds 64 KiB")
        return decode_control_response(bytes(chunks))
