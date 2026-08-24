import unittest
import re

from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.dsl import concat
from rfsoc_pulse_model.cycle.dsl.expr import ConstExpr
from rfsoc_pulse_model.cycle.dsl.fixed import (
    round_shift_ties_away_from_zero,
    signed_out_of_range,
    saturate_signed,
    signed_mul,
)
from rfsoc_pulse_model.cycle.dsl.module import RTLModule
from rfsoc_pulse_model.cycle.dsl.simulator import CycleSimulator
from tests.cycle.verilog_eval import evaluate_verilog_expression


def _twos_complement(width: int, value: int) -> int:
    return value & ((1 << width) - 1)


class FixedPointProbe(RTLModule):
    module_name = "fixed_point_probe"

    def __init__(
        self,
        product: ConstExpr,
        rounded: ConstExpr,
        saturated: ConstExpr,
        out_of_range: ConstExpr,
    ) -> None:
        super().__init__()
        self.clk_i = self.input("clk_i")
        self.rst_i = self.input("rst_i")
        self.product_o = self.output("product_o", 48)
        self.rounded_o = self.output_reg("rounded_o", 24)
        self.saturated_o = self.output_reg("saturated_o", 24)
        self.out_of_range_o = self.output_reg("out_of_range_o")
        self.reset_signal = self.rst_i
        self._product = product
        self._rounded = rounded
        self._saturated = saturated
        self._out_of_range = out_of_range

    def compute(self) -> None:
        self.drive(self.product_o, self._product)

    def clock(self) -> None:
        self.update(self.rounded_o, self._rounded, reset=0)
        self.update(self.saturated_o, self._saturated, reset=0)
        self.update(self.out_of_range_o, self._out_of_range, reset=0)


class SignedMultiplyTest(unittest.TestCase):
    def test_signed_mul_evaluates_positive_and_negative_operands(self) -> None:
        positive = signed_mul(
            ConstExpr(3, 16, signed=True),
            ConstExpr(5, 24, signed=True),
            48,
        )
        negative = signed_mul(
            ConstExpr(-3, 16, signed=True),
            ConstExpr(5, 24, signed=True),
            48,
        )

        self.assertTrue(positive.signed)
        self.assertEqual(positive.width, 48)
        self.assertEqual(positive.evaluate(), _twos_complement(48, 15))
        self.assertEqual(negative.evaluate(), _twos_complement(48, -15))

    def test_signed_mul_is_usable_by_rtlmodule_drive_and_update(self) -> None:
        product = signed_mul(
            ConstExpr(-7, 16, signed=True),
            ConstExpr(9, 24, signed=True),
            48,
        )
        probe = FixedPointProbe(
            product=product,
            rounded=round_shift_ties_away_from_zero(
                ConstExpr(-6, 32, signed=True),
                2,
                24,
            ),
            saturated=saturate_signed(
                ConstExpr((1 << 23) + 1, 32, signed=True),
                24,
            ),
            out_of_range=signed_out_of_range(
                ConstExpr((1 << 23) + 1, 32, signed=True),
                24,
            ),
        )
        sim = CycleSimulator(probe)

        outputs = sim.step({"rst_i": 0})

        self.assertEqual(outputs["product_o"], _twos_complement(48, -63))
        self.assertEqual(outputs["rounded_o"], _twos_complement(24, -2))
        self.assertEqual(outputs["saturated_o"], _twos_complement(24, (1 << 23) - 1))
        self.assertEqual(outputs["out_of_range_o"], 1)

        rtl = VerilogEmitter().emit(probe)
        self.assertEqual(rtl, VerilogEmitter().emit(probe))
        self.assertIn("output reg [47:0] product_o", rtl)
        self.assertIn("output reg [23:0] rounded_o", rtl)
        self.assertIn("output reg [23:0] saturated_o", rtl)
        self.assertIn("output reg out_of_range_o", rtl)
        self.assertIn("$signed", rtl)
        self.assertIn(">>> 2", rtl)
        self.assertIn("?", rtl)

    def test_signed_mul_rejects_unsigned_operands_and_nonpositive_width(self) -> None:
        with self.assertRaisesRegex(ValueError, "signed"):
            signed_mul(ConstExpr(3, 16), ConstExpr(5, 24, signed=True), 48)
        with self.assertRaisesRegex(ValueError, "positive"):
            signed_mul(
                ConstExpr(3, 16, signed=True),
                ConstExpr(5, 24, signed=True),
                0,
            )
        with self.assertRaisesRegex(ValueError, "positive"):
            signed_mul(
                ConstExpr(3, 16, signed=True),
                ConstExpr(5, 24, signed=True),
                -1,
            )


