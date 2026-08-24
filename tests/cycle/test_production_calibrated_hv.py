import copy
import dataclasses
import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    EightChannelAdcFrame,
    PhysicalChannelMapEntry,
)
from rfsoc_pulse_model.common.types import ChannelRole, GainRange
from rfsoc_pulse_model.common.types import Polarization, RangeSelectionMode, SampleDomain
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
from rfsoc_pulse_model.golden.adc_frontend import GoldenEightChannelAdcFrontend
from tests.cycle.verilog_eval import evaluate_verilog_expression


def _pack_channels(values: list[int], width: int) -> int:
    mask = (1 << width) - 1
    return sum((value & mask) << (width * index) for index, value in enumerate(values))


def _pack_hv(h_value: int, v_value: int) -> int:
    return _pack_channels([h_value, v_value], 24)


def _signed_code(value: int, width: int) -> int:
    value &= (1 << width) - 1
    return value - (1 << width) if value & (1 << (width - 1)) else value


def _unpack_hv(value: int) -> tuple[int, int]:
    return (
        _signed_code(value, 24),
        _signed_code(value >> 24, 24),
    )


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

    def _beat_from_vectors(
        self,
        i_vectors: np.ndarray,
        q_vectors: np.ndarray,
        *,
        selected_h: int,
        selected_v: int,
        sample_base: int = 0,
    ) -> dict[str, int]:
        return {
            "frontend_enable_i": 1,
            "rx_valid_i": 1,
            "rx_i_lane0_i": _pack_channels(i_vectors[:, 0].tolist(), 16),
            "rx_q_lane0_i": _pack_channels(q_vectors[:, 0].tolist(), 16),
            "rx_i_lane1_i": _pack_channels(i_vectors[:, 1].tolist(), 16),
            "rx_q_lane1_i": _pack_channels(q_vectors[:, 1].tolist(), 16),
            "sample_base_index_i": sample_base,
            "stream_active_i": 1,
            "format_error_i": 0,
            "gap_error_i": 0,
            "selected_range_h_i": selected_h,
            "selected_range_v_i": selected_v,
        }

    def _normalized_identity_config(self) -> ModelConfig:
        normalized_map = tuple(
            dataclasses.replace(entry, nominal_gain_db=0.0)
            for entry in self.config.adc_channel_map
        )
        return dataclasses.replace(self.config, adc_channel_map=normalized_map)

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

    def test_golden_identity_profile_matches_quantized_candidate_for_all_hv_ranges(self) -> None:
        # Normalize the in-memory map so this test isolates the candidate's
        # fixed-point scalar boundary from the Golden nominal analog gains.
        config = self._normalized_identity_config()
        calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )
        i_vectors = np.array(
            [
                [32767, -32768],
                [12345, -12345],
                [-23456, 23456],
                [1111, -1111],
                [-30000, 30000],
                [22222, -22222],
                [-11111, 11111],
                [3333, -3333],
            ],
            dtype=np.int64,
        )
        q_vectors = np.array(
            [
                [-1, 1],
                [2345, -2345],
                [-3001, 3001],
                [4444, -4444],
                [30000, -30000],
                [-2222, 2222],
                [11111, -11111],
                [-5555, 5555],
            ],
            dtype=np.int64,
        )
        frame = EightChannelAdcFrame(
            i_vectors.astype(np.complex128) + 1j * q_vectors,
            np.zeros((8, 2), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        golden = GoldenEightChannelAdcFrontend(config, calibration)
        module = RxCalibratedHvFrontend2Spc(
            config,
            HvCalibrationCoefficients.identity(),
        )
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})
        reflection_format = config.numeric_formats["reflection_sample"]

        for selected_h in range(3):
            for selected_v in range(3):
                result = golden.reconstruct(
                    frame,
                    mode=RangeSelectionMode.FIXED,
                    fixed_ranges={
                        Polarization.H: (GainRange.HIGH, GainRange.MID, GainRange.LOW)[selected_h],
                        Polarization.V: (GainRange.HIGH, GainRange.MID, GainRange.LOW)[selected_v],
                    },
                )
                out = sim.step(
                    self._beat_from_vectors(
                        i_vectors,
                        q_vectors,
                        selected_h=selected_h,
                        selected_v=selected_v,
                        sample_base=2 * (selected_h * 3 + selected_v),
                    )
                )
                self.assertEqual(out["incident_valid_o"], 1)
                for sample_index, lane_name in enumerate(
                    ("incident_i_lane0_o", "incident_i_lane1_o")
                ):
                    expected_h_i = reflection_format.quantize(
                        result.incident.samples[0, sample_index].real
                    )
                    expected_v_i = reflection_format.quantize(
                        result.incident.samples[1, sample_index].real
                    )
                    self.assertEqual(
                        _unpack_hv(out[lane_name]),
                        (expected_h_i, expected_v_i),
                    )
                for sample_index, lane_name in enumerate(
                    ("incident_q_lane0_o", "incident_q_lane1_o")
                ):
                    expected_h_q = reflection_format.quantize(
                        result.incident.samples[0, sample_index].imag
                    )
                    expected_v_q = reflection_format.quantize(
                        result.incident.samples[1, sample_index].imag
                    )
                    self.assertEqual(
                        _unpack_hv(out[lane_name]),
                        (expected_h_q, expected_v_q),
                    )

    def test_consecutive_valid_beats_have_registered_latency_and_no_backpressure(self) -> None:
        module = RxCalibratedHvFrontend2Spc(self.config, self.coefficients)
        sim = CycleSimulator(module)
        sim.step({"rst_i": 1})
        idle = sim.step(self.base_inputs)
        self.assertEqual(idle["incident_valid_o"], 0)
        self.assertEqual(module.latency_cycles, 1)
        self.assertFalse(module.accepts_backpressure)
        self.assertNotIn("ready", {port.name for port in module.ports})

        outputs = []
        for beat_index, sample_base in enumerate(range(0, 8, 2)):
            outputs.append(
                sim.step(
                    self._beat(
                        selected_h=beat_index % 3,
                        selected_v=(beat_index + 1) % 3,
                        sample_base=sample_base,
                    )
                )
            )

        self.assertEqual(
            [out["incident_valid_o"] for out in outputs],
            [1, 1, 1, 1],
        )
        self.assertEqual(
            [out["sample_base_index_o"] for out in outputs],
            [0, 2, 4, 6],
        )

    def test_golden_identity_profile_uses_authority_saturation_on_both_rails(self) -> None:
        config = self._normalized_identity_config()
        calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )
        reflection_format = config.numeric_formats["reflection_sample"]
        positive_over = reflection_format.to_float(reflection_format.maximum) + 1.0
        negative_over = reflection_format.to_float(reflection_format.minimum) - 1.0
        samples = np.zeros((8, 2), dtype=np.complex128)
        samples[0, 0] = positive_over
        samples[4, 1] = negative_over
        result = GoldenEightChannelAdcFrontend(config, calibration).reconstruct(
            EightChannelAdcFrame(
                samples,
                np.zeros((8, 2), dtype=np.bool_),
                SampleDomain.RFDC_COMPLEX_INPUT,
                500_000_000,
            ),
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={
                Polarization.H: GainRange.HIGH,
                Polarization.V: GainRange.HIGH,
            },
        )

        self.assertEqual(
            reflection_format.quantize(result.incident.samples[0, 0].real),
            reflection_format.maximum,
        )
        self.assertEqual(
            reflection_format.quantize(result.incident.samples[1, 1].real),
            reflection_format.minimum,
        )

    def test_candidate_verilog_is_byte_deterministic_with_complete_widths(self) -> None:
        first_module = RxCalibratedHvFrontend2Spc(self.config, self.coefficients)
        second_module = RxCalibratedHvFrontend2Spc(self.config, self.coefficients)
        emitter = VerilogEmitter()
        first = emitter.emit(first_module)
        second = emitter.emit(second_module)
        self.assertEqual(first, second)

        expected_widths = {
            "clk_i": 1,
            "rst_i": 1,
            "frontend_enable_i": 1,
            "rx_valid_i": 1,
            "rx_i_lane0_i": 128,
            "rx_q_lane0_i": 128,
            "rx_i_lane1_i": 128,
            "rx_q_lane1_i": 128,
            "sample_base_index_i": 64,
            "stream_active_i": 1,
            "format_error_i": 1,
            "gap_error_i": 1,
            "selected_range_h_i": 2,
            "selected_range_v_i": 2,
            "incident_valid_o": 1,
            "incident_i_lane0_o": 48,
            "incident_q_lane0_o": 48,
            "incident_i_lane1_o": 48,
            "incident_q_lane1_o": 48,
            "sample_base_index_o": 64,
            "stream_active_o": 1,
            "format_error_o": 1,
            "gap_error_o": 1,
            "calibration_error_o": 1,
            "selected_range_h_o": 2,
            "selected_range_v_o": 2,
        }
        self.assertEqual(
            {port.name: port.width for port in first_module.ports},
            expected_widths,
        )
        for name, width in expected_widths.items():
            declaration = f"{('input wire' if name.endswith('_i') or name in {'clk_i', 'rst_i'} else 'output reg')}"
            if width == 1:
                self.assertIn(f"{declaration} {name}", first)
            else:
                self.assertIn(f"{declaration} [{width - 1}:0] {name}", first)
        self.assertNotIn("ready", first)
        self.assertNotIn("backpressure", first)


if __name__ == "__main__":
    unittest.main()
