import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.hardware.tx_iq_axis_boundary import (
    TxIqAxisBoundary2Spc,
)


class TxIqAxisBoundaryEmitterTest(unittest.TestCase):
    def test_emitter_preserves_iq_word_order_and_status_registers(self) -> None:
        module = TxIqAxisBoundary2Spc(ModelConfig.load_default())

        rtl = VerilogEmitter().emit(module)

        self.assertIn("module tx_iq_axis_boundary_2spc", rtl)
        self.assertIn("output reg [511:0] dac_tdata_o", rtl)
        self.assertIn("output reg [7:0] dac_tvalid_o", rtl)
        self.assertIn("output reg source_advance_o", rtl)
        self.assertIn(
            "{dac_q_lane1_i[15:0], dac_i_lane1_i[15:0], "
            "dac_q_lane0_i[15:0], dac_i_lane0_i[15:0]}",
            rtl,
        )
        self.assertIn("underrun_o <= next_underrun", rtl)


if __name__ == "__main__":
    unittest.main()
