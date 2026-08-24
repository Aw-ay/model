import copy
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import PhysicalChannelMapEntry
from rfsoc_pulse_model.common.types import ChannelRole, GainRange
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from rfsoc_pulse_model.cycle.hardware.production_calibrated_hv import (
    CALIBRATION_COEFFICIENT_FORMAT,
    HvCalibrationCoefficients,
    RxCalibratedHvFrontend2Spc,
)


def _pack_channels(values: list[int], width: int) -> int:
    mask = (1 << width) - 1
    return sum((value & mask) << (width * index) for index, value in enumerate(values))


def _pack_hv(h_value: int, v_value: int) -> int:
    return _pack_channels([h_value, v_value], 24)


class RxCalibratedHvFrontend2SpcTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.coefficients = HvCalibrationCoefficients.identity()
        self.module = RxCalibratedHvFrontend2Spc(self.config, self.coefficients)
        self.sim = CycleSimulator(self.module)
        self.sim.step({"rst_i": 1})
        self.base_inputs = {
            "frontend_enable_i": 1,
            "rx_valid_i": 0,
            "rx_i_lane0_i": 0,
            "rx_q_lane0_i": 0,
            "rx_i_lane1_i": 0,
            "rx_q_lane1_i": 0,
            "sample_base_index_i": 0,
            "stream_active_i": 0,
            "format_error_i": 0,
            "gap_error_i": 0,
            "selected_range_h_i": 0,
            "selected_range_v_i": 0,
        }
        self.i_lane0 = [101, 201, 301, 9001, 401, 501, 601, 9002]
        self.q_lane0 = [-101, -201, -301, -9101, -401, -501, -601, -9102]
        self.i_lane1 = [111, 211, 311, 9011, 411, 511, 611, 9012]
        self.q_lane1 = [-111, -211, -311, -9111, -411, -511, -611, -9112]

    def step(self, **updates: int) -> dict[str, int]:
        return self.sim.step({**self.base_inputs, **updates})

    def _beat(self, *, selected_h: int, selected_v: int, sample_base: int = 0) -> dict[str, int]:
        return {
            "frontend_enable_i": 1,
            "rx_valid_i": 1,
            "rx_i_lane0_i": _pack_channels(self.i_lane0, 16),
            "rx_q_lane0_i": _pack_channels(self.q_lane0, 16),
            "rx_i_lane1_i": _pack_channels(self.i_lane1, 16),
            "rx_q_lane1_i": _pack_channels(self.q_lane1, 16),
            "sample_base_index_i": sample_base,
            "stream_active_i": 1,
            "format_error_i": 0,
            "gap_error_i": 0,
            "selected_range_h_i": selected_h,
            "selected_range_v_i": selected_v,
        }

    def test_selects_only_echo_channels_for_high_mid_and_low_ranges(self) -> None:
        cases = [
            (0, _pack_hv(101 << 4, 401 << 4), _pack_hv(-101 << 4, -401 << 4)),
            (1, _pack_hv(201 << 4, 501 << 4), _pack_hv(-201 << 4, -501 << 4)),
            (2, _pack_hv(301 << 4, 601 << 4), _pack_hv(-301 << 4, -601 << 4)),
        ]

        for selected_range, expected_i0, expected_q0 in cases:
            self.sim.step({"rst_i": 1})
            out = self.sim.step(
                self._beat(
                    selected_h=selected_range,
                    selected_v=selected_range,
                    sample_base=2 * selected_range,
                )
            )
            self.assertEqual(out["incident_valid_o"], 1)
            self.assertEqual(out["sample_base_index_o"], 2 * selected_range)
            self.assertEqual(out["selected_range_h_o"], selected_range)
            self.assertEqual(out["selected_range_v_o"], selected_range)
            self.assertEqual(out["incident_i_lane0_o"], expected_i0)
            self.assertEqual(
                out["incident_i_lane1_o"],
                expected_i0 + ((10 << 4) | ((10 << 4) << 24)),
            )
            self.assertEqual(out["incident_q_lane0_o"], expected_q0)
            self.assertEqual(
                out["incident_q_lane1_o"],
                expected_q0 - ((10 << 4) | ((10 << 4) << 24)),
            )

            self.assertNotIn(9001 << 4, (out["incident_i_lane0_o"] & ((1 << 24) - 1),))
            self.assertNotIn(9002 << 4, (out["incident_i_lane0_o"] >> 24,))  # ADC3/ADC7 never surface

    def test_reserved_range_code_is_sticky_once_enabled(self) -> None:
        out = self.step(**self._beat(selected_h=3, selected_v=0))
        self.assertEqual(out["incident_valid_o"], 0)
        self.assertEqual(out["calibration_error_o"], 1)
        self.assertEqual(out["incident_i_lane0_o"], 0)
        self.assertEqual(out["incident_q_lane0_o"], 0)

        blocked = self.step(**self._beat(selected_h=0, selected_v=0, sample_base=2))
        self.assertEqual(blocked["incident_valid_o"], 0)
        self.assertEqual(blocked["calibration_error_o"], 1)
        self.assertEqual(blocked["sample_base_index_o"], 0)

    def test_pre_enable_reserved_range_is_ignored_and_reset_rearms(self) -> None:
        pre_enable = self.step(frontend_enable_i=0, rx_valid_i=1, selected_range_h_i=3)
        self.assertEqual(pre_enable["calibration_error_o"], 0)
        self.assertEqual(pre_enable["incident_valid_o"], 0)

        self.step(**self._beat(selected_h=3, selected_v=0))
        self.sim.step({"rst_i": 1})
        recovered = self.sim.step(self._beat(selected_h=0, selected_v=0, sample_base=8))
        self.assertEqual(recovered["incident_valid_o"], 1)
        self.assertEqual(recovered["calibration_error_o"], 0)
        self.assertEqual(recovered["sample_base_index_o"], 8)

    def test_upstream_faults_propagate_and_fail_closed(self) -> None:
        format_fault = self.step(**{**self._beat(selected_h=0, selected_v=0), "format_error_i": 1})
        self.assertEqual(format_fault["format_error_o"], 1)
        self.assertEqual(format_fault["incident_valid_o"], 0)
        self.assertEqual(format_fault["stream_active_o"], 0)

        blocked = self.step(**self._beat(selected_h=0, selected_v=0, sample_base=2))
        self.assertEqual(blocked["format_error_o"], 1)
        self.assertEqual(blocked["incident_valid_o"], 0)
        self.assertEqual(blocked["incident_i_lane0_o"], 0)
        self.assertEqual(blocked["incident_q_lane0_o"], 0)

        self.sim.step({"rst_i": 1})
        gap_fault = self.sim.step(
            {**self._beat(selected_h=0, selected_v=0, sample_base=4), "gap_error_i": 1}
        )
        self.assertEqual(gap_fault["gap_error_o"], 1)
        self.assertEqual(gap_fault["incident_valid_o"], 0)

    def test_rejects_mutated_channel_map_that_loses_echo_ownership(self) -> None:
        bad_config = ModelConfig.load_default()
        bad_entries = list(copy.deepcopy(bad_config.adc_channel_map))
        bad_entries[2] = PhysicalChannelMapEntry(
            **{
                **bad_entries[2].__dict__,
                "allowed_roles": (ChannelRole.CALIBRATION,),
                "gain_range": GainRange.REFERENCE,
            }
        )
        object.__setattr__(bad_config, "adc_channel_map", tuple(bad_entries))

        with self.assertRaisesRegex(ValueError, "one echo path"):
            RxCalibratedHvFrontend2Spc(bad_config, self.coefficients)

    def test_applies_custom_coefficients_for_unity_gain_negative_gain_and_halfway_rounding(self) -> None:
        coefficients = HvCalibrationCoefficients(
            h_high=1 << 20,
            h_mid=-(1 << 20),
            h_low=1 << 20,
            v_high=3 << 19,
            v_mid=1 << 15,
            v_low=1 << 20,
        )
        module = RxCalibratedHvFrontend2Spc(self.config, coefficients)
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})

        high = sim.step(self._beat(selected_h=0, selected_v=0))
        self.assertEqual(high["incident_i_lane0_o"], _pack_hv(101 << 4, 401 * 24))
        self.assertEqual(high["incident_q_lane0_o"], _pack_hv(-101 << 4, -401 * 24))

        rounding_inputs = {
            **self._beat(selected_h=1, selected_v=1, sample_base=4),
            "rx_i_lane0_i": _pack_channels([0, 1, 0, 9001, 0, 1, 0, 9002], 16),
            "rx_q_lane0_i": _pack_channels([0, -1, 0, -9001, 0, -1, 0, -9002], 16),
            "rx_i_lane1_i": _pack_channels([0, -1, 0, 9011, 0, -1, 0, 9012], 16),
            "rx_q_lane1_i": _pack_channels([0, 1, 0, -9011, 0, 1, 0, -9012], 16),
        }
        rounded = sim.step(rounding_inputs)
        self.assertEqual(rounded["incident_i_lane0_o"], _pack_hv(-16, 1))
        self.assertEqual(rounded["incident_q_lane0_o"], _pack_hv(16, -1))
        self.assertEqual(rounded["incident_i_lane1_o"], _pack_hv(16, -1))
        self.assertEqual(rounded["incident_q_lane1_o"], _pack_hv(-16, 1))

    def test_invalid_coefficients_raise_sticky_calibration_error(self) -> None:
        bad_coefficients = HvCalibrationCoefficients.identity()
        object.__setattr__(
            bad_coefficients,
            "h_high",
            CALIBRATION_COEFFICIENT_FORMAT.maximum + 1,
        )
        module = RxCalibratedHvFrontend2Spc(self.config, bad_coefficients)
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})

        out = sim.step(self._beat(selected_h=0, selected_v=0))
        self.assertEqual(out["incident_valid_o"], 0)
        self.assertEqual(out["calibration_error_o"], 1)
        self.assertEqual(out["incident_i_lane0_o"], 0)
        self.assertEqual(out["incident_q_lane0_o"], 0)


if __name__ == "__main__":
    unittest.main()
