import copy
import json
from pathlib import Path
import unittest

try:
    from rfsoc_pulse_model.ip.calibrator_platform import CalibratorPlatformConfig
except ImportError:  # RED: the production authority does not exist yet.
    CalibratorPlatformConfig = None  # type: ignore[assignment,misc]


class CalibratorPlatformConfigTest(unittest.TestCase):
    @staticmethod
    def root_path() -> Path:
        return Path(__file__).resolve().parents[2] / "config/calibrator_platform.json"

    def test_default_authority_is_deployable_on_the_v21_board(self) -> None:
        self.assertIsNotNone(CalibratorPlatformConfig)
        assert CalibratorPlatformConfig is not None

        config = CalibratorPlatformConfig.load_default()

        self.assertEqual(config.device_part, "xczu27dr-fsve1156-2-i")
        self.assertEqual(
            (config.vivado_version, config.vitis_version, config.petalinux_version),
            ("2025.2", "2025.2", "2025.2"),
        )
        self.assertEqual(config.gem3.phy_model, "RTL8211FD")
        self.assertEqual(config.gem3.phy_address, 7)
        self.assertEqual(config.gem3.interface, "rgmii-id")
        self.assertEqual(config.gem3.mio_range, (64, 77))
        self.assertEqual(config.gem3.reset_source, "PS_POR_B")
        self.assertEqual(config.emmc.mio_range, (13, 23))
        self.assertEqual(config.dma.stream_width_bits, 128)
        self.assertEqual(config.dma.ps_slave_port, "S_AXI_HP0_FPD")
        self.assertEqual(config.maximum_channel_alignment_samples, 2047)
        config.require_deployable()

    def test_authority_rejects_tool_version_drift_and_unsafe_phy_wiring(self) -> None:
        self.assertTrue(self.root_path().is_file())
        payload = json.loads(self.root_path().read_text(encoding="utf-8"))
        self.assertIsNotNone(CalibratorPlatformConfig)
        assert CalibratorPlatformConfig is not None

        wrong_version = copy.deepcopy(payload)
        wrong_version["vitis_version"] = "2025.1"
        with self.assertRaisesRegex(ValueError, "tool versions must all be 2025.2"):
            CalibratorPlatformConfig.from_mapping(wrong_version)

        wrong_phy = copy.deepcopy(payload)
        wrong_phy["gem3"]["mio_range"] = [63, 76]
        with self.assertRaisesRegex(ValueError, "GEM3 MIO range"):
            CalibratorPlatformConfig.from_mapping(wrong_phy)

        wrong_reset = copy.deepcopy(payload)
        wrong_reset["gem3"]["reset_source"] = "MIO24"
        with self.assertRaisesRegex(ValueError, "PS_POR_B"):
            CalibratorPlatformConfig.from_mapping(wrong_reset)

    def test_root_and_package_authorities_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            self.root_path().read_bytes(),
            (root / "src/rfsoc_pulse_model/config/calibrator_platform.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
