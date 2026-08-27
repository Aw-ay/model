from pathlib import Path
import unittest


class CalibratorRtlContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.core = (cls.root / "rtl/calibrator_core.sv").read_text(encoding="utf-8")
        cls.control = (cls.root / "rtl/calibrator_control_axi.sv").read_text(encoding="utf-8")

    def test_core_has_eight_64_bit_inputs_and_non_backpressuring_ready(self) -> None:
        for channel in range(8):
            prefix = f"s{channel:02d}_axis"
            self.assertIn(f"input  wire [63:0]  {prefix}_tdata", self.core)
            self.assertIn(f"assign {prefix}_tready = 1'b1;", self.core)
        self.assertIn("output reg  [127:0] m_event_axis_tdata", self.core)
        self.assertIn("output reg  [15:0]  m_event_axis_tkeep", self.core)
        self.assertIn("event_iq [0:31]", self.core)
        self.assertIn("history [0:7][0:31]", self.core)
        self.assertIn("active_event_id", self.core)
        self.assertIn("active_config_version", self.core)
        self.assertIn("32'h31414D44", self.core)
        self.assertIn("stream_index == 11", self.core)
        self.assertIn("drop_count_o <= drop_count_o + 1'b1", self.core)
        self.assertIn("power_i_pipe", self.core)
        self.assertIn("power_q_pipe", self.core)
        self.assertIn("power_sum_pipe", self.core)
        self.assertIn("detector_i_pipe", self.core)
        self.assertIn("detector_q_pipe", self.core)
        self.assertIn("power_i_mult", self.core)
        self.assertIn("power_q_mult", self.core)

    def test_control_implements_identity_safety_and_shadow_commit_guards(self) -> None:
        self.assertIn("32'h43414C31", self.control)
        self.assertIn("32'h00010000", self.control)
        self.assertIn("control_reg <= 32'h00000004", self.control)
        self.assertIn("if (!control_reg[0])", self.control)
        self.assertIn("config_version_o <= config_version_o + 1'b1", self.control)
        self.assertIn("address >= 12'h100", self.control)
        self.assertIn("address < 12'h200", self.control)


if __name__ == "__main__":
    unittest.main()
