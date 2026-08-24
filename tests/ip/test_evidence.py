import dataclasses
import hashlib
from importlib import resources
import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.evidence import (
    CatalogEvidence,
    CatalogResolutionStatus,
    build_catalog_provenance,
    build_catalog_request,
    canonical_json_bytes,
    parse_catalog_evidence,
    validate_catalog_provenance,
    validate_catalog_evidence,
)
from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.tcl import emit_catalog_discovery_tcl
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


def make_evidence_fixture() -> tuple[HardwareArchitectureConfig, bytes, bytes, CatalogEvidence]:
    config = HardwareArchitectureConfig.load_default()
    config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    discovery_tcl_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_payload = build_catalog_request(
        config,
        architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        generated_tcl_sha256=hashlib.sha256(discovery_tcl_bytes).hexdigest(),
    )
    request_bytes = canonical_json_bytes(request_payload)
    resolved = {}
    for family in config.required_families():
        resolved[family.family_id] = (
            family.vlnv
            if family.vlnv is not None
            else family.catalog_pattern[:-1] + "1.0"
        )
    evidence = CatalogEvidence(
        evidence_schema_version=1,
        architecture_config_sha256=request_payload["architecture_config_sha256"],
        generated_tcl_sha256=request_payload["generated_tcl_sha256"],
        catalog_request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        vivado_version="2025.2",
        run_id="1234-1730000000000",
        resolved_vlnv=tuple(sorted(resolved.items())),
    )
    return config, request_bytes, discovery_tcl_bytes, evidence


def evidence_tsv(evidence: CatalogEvidence) -> str:
    rows = [
        ("meta", "evidence_schema_version", str(evidence.evidence_schema_version)),
        ("meta", "architecture_config_sha256", evidence.architecture_config_sha256),
        ("meta", "generated_tcl_sha256", evidence.generated_tcl_sha256),
        ("meta", "catalog_request_sha256", evidence.catalog_request_sha256),
        ("meta", "vivado_version", evidence.vivado_version),
        ("meta", "run_id", evidence.run_id),
    ]
    rows.extend(("ip", family_id, vlnv) for family_id, vlnv in evidence.resolved_vlnv)
    return "".join(f"{kind}\t{key}\t{value}\n" for kind, key, value in rows)


