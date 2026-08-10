import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.catalog import (
    parse_resolved_ip_vlnv,
    validate_resolved_catalog,
)
from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.types import (
    HardwareArchitectureConfig,
    RFDC_2_6_VLNV,
)


VALID_CATALOG_TSV = """rfdc\txilinx.com:ip:usp_rf_data_converter:2.6
axis_register_slice\txilinx.com:ip:axis_register_slice:1.1
axis_data_fifo\txilinx.com:ip:axis_data_fifo:2.0
axis_clock_converter\txilinx.com:ip:axis_clock_converter:1.1
axis_dwidth_converter\txilinx.com:ip:axis_dwidth_converter:1.1
axis_combiner\txilinx.com:ip:axis_combiner:1.1
axis_broadcaster\txilinx.com:ip:axis_broadcaster:1.1
axis_switch\txilinx.com:ip:axis_switch:1.1
fir_compiler\txilinx.com:ip:fir_compiler:7.2
"""


class ResolvedIpCatalogTest(unittest.TestCase):
    def test_catalog_parser_requires_exact_rfdc_and_all_initial_ip(self) -> None:
        resolved = parse_resolved_ip_vlnv(VALID_CATALOG_TSV)

        self.assertEqual(resolved["rfdc"], RFDC_2_6_VLNV)
        validate_resolved_catalog(
            HardwareArchitectureConfig.load_default(), resolved
        )

    def test_catalog_validation_rejects_wrong_rfdc_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "RF Data Converter 2.6"):
            validate_resolved_catalog(
                HardwareArchitectureConfig.load_default(),
                {"rfdc": "xilinx.com:ip:usp_rf_data_converter:2.7"},
            )

    def test_catalog_parser_rejects_duplicate_logical_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_resolved_ip_vlnv(
                "rfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
                "rfdc\txilinx.com:ip:usp_rf_data_converter:2.7\n"
            )

    def test_catalog_validation_rejects_missing_or_wrong_ip_family(self) -> None:
        resolved = parse_resolved_ip_vlnv(VALID_CATALOG_TSV)
        del resolved["axis_data_fifo"]
        with self.assertRaisesRegex(ValueError, "missing.*axis_data_fifo"):
            validate_resolved_catalog(
                HardwareArchitectureConfig.load_default(), resolved
            )

        resolved = parse_resolved_ip_vlnv(VALID_CATALOG_TSV)
        resolved["fir_compiler"] = "xilinx.com:ip:dds_compiler:6.0"
        with self.assertRaisesRegex(ValueError, "fir_compiler.*does not match"):
            validate_resolved_catalog(
                HardwareArchitectureConfig.load_default(), resolved
            )

    def test_generation_publishes_only_validated_catalog_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unverified = generate_ip_architecture(root)
            self.assertEqual(
                unverified["catalog_resolution_status"], "unverified"
            )
            self.assertNotIn("resolved_ip_vlnv_sha256", unverified)

            tsv_path = root / "metadata/resolved_ip_vlnv.tsv"
            tsv_path.write_text(VALID_CATALOG_TSV, encoding="utf-8")
            resolved = generate_ip_architecture(root)
            json_bytes = (root / "metadata/resolved_ip_vlnv.json").read_bytes()

            self.assertEqual(
                resolved["catalog_resolution_status"],
                "vivado_2025_2_resolved",
            )
            self.assertEqual(
                resolved["resolved_ip_vlnv_sha256"],
                hashlib.sha256(json_bytes).hexdigest(),
            )
            self.assertEqual(
                json.loads(json_bytes),
                parse_resolved_ip_vlnv(VALID_CATALOG_TSV),
            )


if __name__ == "__main__":
    unittest.main()
