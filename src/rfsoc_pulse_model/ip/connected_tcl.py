"""Pure, deterministic realization/readback Tcl for the connected RFDC shell."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .connected import ConnectedShellRequest, canonical_connected_json_bytes
from .platform import PsPlatformConfig
from .rfdc_probe import RfdcProbeInterface, RfdcProbeResult


_TOKEN = re.compile(r"[A-Za-z0-9_.:+/-]+\Z")
_VALUE = re.compile(r"[^{}\[\]$;`\\\r\n]+\Z")
_RF_PROPERTY = re.compile(r"[A-Za-z0-9_]+\Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _token(value: str, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{field} is not a safe Tcl token")
    return value


def _value(value: str, field: str) -> str:
    if not isinstance(value, str) or not _VALUE.fullmatch(value):
        raise ValueError(f"{field} is not safe for Tcl braces")
    return value


@dataclass(frozen=True)
class ConnectedTclArtifacts:
    request_bytes: bytes
    realization_tcl: bytes
    verification_tcl: bytes
    rfdc_properties: tuple[tuple[str, str], ...]
    rfdc_interfaces: tuple[RfdcProbeInterface, ...]
    ps_properties: tuple[tuple[str, str], ...]
    external_rf_interfaces: tuple[RfdcProbeInterface, ...]
    mts_properties: tuple[tuple[str, str], ...]

    @property
    def request_sha256(self) -> str: return _sha(self.request_bytes)
    @property
    def realization_tcl_sha256(self) -> str: return _sha(self.realization_tcl)
    @property
    def verification_tcl_sha256(self) -> str: return _sha(self.verification_tcl)


def _external_rf_interfaces(items: tuple[RfdcProbeInterface, ...]) -> tuple[RfdcProbeInterface, ...]:
    if not isinstance(items, tuple) or any(not isinstance(item, RfdcProbeInterface) for item in items):
        raise ValueError("rfdc_interfaces must be Task-4 RfdcProbeInterface values")
    expected = {"adc0_clk", "adc1_clk", "adc2_clk", "adc3_clk", "dac0_clk", "dac1_clk", "sysref_in"}
    expected |= {f"vin{tile}_{suffix}" for tile in range(4) for suffix in ("01", "23")}
    expected |= {f"vout{tile}{index}" for tile in range(2) for index in range(4)}
    selected = tuple(sorted((item for item in items if item.name in expected), key=lambda item: item.name))
    if {item.name for item in selected} != expected:
        raise ValueError("Task-4 RF reference/SYSREF/analogue inventory is incomplete")
    return selected


def _request_rfdc_property_names(request: ConnectedShellRequest) -> frozenset[str]:
    """Return the exact CONFIG names allowed to cross into connected Tcl.

    The Task-4 probe keeps the full Vivado CONFIG readback inventory.  The
    connected request carries the model's semantic tile/slice selection, so
    it can reconstruct the exact candidate-name whitelist without promoting
    arbitrary measured properties into the production realization.
    """
    semantics = request.rfdc_semantics
    for field in ("adc_slices", "dac_slices"):
        value = getattr(semantics, field)
        if len(value) != len(set(value)):
            raise ValueError(f"request contains duplicate {field}")
    names: set[str] = set()
    for tile in range(4):
        names.update({
            f"ADC{tile}_Enable", f"ADC{tile}_PLL_Enable",
            f"ADC{tile}_Sampling_Rate", f"ADC{tile}_Fabric_Freq",
        })
    for tile, slice_index in semantics.adc_slices:
        if tile not in range(4) or slice_index not in range(4):
            raise ValueError("request contains an invalid ADC RFDC tile/slice")
        suffix = f"{tile}{slice_index}"
        names.update({
            f"ADC_Slice{suffix}_Enable", f"ADC_Data_Type{suffix}",
            f"ADC_Decimation_Mode{suffix}", f"ADC_Data_Width{suffix}",
            f"ADC_Mixer_Type{suffix}", f"ADC_Mixer_Mode{suffix}",
            f"ADC_NCO_Freq{suffix}",
        })
    for tile in range(2):
        names.update({
            f"DAC{tile}_Enable", f"DAC{tile}_PLL_Enable",
            f"DAC{tile}_Sampling_Rate", f"DAC{tile}_Fabric_Freq",
        })
    for tile, slice_index in semantics.dac_slices:
        if tile not in range(2) or slice_index not in range(4):
            raise ValueError("request contains an invalid DAC RFDC tile/slice")
        suffix = f"{tile}{slice_index}"
        names.update({
            f"DAC_Slice{suffix}_Enable", f"DAC_Data_Type{suffix}",
            f"DAC_Interpolation_Mode{suffix}", f"DAC_Data_Width{suffix}",
            f"DAC_Mixer_Type{suffix}", f"DAC_Mixer_Mode{suffix}",
            f"DAC_NCO_Freq{suffix}",
        })
    return frozenset(names)


def _apply_required_mts(
    request: ConnectedShellRequest, probe: RfdcProbeResult,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Promote only the exact per-tile MTS names proven by the Task-4 probe."""
    measured = dict(probe.applied_config)
    if len(measured) != len(probe.applied_config):
        raise ValueError("RFDC properties must be unique")
    allowed = _request_rfdc_property_names(request)
    missing = sorted(allowed - set(measured))
    if missing:
        raise ValueError("RFDC CONFIG whitelist is incomplete: " + ",".join(missing))
    configured = {name: measured[name] for name in allowed}
    authority: dict[tuple[str, int], str] = {}
    inventory_names = {item.name for item in probe.mts_property_inventory}
    for converter, tile, name in probe.mts_bindings:
        key = (converter, tile)
        if key in authority or name not in inventory_names:
            raise ValueError("Task-4 MTS binding is not canonical")
        authority[key] = name
    readbacks = set(probe.mts_value_readback)
    for name in authority.values():
        if (name, "false", "false") not in readbacks or (name, "true", "true") not in readbacks:
            raise ValueError("Task-4 MTS readback is not canonical")
    requested_tiles = {
        (group.converter, tile) for group in request.mts_groups for tile in group.tiles
    }
    if set(authority) != requested_tiles:
        raise ValueError("Task-4 MTS authority does not match the requested tile groups")
    expected: list[tuple[str, str]] = []
    for group in request.mts_groups:
        for tile in group.tiles:
            name = authority[(group.converter, tile)]
            configured[name] = "true"
            expected.append((name, "true"))
    return tuple(sorted(configured.items())), tuple(sorted(expected))


