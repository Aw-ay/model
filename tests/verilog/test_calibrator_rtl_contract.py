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
        self.assertIn("control_reg <= `CAL_CONTROL_RESET", self.control)
        self.assertIn("if (!control_reg[0])", self.control)
        self.assertIn("config_version_o <= config_version_o + 1'b1", self.control)
        self.assertIn("address >= 12'h100", self.control)
        self.assertIn("address < 12'h200", self.control)

    def test_control_commits_a_compact_active_calibration_snapshot(self) -> None:
        """The RX domain must never observe live, partly-written shadow words."""
        for declaration in (
            "output wire [87:0] calibration_integer_delay_o",
            "output wire [159:0] calibration_fractional_delay_o",
            "output wire [191:0] calibration_gain_real_o",
            "output wire [191:0] calibration_gain_imag_o",
            "output wire [7:0] calibration_flags_o",
        ):
            self.assertIn(declaration, self.control)
        self.assertIn("channel_active", self.control)
        self.assertIn("channel_active[channel_index][word_index] <=", self.control)
        self.assertIn("channel_shadow[channel_index][word_index]", self.control)
        self.assertIn("ERROR_COMMIT_WHILE_RUNNING", self.control)
        self.assertIn("ERROR_INVALID_CALIBRATION", self.control)

    def test_all_abi_owned_reset_values_come_from_the_generated_header(self) -> None:
        for name in (
            "CONTROL", "DETECT_THRESHOLD", "NOISE_ALPHA_Q31",
            "RANGE_HOLD_SAMPLES", "RANGE_HIGH_WATER_Q16",
            "RANGE_LOW_WATER_Q16", "STREAM_ERRORS", "CONFIG_VERSION",
            "CHANNEL_INTEGER_DELAY", "CHANNEL_FRACTIONAL_DELAY_Q20",
            "CHANNEL_GAIN_REAL", "CHANNEL_GAIN_IMAG", "CHANNEL_CALIBRATION_FLAGS",
        ):
            self.assertIn(f"`CAL_{name}_RESET", self.control)


if __name__ == "__main__":
    unittest.main()
