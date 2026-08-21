"""Canonical catalog evidence parsing, binding, and candidate locks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
from importlib import resources
import json
import re

from .catalog import _vlnv_identity, validate_resolved_catalog
from .types import HardwareArchitectureConfig


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VIVADO_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
META_ORDER = (
    "evidence_schema_version",
    "architecture_config_sha256",
    "generated_tcl_sha256",
    "catalog_request_sha256",
    "vivado_version",
    "run_id",
)
META_ORDER_V2 = (
    "evidence_schema_version",
    "architecture_config_sha256",
    "generated_tcl_sha256",
    "catalog_request_sha256",
    "vivado_version",
    "environment_manifest_sha256",
    "run_id",
)
RUN_ID_RE = re.compile(r"^[0-9]+-[0-9]+$")


class CatalogResolutionStatus(str, Enum):
    """Truthful catalog-evidence status for the current generated inputs."""

    UNVERIFIED = "unverified"
    STALE_EVIDENCE = "stale_evidence"
    ALL_REQUIRED_IP_RESOLVED = "all_required_ip_resolved"


@dataclass(frozen=True)
class CatalogEvidence:
    evidence_schema_version: int
    architecture_config_sha256: str
    generated_tcl_sha256: str
    catalog_request_sha256: str
    vivado_version: str
    run_id: str
    resolved_vlnv: tuple[tuple[str, str], ...]
    environment_manifest_sha256: str | None = None


@dataclass(frozen=True)
class ValidatedCatalogEvidence:
    status: CatalogResolutionStatus
    catalog_resolution_complete: bool
    resolved_vlnv: Mapping[str, str]
    evidence: CatalogEvidence


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    """Return canonical, human-readable UTF-8 JSON with one trailing newline."""

    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def build_catalog_request(
    config: HardwareArchitectureConfig,
    architecture_config_sha256: str,
    generated_tcl_sha256: str,
) -> dict[str, object]:
    """Build the discovery-provenance request after discovery Tcl is final."""

    return {
        "architecture_schema_version": config.architecture_schema_version,
        "architecture_config_version": config.architecture_config_version,
        "architecture_config_sha256": architecture_config_sha256,
        "generated_tcl_sha256": generated_tcl_sha256,
        "vivado_version": config.vivado_version,
        "required_families": [
            {
                "family_id": family.family_id,
                "catalog_pattern": family.catalog_pattern,
                "vlnv": family.vlnv,
            }
            for family in config.required_families()
        ],
    }


def parse_catalog_evidence(text: str) -> CatalogEvidence:
    """Parse exactly the schema-v2 three-column catalog TSV grammar."""

    if not text.endswith("\n") or text.endswith("\n\n"):
        raise ValueError("catalog evidence requires a single trailing newline")

    metadata: dict[str, str] = {}
    resolved: dict[str, str] = {}
    metadata_index = 0
    metadata_order: tuple[str, ...] = META_ORDER
    for line_number, line in enumerate(text[:-1].split("\n"), start=1):
        if line.count("\t") != 2:
            raise ValueError(f"malformed catalog evidence row {line_number}")
        kind, key, value = line.split("\t")
        if kind not in {"meta", "ip"}:
            raise ValueError(f"unknown catalog evidence row kind on row {line_number}")
        if not key or key != key.strip() or not value or value != value.strip():
            raise ValueError(f"blank or padded catalog evidence value on row {line_number}")
        if kind == "meta":
            if key not in {*META_ORDER, "environment_manifest_sha256"}:
                raise ValueError(f"unknown catalog evidence metadata: {key}")
            if key in metadata:
                raise ValueError(f"catalog evidence metadata duplicate: {key}")
            if metadata_index == len(metadata_order) or key != metadata_order[metadata_index]:
                expected = (
                    "no further metadata"
                    if metadata_index == len(metadata_order)
                    else metadata_order[metadata_index]
                )
                raise ValueError(
                    "catalog evidence metadata order mismatch: "
                    f"expected {expected}, got {key}"
                )
            metadata[key] = value
            metadata_index += 1
            if key == "evidence_schema_version":
                if value == "2":
                    metadata_order = META_ORDER_V2
                elif value != "1":
                    raise ValueError("unsupported evidence_schema_version")
            continue
        if metadata_index != len(metadata_order):
            raise ValueError("catalog evidence ip row before metadata header")
        if key in resolved:
            raise ValueError(f"duplicate catalog evidence family: {key}")
        _vlnv_identity(value, f"catalog evidence {key}")
        resolved[key] = value

    missing_metadata = list(metadata_order[metadata_index:])
    if missing_metadata:
        raise ValueError(f"missing catalog evidence metadata: {missing_metadata}")
    if metadata["evidence_schema_version"] not in {"1", "2"}:
        raise ValueError("unsupported evidence_schema_version")
    for field_name in (
        "architecture_config_sha256",
        "generated_tcl_sha256",
        "catalog_request_sha256",
    ):
        if not _SHA256_RE.fullmatch(metadata[field_name]):
            raise ValueError(f"malformed SHA-256 for {field_name}")
    if not _VIVADO_VERSION_RE.fullmatch(metadata["vivado_version"]):
        raise ValueError("malformed vivado_version")
    if not RUN_ID_RE.fullmatch(metadata["run_id"]):
        raise ValueError("malformed run_id")
    environment_manifest_sha256 = metadata.get("environment_manifest_sha256")
    if environment_manifest_sha256 is not None and not _SHA256_RE.fullmatch(
        environment_manifest_sha256
    ):
        raise ValueError("malformed SHA-256 for environment_manifest_sha256")
    return CatalogEvidence(
        evidence_schema_version=int(metadata["evidence_schema_version"]),
        architecture_config_sha256=metadata["architecture_config_sha256"],
        generated_tcl_sha256=metadata["generated_tcl_sha256"],
        catalog_request_sha256=metadata["catalog_request_sha256"],
        vivado_version=metadata["vivado_version"],
        run_id=metadata["run_id"],
        resolved_vlnv=tuple(resolved.items()),
        environment_manifest_sha256=environment_manifest_sha256,
    )


def validate_catalog_evidence(
    config: HardwareArchitectureConfig,
    request_bytes: bytes,
    discovery_tcl_bytes: bytes,
    evidence: CatalogEvidence,
    environment_manifest_sha256: str | None = None,
) -> ValidatedCatalogEvidence:
    """Validate exact family identities before classifying provenance staleness."""

    resolved_items = evidence.resolved_vlnv
    resolved_ids = [family_id for family_id, _ in resolved_items]
    if len(resolved_ids) != len(set(resolved_ids)):
        raise ValueError("duplicate catalog evidence family")
    resolved = dict(resolved_items)
    for family_id, vlnv in resolved.items():
        if not family_id or family_id != family_id.strip():
            raise ValueError("blank or padded catalog evidence family")
        if not vlnv or vlnv != vlnv.strip():
            raise ValueError("blank or padded catalog evidence VLNV")
        _vlnv_identity(vlnv, f"catalog evidence {family_id}")
    validate_resolved_catalog(config, resolved)
    _validate_evidence_fields(evidence)
    if environment_manifest_sha256 is not None:
        if not _SHA256_RE.fullmatch(environment_manifest_sha256):
            raise ValueError("environment_manifest_sha256 must be lowercase SHA-256")
        if evidence.environment_manifest_sha256 != environment_manifest_sha256:
            return ValidatedCatalogEvidence(
                status=CatalogResolutionStatus.STALE_EVIDENCE,
                catalog_resolution_complete=False,
                resolved_vlnv=dict(sorted(resolved.items())),
                evidence=evidence,
            )
    elif evidence.environment_manifest_sha256 is not None:
        return ValidatedCatalogEvidence(
            status=CatalogResolutionStatus.STALE_EVIDENCE,
            catalog_resolution_complete=False,
            resolved_vlnv=dict(sorted(resolved.items())),
            evidence=evidence,
        )

    source_config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    expected_config_sha256 = hashlib.sha256(source_config_bytes).hexdigest()
    expected_tcl_sha256 = hashlib.sha256(discovery_tcl_bytes).hexdigest()
    expected_request = canonical_json_bytes(
        build_catalog_request(config, expected_config_sha256, expected_tcl_sha256)
    )
    current = (
        request_bytes == expected_request
        and evidence.architecture_config_sha256 == expected_config_sha256
        and evidence.generated_tcl_sha256 == expected_tcl_sha256
        and evidence.catalog_request_sha256 == hashlib.sha256(request_bytes).hexdigest()
        and evidence.vivado_version == config.vivado_version
        and (
            environment_manifest_sha256 is None
            or evidence.environment_manifest_sha256 == environment_manifest_sha256
        )
    )
    status = (
        CatalogResolutionStatus.ALL_REQUIRED_IP_RESOLVED
        if current
        else CatalogResolutionStatus.STALE_EVIDENCE
    )
    return ValidatedCatalogEvidence(
        status=status,
        catalog_resolution_complete=status is CatalogResolutionStatus.ALL_REQUIRED_IP_RESOLVED,
        resolved_vlnv=dict(sorted(resolved.items())),
        evidence=evidence,
    )


def build_candidate_lock(
    config: HardwareArchitectureConfig,
    evidence: ValidatedCatalogEvidence,
) -> dict[str, object]:
    """Build a non-production candidate only from accepted current evidence."""

    if evidence.status is not CatalogResolutionStatus.ALL_REQUIRED_IP_RESOLVED:
        raise ValueError("candidate lock requires current complete catalog evidence")
    validate_resolved_catalog(config, evidence.resolved_vlnv)
    return {
        "lock_schema_version": 1,
        "architecture_config_sha256": evidence.evidence.architecture_config_sha256,
        "generated_tcl_sha256": evidence.evidence.generated_tcl_sha256,
        "catalog_request_sha256": evidence.evidence.catalog_request_sha256,
        "vivado_version": evidence.evidence.vivado_version,
        "families": dict(sorted(evidence.resolved_vlnv.items())),
    }


def _validate_evidence_fields(evidence: CatalogEvidence) -> None:
    if evidence.evidence_schema_version not in {1, 2}:
        raise ValueError("unsupported evidence_schema_version")
    for field_name in (
        "architecture_config_sha256",
        "generated_tcl_sha256",
        "catalog_request_sha256",
    ):
        value = getattr(evidence, field_name)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError(f"malformed SHA-256 for {field_name}")
    if not isinstance(evidence.vivado_version, str) or not _VIVADO_VERSION_RE.fullmatch(
        evidence.vivado_version
    ):
        raise ValueError("malformed vivado_version")
    if not isinstance(evidence.run_id, str) or not RUN_ID_RE.fullmatch(evidence.run_id):
        raise ValueError("malformed run_id")
    if evidence.evidence_schema_version == 2:
        if not isinstance(evidence.environment_manifest_sha256, str) or not _SHA256_RE.fullmatch(
            evidence.environment_manifest_sha256
        ):
            raise ValueError("schema-v2 catalog evidence requires environment_manifest_sha256")
    elif evidence.environment_manifest_sha256 is not None:
        raise ValueError("schema-v1 catalog evidence must not contain environment_manifest_sha256")
