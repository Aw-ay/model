import json
from pathlib import Path
import tempfile
import unittest
import zipfile

try:
    from rfsoc_pulse_model.ip.calibrator_build import (
        finalize_xsa_with_bitstream,
        generate_calibrator_sources,
    )
except ImportError:  # RED until the reproducible deployment generator exists.
    generate_calibrator_sources = None  # type: ignore[assignment]
    finalize_xsa_with_bitstream = None  # type: ignore[assignment]


class CalibratorBuildGeneratorTest(unittest.TestCase):
    def test_generation_writes_tcl_all_abi_consumers_and_hash_manifest(self) -> None:
        self.assertIsNotNone(generate_calibrator_sources)
        assert generate_calibrator_sources is not None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_calibrator_sources(root)

            required = {
                "build_calibrator.tcl",
                "calibrator_registers.h",
                "calibrator_registers.vh",
                "calibrator_registers.py",
                "calibrator.dtsi",
            }
            self.assertEqual(set(manifest["artifacts"]), required)
            self.assertEqual(manifest["vivado_version"], "2025.2")
            for filename in required:
                self.assertTrue((root / filename).is_file())
                self.assertEqual(len(manifest["artifacts"][filename]), 64)
            on_disk = json.loads((root / "generation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, manifest)

    def test_finalizer_adds_and_verifies_bitstream_metadata(self) -> None:
        self.assertIsNotNone(finalize_xsa_with_bitstream)
        assert finalize_xsa_with_bitstream is not None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "calibrator_no_bit.xsa"
            bit = root / "calibrator.bit"
            output = root / "calibrator.xsa"
            bit.write_bytes(b"known-bitstream")
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("xsa.json", json.dumps({"files": []}))
                archive.writestr(
                    "xsa.xml",
                    '<?xml version="1.0"?><Root><DSA><Files /></DSA></Root>',
                )
                archive.writestr("calibrator.hwh", b"hardware")

            result = finalize_xsa_with_bitstream(source, bit, output)

            self.assertEqual(result["bitstream_size"], len(b"known-bitstream"))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("calibrator.bit"), b"known-bitstream")
                metadata = json.loads(archive.read("xsa.json"))
                self.assertIn(
                    {"name": "calibrator.bit", "type": "BITSTREAM"},
                    metadata["files"],
                )
                self.assertIn(b'Type="BITSTREAM"', archive.read("xsa.xml"))


if __name__ == "__main__":
    unittest.main()
