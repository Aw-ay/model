"""Deterministic Vivado Tcl emission for catalog discovery and realization."""

from __future__ import annotations

from collections.abc import Mapping
import re

from .types import HardwareArchitectureConfig, IpInstanceLifecycle


def emit_catalog_discovery_tcl(
    config: HardwareArchitectureConfig,
    environment_manifest_sha256: str | None = None,
) -> str:
    """Emit catalog-only Tcl for every required IP family.

    The discovery Tcl is an architecture-authority artifact.  Its bytes must
    therefore be invariant across machines.  Environment provenance is bound
    by the Python-side catalog provenance record after this stable script has
    run; it must never be added as a Tcl argument because doing so would
    change the production lock hash on every migration.

    ``environment_manifest_sha256`` is retained as a compatibility argument
    for callers from the first migration implementation.  It is validated but
    intentionally not emitted into the authority Tcl.
    """

    required_families = config.required_families()
    if environment_manifest_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", environment_manifest_sha256
    ):
        raise ValueError("environment_manifest_sha256 must be lowercase SHA-256")
    argument_count = 3
    argument_names = "architecture_config_sha256 generated_tcl_sha256 catalog_request_sha256"
    lines = [
        "# Generated file. Modify the Python architecture source, not this Tcl.",
        "set required_vivado_prefix {2025.2}",
        "set actual_vivado_version [version -short]",
        "if {![string match ${required_vivado_prefix}* $actual_vivado_version]} {",
        "  error \"Vivado 2025.2 is required, got $actual_vivado_version\"",
        "}",
        "",
        f"if {{[llength $argv] != {argument_count}}} {{",
        f"  error \"usage: discover_ip_catalog.tcl {argument_names}\"",
        "}",
        f"lassign $argv {argument_names}",
        "",
        f"foreach argument_name {{{argument_names}}} {{",
        "  set argument_value [set $argument_name]",
        "  if {![regexp {^[0-9a-f]{64}$} $argument_value]} {",
        "    error \"invalid ${argument_name}: expected 64 lowercase hexadecimal characters\"",
        "  }",
        "}",
        "",
        f"create_project -in_memory -part {{{config.device_part}}}",
        "update_ip_catalog",
        "",
        "set script_dir [file dirname [file normalize [info script]]]",
        "set build_root [file dirname $script_dir]",
        "set metadata_dir [file join $build_root {metadata}]",
        "file mkdir $metadata_dir",
        "set evidence_path [file join $metadata_dir {catalog_evidence.tsv}]",
        "set catalog_evidence [open $evidence_path {w}]",
        "",
        "array set catalog_patterns {",
    ]
    for family in required_families:
        lines.append(f"  {{{family.family_id}}} {{{family.catalog_pattern}}}")
    lines.extend(["}", "", "array set exact_vlnvs {"])
    for family in required_families:
        if family.vlnv is not None:
            lines.append(f"  {{{family.family_id}}} {{{family.vlnv}}}")
    lines.extend(
        [
            "}",
            "",
            "proc resolve_catalog_ip {family_id} {",
            "  global catalog_patterns exact_vlnvs",
            "  set matches [lsort -dictionary [get_ipdefs -all -quiet $catalog_patterns($family_id)]]",
            "  if {[llength $matches] == 0} {",
            "    error \"required IP family is unavailable: $family_id\"",
            "  }",
            "  if {[info exists exact_vlnvs($family_id)]} {",
            "    set exact_vlnv $exact_vlnvs($family_id)",
            "    if {[lsearch -exact $matches $exact_vlnv] < 0} {",
            "      error \"required exact IP is unavailable: $exact_vlnv\"",
            "    }",
            "    return $exact_vlnv",
            "  }",
            "  return [lindex $matches end]",
            "}",
            "",
            "puts $catalog_evidence \"meta\\tevidence_schema_version\\t1\"",
            "puts $catalog_evidence \"meta\\tarchitecture_config_sha256\\t$architecture_config_sha256\"",
            "puts $catalog_evidence \"meta\\tgenerated_tcl_sha256\\t$generated_tcl_sha256\"",
            "puts $catalog_evidence \"meta\\tcatalog_request_sha256\\t$catalog_request_sha256\"",
            "puts $catalog_evidence \"meta\\tvivado_version\\t$actual_vivado_version\"",
            "puts $catalog_evidence \"meta\\trun_id\\t[pid]-[clock milliseconds]\"",
            "",
        ]
    )
    for family in required_families:
        lines.extend(
            [
                f"set resolved_vlnv [resolve_catalog_ip {{{family.family_id}}}]",
                f"puts $catalog_evidence \"ip\\t{family.family_id}\\t$resolved_vlnv\"",
            ]
        )
    lines.extend(["", "close $catalog_evidence", ""])
    return "\n".join(lines)


def emit_architecture_realization_tcl(
    config: HardwareArchitectureConfig,
    resolved_vlnv: Mapping[str, str] | None = None,
) -> str:
    """Emit an unconnected BD containing only materialized IP instances."""

    resolutions = {} if resolved_vlnv is None else dict(resolved_vlnv)
    materialized: list[tuple[str, str]] = []
    for instance in config.ip_instances:
        if instance.lifecycle is not IpInstanceLifecycle.MATERIALIZED:
            continue
        family = config.family_by_id(instance.family_ref)
        vlnv = resolutions.get(family.family_id, family.vlnv)
        if vlnv is None:
            raise ValueError(
                f"materialized instance {instance.instance_name} requires a resolved VLNV"
            )
        materialized.append((instance.instance_name, vlnv))

    lines = [
        "# Generated file. Modify the Python architecture source, not this Tcl.",
        "if {[llength [get_projects -quiet]] == 0} {",
        f"  create_project -in_memory -part {{{config.device_part}}}",
        "} else {",
        "  set current_part [get_property PART [current_project]]",
        f"  if {{$current_part ne {{{config.device_part}}}}} {{",
        f'    error "existing project PART mismatch: expected {config.device_part}, got $current_part"',
        "  }",
        "}",
        "if {[current_bd_design -quiet] eq {}} {",
        "  create_bd_design {ip_architecture_skeleton}",
        "}",
        "",
    ]
    for instance_name, vlnv in materialized:
        lines.append(
            f"create_bd_cell -type ip -vlnv {{{vlnv}}} {{{instance_name}}}"
        )
    lines.extend(["", "puts {IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON}", ""])
    return "\n".join(lines)