def emit_connected_tcl(
    request: ConnectedShellRequest,
    platform: PsPlatformConfig,
    probe: RfdcProbeResult,
) -> ConnectedTclArtifacts:
    """Emit disk-backed realization plus complete machine-readback protocol.

    The verification Tcl emits only actual readback TSV and reports.  The
    runner converts that protocol into Task-3 canonical evidence after hashing
    reports, so Tcl never has to implement JSON or SHA-256.
    """
    if not isinstance(request, ConnectedShellRequest) or not isinstance(platform, PsPlatformConfig):
        raise ValueError("request and platform must be validated authority objects")
    if not isinstance(probe, RfdcProbeResult):
        raise ValueError("probe must be a validated Task-4 RfdcProbeResult")
    if request.device_part != platform.device_part: raise ValueError("request/platform device part mismatch")
    cells = {cell.name: cell.vlnv for cell in request.cells}
    if len(cells) != 8: raise ValueError("request must contain exactly eight cells")
    rfdc = next((name for name, vlnv in cells.items() if vlnv == "xilinx.com:ip:usp_rf_data_converter:2.6"), None)
    if rfdc is None: raise ValueError("request lacks exact RFDC 2.6")
    for name, vlnv in cells.items(): _token(name, "cell name"); _token(vlnv, "cell VLNV")
    for name, value in platform.properties.items(): _token(name, "PS property"); _value(value, "PS property value")
    if not probe.applied_config or len(set(probe.applied_config)) != len(probe.applied_config): raise ValueError("RFDC properties must be unique and nonempty")
    for name, value in probe.applied_config:
        if not isinstance(name, str) or not _RF_PROPERTY.fullmatch(name): raise ValueError("RFDC property is unsafe")
        _value(value, "RFDC property value")
    effective_rfdc_properties, mts_properties = _apply_required_mts(request, probe)
    effective_ps_properties = dict(platform.properties)
    if effective_ps_properties.get("CONFIG.PSU__USE__M_AXI_GP2", "0") != "0":
        raise ValueError("connected RFDC shell requires the unused HPM0_LPD master to be disabled")
    # The reviewed shell owns HPM0_FPD only. Vivado's PS default also
    # exposes HPM0_LPD, so make that non-owned path explicitly unavailable.
    effective_ps_properties["CONFIG.PSU__USE__M_AXI_GP2"] = "0"
    external_rf = _external_rf_interfaces(probe.interfaces)
    ps = next(name for name, vlnv in cells.items() if vlnv == platform.ps_vlnv)
    smart = next(name for name, vlnv in cells.items() if ":smartconnect:" in vlnv)
    inverter = next(name for name, vlnv in cells.items() if ":util_vector_logic:" in vlnv)
    irq = next(name for name, vlnv in cells.items() if ":xlconcat:" in vlnv)
    resets = {reset.domain: reset for reset in request.resets}
    reset_cells = {domain: next(member.split("/")[0] for member in resets[domain].dcm_locked_members if "/" in member) for domain in ("ctrl", "rx", "tx")}
    lines = [
        "# Generated. Edit the Python model, never this Tcl.",
        "if {![info exists ::env(CONNECTED_PROJECT_DIR)]} { error {CONNECTED_PROJECT_DIR is required} }",
        "if {[llength [get_projects -quiet]] == 0} {",
        f"  create_project connected_rfdc_shell $::env(CONNECTED_PROJECT_DIR) -part {{{_token(request.device_part, 'part')}}}",
        "} else {",
        f"  if {{[get_property PART [current_project]] ne {{{_token(request.device_part, 'part')}}}}} {{ error {{existing project PART mismatch}} }}",
        "}",
        "if {[current_bd_design -quiet] ne {}} { error {current BD must be empty} }",
        "create_bd_design {connected_rfdc_shell}",
    ]
    for name in sorted(cells): lines.append(f"create_bd_cell -type ip -vlnv {{{cells[name]}}} {{{name}}}")
    lines += ["set_property -dict [list \\"]
    lines += [f"  {{{name}}} {{{value}}} \\" for name, value in sorted(effective_ps_properties.items())]
    lines += [f"] [get_bd_cells {{{ps}}}]", "set_property -dict [list \\"]
    lines += [f"  {{CONFIG.{name}}} {{{value}}} \\" for name, value in effective_rfdc_properties]
    lines += [f"] [get_bd_cells {{{rfdc}}}]", f"set_property -dict [list {{CONFIG.C_OPERATION}} {{not}} {{CONFIG.C_SIZE}} {{1}}] [get_bd_cells {{{inverter}}}]", f"set_property -dict [list {{CONFIG.NUM_PORTS}} {{1}}] [get_bd_cells {{{irq}}}]"]
    # Named nets make readback compare names, not Vivado-created aliases.
    lines += [
        "create_bd_net {ctrl_axis_clk}", f"connect_bd_net [get_bd_nets {{ctrl_axis_clk}}] [get_bd_pins {{{ps}/pl_clk0}}] [get_bd_pins {{{ps}/maxihpm0_fpd_aclk}}] [get_bd_pins {{{smart}/aclk}}] [get_bd_pins {{{rfdc}/s_axi_aclk}}] [get_bd_pins {{{reset_cells['ctrl']}/slowest_sync_clk}}]",
        "create_bd_net {rx_axis_clk}", f"connect_bd_net [get_bd_nets {{rx_axis_clk}}] [get_bd_pins {{{rfdc}/clk_adc0}}] [get_bd_pins {{{rfdc}/m0_axis_aclk}}] [get_bd_pins {{{rfdc}/m1_axis_aclk}}] [get_bd_pins {{{rfdc}/m2_axis_aclk}}] [get_bd_pins {{{rfdc}/m3_axis_aclk}}] [get_bd_pins {{{reset_cells['rx']}/slowest_sync_clk}}]",
        "create_bd_net {tx_axis_clk}", f"connect_bd_net [get_bd_nets {{tx_axis_clk}}] [get_bd_pins {{{rfdc}/clk_dac0}}] [get_bd_pins {{{rfdc}/s0_axis_aclk}}] [get_bd_pins {{{rfdc}/s1_axis_aclk}}] [get_bd_pins {{{reset_cells['tx']}/slowest_sync_clk}}]",
        f"connect_bd_intf_net [get_bd_intf_pins {{{ps}/M_AXI_HPM0_FPD}}] [get_bd_intf_pins {{{smart}/S00_AXI}}]",
        f"connect_bd_intf_net [get_bd_intf_pins {{{smart}/M00_AXI}}] [get_bd_intf_pins {{{rfdc}/s_axi}}]",
        f"connect_bd_net [get_bd_pins {{{ps}/pl_resetn0}}] [get_bd_pins {{{inverter}/Op1}}]",
    ]
    for domain in ("ctrl", "rx", "tx"):
        reset = resets[domain]; cell = reset_cells[domain]
        lines += [f"connect_bd_net [get_bd_pins {{{inverter}/Res}}] [get_bd_pins {{{cell}/ext_reset_in}}]", f"create_bd_net {{{reset.reset_net}}}", f"create_bd_port -dir I {{{reset.dcm_locked_pin}}}", f"connect_bd_net [get_bd_ports {{{reset.dcm_locked_pin}}}] [get_bd_pins {{{cell}/dcm_locked}}]"]
        for member in reset.members: lines.append(f"connect_bd_net [get_bd_nets {{{reset.reset_net}}}] [get_bd_pins {{{cell}/peripheral_aresetn}}] [get_bd_pins {{{member}}}]")
    lines += [f"connect_bd_net [get_bd_pins {{{rfdc}/irq}}] [get_bd_pins {{{irq}/In0}}]", f"connect_bd_net [get_bd_pins {{{irq}/dout}}] [get_bd_pins {{{ps}/pl_ps_irq0}}]"]
    lines += [
        f"set rfdc_adc_axis_freq_mhz [get_property CONFIG.ADC0_Outclk_Freq [get_bd_cells {{{rfdc}}}]]",
        f"set rfdc_dac_axis_freq_mhz [get_property CONFIG.DAC0_Outclk_Freq [get_bd_cells {{{rfdc}}}]]",
    ]
    for interface in request.interfaces:
        lines.append(f"make_bd_intf_pins_external [get_bd_intf_pins {{{rfdc}/{interface.name}}}]")
        if re.fullmatch(r"m\d\d_axis", interface.name):
            lines.append(
                f"set_property CONFIG.FREQ_HZ [expr {{int(round(1000000.0 * $rfdc_adc_axis_freq_mhz))}}] "
                f"[get_bd_intf_ports {{{interface.name}_0}}]"
            )
        elif re.fullmatch(r"s\d\d_axis", interface.name):
            lines.append(
                f"set_property CONFIG.FREQ_HZ [expr {{int(round(1000000.0 * $rfdc_dac_axis_freq_mhz))}}] "
                f"[get_bd_intf_ports {{{interface.name}_0}}]"
            )
    for interface in external_rf: lines.append(f"make_bd_intf_pins_external [get_bd_intf_pins {{{rfdc}/{interface.name}}}]")
    lines += [f"assign_bd_address [get_bd_addr_segs {{{rfdc}/s_axi/Reg}}]", "validate_bd_design", "save_bd_design", ""]
    realization = "\n".join(lines).encode("utf-8")
    effective_ps_properties_tuple = tuple(sorted(effective_ps_properties.items()))
    verification = _emit_verification(request, rfdc, effective_rfdc_properties, effective_ps_properties_tuple, external_rf, mts_properties, _sha(realization))
    return ConnectedTclArtifacts(canonical_connected_json_bytes(request), realization, verification, effective_rfdc_properties, probe.interfaces, effective_ps_properties_tuple, external_rf, mts_properties)


