import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.hardware.rx_group_ingress import RxGroupIngress2Spc


class RxGroupIngressEmitterTest(unittest.TestCase):
    def test_emitter_is_deterministic_and_preserves_cycle_structure(self) -> None:
        module = RxGroupIngress2Spc(ModelConfig.load_default())
        first = VerilogEmitter().emit(module)
        second = VerilogEmitter().emit(module)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("`timescale 1ns/1ps\n"))
        self.assertIn("module rx_group_ingress_2spc", first)
        self.assertIn("input wire [255:0] adc_i_tdata_i", first)
        self.assertIn("output reg [127:0] rx_i_lane0_o", first)
        self.assertIn("output reg [63:0] sample_base_index_o", first)
        self.assertIn("always @(*)", first)
        self.assertIn("always @(posedge clk_i)", first)
        self.assertNotIn("tready", first.lower())
