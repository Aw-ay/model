"""Vivado Tcl emission for the deliberately unconnected IP skeleton."""

from __future__ import annotations

from .registry import ArchitectureRegistry
from .types import HardwareArchitectureConfig, ImplementationKind


_INITIAL_SKELETON_IP = (
    "axis_register_slice",
    "axis_data_fifo",
    "axis_clock_converter",
    "axis_dwidth_converter",
    "axis_combiner",
    "axis_broadcaster",
    "axis_switch",
    "fir_compiler",
)


def emit_ip_skeleton_tcl(
    config: HardwareArchitectureConfig,
    registry: ArchitectureRegistry,
) -> str:
    """Emit a catalog-resolving, unconnected Vivado Block Design skeleton."""

    rfdc = registry.by_name(config.rfdc.ip.logical_name)
    if (
        rfdc.kind is not ImplementationKind.AMD_IP
        or not rfdc.production
        or rfdc.vlnv != config.rfdc.ip.vlnv
    ):
        raise ValueError("RFDC registry ownership does not match architecture config")

    specs = {spec.logical_name: spec for spec in config.required_ip_families}
    for logical_name in _INITIAL_SKELETON_IP:
        block = registry.by_name(logical_name)
        if block.kind is not ImplementationKind.AMD_IP or not block.production:
            raise ValueError(f"{logical_name} must be a production AMD IP block")
        if logical_name not in specs:
            raise ValueError(f"missing catalog pattern for {logical_name}")

    lines = [
        "# Generated file. Modify the Python architecture source, not this Tcl.",
        "set required_vivado_prefix {2025.2}",
        "set actual_vivado_version [version -short]",
        "if {![string match ${required_vivado_prefix}* $actual_vivado_version]} {",
        "  error \"Vivado 2025.2 is required, got $actual_vivado_version\"",
        "}",
        "",
        "if {[llength [get_projects -quiet]] == 0} {",
        "  create_project -in_memory -part {xczu27dr-fsve1156-2-i}",
        "}",
        "if {[current_bd_design -quiet] eq {}} {",
        "  create_bd_design {ip_architecture_skeleton}",
        "}",
        "",
        "set script_dir [file dirname [file normalize [info script]]]",
        "set build_root [file dirname $script_dir]",
        "set metadata_dir [file join $build_root {metadata}]",
        "file mkdir $metadata_dir",
        "set evidence_path [file join $metadata_dir {resolved_ip_vlnv.tsv}]",
        "set resolved_ip_evidence [open $evidence_path {w}]",
        "",
        "proc require_exact_ip {vlnv} {",
        "  set matches [get_ipdefs -all -quiet $vlnv]",
        "  if {[lsearch -exact $matches $vlnv] < 0} {",
        "    error \"required exact IP is unavailable: $vlnv\"",
        "  }",
        "  return $vlnv",
        "}",
        "",
        "array set catalog_patterns {",
    ]
    for logical_name in _INITIAL_SKELETON_IP:
        lines.append(
            f"  {{{logical_name}}} {{{specs[logical_name].catalog_pattern}}}"
        )
    lines.extend(
        [
            "}",
            "",
            "proc resolve_catalog_ip {logical_name} {",
            "  global catalog_patterns resolved_ip_evidence",
            "  if {![info exists catalog_patterns($logical_name)]} {",
            "    error \"no catalog pattern for $logical_name\"",
            "  }",
            "  set matches [lsort -dictionary [get_ipdefs -all -quiet $catalog_patterns($logical_name)]]",
            "  if {[llength $matches] == 0} {",
            "    error \"required IP family is unavailable: $logical_name\"",
            "  }",
            "  set resolved_vlnv [lindex $matches end]",
            "  puts $resolved_ip_evidence \"$logical_name\\t$resolved_vlnv\"",
            "  return $resolved_vlnv",
            "}",
            "",
            f"set rfdc_vlnv {{{config.rfdc.ip.vlnv}}}",
            "require_exact_ip $rfdc_vlnv",
            "puts $resolved_ip_evidence \"rfdc\\t$rfdc_vlnv\"",
            "create_bd_cell -type ip -vlnv $rfdc_vlnv rfdc",
            "",
        ]
    )
    for logical_name in _INITIAL_SKELETON_IP:
        lines.extend(
            [
                f"set resolved_vlnv [resolve_catalog_ip {{{logical_name}}}]",
                f"create_bd_cell -type ip -vlnv $resolved_vlnv {{{logical_name}}}",
                "",
            ]
        )
    lines.extend(
        [
            "close $resolved_ip_evidence",
            f"set topology_status {{{config.topology_status}}}",
            "set integration_accepted 0",
            "puts {IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON}",
            "",
        ]
    )
    return "\n".join(lines)
