"""Command-line control, UDP capture and acceptance statistics."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import socket
import struct
import sys
import time
from typing import Any, Sequence

from rfsoc_pulse_model.common.network_protocol import DecodedEvent, ProtocolError
from .calibrator_client import ControlClient, ControlProtocolError, EventReassembler


_IQ_RECORD_HEADER = struct.Struct("<QI B 3x")
_IQ_SAMPLE = struct.Struct("<hh")


class EventArchive:
    """Append event metadata and compact IQ16 records without per-event files."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._metadata = None
        self._iq = None

    def __enter__(self) -> "EventArchive":
        self.directory.mkdir(parents=True, exist_ok=True)
        self._metadata = (self.directory / "events.jsonl").open("a", encoding="utf-8", newline="\n")
        self._iq = (self.directory / "events.iq16le").open("ab")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._metadata is not None:
            self._metadata.close()
        if self._iq is not None:
            self._iq.close()

    def write(self, event: DecodedEvent) -> None:
        if self._metadata is None or self._iq is None:
            raise RuntimeError("EventArchive must be used as a context manager")
        metadata: dict[str, Any] = {
            "sequence": event.sequence,
            "event_id": event.event_id,
            "config_version": event.config_version,
            "toa_samples": event.toa_samples,
            "channel_mask": event.channel_mask,
            "pdws": [],
        }
        for pdw in event.pdws:
            item = asdict(pdw)
            item.pop("iq")
            item["range_id"] = int(pdw.range_id)
            item["polarization"] = pdw.polarization.value if pdw.polarization is not None else None
            metadata["pdws"].append(item)
            self._iq.write(_IQ_RECORD_HEADER.pack(event.event_id, event.config_version, pdw.channel))
            for i_value, q_value in pdw.iq:
                self._iq.write(_IQ_SAMPLE.pack(i_value, q_value))
        self._metadata.write(json.dumps(metadata, separators=(",", ":"), sort_keys=True) + "\n")


def _parse_parameters(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("parameters must be a JSON object") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("parameters must be a JSON object")
    return parsed


def _control(arguments: argparse.Namespace) -> int:
    response = ControlClient(arguments.host, port=arguments.port, timeout=arguments.timeout).request(
        arguments.command, **arguments.parameters
    )
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


def _receive(arguments: argparse.Namespace) -> int:
    receiver = EventReassembler(max_pending_events=arguments.max_pending)
    started = time.monotonic()
    events = 0
    corrupt = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, arguments.receive_buffer)
        udp.bind((arguments.bind, arguments.port))
        udp.settimeout(1.0)
        with EventArchive(arguments.output) as archive:
            while True:
                elapsed = time.monotonic() - started
                if arguments.duration is not None and elapsed >= arguments.duration:
                    break
                if arguments.events is not None and events >= arguments.events:
                    break
                try:
                    datagram, _peer = udp.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    event = receiver.push(datagram)
                except ProtocolError:
                    corrupt += 1
                    continue
                if event is not None:
                    archive.write(event)
                    events += 1
    stats = {
        "elapsed_seconds": time.monotonic() - started,
        "events": events,
        "datagrams": receiver.sequence.received,
        "wire_gaps": receiver.sequence.lost,
        "duplicates": receiver.sequence.duplicates,
        "reordered": receiver.sequence.reordered,
        "duplicate_fragments": receiver.duplicate_fragments,
        "evicted_events": receiver.evicted_events,
        "corrupt_datagrams": corrupt,
        "pending_events": receiver.pending_events,
    }
    print(json.dumps(stats, indent=2, sort_keys=True))
    if arguments.require_events is not None and events < arguments.require_events:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calibrator-cli")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    control = subcommands.add_parser("control", help="send one TCP JSON-lines command")
    control.add_argument("host")
    control.add_argument("command")
    control.add_argument("--parameters", type=_parse_parameters, default={})
    control.add_argument("--port", type=int, default=47001)
    control.add_argument("--timeout", type=float, default=5.0)
    control.set_defaults(handler=_control)

    receive = subcommands.add_parser("receive", help="capture, verify and store UDP events")
    receive.add_argument("--bind", default="0.0.0.0")
    receive.add_argument("--port", type=int, default=47000)
    receive.add_argument("--output", type=Path, required=True)
    receive.add_argument("--events", type=int)
    receive.add_argument("--duration", type=float)
    receive.add_argument("--require-events", type=int)
    receive.add_argument("--max-pending", type=int, default=256)
    receive.add_argument("--receive-buffer", type=int, default=16 * 1024 * 1024)
    receive.set_defaults(handler=_receive)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (ControlProtocolError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
