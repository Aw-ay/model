"""Deterministic metadata generation for the AMD IP-first architecture."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

from .evidence import (
    CatalogResolutionStatus,
    build_candidate_lock,
    build_catalog_request,
    build_catalog_provenance,
    canonical_json_bytes,
    parse_catalog_evidence,
    validate_catalog_provenance,
    validate_catalog_evidence,
)
from .registry import ArchitectureRegistry
from .tcl import emit_architecture_realization_tcl, emit_catalog_discovery_tcl
from .types import HardwareArchitectureConfig
from .lock import (
    GenerationMode,
    decode_production_lock_json,
    validate_production_lock,
)
from .connected import ConnectedAuthorityBytes, build_connected_request, canonical_connected_json_bytes
from .connected_tcl import emit_connected_tcl
from .platform import PsPlatformConfig
from .rfdc_probe import parse_rfdc_probe_evidence
from rfsoc_pulse_model.common.config import ModelConfig
from .environment import (
    parse_environment_manifest,
    require_environment_ready,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bind_generation_environment(
    root: Path, environment_manifest_bytes: bytes | None,
) -> bytes | None:
    """Use only the current Phase-0 manifest when a migration build has one."""

    manifest_path = root / "metadata" / "environment_manifest.json"
    if not manifest_path.is_file():
        return environment_manifest_bytes
    _manifest, current_manifest_bytes = require_environment_ready(root)
    if environment_manifest_bytes is None:
        return current_manifest_bytes
    provided = parse_environment_manifest(environment_manifest_bytes)
    current = parse_environment_manifest(current_manifest_bytes)
    if provided.sha256 != current.sha256:
        raise ValueError("provided environment manifest is not the Phase-0 manifest")
    return environment_manifest_bytes


def generate_ip_architecture(
    output_root: Path,
    ip_mode: GenerationMode | str = GenerationMode.DEVELOPMENT,
    *,
    environment_manifest_bytes: bytes | None = None,
) -> dict[str, object]:
    """Generate unconnected architecture artifacts in strict provenance order."""

    mode = GenerationMode(ip_mode)
    root = Path(output_root)
    config_resource = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    )
    source_bytes = config_resource.read_bytes()
    source_config_sha256 = _sha256(source_bytes)
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.default()

    environment_manifest_bytes = _bind_generation_environment(
        Path(output_root), environment_manifest_bytes
    )
    environment_manifest_sha256 = None
    if environment_manifest_bytes is not None:
        environment_manifest_sha256 = parse_environment_manifest(
            environment_manifest_bytes
        ).sha256

    # Discovery is architecture authority.  Environment provenance is bound
    # separately below and must not change the packaged lock hash.
    discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    generated_tcl_sha256 = _sha256(discovery_bytes)
    realization_bytes = emit_architecture_realization_tcl(config).encode("utf-8")
    realization_tcl_sha256 = _sha256(realization_bytes)
    request_bytes = canonical_json_bytes(
        build_catalog_request(config, source_config_sha256, generated_tcl_sha256)
    )
    production_lock_valid = _validate_packaged_lock(
        mode, config, request_bytes, discovery_bytes
    )

    metadata_root = root / "metadata"
    vivado_root = root / "vivado"
    metadata_root.mkdir(parents=True, exist_ok=True)
    vivado_root.mkdir(parents=True, exist_ok=True)
    (vivado_root / "discover_ip_catalog.tcl").write_bytes(discovery_bytes)
    (vivado_root / "realize_ip_architecture.tcl").write_bytes(realization_bytes)
    (metadata_root / "catalog_request.json").write_bytes(request_bytes)
    catalog_request_sha256 = _sha256(request_bytes)
    candidate_path = metadata_root / "ip_lock.candidate.json"
    if candidate_path.exists():
        if not candidate_path.is_file():
            raise ValueError(f"candidate lock path is not a file: {candidate_path}")
        candidate_path.unlink()
    provenance_path = metadata_root / "catalog_provenance.json"
    if provenance_path.exists():
        if not provenance_path.is_file():
            raise ValueError(f"catalog provenance path is not a file: {provenance_path}")
        provenance_path.unlink()
    evidence_path = metadata_root / "catalog_evidence.tsv"
    if evidence_path.is_file():
        validated_evidence = validate_catalog_evidence(
            config,
            request_bytes,
            discovery_bytes,
            parse_catalog_evidence(evidence_path.read_text(encoding="utf-8")),
            environment_manifest_sha256,
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
        if environment_manifest_sha256 is not None:
            evidence_bytes = evidence_path.read_bytes()
            provenance_path.write_bytes(
                canonical_json_bytes(
                    build_catalog_provenance(
                        evidence_bytes,
                        request_bytes,
                        discovery_bytes,
                        validated_evidence.evidence,
                        environment_manifest_sha256,
                    )
                )
            )

    rfdc_family = config.family_by_id("rfdc")
    architecture: dict[str, object] = {
        "architecture_schema_version": config.architecture_schema_version,
        "architecture_config_version": config.architecture_config_version,
        "vivado_version": config.vivado_version,
        "generation_mode": config.generation_mode,
        "ip_mode": mode.value,
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
        "production_lock_valid": production_lock_valid,
    }
    if environment_manifest_sha256 is not None:
        architecture["environment_manifest_sha256"] = environment_manifest_sha256
    (metadata_root / "ip_architecture.json").write_bytes(
        canonical_json_bytes(architecture)
    )
    return architecture


def generate_connected_rfdc_shell(
    output_root: Path,
    probe_evidence_bytes: bytes,
    probe_tcl_bytes: bytes,
    *,
    environment_manifest_bytes: bytes | None = None,
) -> dict[str, object]:
    """Generate connected-shell request/Tcl from explicit Task-4 evidence.

    This is artifact orchestration only.  It does not run Vivado, create a
    lifecycle marker or make structural-readiness claims.
    """

    root = Path(output_root)
    environment_manifest_bytes = _bind_generation_environment(
        root, environment_manifest_bytes
    )
    if environment_manifest_bytes is not None:
        parse_environment_manifest(environment_manifest_bytes)
    model = ModelConfig.load_default()
    architecture = HardwareArchitectureConfig.load_default()
    platform = PsPlatformConfig.load_default()
    model_bytes = resources.files("rfsoc_pulse_model.config").joinpath("default.json").read_bytes()
    architecture_bytes = resources.files("rfsoc_pulse_model.config").joinpath("ip_architecture.json").read_bytes()
    platform_bytes = resources.files("rfsoc_pulse_model.config").joinpath("ps_platform.json").read_bytes()
    lock_bytes = resources.files("rfsoc_pulse_model.config").joinpath("ip_lock.json").read_bytes()
    production_lock = decode_production_lock_json(lock_bytes, "packaged production lock")
    environment_manifest_sha256 = (
        parse_environment_manifest(environment_manifest_bytes).sha256
        if environment_manifest_bytes is not None else None
    )
    # Keep the discovery/lock bytes machine-independent.  The environment
    # manifest is already bound in the connected request and in the catalog
    # provenance record validated below.
    discovery_bytes = emit_catalog_discovery_tcl(architecture).encode("utf-8")
    catalog_request_bytes = canonical_json_bytes(build_catalog_request(
        architecture, _sha256(architecture_bytes), _sha256(discovery_bytes)
    ))
    if environment_manifest_sha256 is not None:
        evidence_path = root / "metadata" / "catalog_evidence.tsv"
        provenance_path = root / "metadata" / "catalog_provenance.json"
        if not evidence_path.is_file() or not provenance_path.is_file():
            raise ValueError(
                "current environment-bound catalog evidence is required before connected generation"
            )
        catalog_evidence_bytes = evidence_path.read_bytes()
        catalog_evidence = parse_catalog_evidence(
            catalog_evidence_bytes.decode("utf-8")
        )
        validated_catalog = validate_catalog_evidence(
            architecture,
            catalog_request_bytes,
            discovery_bytes,
            catalog_evidence,
            environment_manifest_sha256,
        )
        if not validated_catalog.catalog_resolution_complete:
            raise ValueError(
                "current environment-bound catalog evidence is not complete"
            )
        validate_catalog_provenance(
            provenance_path.read_bytes(),
            catalog_evidence_bytes,
            catalog_request_bytes,
            discovery_bytes,
            catalog_evidence,
            environment_manifest_sha256,
        )
    probe = parse_rfdc_probe_evidence(
        probe_evidence_bytes,
        probe_tcl_bytes,
        model,
        architecture,
        environment_manifest_sha256=(
            parse_environment_manifest(environment_manifest_bytes).sha256
            if environment_manifest_bytes is not None else None
        ),
    )
    authority_bytes = ConnectedAuthorityBytes(
        model_bytes, architecture_bytes, platform_bytes, lock_bytes,
        discovery_bytes, catalog_request_bytes, environment_manifest_bytes or b"",
    )
    request = build_connected_request(
        model, architecture, platform, production_lock, probe.provenance, authority_bytes
    )
    artifacts = emit_connected_tcl(
        request, platform, probe
    )
    metadata_root = root / "metadata"
    vivado_root = root / "vivado"
    metadata_root.mkdir(parents=True, exist_ok=True)
    vivado_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "connected_request.json").write_bytes(artifacts.request_bytes)
    (metadata_root / "rfdc_probe_evidence.json").write_bytes(probe_evidence_bytes)
    (vivado_root / "probe_rfdc_contract.tcl").write_bytes(probe_tcl_bytes)
    (vivado_root / "realize_connected_rfdc_shell.tcl").write_bytes(artifacts.realization_tcl)
    (vivado_root / "verify_connected_rfdc_shell.tcl").write_bytes(artifacts.verification_tcl)
    return {
        "request_sha256": artifacts.request_sha256,
        "realization_tcl_sha256": artifacts.realization_tcl_sha256,
        "verification_tcl_sha256": artifacts.verification_tcl_sha256,
        "probe_tcl_sha256": probe.provenance.probe_tcl_sha256,
        "probe_raw_output_sha256": probe.provenance.raw_output_sha256,
        "probe_run_id": probe.provenance.run_id,
        "production_integration_ready": False,
    }


def _validate_packaged_lock(
    mode: GenerationMode,
    config: HardwareArchitectureConfig,
    request_bytes: bytes,
    discovery_bytes: bytes,
    *,
    lock_resource=None,
) -> bool:
    resource = lock_resource or resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_lock.json"
    )
    if not resource.is_file():
        if mode is GenerationMode.PRODUCTION:
            raise ValueError("production lock is missing")
        return False
    try:
        payload = decode_production_lock_json(
            resource.read_bytes(), "packaged production lock"
        )
        return validate_production_lock(
            config, request_bytes, discovery_bytes, payload
        ).valid
    except (OSError, ValueError) as error:
        if mode is GenerationMode.PRODUCTION:
            raise ValueError("production lock is invalid") from error
        return False