def _emit_verification(request: ConnectedShellRequest, rfdc: str, properties: tuple[tuple[str, str], ...], ps_properties: tuple[tuple[str, str], ...], external_rf: tuple[RfdcProbeInterface, ...], mts_properties: tuple[tuple[str, str], ...], realization_sha: str) -> bytes:
    lines = [
        "# Generated readback protocol; runner alone publishes lifecycle state.",
        "foreach key {CONNECTED_READBACK_TSV CONNECTED_REPORT_DIR CONNECTED_VERIFICATION_TCL_SHA256} { if {![info exists ::env($key)]} { error \"$key is required\" } }",
        "set connected_out [open $::env(CONNECTED_READBACK_TSV) {w}]",
        "proc connected_emit {kind args} { global connected_out; foreach value $args { if {[regexp {[;`$\\[\\]\\\\\\r\\n\\t]} $value]} { error {unsafe readback field} } }; puts $connected_out [join [concat CONNECTED_READBACK $kind $args] \"\\t\"] }",
        f"connected_emit META request_sha256 {_sha(canonical_connected_json_bytes(request))}",
        f"connected_emit META realization_tcl_sha256 {realization_sha}",
        "connected_emit META verification_tcl_sha256 $::env(CONNECTED_VERIFICATION_TCL_SHA256)",
        "connected_emit META vivado_version [version -short]", "connected_emit META device_part [get_property PART [current_project]]",
        "set validate_result [validate_bd_design -quiet]", "if {[llength $validate_result] != 0} { error {validate_bd_design returned violations} }", "set connected_bd_design [get_bd_designs -quiet connected_rfdc_shell]", "if {[llength $connected_bd_design] != 1} { error {connected BD design is not unique} }", "set connected_bd_file [get_files -quiet [get_property FILE_NAME $connected_bd_design]]", "if {[llength $connected_bd_file] != 1} { error {connected BD file is not unique} }", "generate_target all $connected_bd_file", "set wrapper [make_wrapper -files $connected_bd_file -top]", "add_files -norecurse $wrapper", "set_property top connected_rfdc_shell_wrapper [current_fileset]", "set synth_run [get_runs -quiet synth_1]", "if {[llength $synth_run] != 1} { error {synth_1 run is not unique} }", "set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects $synth_run", "connected_emit META synthesis_mode out_of_context", "connected_emit META axis_boundary bd_external_interfaces", "launch_runs synth_1 -jobs 1", "wait_on_run synth_1", "set synth_status [get_property STATUS [get_runs synth_1]]", "if {$synth_status ne {synth_design Complete!}} { error {synthesis incomplete} }", "open_run synth_1",
        "report_cdc -details -file [file join $::env(CONNECTED_REPORT_DIR) {cdc.rpt}]", "report_clock_interaction -file [file join $::env(CONNECTED_REPORT_DIR) {clock_interaction.rpt}]", "report_timing_summary -report_unconstrained -no_detailed_paths -file [file join $::env(CONNECTED_REPORT_DIR) {timing_summary.rpt}]", "report_utilization -file [file join $::env(CONNECTED_REPORT_DIR) {utilization.rpt}]",
    ]
    lines += [
        "connected_emit META timing_scope ooc_boundary_only",
        "set vendor_waiver_user {USP_RF_DATA_CONVERTER}",
        "set vendor_waiver_tag {1033132}",
        "set vendor_adc_from {}",
        "set vendor_adc_to {}",
        "foreach tile {0 1 2 3} {",
        "  set vendor_adc_from_candidates [get_pins -hier -quiet -filter [format {NAME =~ */rfdc_0/inst/adc%d_cmn_control_ff_reg*} $tile]]",
        "  set vendor_adc_to_candidates [get_pins -hier -quiet -filter [format {NAME =~ */rfdc_0/inst/connected_*_rf_wrapper_i/rx%d_u_adc/CONTROL_COMMON*} $tile]]",
        "  set from_pin {}",
        "  foreach candidate $vendor_adc_from_candidates {",
        "    set candidate_name [get_property NAME $candidate]",
        "    if {[regexp [format {adc%d_cmn_control_ff_reg\\[12\\]/C$} $tile] $candidate_name]} { lappend from_pin $candidate }",
        "  }",
        "  set to_pin {}",
        "  foreach candidate $vendor_adc_to_candidates {",
        "    set candidate_name [get_property NAME $candidate]",
        "    if {[regexp [format {rx%d_u_adc/CONTROL_COMMON\\[12\\]$} $tile] $candidate_name]} { lappend to_pin $candidate }",
        "  }",
        "  if {[llength $from_pin] != 1 || [llength $to_pin] != 1} { error {AMD RFDC CDC-13 waiver endpoint discovery mismatch} }",
        "  lappend vendor_adc_from $from_pin",
        "  lappend vendor_adc_to $to_pin",
        "}",
        "create_waiver -user $vendor_waiver_user -type CDC -id CDC-13 -tags $vendor_waiver_tag -description {Passing the MTS FIFO enable from the management to the fabric clock} -from $vendor_adc_from -to $vendor_adc_to",
        "set vendor_ipif_to [get_pins -hier -filter {NAME =~ */IP2Bus_Data_reg* && REF_PIN_NAME == D}]",
        "if {[llength $vendor_ipif_to] != 32} { error {AMD RFDC CDC waiver IPIF endpoint inventory mismatch} }",
        "set vendor_marker_cntr_from [get_pins -hier -filter {NAME =~ */i_rf_conv_mt_mrk_counter_adc*/*mrk_cntr_ff_reg* && REF_PIN_NAME == C}]",
        "set vendor_marker_loc_from [get_pins -hier -filter {NAME =~ */i_rf_conv_mt_mrk_counter_adc*/*mrk_loc_ff_reg* && REF_PIN_NAME == C}]",
        "set vendor_adc_internal_from [get_pins -hier -filter {NAME =~ */connected_*_rf_wrapper_i/rx*_u_adc/INTERNAL_FBRC_DIV2_MUX}]",
        "set vendor_dac_internal_from [get_pins -hier -filter {NAME =~ */connected_*_rf_wrapper_i/tx*_u_dac/INTERNAL_FBRC_MUX}]",
        "if {[llength $vendor_marker_cntr_from] == 0 || [llength $vendor_marker_loc_from] == 0 || [llength $vendor_adc_internal_from] != 4 || [llength $vendor_dac_internal_from] != 2} { error {AMD RFDC CDC-15 waiver endpoint inventory mismatch} }",
        "create_waiver -user $vendor_waiver_user -type CDC -id CDC-15 -tags $vendor_waiver_tag -description {Passing the marker counter signals from the fabric to the management clock} -from $vendor_marker_cntr_from -to $vendor_ipif_to",
        "create_waiver -user $vendor_waiver_user -type CDC -id CDC-15 -tags $vendor_waiver_tag -description {Passing the marker counter signals from the fabric to the management clock} -from $vendor_marker_loc_from -to $vendor_ipif_to",
        "create_waiver -user $vendor_waiver_user -type CDC -id CDC-15 -tags $vendor_waiver_tag -description {Passing DAC and ADC outputs to the status registers} -from $vendor_adc_internal_from -to $vendor_ipif_to",
        "create_waiver -user $vendor_waiver_user -type CDC -id CDC-15 -tags $vendor_waiver_tag -description {Passing DAC and ADC outputs to the status registers} -from $vendor_dac_internal_from -to $vendor_ipif_to",
        "report_cdc -details -show_waiver -file [file join $::env(CONNECTED_REPORT_DIR) {cdc.rpt}]",
    ]
    for cell in request.cells: lines.append(f"connected_emit CELL {cell.name} [get_property VLNV [get_bd_cells {{{cell.name}}}]]")
    ps = next(cell.name for cell in request.cells if cell.vlnv == "xilinx.com:ip:zynq_ultra_ps_e:3.5")
    inverter = next(cell.name for cell in request.cells if ":util_vector_logic:" in cell.vlnv)
    concat = next(cell.name for cell in request.cells if ":xlconcat:" in cell.vlnv)
    for name, _ in ps_properties: lines.append(f"connected_emit PS_CONFIG {name} [get_property {name} [get_bd_cells {{{ps}}}]]")
    for name, _ in properties: lines.append(f"connected_emit CONFIG {name} [get_property CONFIG.{name} [get_bd_cells {{{rfdc}}}]]")
    for name, _ in mts_properties: lines.append(f"connected_emit MTS {name} [get_property CONFIG.{name} [get_bd_cells {{{rfdc}}}]]")
    for item in request.interfaces: lines.append(f"connected_emit DATA {item.name} [get_property MODE [get_bd_intf_pins {{{rfdc}/{item.name}}}]] [get_property VLNV [get_bd_intf_pins {{{rfdc}/{item.name}}}]] [get_property CONFIG.TDATA_NUM_BYTES [get_bd_intf_pins {{{rfdc}/{item.name}}}]]")
    for item in external_rf: lines.append(f"connected_emit RF {item.name} [get_property MODE [get_bd_intf_pins {{{rfdc}/{item.name}}}]] [get_property VLNV [get_bd_intf_pins {{{rfdc}/{item.name}}}]]")
    lines.append(f"connected_emit INVERTER C_OPERATION [get_property CONFIG.C_OPERATION [get_bd_cells {{{inverter}}}]] C_SIZE [get_property CONFIG.C_SIZE [get_bd_cells {{{inverter}}}]]")
    lines.append(f"connected_emit CONCAT NUM_PORTS [get_property CONFIG.NUM_PORTS [get_bd_cells {{{concat}}}]]")
    # actual generated external names are checked as an exact inventory by their
    # authoritative internal source pins.
    for item in request.interfaces: lines.append(f"connected_emit PORT {item.name} [get_property NAME [get_bd_intf_ports {{{item.name}_0}}]]")
    for item in external_rf: lines.append(f"connected_emit PORT {item.name} [get_property NAME [get_bd_intf_ports {{{item.name}_0}}]]")
    for clock in request.clocks:
        for member in clock.members: lines.append(f"connected_emit CLOCK {clock.domain} {member} [get_property NAME [get_bd_nets -of_objects [get_bd_pins {{{member}}}]]]")
    for reset in request.resets:
        for member in reset.members:
            lines.append(f"connected_emit RESET {reset.domain} {member} [get_property NAME [get_bd_nets -of_objects [get_bd_pins {{{member}}}]]]")
        lines.append(f"connected_emit LOCK {reset.domain} {reset.dcm_locked_pin} [get_property NAME [get_bd_nets -of_objects [get_bd_pins {{{reset.dcm_locked_members[-1]}}}]]]")
    lines += [
        "connected_emit ADDRESS rfdc_0/s_axi/Reg [get_bd_addr_segs rfdc_0/s_axi/Reg]", "connected_emit IRQ rfdc_0/irq irq_concat_0/In0 irq_concat_0/dout zynq_ultra_ps_e_0/pl_ps_irq0",
        "connected_emit BOOL validate_bd_design_passed [expr {[llength $validate_result] == 0 ? \"true\" : \"false\"}]", "connected_emit BOOL synthesis_completed [expr {$synth_status eq {synth_design Complete!} ? \"true\" : \"false\"}]", "connected_emit BOOL mts_runtime_verified false", "connected_emit END", "close $connected_out", "",
    ]
    return "\n".join(lines).encode("utf-8")