class RoundShiftTest(unittest.TestCase):
    def test_round_shift_ties_away_from_zero_handles_halfway_values(self) -> None:
        positive = round_shift_ties_away_from_zero(
            ConstExpr(6, 32, signed=True),
            2,
            24,
        )
        negative = round_shift_ties_away_from_zero(
            ConstExpr(-6, 32, signed=True),
            2,
            24,
        )
        passthrough = round_shift_ties_away_from_zero(
            ConstExpr(-7, 32, signed=True),
            0,
            24,
        )

        self.assertEqual(positive.evaluate(), _twos_complement(24, 2))
        self.assertEqual(negative.evaluate(), _twos_complement(24, -2))
        self.assertEqual(passthrough.evaluate(), _twos_complement(24, -7))

    def test_round_shift_ties_away_from_zero_handles_non_half_values(self) -> None:
        positive = round_shift_ties_away_from_zero(
            ConstExpr(5, 32, signed=True),
            2,
            24,
        )
        negative = round_shift_ties_away_from_zero(
            ConstExpr(-5, 32, signed=True),
            2,
            24,
        )
        more_negative = round_shift_ties_away_from_zero(
            ConstExpr(-7, 32, signed=True),
            2,
            24,
        )

        self.assertEqual(positive.evaluate(), _twos_complement(24, 1))
        self.assertEqual(negative.evaluate(), _twos_complement(24, -1))
        self.assertEqual(more_negative.evaluate(), _twos_complement(24, -2))
        self.assertIn("(($signed(32'sd5) + 24'sd2) >>> 2)", positive.verilog())
        self.assertIn("(-(((-", negative.verilog())
        self.assertIn("(($signed(32'sd-5) < 0)", negative.verilog())
        self.assertIn("($signed(32'sd-7) < 0)", more_negative.verilog())

    def test_round_shift_emits_explicit_result_width_for_all_paths(self) -> None:
        cases = (
            (ConstExpr((1 << 47) - 1, 48, signed=True), 16, 32),
            (ConstExpr(-((1 << 47) - 1), 48, signed=True), 16, 32),
            (ConstExpr(5, 16, signed=True), 0, 24),
            (ConstExpr(-5, 16, signed=True), 0, 24),
            (ConstExpr(-(1 << 23), 32, signed=True), 0, 24),
        )

        for value, shift, result_width in cases:
            expr = round_shift_ties_away_from_zero(value, shift, result_width)
            emitted = evaluate_verilog_expression(expr.verilog(), {})

            self.assertEqual(emitted.width, result_width)
            self.assertEqual(emitted.raw, expr.evaluate())
            self.assertTrue(emitted.signed)

        for source_value, expected_value in (
            ((1 << 23) - 1, (1 << 23) - 1),
            (-(1 << 23), -(1 << 23)),
        ):
            composed = saturate_signed(
                round_shift_ties_away_from_zero(
                    ConstExpr(source_value, 32, signed=True),
                    0,
                    24,
                ),
                24,
            )
            emitted = evaluate_verilog_expression(composed.verilog(), {})

            self.assertEqual(emitted.width, 24)
            self.assertEqual(emitted.raw, composed.evaluate())
            self.assertEqual(emitted.raw, _twos_complement(24, expected_value))


