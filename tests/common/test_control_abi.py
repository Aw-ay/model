import json
from pathlib import Path
import unittest

try:
    from rfsoc_pulse_model.common.control_abi import ControlAbi
except ImportError:  # RED until the single-source ABI exists.
    ControlAbi = None  # type: ignore[assignment,misc]


class ControlAbiTest(unittest.TestCase):
    @staticmethod
    def config_path() -> Path:
        return Path(__file__).resolve().parents[2] / "config/calibrator_registers.json"

    def test_default_map_has_required_controls_and_channel_shadows(self) -> None:
        self.assertIsNotNone(ControlAbi)
        assert ControlAbi is not None
        abi = ControlAbi.load_default()

        self.assertEqual(abi.base_address, 0xA0000000)
        self.assertEqual(abi.abi_version, 0x00010000)
        self.assertEqual(abi.register("PROJECT_ID").reset, 0x43414C31)
        self.assertEqual(abi.register("CONTROL").offset, 0x008)
        self.assertEqual(abi.register("COMMIT_CALIBRATION").access, "wo")
        self.assertEqual(abi.register("EVENT_COUNT_LO").offset, 0x01C)
        self.assertEqual(abi.register("DROP_COUNT_HI").offset, 0x028)
        self.assertEqual(abi.channel_base, 0x100)
        self.assertEqual(abi.channel_stride, 0x20)
        self.assertEqual(abi.channel_register(7, "GAIN_IMAG").offset, 0x1EC)
        self.assertEqual(abi.channel_register(7, "INTEGER_DELAY").maximum, 2047)
        abi.require_complete()

    def test_bad_alignment_overlap_and_missing_required_register_are_rejected(self) -> None:
        self.assertTrue(self.config_path().is_file())
        self.assertIsNotNone(ControlAbi)
        assert ControlAbi is not None
        payload = json.loads(self.config_path().read_text(encoding="utf-8"))

        payload["registers"][0]["offset"] = 2
        with self.assertRaisesRegex(ValueError, "32-bit aligned"):
            ControlAbi.from_mapping(payload)

        payload = json.loads(self.config_path().read_text(encoding="utf-8"))
        payload["registers"][1]["offset"] = payload["registers"][0]["offset"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            ControlAbi.from_mapping(payload)

        payload = json.loads(self.config_path().read_text(encoding="utf-8"))
        payload["registers"] = [r for r in payload["registers"] if r["name"] != "MTS_STATUS"]
        with self.assertRaisesRegex(ValueError, "required register"):
            ControlAbi.from_mapping(payload)

    def test_generators_share_the_same_offsets(self) -> None:
        self.assertIsNotNone(ControlAbi)
        assert ControlAbi is not None
        abi = ControlAbi.load_default()

        c_header = abi.emit_c_header()
        verilog = abi.emit_verilog_header()
        python = abi.emit_python_constants()
        device_tree = abi.emit_device_tree_binding()

        for artifact in (c_header, verilog, python):
            self.assertIn("CONTROL", artifact)
            self.assertIn("00000008", artifact)
            self.assertIn("COMMIT_CALIBRATION", artifact)
        self.assertIn("reg = <0x0 0xa0000000 0x0 0x10000>;", device_tree)

    def test_root_and_package_maps_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            self.config_path().read_bytes(),
            (root / "src/rfsoc_pulse_model/config/calibrator_registers.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
