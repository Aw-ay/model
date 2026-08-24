import dataclasses
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.types import RfdcDacClockingMode
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from rfsoc_pulse_model.cycle.hardware.tx_iq_axis_boundary import (
    TxIqAxisBoundary2Spc,
)


def _lanes(values: tuple[int, ...]) -> int:
    word = 0
    for channel, value in enumerate(values):
        word |= (value & 0xFFFF) << (channel * 16)
    return word


class TxIqAxisBoundary2SpcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = TxIqAxisBoundary2Spc(ModelConfig.load_default())
        self.sim = CycleSimulator(self.module)
        self.zeros = {
            "tx_enable_i": 0,
            "clear_status_i": 0,
            "source_valid_i": 0,
            "dac_i_lane0_i": 0,
            "dac_q_lane0_i": 0,
            "dac_i_lane1_i": 0,
            "dac_q_lane1_i": 0,
            "dac_tready_i": 0,
        }
        self.sim.step({**self.zeros, "rst_i": 1})

    def step(self, **updates: int) -> dict[str, int]:
        return self.sim.step({**self.zeros, "rst_i": 0, **updates})

    def test_all_eight_iq_beats_pack_and_advance_atomically(self) -> None:
        i0 = (-32768, 1, 2, 3, 4, 5, 6, 7)
        q0 = (-1, 11, 12, 13, 14, 15, 16, 17)
        i1 = (12345, 21, 22, 23, 24, 25, 26, 27)
        q1 = (32767, 31, 32, 33, 34, 35, 36, 37)

        out = self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
            dac_i_lane0_i=_lanes(i0),
            dac_q_lane0_i=_lanes(q0),
            dac_i_lane1_i=_lanes(i1),
            dac_q_lane1_i=_lanes(q1),
        )

        self.assertEqual(out["dac_tvalid_o"], 0xFF)
        self.assertEqual(out["source_advance_o"], 1)
        self.assertEqual(out["stream_active_o"], 1)
        self.assertEqual(out["underrun_o"], 0)
        self.assertEqual(
            out["dac_tdata_o"] & ((1 << 64) - 1),
            0x7FFF_3039_FFFF_8000,
        )
        channel7 = (out["dac_tdata_o"] >> (7 * 64)) & ((1 << 64) - 1)
        self.assertEqual(channel7, 0x0025_001B_0011_0007)

    def test_ready_loss_after_start_fails_closed_and_never_silently_resumes(self) -> None:
        self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
        )

        failed = self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFE,
            dac_i_lane0_i=_lanes((1,) * 8),
        )
        self.assertEqual(failed["dac_tdata_o"], 0)
        self.assertEqual(failed["source_advance_o"], 0)
        self.assertEqual(failed["stream_active_o"], 0)
        self.assertEqual(failed["underrun_o"], 1)

        resumed = self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
            dac_i_lane0_i=_lanes((2,) * 8),
        )
        self.assertEqual(resumed["dac_tdata_o"], 0)
        self.assertEqual(resumed["source_advance_o"], 0)
        self.assertEqual(resumed["underrun_o"], 1)

    def test_missing_source_beat_is_an_underrun_only_after_stream_start(self) -> None:
        waiting = self.step(tx_enable_i=1, dac_tready_i=0xFF)
        self.assertEqual(waiting["underrun_o"], 0)
        self.assertEqual(waiting["stream_active_o"], 0)

        self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
        )
        failed = self.step(tx_enable_i=1, dac_tready_i=0xFF)
        self.assertEqual(failed["dac_tdata_o"], 0)
        self.assertEqual(failed["underrun_o"], 1)

    def test_disabled_clear_rearms_without_full_reset(self) -> None:
        self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
        )
        self.step(tx_enable_i=1, source_valid_i=0, dac_tready_i=0xFF)

        cleared = self.step(tx_enable_i=0, clear_status_i=1)
        self.assertEqual(cleared["underrun_o"], 0)
        restarted = self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
        )
        self.assertEqual(restarted["source_advance_o"], 1)
        self.assertEqual(restarted["stream_active_o"], 1)

    def test_single_clock_boundary_rejects_per_tile_cdc_configuration(self) -> None:
        config = dataclasses.replace(
            ModelConfig.load_default(),
            rfdc_dac_clocking_mode=RfdcDacClockingMode.PER_TILE_CDC,
        )
        with self.assertRaisesRegex(ValueError, "per-tile CDC"):
            TxIqAxisBoundary2Spc(config)


if __name__ == "__main__":
    unittest.main()
