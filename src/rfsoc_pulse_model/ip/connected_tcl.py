"""Deterministic Tcl emission for the connected RFDC shell.

The emitter is deliberately a pure transformation.  It neither launches
Vivado nor publishes acceptance state; ``connected_runner`` owns that
transactional boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .connected import ConnectedShellRequest, canonical_connected_json_bytes
from .platform import PsPlatformConfig


_SAFE_TCL_TOKEN = re.compile(r"[A-Za-z0-9_.:+/-]+\Z")
_SAFE_TCL_PROPERTY = re.compile(r"CONFIG\.[A-Za-z0-9_]+(?:__[A-Za-z0-9_]+)*\Z")
_SAFE_RFDC_PROPERTY = re.compile(r"[A-Za-z0-9_]+\Z")
_SAFE_TCL_VALUE = re.compile(r"[^{}\[\]$;\\\r\n]+\Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe(value: str, field: str, *, property_name: bool = False, literal_value: bool = False) -> str:
    pattern = _SAFE_TCL_VALUE if literal_value else (_SAFE_TCL_PROPERTY if property_name else _SAFE_TCL_TOKEN)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{field} is not a safe Tcl token")
    return value


def _property_lines(properties: tuple[tuple[str, str], ...], cell: str) -> list[str]:
    if not properties or len({name for name, _ in properties}) != len(properties):
        raise ValueError("RFDC properties must be a nonempty unique tuple")
    lines = ["set_property -dict [list"]
    for name, value in properties:
        if not isinstance(name, str) or not _SAFE_RFDC_PROPERTY.fullmatch(name):
            raise ValueError("RFDC property is not a safe Tcl token")
        lines.append(f"  {{CONFIG.{name}}} {{{_safe(value, 'RFDC property value', literal_value=True)}}}")
    lines.append(f"] [get_bd_cells {{{_safe(cell, 'RFDC cell')}}}]")
    return lines


@dataclass(frozen=True)
class ConnectedTclArtifacts:
    """All deterministic, non-lifecycle bytes needed for one shell attempt."""

    request_bytes: bytes
    realization_tcl: bytes
    verification_tcl: bytes

    @property
    def request_sha256(self) -> str:
        return _sha256(self.request_bytes)

    @property
    def realization_tcl_sha256(self) -> str:
        return _sha256(self.realization_tcl)

    @property
    def verification_tcl_sha256(self) -> str:
        return _sha256(self.verification_tcl)


def emit_connected_tcl(
    request: ConnectedShellRequest,
    platform: PsPlatformConfig,
    rfdc_properties: tuple[tuple[str, str], ...],
) -> ConnectedTclArtifacts:
    """Emit the exact shell realization and attempt-local verification Tcl.

    ``rfdc_properties`` must come from a parsed Task-4 probe result's exact
    ``applied_config`` tuple.  The public API accepts the tuple instead of a
    raw diagnostic file so this layer never parses TSV or recreates RFDC
    configuration policy.
    """

    if not isinstance(request, ConnectedShellRequest):
        raise ValueError("request must be a ConnectedShellRequest")
    if not isinstance(platform, PsPlatformConfig):
        raise ValueError("platform must be a PsPlatformConfig")
    if request.device_part != platform.device_part:
        raise ValueError("request/platform device part mismatch")
    cells = {cell.name: cell.vlnv for cell in request.cells}
    if len(cells) != 8:
        raise ValueError("request must contain exactly eight unique cells")
    rfdc = next((name for name, vlnv in cells.items() if vlnv == "xilinx.com:ip:usp_rf_data_converter:2.6"), None)
    if rfdc is None:
        raise ValueError("request lacks exact RFDC 2.6 cell")
    for cell_name, vlnv in cells.items():
        _safe(cell_name, "cell name")
        _safe(vlnv, "cell VLNV")
    for interface in request.interfaces:
        _safe(interface.name, "interface name")
    for name, value in platform.properties.items():
        _safe(name, "PS property", property_name=True)
        _safe(value, "PS property value", literal_value=True)

    ps = next(name for name, vlnv in cells.items() if vlnv == platform.ps_vlnv)
    smartconnect = next(name for name, vlnv in cells.items() if ":smartconnect:" in vlnv)
    resets = {item.domain: item for item in request.resets}
    reset_cells = {
        domain: next(member.split("/")[0] for member in resets[domain].dcm_locked_members if "/" in member)
        for domain in ("ctrl", "rx", "tx")
    }
    irq_concat = next(name for name, vlnv in cells.items() if ":xlconcat:" in vlnv)
    inverter = next(name for name, vlnv in cells.items() if ":util_vector_logic:" in vlnv)

    lines = [
        "# Generated file. Modify the Python model, not this Tcl.",
        "if {[llength [get_projects -quiet]] == 0} {",
        f"  create_project -in_memory -part {{{_safe(request.device_part, 'device part')}}}",
        "} else {",
        "  set current_part [get_property PART [current_project]]",
        f"  if {{$current_part ne {{{_safe(request.device_part, 'device part')}}}}} {{",
        f"    error \"existing project PART mismatch: expected {request.device_part}, got $current_part\"",
        "  }",
        "}",
        "if {[current_bd_design -quiet] ne {}} { error {current BD must be empty} }",
        "create_bd_design {connected_rfdc_shell}",
        "",
    ]
    for name in sorted(cells):
        lines.append(f"create_bd_cell -type ip -vlnv {{{cells[name]}}} {{{name}}}")
    lines.extend(["", "# Reviewed processing-system board settings.", "set_property -dict [list"])
    for name, value in sorted(platform.properties.items()):
        lines.append(f"  {{{name}}} {{{value}}}")
    lines.extend([f"] [get_bd_cells {{{ps}}}]", "", "# RFDC settings measured by Task-4 probe."])
    lines.extend(_property_lines(rfdc_properties, rfdc))
    lines.extend([
        "",
        "# 100 MHz AXI-Lite control plane and reset inversion.",
        f"connect_bd_net [get_bd_pins {{{ps}/pl_clk0}}] [get_bd_pins {{{smartconnect}/aclk}}] [get_bd_pins {{{rfdc}/s_axi_aclk}}] [get_bd_pins {{{reset_cells['ctrl']}/slowest_sync_clk}}]",
        f"connect_bd_intf_net [get_bd_intf_pins {{{ps}/M_AXI_HPM0_FPD}}] [get_bd_intf_pins {{{smartconnect}/S00_AXI}}]",
        f"connect_bd_intf_net [get_bd_intf_pins {{{smartconnect}/M00_AXI}}] [get_bd_intf_pins {{{rfdc}/s_axi}}]",
        f"connect_bd_net [get_bd_pins {{{ps}/pl_resetn0}}] [get_bd_pins {{{inverter}/Op1}}]",
        f"connect_bd_net [get_bd_pins {{{inverter}/Res}}] [get_bd_pins {{{reset_cells['ctrl']}/ext_reset_in}}]",
        f"connect_bd_net [get_bd_pins {{{inverter}/Res}}] [get_bd_pins {{{reset_cells['rx']}/ext_reset_in}}]",
        f"connect_bd_net [get_bd_pins {{{inverter}/Res}}] [get_bd_pins {{{reset_cells['tx']}/ext_reset_in}}]",
        "",
        "# Candidate common RX/TX clocks are direct RFDC clock outputs; no CDC is inserted.",
        f"connect_bd_net [get_bd_pins {{{rfdc}/clk_adc0}}] [get_bd_pins {{{rfdc}/m0_axis_aclk}}] [get_bd_pins {{{rfdc}/m1_axis_aclk}}] [get_bd_pins {{{rfdc}/m2_axis_aclk}}] [get_bd_pins {{{rfdc}/m3_axis_aclk}}] [get_bd_pins {{{reset_cells['rx']}/slowest_sync_clk}}]",
        f"connect_bd_net [get_bd_pins {{{rfdc}/clk_dac0}}] [get_bd_pins {{{rfdc}/s0_axis_aclk}}] [get_bd_pins {{{rfdc}/s1_axis_aclk}}] [get_bd_pins {{{reset_cells['tx']}/slowest_sync_clk}}]",
    ])
    for domain in ("ctrl", "rx", "tx"):
        reset = resets[domain]
        lines.extend([
            f"create_bd_port -dir I {{{reset.dcm_locked_pin}}}",
            f"connect_bd_net [get_bd_ports {{{reset.dcm_locked_pin}}}] [get_bd_pins {{{reset_cells[domain]}/dcm_locked}}]",
        ])
        for member in reset.members:
            lines.append(
                f"connect_bd_net [get_bd_pins {{{reset_cells[domain]}/peripheral_aresetn}}] "
                f"[get_bd_pins {{{member}}}]"
            )
    lines.extend([
        "",
        "# RFDC interrupt is explicitly routed to PS IRQ0.",
        f"connect_bd_net [get_bd_pins {{{rfdc}/irq}}] [get_bd_pins {{{irq_concat}/In0}}]",
        f"connect_bd_net [get_bd_pins {{{irq_concat}/dout}}] [get_bd_pins {{{ps}/pl_ps_irq0}}]",
        "",
        "# External names are evidence labels; RFDC internal pins remain the authority.",
    ])
    for interface in request.interfaces:
        lines.append(f"make_bd_intf_pins_external [get_bd_intf_pins {{{rfdc}/{interface.name}}}]")
    lines.extend([
        f"assign_bd_address [get_bd_addr_segs {{{rfdc}/s_axi/Reg}}]",
        "validate_bd_design",
        "save_bd_design",
        "",
    ])
    realization = ("\n".join(lines)).encode("utf-8")
    verification = _emit_verification_tcl(request, _sha256(realization))
    return ConnectedTclArtifacts(
        request_bytes=canonical_connected_json_bytes(request),
        realization_tcl=realization,
        verification_tcl=verification,
    )


def _emit_verification_tcl(request: ConnectedShellRequest, realization_sha256: str) -> bytes:
    """Emit an attempt-local checker.  It has no lifecycle publication command."""

    lines = [
        "# Generated attempt-local verification Tcl; it cannot publish success.",
        "if {![info exists ::env(CONNECTED_CANDIDATE_EVIDENCE)]} { error {CONNECTED_CANDIDATE_EVIDENCE is required} }",
        "if {![info exists ::env(CONNECTED_REPORT_DIR)]} { error {CONNECTED_REPORT_DIR is required} }",
        "set candidate [open $::env(CONNECTED_CANDIDATE_EVIDENCE) {w}]",
        f"puts $candidate {{\"connected_request_sha256\":\"{_sha256(canonical_connected_json_bytes(request))}\",\"realization_tcl_sha256\":\"{realization_sha256}\"}}",
        "close $candidate",
        "report_cdc -file [file join $::env(CONNECTED_REPORT_DIR) {cdc.rpt}]",
        "report_clock_interaction -file [file join $::env(CONNECTED_REPORT_DIR) {clock_interaction.rpt}]",
        "report_timing_summary -file [file join $::env(CONNECTED_REPORT_DIR) {timing_summary.rpt}]",
        "report_utilization -file [file join $::env(CONNECTED_REPORT_DIR) {utilization.rpt}]",
        "",
    ]
    return "\n".join(lines).encode("utf-8")
