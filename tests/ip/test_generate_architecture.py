import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.evidence import (
    build_catalog_request,
    canonical_json_bytes,
)
from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.lock import GenerationMode
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

    def test_development_mode_reports_missing_production_lock_truthfully(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            architecture = generate_ip_architecture(
                Path(temporary), GenerationMode.DEVELOPMENT
            )

        self.assertFalse(architecture["production_lock_valid"])

    def test_production_mode_fails_closed_without_a_lock_before_output_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "not-written"
            with self.assertRaisesRegex(ValueError, "production lock.*missing"):
                generate_ip_architecture(root, GenerationMode.PRODUCTION)
            self.assertFalse(root.exists())

    def test_top_level_cli_accepts_explicit_ip_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                generate_main(
                    ["--output", temporary, "--ip-mode", "development"]
                ),
                0,
            )
            metadata = Path(temporary) / "metadata/ip_architecture.json"
            self.assertFalse(json.loads(metadata.read_text(encoding="utf-8"))["production_lock_valid"])


if __name__ == "__main__":
    unittest.main()
