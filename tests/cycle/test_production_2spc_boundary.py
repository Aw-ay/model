import dataclasses
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.types import (
    RfdcAdcClockingMode,
    RfdcDacClockingMode,
)
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from rfsoc_pulse_model.cycle.hardware.production_2spc import (
    ContinuousStreamTimebase,
    RxContinuousIngress2Spc,
    TxContinuousEgress2Spc,
)


def _flatten_words(words: list[int]) -> int:
    return sum((word & 0xFFFF_FFFF) << (32 * index) for index, word in enumerate(words))


def _pack_lanes(values: list[int]) -> int:
    return sum((value & 0xFFFF) << (16 * index) for index, value in enumerate(values))


class RxContinuousIngress2SpcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.module = RxContinuousIngress2Spc(self.config)
        self.sim = CycleSimulator(self.module)

    def _beat(self) -> dict[str, int]:
        i_samples = [(-32768 + channel, 1000 + channel) for channel in range(8)]
        q_samples = [(-1 - channel, 32767 - channel) for channel in range(8)]
        i_words = [self.config.rfdc_axis.pack_adc_component_samples(pair) for pair in i_samples]
        q_words = [self.config.rfdc_axis.pack_adc_component_samples(pair) for pair in q_samples]
        return {
            "adc_i_tdata_i": _flatten_words(i_words),
            "adc_q_tdata_i": _flatten_words(q_words),
            "adc_i_tvalid_i": 0xFF,
            "adc_q_tvalid_i": 0xFF,
            "acquisition_enable_i": 1,
            "expected_i0": _pack_lanes([pair[0] for pair in i_samples]),
            "expected_i1": _pack_lanes([pair[1] for pair in i_samples]),
            "expected_q0": _pack_lanes([pair[0] for pair in q_samples]),
            "expected_q1": _pack_lanes([pair[1] for pair in q_samples]),
        }

    def test_accepts_two_samples_and_preserves_rfdc_lane_order(self) -> None:
        self.sim.step({"rst_i": 1})
        beat = self._beat()
        out = self.sim.step({key: value for key, value in beat.items() if not key.startswith("expected")})

        self.assertEqual(out["rx_valid_o"], 1)
        self.assertEqual(out["sample_base_index_o"], 0)
        self.assertEqual(out["rx_i_lane0_o"], beat["expected_i0"])
        self.assertEqual(out["rx_i_lane1_o"], beat["expected_i1"])
        self.assertEqual(out["rx_q_lane0_o"], beat["expected_q0"])
        self.assertEqual(out["rx_q_lane1_o"], beat["expected_q1"])

        second = self.sim.step({key: value for key, value in beat.items() if not key.startswith("expected")})
        self.assertEqual(second["sample_base_index_o"], 2)

    def test_pre_arm_patterns_are_ignored_and_post_arm_faults_are_sticky(self) -> None:
        self.sim.step({"rst_i": 1})
        beat = self._beat()
        pre_arm = {key: value for key, value in beat.items() if not key.startswith("expected")}
        pre_arm["acquisition_enable_i"] = 0
        pre_arm["adc_q_tvalid_i"] = 0x7F
        out = self.sim.step(pre_arm)
        self.assertEqual(out["format_error_o"], 0)

        partial = {key: value for key, value in beat.items() if not key.startswith("expected")}
        partial["adc_q_tvalid_i"] = 0x7F
        out = self.sim.step(partial)
        self.assertEqual(out["format_error_o"], 1)
        self.assertEqual(out["rx_valid_o"], 0)

        recovered_input = {key: value for key, value in beat.items() if not key.startswith("expected")}
        blocked = self.sim.step(recovered_input)
        self.assertEqual(blocked["format_error_o"], 1)
        self.assertEqual(blocked["rx_valid_o"], 0)

    def test_all_idle_is_a_separate_sticky_gap_fault(self) -> None:
        self.sim.step({"rst_i": 1})
        beat = self._beat()
        self.sim.step({key: value for key, value in beat.items() if not key.startswith("expected")})
        gap = {key: value for key, value in beat.items() if not key.startswith("expected")}
        gap["adc_i_tvalid_i"] = 0
        gap["adc_q_tvalid_i"] = 0
        out = self.sim.step(gap)
        self.assertEqual(out["gap_error_o"], 1)
        self.assertEqual(out["format_error_o"], 0)

    def test_rejects_per_tile_cdc_configuration(self) -> None:
        config = dataclasses.replace(
            self.config,
            rfdc_adc_clocking_mode=RfdcAdcClockingMode.PER_TILE_CDC,
        )
        with self.assertRaisesRegex(ValueError, "common PL clock"):
            RxContinuousIngress2Spc(config)


class ContinuousStreamTimebaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = ContinuousStreamTimebase()
        self.sim = CycleSimulator(self.module)
        self.base = {
            "acquisition_enable_i": 1,
            "sample_valid_i": 0,
            "sample_base_index_i": 0,
            "upstream_fault_i": 0,
        }
        self.sim.step({"rst_i": 1})

    def step(self, **updates: int) -> dict[str, int]:
        return self.sim.step({**self.base, "rst_i": 0, **updates})

    def test_accepts_zero_then_exact_two_sample_index_steps(self) -> None:
        first = self.step(sample_valid_i=1, sample_base_index_i=0)
        self.assertEqual(first["time_valid_o"], 1)
        self.assertEqual(first["sample_base_index_o"], 0)
        self.assertEqual(first["stream_active_o"], 1)

        second = self.step(sample_valid_i=1, sample_base_index_i=2)
        self.assertEqual(second["time_valid_o"], 1)
        self.assertEqual(second["sample_base_index_o"], 2)
        self.assertEqual(second["timebase_error_o"], 0)

    def test_missing_beat_and_discontinuity_fail_closed(self) -> None:
        self.step(sample_valid_i=1, sample_base_index_i=0)
        missing = self.step(sample_valid_i=0)
        self.assertEqual(missing["time_valid_o"], 0)
        self.assertEqual(missing["timebase_error_o"], 1)
        self.assertEqual(missing["stream_integrity_error_o"], 1)

        blocked = self.step(sample_valid_i=1, sample_base_index_i=2)
        self.assertEqual(blocked["time_valid_o"], 0)
        self.assertEqual(blocked["sample_base_index_o"], 0)

        self.sim.step({"rst_i": 1})
        self.step(sample_valid_i=1, sample_base_index_i=0)
        discontinuity = self.step(sample_valid_i=1, sample_base_index_i=4)
        self.assertEqual(discontinuity["timebase_error_o"], 1)
        self.assertEqual(discontinuity["stream_integrity_error_o"], 1)

    def test_upstream_fault_propagates_without_repairing_data(self) -> None:
        out = self.step(sample_valid_i=1, sample_base_index_i=0, upstream_fault_i=1)
        self.assertEqual(out["time_valid_o"], 0)
        self.assertEqual(out["stream_integrity_error_o"], 1)
        self.assertEqual(out["sample_base_index_o"], 0)

    def test_reset_recovers_the_epoch(self) -> None:
        self.step(sample_valid_i=1, sample_base_index_i=0)
        self.step(sample_valid_i=0)
        self.sim.step({"rst_i": 1})
        out = self.step(sample_valid_i=1, sample_base_index_i=0)
        self.assertEqual(out["time_valid_o"], 1)
        self.assertEqual(out["timebase_error_o"], 0)


class TxContinuousEgress2SpcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.module = TxContinuousEgress2Spc(self.config)
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

    def test_packs_all_eight_channels_atomically(self) -> None:
        i0 = (-32768, 1, 2, 3, 4, 5, 6, 7)
        q0 = (-1, 11, 12, 13, 14, 15, 16, 17)
        i1 = (12345, 21, 22, 23, 24, 25, 26, 27)
        q1 = (32767, 31, 32, 33, 34, 35, 36, 37)
        out = self.step(
            tx_enable_i=1,
            source_valid_i=1,
            dac_tready_i=0xFF,
            dac_i_lane0_i=_pack_lanes(list(i0)),
            dac_q_lane0_i=_pack_lanes(list(q0)),
            dac_i_lane1_i=_pack_lanes(list(i1)),
            dac_q_lane1_i=_pack_lanes(list(q1)),
        )
        self.assertEqual(out["dac_tvalid_o"], 0xFF)
        self.assertEqual(out["source_advance_o"], 1)
        self.assertEqual(out["stream_active_o"], 1)
        self.assertEqual(out["dac_tdata_o"] & ((1 << 64) - 1), 0x7FFF_3039_FFFF_8000)

    def test_ready_or_source_loss_is_sticky_underrun(self) -> None:
        self.step(tx_enable_i=1, source_valid_i=1, dac_tready_i=0xFF)
        failed = self.step(tx_enable_i=1, source_valid_i=1, dac_tready_i=0xFE)
        self.assertEqual(failed["dac_tdata_o"], 0)
        self.assertEqual(failed["source_advance_o"], 0)
        self.assertEqual(failed["underrun_o"], 1)

        resumed = self.step(tx_enable_i=1, source_valid_i=1, dac_tready_i=0xFF)
        self.assertEqual(resumed["dac_tdata_o"], 0)
        self.assertEqual(resumed["underrun_o"], 1)

    def test_disabled_clear_rearms_and_rejects_per_tile_cdc(self) -> None:
        self.step(tx_enable_i=1, source_valid_i=1, dac_tready_i=0xFF)
        self.step(tx_enable_i=1, source_valid_i=0, dac_tready_i=0xFF)
        cleared = self.step(clear_status_i=1)
        self.assertEqual(cleared["underrun_o"], 0)

        config = dataclasses.replace(
            self.config,
            rfdc_dac_clocking_mode=RfdcDacClockingMode.PER_TILE_CDC,
        )
        with self.assertRaisesRegex(ValueError, "per-tile CDC"):
            TxContinuousEgress2Spc(config)


if __name__ == "__main__":
    unittest.main()
