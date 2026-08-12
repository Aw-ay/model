import hashlib
from importlib import resources
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.evidence import (
    build_catalog_request,
    canonical_json_bytes,
)
from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.generate import _validate_packaged_lock
from rfsoc_pulse_model.ip.lock import GenerationMode
from rfsoc_pulse_model.ip.tcl import emit_catalog_discovery_tcl
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig
from rfsoc_pulse_model.generate import main as generate_main


class GenerateIpArchitectureTest(unittest.TestCase):
    def test_canonical_request_has_sorted_utf8_json_and_one_newline(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        request = build_catalog_request(config, "a" * 64, "b" * 64)
        payload = canonical_json_bytes(request)

        self.assertTrue(payload.endswith(b"\n"))
        self.assertEqual(payload, json.dumps(
            request, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8") + b"\n")
        self.assertEqual(json.loads(payload), request)

    def test_generated_artifacts_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = generate_ip_architecture(root)
            first_bytes = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            second = generate_ip_architecture(root)
            second_bytes = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(
                first["catalog_request_sha256"],
                hashlib.sha256(first_bytes[Path("metadata/catalog_request.json")]).hexdigest(),
            )

    def test_development_mode_reports_missing_explicit_production_lock_truthfully(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = HardwareArchitectureConfig.load_default()
            config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
                "ip_architecture.json"
            ).read_bytes()
            discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
            request_bytes = canonical_json_bytes(
                build_catalog_request(
                    config,
                    hashlib.sha256(config_bytes).hexdigest(),
                    hashlib.sha256(discovery_bytes).hexdigest(),
                )
            )
            self.assertFalse(
                _validate_packaged_lock(
                    GenerationMode.DEVELOPMENT,
                    config,
                    request_bytes,
                    discovery_bytes,
                    lock_resource=Path(temporary) / "missing-ip_lock.json",
                )
            )

    def test_production_mode_fails_closed_without_a_lock_before_output_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = HardwareArchitectureConfig.load_default()
            config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
                "ip_architecture.json"
            ).read_bytes()
            discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
            request_bytes = canonical_json_bytes(
                build_catalog_request(
                    config,
                    hashlib.sha256(config_bytes).hexdigest(),
                    hashlib.sha256(discovery_bytes).hexdigest(),
                )
            )
            with self.assertRaisesRegex(ValueError, "production lock.*missing"):
                _validate_packaged_lock(
                    GenerationMode.PRODUCTION,
                    config,
                    request_bytes,
                    discovery_bytes,
                    lock_resource=Path(temporary) / "missing-ip_lock.json",
                )

    def test_top_level_cli_accepts_explicit_ip_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                generate_main(
                    ["--output", temporary, "--ip-mode", "development"]
                ),
                0,
            )
            metadata = Path(temporary) / "metadata/ip_architecture.json"
            self.assertTrue(json.loads(metadata.read_text(encoding="utf-8"))["production_lock_valid"])

    def test_packaged_lock_decoder_rejects_duplicate_family_keys(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
            "ip_architecture.json"
        ).read_bytes()
        discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
        request_bytes = canonical_json_bytes(
            build_catalog_request(
                config,
                hashlib.sha256(config_bytes).hexdigest(),
                hashlib.sha256(discovery_bytes).hexdigest(),
            )
        )
        payload = json.loads(
            canonical_json_bytes({
                "lock_schema_version": 1,
                "architecture_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
                "generated_tcl_sha256": hashlib.sha256(discovery_bytes).hexdigest(),
                "catalog_request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                "vivado_version": config.vivado_version,
                "families": {
                    family.family_id: family.vlnv or family.catalog_pattern[:-1] + "1.0"
                    for family in config.required_families()
                },
            }).decode("utf-8")
        )
        families = json.dumps(payload["families"], sort_keys=True)
        duplicate_families = families.replace(
            '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0",',
            '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0", '
            '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0",',
        )
        raw = json.dumps({**payload, "families": None}, sort_keys=True).replace(
            '"families": null', f'"families": {duplicate_families}'
        )
        with tempfile.TemporaryDirectory() as temporary:
            resource = Path(temporary) / "ip_lock.json"
            resource.write_text(raw, encoding="utf-8")
            self.assertFalse(
                _validate_packaged_lock(
                    GenerationMode.DEVELOPMENT,
                    config,
                    request_bytes,
                    discovery_bytes,
                    lock_resource=resource,
                )
            )
            with self.assertRaisesRegex(ValueError, "production lock is invalid"):
                _validate_packaged_lock(
                    GenerationMode.PRODUCTION,
                    config,
                    request_bytes,
                    discovery_bytes,
                    lock_resource=resource,
                )


if __name__ == "__main__":
    unittest.main()