class SaturateSignedTest(unittest.TestCase):
    def test_saturate_signed_clamps_both_rails_and_preserves_endpoints(self) -> None:
        positive = saturate_signed(ConstExpr((1 << 23) + 1, 32, signed=True), 24)
        negative = saturate_signed(ConstExpr(-(1 << 23) - 1, 32, signed=True), 24)
        high_endpoint = saturate_signed(ConstExpr((1 << 23) - 1, 32, signed=True), 24)
        low_endpoint = saturate_signed(ConstExpr(-(1 << 23), 32, signed=True), 24)

        self.assertEqual(positive.evaluate(), _twos_complement(24, (1 << 23) - 1))
        self.assertEqual(negative.evaluate(), _twos_complement(24, -(1 << 23)))
        self.assertEqual(high_endpoint.evaluate(), _twos_complement(24, (1 << 23) - 1))
        self.assertEqual(low_endpoint.evaluate(), _twos_complement(24, -(1 << 23)))

    def test_saturate_signed_emits_compare_and_select_logic(self) -> None:
        expr = saturate_signed(ConstExpr((1 << 23) + 1, 32, signed=True), 24)

        self.assertTrue(expr.signed)
        self.assertEqual(expr.width, 24)
        self.assertIn("$signed", expr.verilog())
        self.assertIn("?", expr.verilog())

    def test_saturate_signed_emits_an_explicit_24_bit_result(self) -> None:
        expr = saturate_signed(ConstExpr((1 << 30) + 3, 48, signed=True), 24)

        self.assertRegex(expr.verilog(), r"\[23:0\]")

    def test_saturate_signed_sign_extends_when_result_is_wider_than_source(self) -> None:
        expr = saturate_signed(ConstExpr(-7, 16, signed=True), 24)

        self.assertIn("$signed({{8{", expr.verilog())

    def test_concat_of_saturated_samples_preserves_both_24_bit_lanes_in_emitted_rtl(self) -> None:
        class SaturateConcatProbe(RTLModule):
            module_name = "saturate_concat_probe"

            def __init__(self) -> None:
                super().__init__()
                self.clk_i = self.input("clk_i")
                self.rst_i = self.input("rst_i")
                self.reset_signal = self.rst_i
                self.packed_o = self.output_reg("packed_o", 48)
                self.next_packed = self.wire("next_packed", 48)

            def compute(self) -> None:
                self.drive(
                    self.next_packed,
                    concat(
                        (
                            saturate_signed(ConstExpr((1 << 30) + 3, 48, signed=True), 24),
                            saturate_signed(ConstExpr(-((1 << 30) + 5), 48, signed=True), 24),
                        )
                    ),
                )

            def clock(self) -> None:
                self.update(self.packed_o, self.next_packed, reset=0)

        rtl = VerilogEmitter().emit(SaturateConcatProbe())
        assignment = next(line for line in rtl.splitlines() if "next_packed =" in line)

        self.assertGreaterEqual(len(re.findall(r"\[23:0\]", assignment)), 2)


class SignedOutOfRangeTest(unittest.TestCase):
    def test_signed_out_of_range_flags_values_beyond_both_rails(self) -> None:
        positive = signed_out_of_range(ConstExpr((1 << 23), 32, signed=True), 24)
        negative = signed_out_of_range(ConstExpr(-(1 << 23) - 1, 32, signed=True), 24)
        high_endpoint = signed_out_of_range(ConstExpr((1 << 23) - 1, 32, signed=True), 24)
        low_endpoint = signed_out_of_range(ConstExpr(-(1 << 23), 32, signed=True), 24)

        self.assertEqual(positive.evaluate(), 1)
        self.assertEqual(negative.evaluate(), 1)
        self.assertEqual(high_endpoint.evaluate(), 0)
        self.assertEqual(low_endpoint.evaluate(), 0)

    def test_signed_out_of_range_emits_signed_compare_logic(self) -> None:
        expr = signed_out_of_range(ConstExpr((1 << 23), 32, signed=True), 24)

        self.assertEqual(expr.width, 1)
        self.assertFalse(expr.signed)
        self.assertIn("$signed", expr.verilog())
        self.assertIn(">", expr.verilog())
        self.assertIn("<", expr.verilog())


if __name__ == "__main__":
    unittest.main()
