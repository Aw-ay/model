"""Pure canonical connected-RFDC-shell request and evidence contract tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from importlib import resources

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.connected import (
    ConnectedAuthorityBytes,
    ConnectedShellEvidence,
    RfdcProbeProvenance,
    build_connected_request,
    canonical_connected_json_bytes,
    parse_connected_request,
    parse_connected_evidence,
    summarize_connected_shell_evidence,
    validate_connected_evidence,
)
from rfsoc_pulse_model.ip.environment import EnvironmentManifest
from rfsoc_pulse_model.ip.lock import decode_production_lock_json
from rfsoc_pulse_model.ip.platform import PsPlatformConfig
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig
from rfsoc_pulse_model.ip.evidence import build_catalog_request, canonical_json_bytes


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authority_bytes(name: str) -> bytes:
    return resources.files("rfsoc_pulse_model.config").joinpath(name).read_bytes()


def authority_fixture() -> tuple[object, object, object]:
    model = ModelConfig.load_default()
    architecture = HardwareArchitectureConfig.load_default()
    platform = PsPlatformConfig.load_default()
    model_bytes = authority_bytes("default.json")
    architecture_bytes = authority_bytes("ip_architecture.json")
    platform_bytes = authority_bytes("ps_platform.json")
    discovery_bytes = b"catalog discovery contract\n"
    catalog_request_bytes = canonical_json_bytes(build_catalog_request(
        architecture, hashlib.sha256(architecture_bytes).hexdigest(),
        hashlib.sha256(discovery_bytes).hexdigest(),
    ))
    lock = dict(decode_production_lock_json(authority_bytes("ip_lock.json"), "fixture lock"))
    lock.update({
        "architecture_config_sha256": hashlib.sha256(architecture_bytes).hexdigest(),
        "generated_tcl_sha256": hashlib.sha256(discovery_bytes).hexdigest(),
        "catalog_request_sha256": hashlib.sha256(catalog_request_bytes).hexdigest(),
        "vivado_version": architecture.vivado_version,
    })
    lock_bytes = canonical_json_bytes(lock)
    return (
        (model, architecture, platform, lock),
        ConnectedAuthorityBytes(
            model_bytes, architecture_bytes, platform_bytes, lock_bytes,
            discovery_bytes, catalog_request_bytes,
        ),
        RfdcProbeProvenance("2025.2", sha("probe Tcl"), sha("probe output"), 42),
    )


def fixture() -> tuple[object, ConnectedShellEvidence, tuple[object, ...]]:
    (model, architecture, platform, lock), bytes_bundle, probe = authority_fixture()
    request = build_connected_request(
        model, architecture, platform, lock, probe, bytes_bundle,
    )
    evidence = ConnectedShellEvidence(
        evidence_schema_version=1,
        connected_request_sha256=sha(canonical_connected_json_bytes(request).decode("utf-8")),
        model_config_sha256=hashlib.sha256(bytes_bundle.model_config_bytes).hexdigest(),
        architecture_config_sha256=hashlib.sha256(bytes_bundle.architecture_config_bytes).hexdigest(),
        ps_platform_config_sha256=hashlib.sha256(bytes_bundle.ps_platform_config_bytes).hexdigest(),
        production_lock_sha256=hashlib.sha256(bytes_bundle.production_lock_bytes).hexdigest(),
        realization_tcl_sha256=sha("realize"), verification_tcl_sha256=sha("verify"),
        vivado_version="2025.2", device_part="xczu27dr-fsve1156-2-i",
        cells=request.cells, interfaces=request.interfaces,
        clocks=request.clocks, resets=request.resets,
        address_path=request.address_path, irq_path=request.irq_path,
        rfdc_semantics=request.rfdc_semantics, mts_groups=request.mts_groups,
        mts_configuration_verified=True, mts_runtime_verified=False,
        validate_bd_design_passed=True, synthesis_completed=True,
        cdc_safe=True, clock_safety_verified=True,
        report_hashes=(("cdc", sha("cdc")), ("clock_interaction", sha("clock")),
                       ("timing_summary", sha("timing")), ("utilization", sha("util"))),
    )
    return request, evidence, (model, architecture, platform, lock, probe, bytes_bundle)


class ConnectedShellContractTest(unittest.TestCase):
    def test_authority_bytes_are_explicit_bound_immutable_inputs(self) -> None:
        (model, architecture, platform, lock), bundle, probe = authority_fixture()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bundle.model_config_bytes = b"forged"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "model_config_bytes"):
            build_connected_request(
                model, architecture, platform, lock, probe,
                dataclasses.replace(bundle, model_config_bytes=b"{}\n"),
            )

    def test_rebound_forged_request_and_evidence_cannot_authorize_readiness(self) -> None:
        request, evidence, context = fixture()
        forged_cell = dataclasses.replace(
            request.cells[0], name="forged_rfdc", vlnv="xilinx.com:ip:not_rfdc:9.9"
        )
        cases = (
            ("cell", {"cells": (forged_cell, *request.cells[1:])}),
            ("interface", {"interfaces": tuple(
                dataclasses.replace(item, iq_component="Q") if item.name == "m00_axis" else item
                for item in request.interfaces)}),
            ("width", {"interfaces": tuple(
                dataclasses.replace(item, width_bits=64) if item.name == "m00_axis" else item
                for item in request.interfaces)}),
            ("clock", {"clocks": tuple(
                dataclasses.replace(item, frequency_hz=1) if item.domain == "rx" else item
                for item in request.clocks)}),
            ("reset", {"resets": tuple(
                dataclasses.replace(item, reset_net="forged_reset") if item.domain == "rx" else item
                for item in request.resets)}),
            ("address", {"address_path": ("forged",)}),
            ("irq", {"irq_path": ("forged",)}),
            ("mts", {"mts_groups": (dataclasses.replace(request.mts_groups[0], tiles=(9,)), request.mts_groups[1])}),
            ("nco", {"rfdc_semantics": dataclasses.replace(request.rfdc_semantics, dac_nco_frequency_hz=1)}),
        )
        for name, changes in cases:
            with self.subTest(name=name):
                forged_request = dataclasses.replace(request, **changes)
                forged_evidence = dataclasses.replace(
                    evidence,
                    connected_request_sha256=hashlib.sha256(
                        canonical_connected_json_bytes(forged_request)
                    ).hexdigest(),
                    cells=forged_request.cells, interfaces=forged_request.interfaces,
                    clocks=forged_request.clocks, resets=forged_request.resets,
                    address_path=forged_request.address_path, irq_path=forged_request.irq_path,
                    rfdc_semantics=forged_request.rfdc_semantics,
                    mts_groups=forged_request.mts_groups,
                )
                result = validate_connected_evidence(forged_request, forged_evidence, *context)
                self.assertFalse(result.rfdc_shell_structural_ready)
                self.assertIn("request_contract_mismatch", result.blocking_reasons)

    def test_invalid_production_lock_cannot_build_rebound_ready_request(self) -> None:
        (model, architecture, platform, lock), bundle, probe = authority_fixture()
        lock_faults = {
            "empty": {},
            "missing_family": {**lock, "families": {k: v for k, v in lock["families"].items() if k != "rfdc"}},
            "wrong_family": {**lock, "families": {**lock["families"], "rfdc": "xilinx.com:ip:usp_rf_data_converter:2.5"}},
            "wrong_architecture_hash": {**lock, "architecture_config_sha256": "0" * 64},
            "wrong_discovery_hash": {**lock, "generated_tcl_sha256": "0" * 64},
            "wrong_catalog_request_hash": {**lock, "catalog_request_sha256": "0" * 64},
            "wrong_vivado": {**lock, "vivado_version": "2024.1"},
        }
        for name, broken_lock in lock_faults.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                broken_bytes = canonical_json_bytes(broken_lock)
                build_connected_request(
                    model, architecture, platform, broken_lock, probe,
                    dataclasses.replace(bundle, production_lock_bytes=broken_bytes),
                )

    def test_connected_json_wire_bytes_are_compact_sorted_utf8_and_one_lf(self) -> None:
        request, _, _ = fixture()
        encoded = canonical_connected_json_bytes(request)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertFalse(encoded.endswith(b"\n\n"))
        self.assertNotIn(b"\n ", encoded)
        self.assertEqual(
            encoded,
            json.dumps(json.loads(encoded), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8") + b"\n",
        )

    def test_environment_bound_request_round_trips_as_schema_v2(self) -> None:
        (model, architecture, platform, lock), bundle, probe = authority_fixture()
        manifest = EnvironmentManifest(
            host="new_machine",
            os="Windows 11",
            python="3.12.9",
            vivado="2025.2",
            vivado_build="6299465",
            repo_root="E:/new/absolute/path",
            git_commit="0" * 40,
            timezone="Asia/Shanghai",
            git_status_clean=True,
            vivado_executable="C:/Xilinx/2025.2/Vivado/bin/vivado.bat",
        )
        bound_probe = dataclasses.replace(
            probe, environment_manifest_sha256=manifest.sha256
        )
        bound_bundle = dataclasses.replace(
            bundle, environment_manifest_bytes=manifest.bytes()
        )

        request = build_connected_request(
            model, architecture, platform, lock, bound_probe, bound_bundle
        )
        encoded = canonical_connected_json_bytes(request)
        parsed = parse_connected_request(encoded)

        self.assertEqual(request.request_schema_version, 2)
        self.assertEqual(request.environment_manifest_sha256, manifest.sha256)
        self.assertEqual(parsed, request)

    def test_true_ready_fixture_has_exact_24_interfaces_and_never_sets_production_ready(self) -> None:
        request, evidence, context = fixture()
        self.assertEqual(len(request.cells), 8)
        self.assertEqual(len(request.interfaces), 24)
        self.assertEqual(len([item for item in request.interfaces if item.direction == "master"]), 16)
        self.assertEqual(len([item for item in request.interfaces if item.direction == "slave"]), 8)
        result = validate_connected_evidence(request, evidence, *context)
        self.assertTrue(result.rfdc_shell_structural_ready)
        self.assertFalse(result.production_integration_ready)
        self.assertEqual(result.blocking_reasons, ())

    def test_evidence_summary_keeps_ooc_shell_separate(self) -> None:
        _, evidence, _ = fixture()

        summary = summarize_connected_shell_evidence(evidence)

        self.assertEqual(summary["status"], "success")
        self.assertTrue(summary["rfdc_shell_structural_ready"])
        self.assertFalse(summary["production_integration_ready"])
        self.assertEqual(summary["interfaces"], 24)
        self.assertTrue(summary["validate_bd_design_passed"])
        self.assertTrue(summary["synthesis_completed"])
        self.assertTrue(summary["cdc_safe"])
        self.assertTrue(summary["clock_safety_verified"])
        self.assertTrue(summary["mts_configuration_verified"])
        self.assertFalse(summary["mts_runtime_verified"])
        self.assertEqual(summary["blocking_reasons"], ["production_integration_pending"])

    def test_probe_provenance_is_immutable_and_requires_canonical_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "run_id"):
            RfdcProbeProvenance("2025.2", "0" * 64, "1" * 64, 0)
        with self.assertRaisesRegex(ValueError, "lowercase SHA"):
            RfdcProbeProvenance("2025.2", "A" * 64, "1" * 64, 1)
        probe = RfdcProbeProvenance("2025.2", "0" * 64, "1" * 64, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            probe.run_id = 2  # type: ignore[misc]

    def test_each_structural_gate_has_stable_reason(self) -> None:
        request, evidence, context = fixture()
        faults = {
            "request": dataclasses.replace(evidence, connected_request_sha256="0" * 64),
            "model_config_sha256": dataclasses.replace(evidence, model_config_sha256="0" * 64),
            "architecture_config_sha256": dataclasses.replace(evidence, architecture_config_sha256="0" * 64),
            "ps_platform_config_sha256": dataclasses.replace(evidence, ps_platform_config_sha256="0" * 64),
            "production_lock_sha256": dataclasses.replace(evidence, production_lock_sha256="0" * 64),
            "part": dataclasses.replace(evidence, device_part="wrong"),
            "vivado": dataclasses.replace(evidence, vivado_version="2024.1"),
            "cell": dataclasses.replace(evidence, cells=evidence.cells[:-1]),
            "interface": dataclasses.replace(evidence, interfaces=evidence.interfaces[:-1]),
            "iq": dataclasses.replace(evidence, interfaces=tuple(
                dataclasses.replace(item, iq_component="Q" if item.iq_component == "I" else "I")
                if item.name == "m00_axis" else item for item in evidence.interfaces)),
            "width": dataclasses.replace(evidence, interfaces=tuple(
                dataclasses.replace(item, width_bits=64) if item.name == "m00_axis" else item
                for item in evidence.interfaces)),
            "clock": dataclasses.replace(evidence, clocks=evidence.clocks[:-1]),
            "reset": dataclasses.replace(evidence, resets=tuple(
                dataclasses.replace(item, reset_net="ctrl_reset") if item.domain == "rx" else item
                for item in evidence.resets)),
            "lock": dataclasses.replace(evidence, resets=tuple(
                dataclasses.replace(item, dcm_locked_pin="wrong") if item.domain == "rx" else item
                for item in evidence.resets)),
            "address": dataclasses.replace(evidence, address_path=("wrong",)),
            "irq": dataclasses.replace(evidence, irq_path=("wrong",)),
            "validation": dataclasses.replace(evidence, validate_bd_design_passed=False),
            "synthesis": dataclasses.replace(evidence, synthesis_completed=False),
            "cdc": dataclasses.replace(evidence, cdc_safe=False),
            "mts": dataclasses.replace(evidence, mts_runtime_verified=True),
            "rfdc": dataclasses.replace(evidence, rfdc_semantics=dataclasses.replace(evidence.rfdc_semantics, dac_nco_frequency_hz=1)),
            "mts_group": dataclasses.replace(evidence, mts_groups=(dataclasses.replace(evidence.mts_groups[0], tiles=(9,)), evidence.mts_groups[1])),
            "mts_configuration": dataclasses.replace(evidence, mts_configuration_verified=False),
            "clock_safety": dataclasses.replace(evidence, clock_safety_verified=False),
        }
        for name, corrupted in faults.items():
            with self.subTest(name=name):
                result = validate_connected_evidence(request, corrupted, *context)
                self.assertFalse(result.rfdc_shell_structural_ready)
                self.assertIn(name if name != "validation" else "validate_bd_design", " ".join(result.blocking_reasons))

    def test_parser_rejects_noncanonical_duplicate_unknown_and_wrong_scalar_bytes(self) -> None:
        _, evidence, _ = fixture()
        encoded = canonical_connected_json_bytes(evidence)
        self.assertEqual(parse_connected_evidence(encoded), evidence)
        with self.assertRaisesRegex(ValueError, "canonical"):
            parse_connected_evidence(encoded + b"\n")
        payload = json.loads(encoded)
        payload["unknown"] = True
        with self.assertRaisesRegex(ValueError, "unknown or missing"):
            parse_connected_evidence(canonical_connected_json_bytes(payload))
        duplicate = encoded.decode("utf-8").replace(
            '"evidence_schema_version":1,',
            '"evidence_schema_version":1,"evidence_schema_version":1,',
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            parse_connected_evidence(duplicate)
        payload = json.loads(encoded)
        payload["mts_configuration_verified"] = 1
        with self.assertRaisesRegex(ValueError, "boolean"):
            parse_connected_evidence(canonical_connected_json_bytes(payload))


if __name__ == "__main__":
    unittest.main()
