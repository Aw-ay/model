import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.tcl import (
    emit_architecture_realization_tcl,
    emit_catalog_discovery_tcl,
)
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


class IpArchitectureTclTest(unittest.TestCase):
    def test_discovery_queries_every_required_family_without_creating_cells(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        tcl = emit_catalog_discovery_tcl(config)

        for family in config.required_families():
            self.assertIn(f"{{{family.family_id}}}", tcl)
            self.assertIn(f"{{{family.catalog_pattern}}}", tcl)
        self.assertNotIn("create_bd_cell", tcl)
        self.assertNotIn("create_project", tcl)
        self.assertNotIn("create_bd_design", tcl)
        self.assertIn("llength $argv", tcl)
        self.assertIn("catalog_evidence.tsv", tcl)

    def test_realization_creates_only_materialized_instances(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        tcl = emit_architecture_realization_tcl(config)

        self.assertIn("create_bd_cell", tcl)
        self.assertIn("{rfdc_0}", tcl)
        self.assertNotIn("monitor_fir_dec2_0", tcl)
        self.assertNotIn("axis_data_fifo", tcl)
        self.assertNotIn("validate_bd_design", tcl)

    def test_request_hash_order_and_tcl_provenance_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            architecture = generate_ip_architecture(root)
            discovery = (root / "vivado/discover_ip_catalog.tcl").read_bytes()
            realization = (
                root / "vivado/realize_ip_architecture.tcl"
            ).read_bytes()
            request_bytes = (root / "metadata/catalog_request.json").read_bytes()
            request = json.loads(request_bytes)

            self.assertEqual(
                request["architecture_config_sha256"],
                architecture["source_config_sha256"],
            )
            self.assertEqual(
                request["generated_tcl_sha256"],
                hashlib.sha256(discovery).hexdigest(),
            )
            self.assertEqual(
                architecture["realization_tcl_sha256"],
                hashlib.sha256(realization).hexdigest(),
            )
            self.assertEqual(
                architecture["catalog_request_sha256"],
                hashlib.sha256(request_bytes).hexdigest(),
            )
            self.assertNotIn(
                request["generated_tcl_sha256"], discovery.decode("utf-8")
            )


if __name__ == "__main__":
    unittest.main()
