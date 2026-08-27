from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from rfsoc_pulse_model.common.network_protocol import encode_event_datagrams
from rfsoc_pulse_model.common.types import (
    ChannelRole,
    ChannelIdentity,
    GainRange,
    IQUnit,
    Polarization,
    PowerUnit,
    PulseEvent,
    PulseRecord,
    RangeId,
    SampleDomain,
)
from rfsoc_pulse_model.host.calibrator_client import (
    ControlProtocolError,
    EventReassembler,
    SequenceTracker,
    decode_control_response,
    encode_control_request,
)
from rfsoc_pulse_model.host.cli import EventArchive


def _event(event_id: int = 9) -> PulseEvent:
    record = PulseRecord(
        channel=0,
        range_id=RangeId.PLUS_20_DB,
        sample_domain=SampleDomain.DETECTOR,
        sample_rate_hz=250_000_000,
        toa_samples=1234,
        pw_samples=17,
        peak_power=900,
        mean_power=400,
        freq_word=-12,
        iq=tuple((index, -index) for index in range(32)),
        iq_width_bits=16,
        iq_fraction_bits=0,
        iq_signed=True,
        iq_unit=IQUnit.ADC_CODE,
        power_width_bits=32,
        power_fraction_bits=0,
        power_unit=PowerUnit.ADC_CODE_SQUARED,
        saturated=False,
        truncated=False,
        overflow=False,
        channel_identity=ChannelIdentity(
            polarization=Polarization.H,
            gain_range=GainRange.HIGH,
            role=ChannelRole.ECHO,
            physical_channel=0,
        ),
    )
    return PulseEvent.from_records(event_id=event_id, records=(record,), config_version=3)


class SequenceTrackerTest(unittest.TestCase):
    def test_counts_loss_duplicate_and_reordering_without_wrap_ambiguity(self) -> None:
        tracker = SequenceTracker()
        for sequence in (10, 11, 14, 14, 13, 15):
            tracker.observe(sequence)
        self.assertEqual(tracker.received, 6)
        self.assertEqual(tracker.lost, 2)
        self.assertEqual(tracker.duplicates, 1)
        self.assertEqual(tracker.reordered, 1)

    def test_accepts_uint64_wrap(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(0xFFFFFFFFFFFFFFFF)
        tracker.observe(0)
        self.assertEqual((tracker.lost, tracker.reordered), (0, 0))


class EventReassemblerTest(unittest.TestCase):
    def test_reassembles_out_of_order_fragments_and_tracks_wire_sequences(self) -> None:
        datagrams = encode_event_datagrams(_event(), sequence=100, mtu=100)
        self.assertGreater(len(datagrams), 1)
        receiver = EventReassembler()
        completed = []
        for datagram in reversed(datagrams):
            event = receiver.push(datagram)
            if event is not None:
                completed.append(event)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].event_id, 9)
        self.assertEqual(completed[0].pdws[0].iq[3], (3, -3))
        self.assertEqual(receiver.pending_events, 0)

    def test_duplicate_fragment_is_ignored_and_accounted(self) -> None:
        datagrams = encode_event_datagrams(_event(), sequence=200, mtu=100)
        receiver = EventReassembler()
        self.assertIsNone(receiver.push(datagrams[0]))
        self.assertIsNone(receiver.push(datagrams[0]))
        for datagram in datagrams[1:-1]:
            self.assertIsNone(receiver.push(datagram))
        self.assertIsNotNone(receiver.push(datagrams[-1]))
        self.assertEqual(receiver.duplicate_fragments, 1)


class ControlProtocolTest(unittest.TestCase):
    def test_encodes_only_supported_commands_as_one_canonical_json_line(self) -> None:
        encoded = encode_control_request("set_threshold", threshold=123)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(
            json.loads(encoded),
            {"command": "set_threshold", "threshold": 123},
        )
        with self.assertRaises(ControlProtocolError):
            encode_control_request("format_emmc")

    def test_rejects_non_object_malformed_or_failed_responses(self) -> None:
        self.assertEqual(decode_control_response(b'{"ok":true,"status":{}}\n')["status"], {})
        for response in (b"[]\n", b"not-json\n", b'{"ok":false,"error":"bad"}\n'):
            with self.subTest(response=response):
                with self.assertRaises(ControlProtocolError):
                    decode_control_response(response)


class EventArchiveTest(unittest.TestCase):
    def test_writes_jsonl_metadata_and_fixed_iq16le_records(self) -> None:
        datagram = encode_event_datagrams(_event(), sequence=7)[0]
        event = EventReassembler().push(datagram)
        assert event is not None
        with tempfile.TemporaryDirectory() as directory:
            with EventArchive(Path(directory)) as archive:
                archive.write(event)
            metadata = json.loads((Path(directory) / "events.jsonl").read_text("utf-8"))
            self.assertEqual((metadata["event_id"], metadata["pdws"][0]["channel"]), (9, 0))
            iq_bytes = (Path(directory) / "events.iq16le").read_bytes()
            self.assertEqual(len(iq_bytes), 16 + 32 * 4)
            self.assertEqual(struct.unpack_from("<QI B 3x", iq_bytes), (9, 3, 0))
            self.assertEqual(struct.unpack_from("<hh", iq_bytes, 16 + 3 * 4), (3, -3))


if __name__ == "__main__":
    unittest.main()