class CatalogEvidenceTest(unittest.TestCase):
    def test_current_complete_evidence_is_resolved(self) -> None:
        config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
        result = validate_catalog_evidence(
            config,
            request_bytes,
            discovery_tcl_bytes,
            evidence,
        )
        self.assertEqual(result.status, CatalogResolutionStatus.ALL_REQUIRED_IP_RESOLVED)
        self.assertEqual(
            set(result.resolved_vlnv),
            {family.family_id for family in config.required_families()},
        )

    def test_old_hashes_are_stale_not_resolved(self) -> None:
        config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
        evidence = dataclasses.replace(evidence, generated_tcl_sha256="0" * 64)
        result = validate_catalog_evidence(
            config,
            request_bytes,
            discovery_tcl_bytes,
            evidence,
        )
        self.assertEqual(result.status, CatalogResolutionStatus.STALE_EVIDENCE)
        self.assertFalse(result.catalog_resolution_complete)

    def test_schema1_catalog_is_environment_bound_by_separate_provenance(self) -> None:
        config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
        evidence_bytes = evidence_tsv(evidence).encode("utf-8")
        manifest_sha256 = "a" * 64
        result = validate_catalog_evidence(
            config,
            request_bytes,
            discovery_tcl_bytes,
            evidence,
            manifest_sha256,
        )
        self.assertTrue(result.catalog_resolution_complete)

        provenance = build_catalog_provenance(
            evidence_bytes,
            request_bytes,
            discovery_tcl_bytes,
            evidence,
            manifest_sha256,
        )
        raw_provenance = canonical_json_bytes(provenance)
        validate_catalog_provenance(
            raw_provenance,
            evidence_bytes,
            request_bytes,
            discovery_tcl_bytes,
            evidence,
            manifest_sha256,
        )

    def test_missing_extra_duplicate_and_wrong_identity_fail(self) -> None:
        config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
        resolved = dict(evidence.resolved_vlnv)

        missing = dict(resolved)
        missing.pop("axi_dma")
        with self.assertRaisesRegex(ValueError, "family set"):
            validate_catalog_evidence(
                config, request_bytes, discovery_tcl_bytes,
                dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(missing.items()))),
            )

        extra = dict(resolved)
        extra["not_required"] = "xilinx.com:ip:xlconstant:1.1"
        with self.assertRaisesRegex(ValueError, "family set"):
            validate_catalog_evidence(
                config, request_bytes, discovery_tcl_bytes,
                dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(extra.items()))),
            )

        wrong = dict(resolved)
        wrong["fir_compiler"] = "xilinx.com:ip:dds_compiler:6.0"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_catalog_evidence(
                config, request_bytes, discovery_tcl_bytes,
                dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(wrong.items()))),
            )

        duplicate_ip = (
            evidence_tsv(evidence)
            + "ip\trfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_catalog_evidence(duplicate_ip)

    def test_parser_enforces_exact_wire_grammar(self) -> None:
        _, _, _, evidence = make_evidence_fixture()
        valid = evidence_tsv(evidence)
        self.assertEqual(parse_catalog_evidence(valid).run_id, "1234-1730000000000")

        with self.assertRaisesRegex(ValueError, "run_id"):
            parse_catalog_evidence(
                valid.replace("1234-1730000000000", "unit-test-1")
            )

        first_ip = "ip\trfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
        with self.assertRaisesRegex(ValueError, "ip row before metadata"):
            parse_catalog_evidence(first_ip + valid)

        rows = valid.splitlines(keepends=True)
        reordered = "".join((rows[0], rows[2], rows[1], *rows[3:]))
        with self.assertRaisesRegex(ValueError, "metadata order"):
            parse_catalog_evidence(reordered)

        repeated = "".join((rows[0], rows[0], *rows[1:]))
        with self.assertRaisesRegex(ValueError, "metadata.*duplicate"):
            parse_catalog_evidence(repeated)

        for malformed_ending in (valid.removesuffix("\n"), valid + "\n"):
            with self.subTest(malformed_ending=repr(malformed_ending[-2:])):
                with self.assertRaisesRegex(ValueError, "single trailing newline"):
                    parse_catalog_evidence(malformed_ending)

    def test_generation_uses_current_evidence_and_removes_only_candidate_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, evidence = make_evidence_fixture()
            metadata = root / "metadata"
            metadata.mkdir(parents=True)
            (metadata / "catalog_evidence.tsv").write_text(
                evidence_tsv(evidence), encoding="utf-8"
            )
            unrelated = metadata / "keep.txt"
            unrelated.write_text("keep", encoding="utf-8")

            resolved = generate_ip_architecture(root)
            candidate = metadata / "ip_lock.candidate.json"
            self.assertEqual(resolved["catalog_resolution_status"], "all_required_ip_resolved")
            self.assertTrue(candidate.is_file())
            self.assertEqual(
                set(json.loads(candidate.read_text(encoding="utf-8"))["families"]),
                {family.family_id for family in HardwareArchitectureConfig.load_default().required_families()},
            )

            (metadata / "catalog_evidence.tsv").write_text(
                evidence_tsv(dataclasses.replace(evidence, generated_tcl_sha256="0" * 64)),
                encoding="utf-8",
            )
            stale = generate_ip_architecture(root)
            self.assertEqual(stale["catalog_resolution_status"], "stale_evidence")
            self.assertFalse(candidate.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_generation_rejects_noncanonical_evidence_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, evidence = make_evidence_fixture()
            metadata = root / "metadata"
            metadata.mkdir(parents=True)
            evidence_path = metadata / "catalog_evidence.tsv"
            candidate = metadata / "ip_lock.candidate.json"
            candidate.write_text("old candidate", encoding="utf-8")
            rows = evidence_tsv(evidence).splitlines(keepends=True)
            evidence_path.write_text(
                "".join((rows[0], rows[2], rows[1], *rows[3:])),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "metadata order"):
                generate_ip_architecture(root)
            self.assertFalse(candidate.exists())

    def test_generation_canonicalizes_windows_vivado_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, evidence = make_evidence_fixture()
            metadata = root / "metadata"
            metadata.mkdir(parents=True)
            evidence_path = metadata / "catalog_evidence.tsv"
            canonical = evidence_tsv(evidence).encode("utf-8")
            evidence_path.write_bytes(canonical.replace(b"\n", b"\r\n"))

            resolved = generate_ip_architecture(root)

            self.assertEqual(
                resolved["catalog_resolution_status"],
                "all_required_ip_resolved",
            )
            self.assertEqual(evidence_path.read_bytes(), canonical)

    def test_generation_ignores_legacy_schema_v1_tsv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "metadata"
            metadata.mkdir(parents=True)
            (metadata / "resolved_ip_vlnv.tsv").write_text(
                "rfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n", encoding="utf-8"
            )
            result = generate_ip_architecture(root)
            self.assertEqual(result["catalog_resolution_status"], "unverified")
            self.assertFalse((metadata / "ip_lock.candidate.json").exists())


if __name__ == "__main__":
    unittest.main()
