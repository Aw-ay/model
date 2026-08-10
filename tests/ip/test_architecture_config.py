import dataclasses
import json
from pathlib import Path
import unittest

from rfsoc_pulse_model.ip.types import (
    HardwareArchitectureConfig,
    ImplementationKind,
)


class HardwareArchitectureConfigTest(unittest.TestCase):
    @staticmethod
    def root_payload() -> dict:
        root = Path(__file__).resolve().parents[2]
        return json.loads(
            (root / "config/ip_architecture.json").read_text(encoding="utf-8")
        )

    def test_default_locks_exact_rfdc_2_6_black_box(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        self.assertEqual(
            config.rfdc.ip.vlnv,
            "xilinx.com:ip:usp_rf_data_converter:2.6",
        )
        self.assertEqual(config.rfdc.ip.kind, ImplementationKind.AMD_IP)
        self.assertEqual(config.vivado_version, "2025.2")
        self.assertEqual(config.generation_mode, "vivado_ip_first")
        self.assertEqual(
            set(config.rfdc.owned_functions),
            {
                "adc",
                "dac",
                "ddc",
                "duc",
                "decimation",
                "interpolation",
                "mixer",
                "nco",
            },
        )

    def test_other_rfdc_version_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["rfdc"]["ip"]["vlnv"] = (
            "xilinx.com:ip:usp_rf_data_converter:2.7"
        )
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            HardwareArchitectureConfig.from_mapping(payload)

    def test_installed_and_root_config_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "config/ip_architecture.json").read_bytes(),
            (
                root
                / "src/rfsoc_pulse_model/config/ip_architecture.json"
            ).read_bytes(),
        )

    def test_dataclass_replace_cannot_bypass_rfdc_gate(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        bad_ip = dataclasses.replace(
            config.rfdc.ip,
            vlnv="xilinx.com:ip:usp_rf_data_converter:2.5",
        )
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            dataclasses.replace(config.rfdc, ip=bad_ip)


if __name__ == "__main__":
    unittest.main()
