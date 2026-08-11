"""Deterministic metadata generation for the AMD IP-first architecture."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

from .evidence import (
    CatalogResolutionStatus,
    build_candidate_lock,
    build_catalog_request,
    canonical_json_bytes,
    parse_catalog_evidence,
    validate_catalog_evidence,
)
from .registry import ArchitectureRegistry
from .tcl import emit_architecture_realization_tcl, emit_catalog_discovery_tcl
from .types import HardwareArchitectureConfig


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_ip_architecture(output_root: Path) -> dict[str, object]:
    """Generate unconnected architecture artifacts in strict provenance order."""

    root = Path(output_root)
    metadata_root = root / "metadata"
    vivado_root = root / "vivado"
    metadata_root.mkdir(parents=True, exist_ok=True)
    vivado_root.mkdir(parents=True, exist_ok=True)

    config_resource = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    )
    source_bytes = config_resource.read_bytes()
    source_config_sha256 = _sha256(source_bytes)
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.default()

    discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    (vivado_root / "discover_ip_catalog.tcl").write_bytes(discovery_bytes)
    generated_tcl_sha256 = _sha256(discovery_bytes)

    realization_bytes = emit_architecture_realization_tcl(config).encode("utf-8")
    (vivado_root / "realize_ip_architecture.tcl").write_bytes(realization_bytes)
    realization_tcl_sha256 = _sha256(realization_bytes)

    request_bytes = canonical_json_bytes(
        build_catalog_request(config, source_config_sha256, generated_tcl_sha256)
    )
    (metadata_root / "catalog_request.json").write_bytes(request_bytes)
    catalog_request_sha256 = _sha256(request_bytes)

    candidate_path = metadata_root / "ip_lock.candidate.json"
    if candidate_path.exists():
        if not candidate_path.is_file():
            raise ValueError(f"candidate lock path is not a file: {candidate_path}")
        candidate_path.unlink()
    evidence_path = metadata_root / "catalog_evidence.tsv"
    if evidence_path.is_file():
        validated_evidence = validate_catalog_evidence(
            config,
            request_bytes,
            discovery_bytes,
            parse_catalog_evidence(evidence_path.read_text(encoding="utf-8")),
        )
    else:
        validated_evidence = None
    catalog_status = (
        CatalogResolutionStatus.UNVERIFIED
        if validated_evidence is None
        else validated_evidence.status
    )
    if validated_evidence is not None and validated_evidence.catalog_resolution_complete:
        candidate_path.write_bytes(
            canonical_json_bytes(build_candidate_lock(config, validated_evidence))
        )

    rfdc_family = config.family_by_id("rfdc")
    architecture: dict[str, object] = {
        "architecture_schema_version": config.architecture_schema_version,
        "architecture_config_version": config.architecture_config_version,
        "vivado_version": config.vivado_version,
        "generation_mode": config.generation_mode,
        "topology_status": config.topology_status,
        "integration_accepted": False,
        "rfdc": {
            "instance_ref": config.rfdc_integration.instance_ref,
            "vlnv": rfdc_family.vlnv,
            "catalog_pattern": rfdc_family.catalog_pattern,
            "configuration_authority": config.rfdc_integration.configuration_authority,
            "dac_analog_output_type": config.rfdc_integration.dac_analog_output_type,
            "dac_mixer_mode": config.rfdc_integration.dac_mixer_mode,
            "dac_mixer_scale_mode": config.rfdc_integration.dac_mixer_scale_mode,
            "dac_nco_frequency_hz": config.rfdc_integration.dac_nco_frequency_hz,
            "proof_status": config.rfdc_integration.proof_status.value,
        },
        "ip_families": [
            {
                "family_id": family.family_id,
                "implementation_kind": family.implementation_kind.value,
                "catalog_pattern": family.catalog_pattern,
                "required": family.required,
                "vlnv": family.vlnv,
            }
            for family in config.ip_families
        ],
        "ip_instances": [
            {
                "instance_name": instance.instance_name,
                "family_ref": instance.family_ref,
                "logical_role": instance.logical_role,
                "lifecycle": instance.lifecycle.value,
                "parameter_status": instance.parameter_status.value,
                "connection_status": instance.connection_status.value,
            }
            for instance in config.ip_instances
        ],
        "blocks": [
            {
                "block_name": block.block_name,
                "implementation_kind": block.implementation_kind.value,
                "responsibilities": list(block.responsibilities),
                "reference_responsibilities": list(block.reference_responsibilities),
                "instance_refs": list(block.instance_refs),
                "architecture_status": block.architecture_status.value,
                "production_accepted": block.production_accepted,
                "source": block.source,
            }
            for block in registry.blocks
        ],
        "source_config_sha256": source_config_sha256,
        "generated_tcl_sha256": generated_tcl_sha256,
        "realization_tcl_sha256": realization_tcl_sha256,
        "catalog_request_sha256": catalog_request_sha256,
        "catalog_resolution_status": catalog_status.value,
        "catalog_resolution_complete": (
            False
            if validated_evidence is None
            else validated_evidence.catalog_resolution_complete
        ),
    }
    (metadata_root / "ip_architecture.json").write_bytes(
        canonical_json_bytes(architecture)
    )
    return architecture
