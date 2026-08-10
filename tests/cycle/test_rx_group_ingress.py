import dataclasses
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from rfsoc_pulse_model.cycle.hardware.rx_group_ingress import RxGroupIngress2Spc
from rfsoc_pulse_model.common.types import RfdcAdcClockingMode


def _flatten_words(words: list[int]) -> int:
    return sum((word & 0xFFFF_FFFF) << (32 * index) for index, word in enumerate(words))


def _pack_lane(samples: list[int]) -> int:
    return sum((sample & 0xFFFF) << (16 * index) for index, sample in enumerate(samples))


class RxGroupIngress2SpcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.axis = self.config.rfdc_axis
        self.module = RxGroupIngress2Spc(self.config)
        self.sim = CycleSimulator(self.module)

    def _beat(self) -> dict[str, int]:
        i_samples = [(-32768 + channel, 1000 + channel) for channel in range(8)]
        q_samples = [(-1 - channel, 32767 - channel) for channel in range(8)]
        i_words = [self.axis.pack_adc_component_samples(pair) for pair in i_samples]
        q_words = [self.axis.pack_adc_component_samples(pair) for pair in q_samples]
        return {
            "adc_i_tdata_i": _flatten_words(i_words),
            "adc_q_tdata_i": _flatten_words(q_words),
            "adc_i_tvalid_i": 0xFF,
            "adc_q_tvalid_i": 0xFF,
            "expected_i0": _pack_lane([pair[0] for pair in i_samples]),
            "expected_i1": _pack_lane([pair[1] for pair in i_samples]),
            "expected_q0": _pack_lane([pair[0] for pair in q_samples]),
            "expected_q1": _pack_lane([pair[1] for pair in q_samples]),
        }

    def test_accepts_two_complete_complex_samples_per_channel_each_cycle(self) -> None:
        self.sim.step({"rst_i": 1})
        beat = self._beat()
        inputs = {key: value for key, value in beat.items() if not key.startswith("expected")}
        inputs["acquisition_enable_i"] = 1
        outputs = self.sim.step(inputs)

        self.assertEqual(outputs["rx_valid_o"], 1)
        self.assertEqual(outputs["stream_active_o"], 1)
        self.assertEqual(outputs["gap_error_o"], 0)
        self.assertEqual(outputs["rx_i_lane0_o"], beat["expected_i0"])
        self.assertEqual(outputs["rx_i_lane1_o"], beat["expected_i1"])
        self.assertEqual(outputs["rx_q_lane0_o"], beat["expected_q0"])
        self.assertEqual(outputs["rx_q_lane1_o"], beat["expected_q1"])
        self.assertEqual(outputs["sample_base_index_o"], 0)

        second = self.sim.step(inputs)
        self.assertEqual(second["sample_base_index_o"], 2)

    def test_partial_group_fails_closed_until_reset(self) -> None:
        self.sim.step({"rst_i": 1})
        partial = self._beat()
        partial["adc_q_tvalid_i"] = 0x7F
        partial["acquisition_enable_i"] = 1
        first = self.sim.step({key: value for key, value in partial.items() if not key.startswith("expected")})

        self.assertEqual(first["rx_valid_o"], 0)
        self.assertEqual(first["format_error_o"], 1)

        complete = self._beat()
        complete["acquisition_enable_i"] = 1
        second = self.sim.step({key: value for key, value in complete.items() if not key.startswith("expected")})
        self.assertEqual(second["rx_valid_o"], 0)
        self.assertEqual(second["sample_base_index_o"], 0)
        self.assertEqual(second["format_error_o"], 1)
        self.assertEqual(second["stream_active_o"], 0)

        self.sim.step({"rst_i": 1})
        recovered = self.sim.step(
            {key: value for key, value in complete.items() if not key.startswith("expected")}
        )
        self.assertEqual(recovered["rx_valid_o"], 1)
        self.assertEqual(recovered["sample_base_index_o"], 0)
        self.assertEqual(recovered["format_error_o"], 0)

    def test_pre_arm_valid_patterns_are_ignored_without_fault(self) -> None:
        self.sim.step({"rst_i": 1})
        partial = self._beat()
        partial["adc_q_tvalid_i"] = 0x7F
        ignored = self.sim.step(
            {key: value for key, value in partial.items() if not key.startswith("expected")}
        )
        self.assertEqual(ignored["rx_valid_o"], 0)
        self.assertEqual(ignored["stream_active_o"], 0)
        self.assertEqual(ignored["format_error_o"], 0)
        self.assertEqual(ignored["gap_error_o"], 0)

        beat = self._beat()
        beat["acquisition_enable_i"] = 1
        accepted = self.sim.step(
            {key: value for key, value in beat.items() if not key.startswith("expected")}
        )
        self.assertEqual(accepted["sample_base_index_o"], 0)

    def test_all_idle_after_arm_is_sticky_gap_and_fails_closed(self) -> None:
        self.sim.step({"rst_i": 1})
        beat = self._beat()
        beat["acquisition_enable_i"] = 1
        accepted = self.sim.step(
            {key: value for key, value in beat.items() if not key.startswith("expected")}
        )
        self.assertEqual(accepted["rx_valid_o"], 1)
        self.assertEqual(accepted["stream_active_o"], 1)

        gap = self.sim.step(
            {
                "acquisition_enable_i": 1,
                "adc_i_tvalid_i": 0,
                "adc_q_tvalid_i": 0,
            }
        )
        self.assertEqual(gap["rx_valid_o"], 0)
        self.assertEqual(gap["stream_active_o"], 0)
        self.assertEqual(gap["gap_error_o"], 1)
        self.assertEqual(gap["format_error_o"], 0)

        blocked = self.sim.step(
            {key: value for key, value in beat.items() if not key.startswith("expected")}
        )
        self.assertEqual(blocked["rx_valid_o"], 0)
        self.assertEqual(blocked["sample_base_index_o"], 0)
        self.assertEqual(blocked["gap_error_o"], 1)

    def test_single_clock_ingress_rejects_per_tile_cdc_configuration(self) -> None:
        config = dataclasses.replace(
            self.config,
            rfdc_adc_clocking_mode=RfdcAdcClockingMode.PER_TILE_CDC,
        )

        with self.assertRaisesRegex(ValueError, "common PL clock"):
            RxGroupIngress2Spc(config)
