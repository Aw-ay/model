import hashlib
import json
from pathlib import Path
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.platform import PsPlatformConfig


class PsPlatformConfigTest(unittest.TestCase):
    @staticmethod
    def root_bytes() -> bytes:
        root = Path(__file__).resolve().parents[2]
        return (root / "config/ps_platform.json").read_bytes()

    @classmethod
    def root_payload(cls) -> dict[str, object]:
        return json.loads(cls.root_bytes())

    def test_default_is_the_frozen_zu27dr_control_platform(self) -> None:
        config = PsPlatformConfig.load_default()

        self.assertEqual(config.platform_schema_version, 1)
        self.assertEqual(config.device_part, ModelConfig.load_default().device_part)
        self.assertEqual(config.device_part, "xczu27dr-fsve1156-2-i")
        self.assertEqual(config.ps_vlnv, "xilinx.com:ip:zynq_ultra_ps_e:3.5")
        self.assertEqual(config.control_clock_hz, 100_000_000)
        self.assertEqual(config.vivado_version, "2025.2")
        self.assertEqual(
            config.source_bd_path,
            "save_v2.1/XCZU27_MEM_TEST_TOP/XCZU27_TOP.srcs/sources_1/bd/design_1/design_1.bd",
        )
        self.assertEqual(config.source_bd_base, "external_workspace_root")
        self.assertRegex(config.source_bd_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(config.gem3_board_io.status, "pending")
        self.assertTrue(config.gem3_board_io.blocking_reason)
        self.assertFalse(config.gem3_realization_allowed)
        with self.assertRaisesRegex(ValueError, "GEM3 board I/O is pending"):
            config.require_gem3_board_io()
        self.assertTrue(config.properties)

    def test_root_schema_is_exact_and_properties_are_the_reviewed_allowlist(self) -> None:
        payload = self.root_payload()
        self.assertEqual(
            set(payload),
            {
                "platform_schema_version",
                "device_part",
                "ps_vlnv",
                "control_clock_hz",
                "source_bd_base",
                "source_bd_path",
                "source_bd_sha256",
                "vivado_version",
                "gem3_board_io",
                "properties",
            },
        )
        self.assertEqual(
            set(payload["properties"]),
            PsPlatformConfig.REVIEWED_PROPERTY_KEYS,
        )

    def test_package_copy_is_byte_identical_to_root_authority(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            self.root_bytes(),
            (root / "src/rfsoc_pulse_model/config/ps_platform.json").read_bytes(),
        )

    def test_properties_are_an_immutable_snapshot(self) -> None:
        config = PsPlatformConfig.load_default()
        with self.assertRaises(TypeError):
            config.properties["CONFIG.PSU__UNKNOWN"] = "1"  # type: ignore[index]

    def test_from_mapping_rejects_unknown_or_missing_schema_keys(self) -> None:
        unknown = self.root_payload()
        unknown["unexpected"] = "value"
        with self.assertRaisesRegex(ValueError, "platform.*keys"):
            PsPlatformConfig.from_mapping(unknown)

        missing = self.root_payload()
        del missing["source_bd_sha256"]
        with self.assertRaisesRegex(ValueError, "platform.*keys"):
            PsPlatformConfig.from_mapping(missing)

    def test_from_mapping_rejects_wrong_scalar_types_and_model_mismatch(self) -> None:
        wrong_clock = self.root_payload()
        wrong_clock["control_clock_hz"] = True
        with self.assertRaisesRegex(ValueError, "control_clock_hz.*integer"):
            PsPlatformConfig.from_mapping(wrong_clock)

        mismatch = self.root_payload()
        mismatch["device_part"] = "xczu28dr-ffvg1517-2-e"
        with self.assertRaisesRegex(ValueError, "device_part.*ModelConfig"):
            PsPlatformConfig.from_mapping(mismatch)

    def test_from_mapping_rejects_non_allowlisted_property_and_non_string_value(self) -> None:
        unknown = self.root_payload()
        unknown["properties"] = dict(unknown["properties"])
        unknown["properties"]["CONFIG.PSU__UNKNOWN"] = "1"
        with self.assertRaisesRegex(ValueError, "unknown PS property"):
            PsPlatformConfig.from_mapping(unknown)

        non_string = self.root_payload()
        non_string["properties"] = dict(non_string["properties"])
        property_name = next(iter(non_string["properties"]))
        non_string["properties"][property_name] = 1
        with self.assertRaisesRegex(ValueError, "PS property"):
            PsPlatformConfig.from_mapping(non_string)

    def test_from_mapping_rejects_non_string_property_keys_without_type_error(self) -> None:
        invalid = self.root_payload()
        invalid["properties"] = dict(invalid["properties"])
        invalid["properties"][1] = "1"
        invalid["properties"]["CONFIG.PSU__UNKNOWN"] = "1"

        with self.assertRaisesRegex(ValueError, "PS property name must be a string"):
            PsPlatformConfig.from_mapping(invalid)

    def test_from_json_text_rejects_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            PsPlatformConfig.from_json_text('{"platform_schema_version": 1, "platform_schema_version": 1}')

    def test_source_provenance_is_a_portable_reference_and_frozen_hash(self) -> None:
        config = PsPlatformConfig.load_default()
        self.assertEqual(
            config.source_bd_sha256,
            "63dc103980f369d1ba7246652cd533382b9ab96bed9ccede4b2dd5536df8517a",
        )
        external_workspace_root = Path(__file__).resolve().parents[4]
        source_bd = config.resolve_source_bd(external_workspace_root)
        self.assertEqual(
            hashlib.sha256(source_bd.read_bytes()).hexdigest(), config.source_bd_sha256
        )

    def test_source_provenance_rejects_noncanonical_or_unsafe_locators(self) -> None:
        for bad_path in (
            "D:/AWAY/RFSOC/save_v2.1/design_1.bd",
            "../save_v2.1/design_1.bd",
            "save_v2.1\\design_1.bd",
            "save_v2.1//design_1.bd",
            "./save_v2.1/design_1.bd",
        ):
            with self.subTest(bad_path=bad_path):
                payload = self.root_payload()
                payload["source_bd_path"] = bad_path
                with self.assertRaisesRegex(ValueError, "source_bd_path"):
                    PsPlatformConfig.from_mapping(payload)

    def test_source_provenance_rejects_unknown_base(self) -> None:
        payload = self.root_payload()
        payload["source_bd_base"] = "workspace"
        with self.assertRaisesRegex(ValueError, "source_bd_base"):
            PsPlatformConfig.from_mapping(payload)

    def test_gem3_board_io_requires_a_pending_blocking_reason(self) -> None:
        payload = self.root_payload()
        payload["gem3_board_io"] = {"status": "pending", "blocking_reason": " "}
        with self.assertRaisesRegex(ValueError, "blocking_reason"):
            PsPlatformConfig.from_mapping(payload)


if __name__ == "__main__":
    unittest.main()
