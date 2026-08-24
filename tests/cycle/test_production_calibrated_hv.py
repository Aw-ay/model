import copy
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import PhysicalChannelMapEntry
from rfsoc_pulse_model.common.types import ChannelRole, GainRange
from rfsoc_pulse_model.cycle.dsl.expr import ConstExpr
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.dsl.fixed import signed_out_of_range, saturate_signed
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from rfsoc_pulse_model.cycle.hardware.production_calibrated_hv import (
    CALIBRATION_COEFFICIENT_FORMAT,
    HvCalibrationCoefficients,
    REFLECTION_SAMPLE_FORMAT,
    RxCalibratedHvFrontend2Spc,
)
from tests.cycle.verilog_eval import evaluate_verilog_expression


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

    def test_selects_only_echo_channels_for_every_valid_h_and_v_selector_pair(self) -> None:
        expected_h_i = {0: 101 << 4, 1: 201 << 4, 2: 301 << 4}
        expected_v_i = {0: 401 << 4, 1: 501 << 4, 2: 601 << 4}
        expected_h_q = {0: -101 << 4, 1: -201 << 4, 2: -301 << 4}
        expected_v_q = {0: -401 << 4, 1: -501 << 4, 2: -601 << 4}
        forbidden = {
            9001 << 4,
            9002 << 4,
            -9101 << 4,
            -9102 << 4,
            9011 << 4,
            9012 << 4,
            -9111 << 4,
            -9112 << 4,
        }

        sample_base = 0
        for selected_h in (0, 1, 2):
            for selected_v in (0, 1, 2):
                self.sim.step({"rst_i": 1})
                out = self.sim.step(
                    self._beat(
                        selected_h=selected_h,
                        selected_v=selected_v,
                        sample_base=sample_base,
                    )
                )
                self.assertEqual(out["incident_valid_o"], 1)
                self.assertEqual(out["sample_base_index_o"], sample_base)
                self.assertEqual(out["selected_range_h_o"], selected_h)
                self.assertEqual(out["selected_range_v_o"], selected_v)
                self.assertEqual(
                    out["incident_i_lane0_o"],
                    _pack_hv(expected_h_i[selected_h], expected_v_i[selected_v]),
                )
                self.assertEqual(
                    out["incident_i_lane1_o"],
                    _pack_hv(expected_h_i[selected_h] + (10 << 4), expected_v_i[selected_v] + (10 << 4)),
                )
                self.assertEqual(
                    out["incident_q_lane0_o"],
                    _pack_hv(expected_h_q[selected_h], expected_v_q[selected_v]),
                )
                self.assertEqual(
                    out["incident_q_lane1_o"],
                    _pack_hv(expected_h_q[selected_h] - (10 << 4), expected_v_q[selected_v] - (10 << 4)),
                )
                for lane_name in (
                    "incident_i_lane0_o",
                    "incident_i_lane1_o",
                    "incident_q_lane0_o",
                    "incident_q_lane1_o",
                ):
                    lane = out[lane_name]
                    lower = lane & ((1 << 24) - 1)
                    upper = lane >> 24
                    self.assertNotIn(lower, forbidden)
                    self.assertNotIn(upper, forbidden)
                sample_base += 2

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

    def test_invalid_coefficients_raise_value_error_before_module_construction(self) -> None:
        bad_coefficients = HvCalibrationCoefficients.identity()
        object.__setattr__(
            bad_coefficients,
            "h_high",
            CALIBRATION_COEFFICIENT_FORMAT.maximum + 1,
        )
        with self.assertRaisesRegex(ValueError, "24-bit signed calibration coefficient"):
            RxCalibratedHvFrontend2Spc(self.config, bad_coefficients)

    def test_runtime_overflow_is_sticky_and_fail_closed(self) -> None:
        class OverflowInjectedFrontend(RxCalibratedHvFrontend2Spc):
            def _calibrate_sample(self, lane_bus, polarization, selected_range):
                if polarization.value == "H" and selected_range.eq(0).evaluate():
                    rounded = ConstExpr(REFLECTION_SAMPLE_FORMAT.maximum + 1, 48, signed=True)
                    return saturate_signed(rounded, 24), signed_out_of_range(rounded, 24)
                return super()._calibrate_sample(lane_bus, polarization, selected_range)

        module = OverflowInjectedFrontend(self.config, HvCalibrationCoefficients.identity())
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})

        out = sim.step(self._beat(selected_h=0, selected_v=0, sample_base=6))
        self.assertEqual(out["incident_valid_o"], 0)
        self.assertEqual(out["calibration_error_o"], 1)
        self.assertEqual(out["incident_i_lane0_o"], 0)
        self.assertEqual(out["incident_q_lane0_o"], 0)
        self.assertEqual(out["stream_active_o"], 0)

        blocked = sim.step(self._beat(selected_h=1, selected_v=1, sample_base=8))
        self.assertEqual(blocked["incident_valid_o"], 0)
        self.assertEqual(blocked["calibration_error_o"], 1)
        self.assertEqual(blocked["sample_base_index_o"], 0)
        self.assertEqual(blocked["incident_i_lane1_o"], 0)

    def test_emitted_candidate_expressions_match_cycle_outputs_for_both_packed_lanes(self) -> None:
        module = RxCalibratedHvFrontend2Spc(self.config, self.coefficients)
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})
        rtl = VerilogEmitter().emit(module)

        beat = self._beat(selected_h=2, selected_v=1, sample_base=12)
        signal_by_name = {
            signal.name: signal
            for signal in (*module.ports, *module.internal_signals)
        }
        environment = {
            name: (signal.value, signal.width, signal.signed)
            for name, signal in signal_by_name.items()
        }
        environment.update(
            {
                name: (value, signal_by_name[name].width, signal_by_name[name].signed)
                for name, value in beat.items()
            }
        )
        environment["rst_i"] = (0, 1, False)
        expected = sim.step(beat)

        for signal_name, output_name in (
            ("next_incident_i_lane0", "incident_i_lane0_o"),
            ("next_incident_q_lane0", "incident_q_lane0_o"),
            ("next_incident_i_lane1", "incident_i_lane1_o"),
            ("next_incident_q_lane1", "incident_q_lane1_o"),
        ):
            prefix = f"    {signal_name} = "
            assignment = next(line for line in rtl.splitlines() if line.startswith(prefix))
            emitted = evaluate_verilog_expression(assignment[len(prefix) : -1], environment)
            self.assertEqual(emitted.width, 48)
            self.assertEqual(emitted.raw, expected[output_name])

        emitted_i = evaluate_verilog_expression(
            next(
                line[len("    next_incident_i_lane0 = ") : -1]
                for line in rtl.splitlines()
                if line.startswith("    next_incident_i_lane0 = ")
            ),
            environment,
        )
        self.assertEqual(emitted_i.raw & ((1 << 24) - 1), 301 << 4)
        self.assertEqual(emitted_i.raw >> 24, 501 << 4)


if __name__ == "__main__":
    unittest.main()
