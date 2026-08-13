"""Pure canonical connected-RFDC-shell request and evidence contract tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from importlib import resources

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.connected import (
    ConnectedShellEvidence,
    RfdcProbeProvenance,
    build_connected_request,
    canonical_connected_json_bytes,
    parse_connected_evidence,
    validate_connected_evidence,
)
from rfsoc_pulse_model.ip.lock import decode_production_lock_json
from rfsoc_pulse_model.ip.platform import PsPlatformConfig
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authority_bytes(name: str) -> bytes:
    return resources.files("rfsoc_pulse_model.config").joinpath(name).read_bytes()


def fixture() -> tuple[object, ConnectedShellEvidence]:
    probe = RfdcProbeProvenance(
        vivado_version="2025.2", probe_tcl_sha256=sha("probe Tcl"),
        raw_output_sha256=sha("probe output"), run_id=42,
    )
    request = build_connected_request(
        ModelConfig.load_default(), HardwareArchitectureConfig.load_default(),
        PsPlatformConfig.load_default(),
        decode_production_lock_json(authority_bytes("ip_lock.json"), "fixture lock"),
        probe,
    )
    evidence = ConnectedShellEvidence(
        evidence_schema_version=1,
        connected_request_sha256=sha(canonical_connected_json_bytes(request).decode("utf-8")),
        model_config_sha256=hashlib.sha256(authority_bytes("default.json")).hexdigest(),
        architecture_config_sha256=hashlib.sha256(authority_bytes("ip_architecture.json")).hexdigest(),
        ps_platform_config_sha256=hashlib.sha256(authority_bytes("ps_platform.json")).hexdigest(),
        production_lock_sha256=hashlib.sha256(authority_bytes("ip_lock.json")).hexdigest(),
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
    return request, evidence


class ConnectedShellContractTest(unittest.TestCase):
    def test_true_ready_fixture_has_exact_24_interfaces_and_never_sets_production_ready(self) -> None:
        request, evidence = fixture()
        self.assertEqual(len(request.cells), 8)
        self.assertEqual(len(request.interfaces), 24)
        self.assertEqual(len([item for item in request.interfaces if item.direction == "master"]), 16)
        self.assertEqual(len([item for item in request.interfaces if item.direction == "slave"]), 8)
        result = validate_connected_evidence(request, evidence)
        self.assertTrue(result.rfdc_shell_structural_ready)
        self.assertFalse(result.production_integration_ready)
        self.assertEqual(result.blocking_reasons, ())

    def test_probe_provenance_is_immutable_and_requires_canonical_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "run_id"):
            RfdcProbeProvenance("2025.2", "0" * 64, "1" * 64, 0)
        with self.assertRaisesRegex(ValueError, "lowercase SHA"):
            RfdcProbeProvenance("2025.2", "A" * 64, "1" * 64, 1)
        probe = RfdcProbeProvenance("2025.2", "0" * 64, "1" * 64, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            probe.run_id = 2  # type: ignore[misc]

    def test_each_structural_gate_has_stable_reason(self) -> None:
        request, evidence = fixture()
        faults = {
            "request": dataclasses.replace(evidence, connected_request_sha256="0" * 64),
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
        }
        for name, corrupted in faults.items():
            with self.subTest(name=name):
                result = validate_connected_evidence(request, corrupted)
                self.assertFalse(result.rfdc_shell_structural_ready)
                self.assertIn(name if name != "validation" else "validate_bd_design", " ".join(result.blocking_reasons))

    def test_parser_rejects_noncanonical_duplicate_unknown_and_wrong_scalar_bytes(self) -> None:
        _, evidence = fixture()
        encoded = canonical_connected_json_bytes(evidence)
        self.assertEqual(parse_connected_evidence(encoded), evidence)
        with self.assertRaisesRegex(ValueError, "canonical"):
            parse_connected_evidence(encoded + b"\n")
        payload = json.loads(encoded)
        payload["unknown"] = True
        with self.assertRaisesRegex(ValueError, "unknown or missing"):
            parse_connected_evidence(canonical_connected_json_bytes(payload))
        duplicate = encoded.decode("utf-8").replace(
            '\n  "evidence_schema_version": 1,',
            '\n  "evidence_schema_version": 1,\n  "evidence_schema_version": 1,',
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            parse_connected_evidence(duplicate)
        payload = json.loads(encoded)
        payload["mts_configuration_verified"] = 1
        with self.assertRaisesRegex(ValueError, "boolean"):
            parse_connected_evidence(canonical_connected_json_bytes(payload))


if __name__ == "__main__":
    unittest.main()
