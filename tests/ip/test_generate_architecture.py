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
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


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


if __name__ == "__main__":
    unittest.main()
