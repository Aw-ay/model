"""Strict parsing and validation of Vivado-resolved IP catalog evidence."""

from __future__ import annotations

from collections.abc import Mapping

from .tcl import INITIAL_SKELETON_IP
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
    """Validate exact RFDC 2.6 and every initial skeleton IP family."""

    actual_rfdc = resolved.get("rfdc")
    if actual_rfdc != RFDC_2_6_VLNV:
        raise ValueError(
            "RF Data Converter 2.6 is required; "
            f"resolved {actual_rfdc!r}"
        )

    specs = {spec.logical_name: spec for spec in config.required_ip_families}
    for logical_name in INITIAL_SKELETON_IP:
        actual = resolved.get(logical_name)
        if actual is None:
            raise ValueError(f"missing resolved IP: {logical_name}")
        spec = specs.get(logical_name)
        if spec is None:
            raise ValueError(f"missing configured IP family: {logical_name}")
        expected_identity = _pattern_identity(
            spec.catalog_pattern, f"configured {logical_name}"
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
