"""Strict parsing and validation of Vivado-resolved IP catalog evidence."""

from __future__ import annotations

from collections.abc import Mapping

from .types import HardwareArchitectureConfig, RFDC_2_6_VLNV


def parse_resolved_ip_vlnv(text: str) -> dict[str, str]:
    """Parse strict logical-name/VLNV TSV evidence emitted by Vivado."""

    resolved: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.count("\t") != 1:
            raise ValueError(f"malformed catalog row {line_number}")
        logical_name, vlnv = line.split("\t")
        if not logical_name or logical_name != logical_name.strip():
            raise ValueError(f"blank or padded logical name on row {line_number}")
        if not vlnv or vlnv != vlnv.strip():
            raise ValueError(f"blank or padded VLNV on row {line_number}")
        if logical_name in resolved:
            raise ValueError(f"duplicate logical name: {logical_name}")
        _vlnv_identity(vlnv, f"resolved {logical_name}")
        resolved[logical_name] = vlnv
    return resolved


def validate_resolved_catalog(
    config: HardwareArchitectureConfig,
    resolved: Mapping[str, str],
) -> None:
    """Validate the exact required family set and each resolved identity."""

    expected = {family.family_id for family in config.required_families()}
    actual = set(resolved)
    if actual != expected:
        raise ValueError(
            "resolved family set mismatch: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )

    actual_rfdc = resolved.get("rfdc")
    if actual_rfdc != RFDC_2_6_VLNV:
        raise ValueError(
            "RF Data Converter 2.6 is required; "
            f"resolved {actual_rfdc!r}"
        )

    specs = {family.family_id: family for family in config.required_families()}
    for logical_name, spec in specs.items():
        actual = resolved[logical_name]
        expected_identity = (
            _vlnv_identity(spec.vlnv, f"configured {logical_name}")
            if spec.vlnv is not None
            else _pattern_identity(spec.catalog_pattern, f"configured {logical_name}")
        )
        actual_identity = _vlnv_identity(actual, f"resolved {logical_name}")
        if actual_identity != expected_identity:
            raise ValueError(
                f"{logical_name} resolved VLNV {actual!r} does not match "
                f"{spec.catalog_pattern!r}"
            )


def _pattern_identity(pattern: str, description: str) -> tuple[str, str, str]:
    parts = pattern.split(":")
    if len(parts) != 4 or parts[3] != "*" or any(not part for part in parts[:3]):
        raise ValueError(f"{description} must be vendor:library:name:*")
    return parts[0], parts[1], parts[2]


def _vlnv_identity(vlnv: str, description: str) -> tuple[str, str, str]:
    parts = vlnv.split(":")
    if len(parts) != 4 or any(not part for part in parts):
        raise ValueError(f"{description} must be vendor:library:name:version")
    return parts[0], parts[1], parts[2]
