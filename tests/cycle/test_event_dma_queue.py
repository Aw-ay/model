import unittest
import struct

from tests.common.test_network_protocol import make_event

try:
    from rfsoc_pulse_model.cycle.hardware.event_dma_queue import EventDmaQueue
except ImportError:  # RED until the non-backpressuring event boundary exists.
    EventDmaQueue = None  # type: ignore[assignment,misc]


class EventDmaQueueTest(unittest.TestCase):
    def test_one_pdw_is_emitted_as_128_bit_axis_beats_with_exact_tkeep(self) -> None:
        assert EventDmaQueue is not None
        queue = EventDmaQueue(capacity_beats=32)
        event = make_event()
        self.assertTrue(queue.submit_event(event))
        beats = queue.drain()

        self.assertEqual(len(beats), 12)  # 32-byte DMA header + 32-byte PDW + 128-byte IQ
        self.assertTrue(all(0 <= beat.tdata < (1 << 128) for beat in beats))
        self.assertTrue(all(beat.tkeep == 0xFFFF for beat in beats))
        self.assertTrue(beats[-1].tlast)
        self.assertTrue(all(beat.event_id == event.event_id for beat in beats))
        payload = b"".join(beat.tdata.to_bytes(16, "little") for beat in beats)
        magic, length, event_id, config_version, toa, channel_mask, pdw_count, flags = struct.unpack_from(
            "<IIIIQIHH", payload
        )
        self.assertEqual(magic, int.from_bytes(b"DMA1", "little"))
        self.assertEqual(length, 192)
        self.assertEqual((event_id, config_version, toa), (event.event_id, 9, event.toa_samples))
        self.assertEqual((channel_mask, pdw_count, flags), (1, 1, 0))
        self.assertEqual(queue.event_count, 1)
        self.assertEqual(queue.drop_count, 0)

    def test_fifo_pressure_drops_the_whole_event_without_partial_beats(self) -> None:
        assert EventDmaQueue is not None
        queue = EventDmaQueue(capacity_beats=11)
        self.assertFalse(queue.submit_event(make_event()))
        self.assertEqual(queue.drain(), ())
        self.assertEqual(queue.event_count, 0)
        self.assertEqual(queue.drop_count, 1)
        self.assertTrue(queue.sticky_errors & queue.ERROR_FIFO_FULL)

    def test_batch_orders_by_toa_then_channel_and_duplicate_is_once_only(self) -> None:
        assert EventDmaQueue is not None
        early = make_event()
        late = make_event()
        object.__setattr__(early, "event_id", 2)
        object.__setattr__(early, "toa_samples", 100)
        object.__setattr__(late, "event_id", 3)
        object.__setattr__(late, "toa_samples", 200)
        queue = EventDmaQueue(capacity_beats=64)
        self.assertEqual(queue.submit_events((late, early)), 2)
        beats = queue.drain()
        first_event_ids = []
        for beat in beats:
            if not first_event_ids or first_event_ids[-1] != beat.event_id:
                first_event_ids.append(beat.event_id)
        self.assertEqual(first_event_ids, [2, 3])

        self.assertFalse(queue.submit_event(early))
        self.assertEqual(queue.drop_count, 1)
        self.assertTrue(queue.sticky_errors & queue.ERROR_DUPLICATE_EVENT)


if __name__ == "__main__":
    unittest.main()
