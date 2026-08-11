"""Canonical catalog-request serialization.

Evidence parsing, evidence validation, and candidate locks intentionally belong
to the following task; this module only defines their deterministic inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
import json

from .types import HardwareArchitectureConfig


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
