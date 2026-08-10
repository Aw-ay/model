import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.generate import generate_ip_architecture


class GenerateIpArchitectureTest(unittest.TestCase):
    def test_metadata_records_external_ip_and_legacy_rtl_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            architecture = generate_ip_architecture(root)
            on_disk = json.loads(
                (root / "metadata/ip_architecture.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(on_disk, architecture)
            self.assertEqual(
                architecture["rfdc"]["vlnv"],
                "xilinx.com:ip:usp_rf_data_converter:2.6",
            )
            self.assertEqual(
                architecture["topology_status"], "unconnected_skeleton"
            )
            self.assertFalse(architecture["integration_accepted"])
            blocks = {
                block["logical_name"]: block for block in architecture["blocks"]
            }
            self.assertFalse(blocks["rx_group_ingress_2spc"]["production"])
            self.assertEqual(
                blocks["tx_iq_axis_boundary_2spc"]["kind"],
                "legacy_non_production",
            )

    def test_metadata_hashes_the_installed_architecture_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            architecture = generate_ip_architecture(Path(temporary))
            project_root = Path(__file__).resolve().parents[2]
            expected = hashlib.sha256(
                (
                    project_root
                    / "src/rfsoc_pulse_model/config/ip_architecture.json"
                ).read_bytes()
            ).hexdigest()

            self.assertEqual(architecture["source_config_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
