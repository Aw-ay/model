"""Deterministic metadata generation for the AMD IP-first architecture."""

from __future__ import annotations

import hashlib
from importlib import resources
import json
from pathlib import Path

from .registry import ArchitectureRegistry
from .types import HardwareArchitectureConfig


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_ip_architecture(output_root: Path) -> dict[str, object]:
    """Generate the machine-readable architecture authority for a build."""

    root = Path(output_root)
    metadata_root = root / "metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)

    config_resource = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    )
    source_bytes = config_resource.read_bytes()
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.default()

    architecture: dict[str, object] = {
        "architecture_schema_version": config.architecture_schema_version,
        "architecture_config_version": config.architecture_config_version,
        "vivado_version": config.vivado_version,
        "generation_mode": config.generation_mode,
        "topology_status": config.topology_status,
        "integration_accepted": False,
        "rfdc": {
            "logical_name": config.rfdc.ip.logical_name,
            "kind": config.rfdc.ip.kind.value,
            "vlnv": config.rfdc.ip.vlnv,
            "catalog_pattern": config.rfdc.ip.catalog_pattern,
            "owned_functions": list(config.rfdc.owned_functions),
            "configuration_authority": config.rfdc.configuration_authority,
            "dac_analog_output_type": config.rfdc.dac_analog_output_type,
            "dac_mixer_mode": config.rfdc.dac_mixer_mode,
            "dac_mixer_scale_mode": config.rfdc.dac_mixer_scale_mode,
            "dac_nco_frequency_hz": config.rfdc.dac_nco_frequency_hz,
            "proof_status": config.rfdc.proof_status,
        },
        "required_ip_families": [
            {
                "logical_name": spec.logical_name,
                "kind": spec.kind.value,
                "catalog_pattern": spec.catalog_pattern,
            }
            for spec in config.required_ip_families
        ],
        "blocks": [
            {
                "logical_name": block.logical_name,
                "kind": block.kind.value,
                "production": block.production,
                "responsibilities": list(block.responsibilities),
                "vlnv": block.vlnv,
                "source": block.source,
            }
            for block in registry.blocks
        ],
        "source_config_sha256": _sha256(source_bytes),
    }
    architecture_bytes = (
        json.dumps(architecture, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    (metadata_root / "ip_architecture.json").write_bytes(architecture_bytes)
    return architecture
