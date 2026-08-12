import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.evidence import build_catalog_request, canonical_json_bytes
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
        self.assertIn(
            f"create_project -in_memory -part {{{config.device_part}}}", tcl
        )
        self.assertEqual(tcl.count("create_project -in_memory -part"), 1)
        self.assertIn("update_ip_catalog", tcl)
        self.assertNotIn("create_project -force", tcl)
        self.assertNotIn("create_bd_design", tcl)
        self.assertIn("llength $argv", tcl)
        self.assertIn("catalog_evidence.tsv", tcl)

    def test_discovery_validates_provenance_hashes_before_opening_evidence(self) -> None:
        tcl = emit_catalog_discovery_tcl(HardwareArchitectureConfig.load_default())

        self.assertIn("regexp {^[0-9a-f]{64}$}", tcl)
        for argument_name in (
            "architecture_config_sha256",
            "generated_tcl_sha256",
            "catalog_request_sha256",
        ):
            self.assertIn(argument_name, tcl)
        self.assertLess(
            tcl.index("regexp {^[0-9a-f]{64}$}"),
            tcl.index("set catalog_evidence [open $evidence_path {w}]"),
        )
        self.assertIn(
            "expected 64 lowercase hexadecimal characters",
            tcl,
        )

    def test_realization_creates_only_materialized_instances(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        tcl = emit_architecture_realization_tcl(config)

        self.assertIn(
            f"create_project -in_memory -part {{{config.device_part}}}", tcl
        )
        self.assertNotIn("xczu27dr-fsve1156-2-i", tcl.replace(config.device_part, ""))
        self.assertIn("create_bd_cell", tcl)
        self.assertIn("{rfdc_0}", tcl)
        self.assertNotIn("monitor_fir_dec2_0", tcl)
        self.assertNotIn("axis_data_fifo", tcl)
        self.assertNotIn("validate_bd_design", tcl)

    def test_part_is_derived_from_cross_checked_config_and_changes_provenance(self) -> None:
        default_config = HardwareArchitectureConfig.load_default()
        alternate_part = "xczu28dr-ffvg1517-2-e"
        payload = json.loads(
            Path(__file__).resolve().parents[2]
            .joinpath("config/ip_architecture.json")
            .read_text(encoding="utf-8")
        )
        payload["device_part"] = alternate_part
        alternate_model_config = ModelConfig.from_mapping(
            {
                **json.loads(
                    Path(__file__).resolve().parents[2]
                    .joinpath("config/default.json")
                    .read_text(encoding="utf-8")
                ),
                "device_part": alternate_part,
            }
        )
        with patch(
            "rfsoc_pulse_model.ip.types.ModelConfig.load_default",
            return_value=alternate_model_config,
        ):
            alternate_config = HardwareArchitectureConfig.from_mapping(payload)

        default_discovery = emit_catalog_discovery_tcl(default_config).encode("utf-8")
        alternate_discovery = emit_catalog_discovery_tcl(alternate_config).encode("utf-8")
        self.assertNotEqual(default_discovery, alternate_discovery)
        self.assertIn(alternate_part.encode("utf-8"), alternate_discovery)
        default_request = canonical_json_bytes(
            build_catalog_request(
                default_config,
                hashlib.sha256(b'default architecture bytes').hexdigest(),
                hashlib.sha256(default_discovery).hexdigest(),
            )
        )
        alternate_request = canonical_json_bytes(
            build_catalog_request(
                alternate_config,
                hashlib.sha256(b'alternate architecture bytes').hexdigest(),
                hashlib.sha256(alternate_discovery).hexdigest(),
            )
        )
        self.assertNotEqual(default_request, alternate_request)
        self.assertNotIn("device_part", json.loads(default_request))

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
