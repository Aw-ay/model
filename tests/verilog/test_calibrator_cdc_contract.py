from pathlib import Path
import unittest


class CalibratorCdcContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        path = cls.root / "rtl/calibrator_control_cdc.sv"
        cls.source = path.read_text(encoding="utf-8") if path.exists() else ""

    def test_uses_handshakes_for_both_multibit_clock_crossings(self) -> None:
        self.assertGreaterEqual(self.source.count("xpm_cdc_handshake"), 2)
        self.assertIn(".WIDTH(67)", self.source)
        self.assertIn(".WIDTH(160)", self.source)
        self.assertIn(".DEST_EXT_HSK(0)", self.source)

    def test_control_destination_resets_to_safe_values(self) -> None:
        self.assertIn("acquisition_enable_rx_o <= 1'b0", self.source)
        self.assertIn("dac_loopback_enable_rx_o <= 1'b0", self.source)
        self.assertIn("dac_mute_rx_o <= 1'b0", self.source)
        self.assertIn("detect_threshold_rx_o <= 32'd0", self.source)
        self.assertIn("config_version_rx_o <= 32'd0", self.source)


if __name__ == "__main__":
    unittest.main()
