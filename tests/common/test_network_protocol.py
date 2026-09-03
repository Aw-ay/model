import unittest

from rfsoc_pulse_model.common.types import (
    IQUnit,
    PowerUnit,
    PulseEvent,
    PulseRecord,
    RangeId,
    SampleDomain,
)

try:
    from rfsoc_pulse_model.common.network_protocol import (
        HEADER_SIZE,
        PDW_HEADER_SIZE,
        ProtocolError,
        decode_event_datagrams,
        encode_event_datagrams,
    )
except ImportError:  # RED until protocol v1 exists.
    HEADER_SIZE = PDW_HEADER_SIZE = None  # type: ignore[assignment]
    ProtocolError = ValueError  # type: ignore[assignment,misc]
    decode_event_datagrams = encode_event_datagrams = None  # type: ignore[assignment]


def make_event(record_count: int = 1) -> PulseEvent:
    iq = tuple((index - 16, 16 - index) for index in range(32))
    records = tuple(
        PulseRecord(
            channel=channel,
            range_id=RangeId(channel % 3),
            sample_domain=SampleDomain.DETECTOR,
            sample_rate_hz=250_000_000,
            iq_width_bits=16,
            iq_fraction_bits=0,
            iq_signed=True,
            iq_unit=IQUnit.ADC_CODE,
            power_width_bits=32,
            power_fraction_bits=0,
            power_unit=PowerUnit.ADC_CODE_SQUARED,
            toa_samples=0x0102030405060708 + channel,
            pw_samples=31 + channel,
            peak_power=1000 + channel,
            mean_power=700 + channel,
            freq_word=-123456 + channel,
            iq=iq,
            saturated=channel == 0,
        )
        for channel in range(record_count)
    )
    return PulseEvent.from_records(event_id=0x10203040, records=records, config_version=9)


class NetworkProtocolTest(unittest.TestCase):
    def test_v1_sizes_and_single_datagram_round_trip(self) -> None:
        self.assertEqual(HEADER_SIZE, 48)
        self.assertEqual(PDW_HEADER_SIZE, 32)
        self.assertIsNotNone(encode_event_datagrams)
        assert encode_event_datagrams is not None and decode_event_datagrams is not None

        datagrams = encode_event_datagrams(make_event(), sequence=123)
        self.assertEqual(len(datagrams), 1)
        decoded = decode_event_datagrams(datagrams)

        self.assertEqual(decoded.sequence, 123)
        self.assertEqual(decoded.event_id, 0x10203040)
        self.assertEqual(decoded.config_version, 9)
        self.assertEqual(decoded.channel_mask, 1)
        self.assertEqual(decoded.pdws[0].iq, tuple((i - 16, 16 - i) for i in range(32)))
        self.assertTrue(decoded.pdws[0].saturated)
        self.assertEqual(decoded.pdws[0].freq_word, -123456)

    def test_fragmentation_is_event_atomic_and_reassembles_in_index_order(self) -> None:
        assert encode_event_datagrams is not None and decode_event_datagrams is not None
        datagrams = encode_event_datagrams(make_event(8), sequence=500, mtu=300)
        self.assertGreater(len(datagrams), 1)
        decoded = decode_event_datagrams(tuple(reversed(datagrams)))
        self.assertEqual(len(decoded.pdws), 8)
        self.assertEqual(decoded.sequence, 500)
        self.assertEqual(decoded.channel_mask, 0xFF)

        with self.assertRaisesRegex(ProtocolError, "missing fragment"):
            decode_event_datagrams(datagrams[:-1])

    def test_crc_unknown_version_and_iq_length_are_rejected(self) -> None:
        assert encode_event_datagrams is not None and decode_event_datagrams is not None
        datagram = bytearray(encode_event_datagrams(make_event(), sequence=1)[0])
        datagram[-1] ^= 0x01
        with self.assertRaisesRegex(ProtocolError, "CRC"):
            decode_event_datagrams((bytes(datagram),))

        datagram = bytearray(encode_event_datagrams(make_event(), sequence=1)[0])
        datagram[4:6] = (2).to_bytes(2, "little")
        with self.assertRaisesRegex(ProtocolError, "version"):
            decode_event_datagrams((bytes(datagram),))

        bad_record = make_event().records[0]
        object.__setattr__(bad_record, "iq", bad_record.iq[:-1])
        bad_event = PulseEvent.from_records(3, (bad_record,), 1)
        with self.assertRaisesRegex(ProtocolError, "exactly 32"):
            encode_event_datagrams(bad_event, sequence=2)


if __name__ == "__main__":
    unittest.main()
