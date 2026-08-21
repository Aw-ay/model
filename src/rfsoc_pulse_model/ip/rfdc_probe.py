"""Deterministic RFDC-only diagnostic probe; no runner or connected BD."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from rfsoc_pulse_model.common.config import ModelConfig

from .connected import RfdcProbeProvenance
from .types import HardwareArchitectureConfig, RFDC_2_6_VLNV


RFDC_PROBE_VLNV = RFDC_2_6_VLNV
_VIVADO_VERSION = "2025.2"
_SAFE_TCL_TOKEN = re.compile(r"[A-Za-z0-9_.:+/-]+\Z")
_SAFE_RAW_FIELD = re.compile(r"[^;`$\[\]\\\r\n\t]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MESSAGE_SEVERITIES = ("WARNING", "CRITICAL_WARNING", "ERROR")
_EVIDENCE_KEYS = frozenset({
    "probe_schema_version", "vivado_version", "device_part", "rfdc_vlnv",
    "cells", "applied_config", "interfaces", "scalar_pins", "messages", "validation_errors",
    "mts_property_inventory", "mts_value_readback", "mts_bindings",
    "probe_tcl_sha256", "raw_output_sha256", "run_id",
    "common_rx_clock_legality_verified", "common_tx_clock_legality_verified",
    "mts_configuration_verified", "mts_runtime_verified",
})
_EVIDENCE_KEYS_V3 = _EVIDENCE_KEYS | {"environment_manifest_sha256"}


def _expected_interfaces() -> tuple[tuple[str, str, str, int], ...]:
    values: list[tuple[str, str, str, int]] = []
    for tile in range(4):
        values.append((f"adc{tile}_clk", "Slave", "xilinx.com:interface:diff_clock_rtl:1.0", 0))
    for tile in range(2):
        values.append((f"dac{tile}_clk", "Slave", "xilinx.com:interface:diff_clock_rtl:1.0", 0))
    for tile in range(4):
        for slice_index in range(4):
            values.append((f"m{tile}{slice_index}_axis", "Master", "xilinx.com:interface:axis_rtl:1.0", 32))
    for tile in range(2):
        for slice_index in range(4):
            values.append((f"s{tile}{slice_index}_axis", "Slave", "xilinx.com:interface:axis_rtl:1.0", 64))
    values.extend((
        ("s_axi", "Slave", "xilinx.com:interface:aximm_rtl:1.0", 0),
        ("sysref_in", "Slave", "xilinx.com:display_usp_rf_data_converter:diff_pins_rtl:1.0", 0),
    ))
    for tile in range(4):
        for suffix in ("01", "23"):
            values.append((f"vin{tile}_{suffix}", "Slave", "xilinx.com:interface:diff_analog_io_rtl:1.0", 0))
    for tile in range(2):
        for slice_index in range(4):
            values.append((f"vout{tile}{slice_index}", "Master", "xilinx.com:interface:diff_analog_io_rtl:1.0", 0))
    return tuple(sorted(values))


def _expected_scalar_pins() -> tuple[tuple[str, str, int], ...]:
    values: dict[str, tuple[str, int]] = {"irq": ("O", 1)}
    for tile in range(4):
        values.update({f"adc{tile}_clk_n": ("I", 1), f"adc{tile}_clk_p": ("I", 1), f"clk_adc{tile}": ("O", 1), f"m{tile}_axis_aclk": ("I", 1), f"m{tile}_axis_aresetn": ("I", 1)})
        for slice_index in range(4):
            prefix = f"m{tile}{slice_index}_axis"
            values.update({f"{prefix}_tdata": ("O", 32), f"{prefix}_tready": ("I", 1), f"{prefix}_tvalid": ("O", 1)})
    for tile in range(2):
        values.update({f"dac{tile}_clk_n": ("I", 1), f"dac{tile}_clk_p": ("I", 1), f"clk_dac{tile}": ("O", 1), f"s{tile}_axis_aclk": ("I", 1), f"s{tile}_axis_aresetn": ("I", 1)})
        for slice_index in range(4):
            prefix = f"s{tile}{slice_index}_axis"
            values.update({f"{prefix}_tdata": ("I", 64), f"{prefix}_tready": ("O", 1), f"{prefix}_tvalid": ("I", 1)})
    values.update({
        "s_axi_aclk": ("I", 1), "s_axi_aresetn": ("I", 1), "s_axi_araddr": ("I", 18), "s_axi_arready": ("O", 1), "s_axi_arvalid": ("I", 1), "s_axi_awaddr": ("I", 18), "s_axi_awready": ("O", 1), "s_axi_awvalid": ("I", 1), "s_axi_bready": ("I", 1), "s_axi_bresp": ("O", 2), "s_axi_bvalid": ("O", 1), "s_axi_rdata": ("O", 32), "s_axi_rready": ("I", 1), "s_axi_rresp": ("O", 2), "s_axi_rvalid": ("O", 1), "s_axi_wdata": ("I", 32), "s_axi_wready": ("O", 1), "s_axi_wstrb": ("I", 4), "s_axi_wvalid": ("I", 1), "sysref_in_n": ("I", 1), "sysref_in_p": ("I", 1),
    })
    for tile in range(4):
        for suffix in ("01", "23"):
            values[f"vin{tile}_{suffix}_n"] = ("I", 1); values[f"vin{tile}_{suffix}_p"] = ("I", 1)
    for tile in range(2):
        for slice_index in range(4):
            values[f"vout{tile}{slice_index}_n"] = ("O", 1); values[f"vout{tile}{slice_index}_p"] = ("O", 1)
    return tuple(sorted((name, direction, width) for name, (direction, width) in values.items()))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _pairs(value: object, field: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be an array")
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"{field} entries must be two-element arrays")
        result.append((_text(item[0], field), _text(item[1], field)))
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(sorted(result))


def _message_counts(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, tuple) or len(item) != 2
        or item[0] not in _MESSAGE_SEVERITIES
        or not isinstance(item[1], int) or isinstance(item[1], bool) or item[1] < 0
        for item in value
    ):
        raise ValueError("messages must be immutable severity/count tuples")
    result = tuple(sorted(value, key=lambda item: _MESSAGE_SEVERITIES.index(item[0])))
    if {severity for severity, _ in result} != set(_MESSAGE_SEVERITIES) or len(result) != len(_MESSAGE_SEVERITIES):
        raise ValueError("messages must contain exactly one count for each severe Vivado severity")
    if any(count != 0 for _, count in result):
        raise ValueError("RFDC probe diagnostic severity is not clean")
    return result


@dataclass(frozen=True)
class RfdcProbeInterface:
    name: str
    mode: str
    vlnv: str
    width_bits: int
    frequency_hz: int
    clock_domain: str
    associated_reset: str

    def __post_init__(self) -> None:
        for field in ("name", "mode", "vlnv", "clock_domain", "associated_reset"):
            _text(getattr(self, field), field)
        _integer(self.width_bits, "interface width_bits", 0)
        _integer(self.frequency_hz, "interface frequency_hz", 0)


@dataclass(frozen=True)
class RfdcProbeScalarPin:
    name: str
    direction: str
    width_bits: int
    frequency_hz: int
    clock_domain: str

    def __post_init__(self) -> None:
        _text(self.name, "scalar pin name")
        if self.direction not in {"I", "O", "IO"}:
            raise ValueError("scalar pin direction is invalid")
        _integer(self.width_bits, "scalar pin width_bits", 1)
        _integer(self.frequency_hz, "scalar pin frequency_hz", 0)
        _text(self.clock_domain, "scalar pin clock_domain")


@dataclass(frozen=True)
class RfdcProbeMtsProperty:
    name: str
    value_type: str
    read_only: bool
    current_value: str
    enumerated_values: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.name, "MTS property name")
        _text(self.value_type, "MTS property type")
        _bool(self.read_only, "MTS property read_only")
        _text(self.current_value, "MTS property current_value")
        if not isinstance(self.enumerated_values, tuple) or any(
            not isinstance(item, str) or not item for item in self.enumerated_values
        ):
            raise ValueError("MTS enumerated_values must be an immutable string tuple")
        if len(self.enumerated_values) != len(set(self.enumerated_values)):
            raise ValueError("MTS enumerated_values must not contain duplicates")


@dataclass(frozen=True)
class RfdcProbeResult:
    provenance: RfdcProbeProvenance
    device_part: str
    rfdc_vlnv: str
    cells: tuple[tuple[str, str], ...]
    applied_config: tuple[tuple[str, str], ...]
    interfaces: tuple[RfdcProbeInterface, ...]
    scalar_pins: tuple[RfdcProbeScalarPin, ...]
    messages: tuple[tuple[str, int], ...]
    validation_errors: tuple[str, ...]
    mts_property_inventory: tuple[RfdcProbeMtsProperty, ...]
    mts_value_readback: tuple[tuple[str, str, str], ...]
    mts_bindings: tuple[tuple[str, int, str], ...]
    common_rx_clock_legality_verified: bool
    common_tx_clock_legality_verified: bool
    mts_configuration_verified: bool
    mts_runtime_verified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, RfdcProbeProvenance):
            raise ValueError("provenance must be RfdcProbeProvenance")
        _text(self.device_part, "device_part")
        if self.rfdc_vlnv != RFDC_PROBE_VLNV:
            raise ValueError(f"rfdc_vlnv must be {RFDC_PROBE_VLNV}")
        object.__setattr__(self, "cells", _pairs(self.cells, "cells"))
        object.__setattr__(self, "applied_config", _pairs(self.applied_config, "applied_config"))
        if self.cells != (("rfdc_0", RFDC_PROBE_VLNV),):
            raise ValueError("probe must contain exactly rfdc_0 at RFDC 2.6")
        if not isinstance(self.interfaces, tuple) or any(not isinstance(item, RfdcProbeInterface) for item in self.interfaces):
            raise ValueError("interfaces must be immutable RfdcProbeInterface values")
        if len({item.name for item in self.interfaces}) != len(self.interfaces):
            raise ValueError("interfaces must not contain duplicate names")
        if not isinstance(self.scalar_pins, tuple) or any(not isinstance(item, RfdcProbeScalarPin) for item in self.scalar_pins):
            raise ValueError("scalar_pins must be immutable RfdcProbeScalarPin values")
        if len({item.name for item in self.scalar_pins}) != len(self.scalar_pins):
            raise ValueError("scalar_pins must not contain duplicate names")
        object.__setattr__(self, "messages", _message_counts(self.messages))
        if not isinstance(self.validation_errors, tuple) or any(not isinstance(item, str) for item in self.validation_errors):
            raise ValueError("validation_errors must be an immutable string tuple")
        _validate_mts_authority(
            self.mts_property_inventory, self.mts_value_readback, self.mts_bindings,
        )
        for field in ("common_rx_clock_legality_verified", "common_tx_clock_legality_verified", "mts_configuration_verified", "mts_runtime_verified"):
            if getattr(self, field) is not False:
                raise ValueError(f"{field} must remain unverified in an RFDC-only probe")


def _candidate_properties(model: ModelConfig, architecture: HardwareArchitectureConfig) -> tuple[tuple[str, str], ...]:
    if architecture.rfdc_integration.instance_ref != "rfdc_0":
        raise ValueError("RFDC probe requires rfdc_0")
    if model.device_part != architecture.device_part:
        raise ValueError("ModelConfig and architecture device parts must match")
    properties: dict[str, str] = {}
    for tile in range(4):
        properties[f"ADC{tile}_Enable"] = "1"
        properties[f"ADC{tile}_PLL_Enable"] = "true"
        properties[f"ADC{tile}_Sampling_Rate"] = f"{model.adc_sample_rate_hz / 1_000_000_000:.3f}"
        properties[f"ADC{tile}_Fabric_Freq"] = f"{model.rx_fabric_clock_hz / 1_000_000:.3f}"
    for entry in model.adc_channel_map:
        suffix = f"{entry.rfdc_tile}{entry.rfdc_slice}"
        properties[f"ADC_Slice{suffix}_Enable"] = "true"
        properties[f"ADC_Data_Type{suffix}"] = "1"
        properties[f"ADC_Decimation_Mode{suffix}"] = str(model.rfdc_decimation)
        properties[f"ADC_Data_Width{suffix}"] = "2"
        properties[f"ADC_Mixer_Type{suffix}"] = "2"
        properties[f"ADC_Mixer_Mode{suffix}"] = "0"
        properties[f"ADC_NCO_Freq{suffix}"] = f"{model.center_frequency_hz / 1_000_000_000:.3f}"
    for tile in range(2):
        properties[f"DAC{tile}_Enable"] = "1"
        properties[f"DAC{tile}_PLL_Enable"] = "true"
        properties[f"DAC{tile}_Sampling_Rate"] = f"{model.dac_sample_rate_hz / 1_000_000_000:.3f}"
        properties[f"DAC{tile}_Fabric_Freq"] = f"{model.rx_fabric_clock_hz / 1_000_000:.3f}"
    for entry in model.dac_channel_map:
        suffix = f"{entry.rfdc_tile}{entry.rfdc_slice}"
        properties[f"DAC_Slice{suffix}_Enable"] = "true"
        properties[f"DAC_Data_Type{suffix}"] = "0"
        properties[f"DAC_Interpolation_Mode{suffix}"] = str(model.rfdc_interpolation)
        properties[f"DAC_Data_Width{suffix}"] = "4"
        properties[f"DAC_Mixer_Type{suffix}"] = "2"
        properties[f"DAC_Mixer_Mode{suffix}"] = "0"
        properties[f"DAC_NCO_Freq{suffix}"] = f"{architecture.rfdc_integration.dac_nco_frequency_hz / 1_000_000_000:.3f}"
    return tuple(sorted(properties.items()))


def _expected_mts_binding_keys(model: ModelConfig) -> frozenset[tuple[str, int]]:
    return frozenset(
        {("adc", entry.rfdc_tile) for entry in model.adc_channel_map}
        | {("dac", entry.rfdc_tile) for entry in model.dac_channel_map}
    )


def emit_rfdc_probe_tcl(model: ModelConfig, architecture: HardwareArchitectureConfig) -> str:
    """Emit a fresh exact-part project with exactly one RFDC 2.6 cell."""
    if not isinstance(model, ModelConfig) or not isinstance(architecture, HardwareArchitectureConfig):
        raise ValueError("model and architecture must be validated authorities")
    candidates = _candidate_properties(model, architecture)
    if any(not _SAFE_TCL_TOKEN.fullmatch(name) or not _SAFE_TCL_TOKEN.fullmatch(value) for name, value in candidates):
        raise ValueError("unsafe RFDC candidate Tcl token")
    properties = "\n".join(f"    CONFIG.{name} {{{value}}} \\" for name, value in candidates)
    mts_targets = tuple(sorted(
        {("adc", entry.rfdc_tile) for entry in model.adc_channel_map}
        | {("dac", entry.rfdc_tile) for entry in model.dac_channel_map}
    ))
    mts_target_tcl = " ".join(f"{{{converter} {tile}}}" for converter, tile in mts_targets)
    return f'''# Generated RFDC-only diagnostic probe. Do not edit.
set probe_part {{{model.device_part}}}
set rfdc_probe_message_base(WARNING) [get_msg_config -severity WARNING -count]
set rfdc_probe_message_base(CRITICAL_WARNING) [get_msg_config -severity {{CRITICAL WARNING}} -count]
set rfdc_probe_message_base(ERROR) [get_msg_config -severity ERROR -count]
create_project rfdc_probe ./rfdc_probe_project -part $probe_part -force
create_bd_design rfdc_probe
set rfdc_0 [create_bd_cell -type ip -vlnv {RFDC_PROBE_VLNV} rfdc_0]
set_property -dict [list \\
{properties}
] $rfdc_0
proc rfdc_probe_field {{value}} {{
    if {{[regexp {{[;`$\\[\\]\\\\\\r\\n\\t]}} $value]}} {{ error "unsafe probe field" }}
    return $value
}}
proc rfdc_probe_get {{object property}} {{
    if {{[catch {{get_property $property $object}} value]}} {{ return {{}} }}
    return [rfdc_probe_field $value]
}}
proc rfdc_probe_emit {{kind args}} {{
    set fields [list RFDC_PROBE $kind]
    foreach field $args {{ lappend fields [rfdc_probe_field $field] }}
    puts [join $fields "\\t"]
}}
rfdc_probe_emit VIVADO_VERSION [version -short]
rfdc_probe_emit DEVICE_PART [get_property PART [current_project]]
rfdc_probe_emit CELL [get_property NAME $rfdc_0] [get_property VLNV $rfdc_0]
set rfdc_probe_mts_properties [list]
foreach property [list_property $rfdc_0] {{
    if {{[string match CONFIG.*Multi_Tile_Sync* $property] || [string match CONFIG.*MTS* $property] || $property eq "CONFIG.Sysref_Source"}} {{
        lappend rfdc_probe_mts_properties $property
    }}
}}
set rfdc_probe_mts_properties [lsort -unique $rfdc_probe_mts_properties]
foreach property $rfdc_probe_mts_properties {{
    set metadata [report_property -all -return_string $rfdc_0 $property]
    set metadata_found false
    foreach line [split $metadata "\\n"] {{
        set columns [regexp -all -inline {{\\S+}} $line]
        if {{[llength $columns] == 4 && [lindex $columns 0] eq $property}} {{
            set enumerated [list_property_value $property $rfdc_0]
            if {{[llength $enumerated] == 0}} {{ set enumerated NONE }} else {{ set enumerated [join $enumerated ,] }}
            rfdc_probe_emit MTS_PROPERTY [string range $property 7 end] [lindex $columns 1] [lindex $columns 2] [lindex $columns 3] $enumerated
            set metadata_found true
        }}
    }}
    if {{!$metadata_found}} {{ error "missing RFDC MTS property metadata: $property" }}
}}
set rfdc_probe_mts_tile_targets [list {mts_target_tcl}]
set rfdc_probe_mts_true_dict [list]
set rfdc_probe_mts_false_dict [list]
set rfdc_probe_mts_canonical_properties [list]
foreach target $rfdc_probe_mts_tile_targets {{
    set converter [lindex $target 0]
    set tile [lindex $target 1]
    set matches [list]
    foreach property $rfdc_probe_mts_properties {{
        set short_name [string range $property 7 end]
        if {{[regexp -nocase [format {{^%s%s.*multi.*tile.*sync$}} $converter $tile] $short_name]}} {{
            lappend matches $property
        }}
    }}
    if {{[llength $matches] != 1}} {{
        error "RFDC MTS tile target did not resolve to exactly one measured property: $converter $tile"
    }}
    set property [lindex $matches 0]
    rfdc_probe_emit MTS_BINDING $converter $tile [string range $property 7 end]
    lappend rfdc_probe_mts_canonical_properties $property
    lappend rfdc_probe_mts_true_dict $property true
    lappend rfdc_probe_mts_false_dict $property false
}}
set_property -dict $rfdc_probe_mts_true_dict $rfdc_0
foreach property $rfdc_probe_mts_canonical_properties {{
    rfdc_probe_emit MTS_VALUE [string range $property 7 end] true [get_property $property $rfdc_0]
}}
set_property -dict $rfdc_probe_mts_false_dict $rfdc_0
foreach property $rfdc_probe_mts_canonical_properties {{
    rfdc_probe_emit MTS_VALUE [string range $property 7 end] false [get_property $property $rfdc_0]
}}
foreach property [lsort [list_property $rfdc_0]] {{
    if {{[string match CONFIG.* $property]}} {{ rfdc_probe_emit CONFIG [string range $property 7 end] [rfdc_probe_get $rfdc_0 $property] }}
}}
foreach pin [lsort [get_bd_intf_pins -quiet -of_objects $rfdc_0]] {{
    set width_bytes [rfdc_probe_get $pin CONFIG.TDATA_NUM_BYTES]
    if {{![string is integer -strict $width_bytes]}} {{ set width_bytes 0 }}
    rfdc_probe_emit INTERFACE [get_property NAME $pin] [rfdc_probe_get $pin MODE] [rfdc_probe_get $pin VLNV] [expr {{$width_bytes * 8}}] [rfdc_probe_get $pin FREQ_HZ] [rfdc_probe_get $pin CLK_DOMAIN] [rfdc_probe_get $pin ASSOCIATED_RESET]
}}
foreach pin [lsort [get_bd_pins -quiet -of_objects $rfdc_0]] {{
    set left [rfdc_probe_get $pin LEFT]; set right [rfdc_probe_get $pin RIGHT]; set width 1
    if {{[string is integer -strict $left] && [string is integer -strict $right]}} {{ set width [expr {{abs($left - $right) + 1}}] }}
    rfdc_probe_emit SCALAR_PIN [get_property NAME $pin] [rfdc_probe_get $pin DIR] $width [rfdc_probe_get $pin FREQ_HZ] [rfdc_probe_get $pin CLK_DOMAIN]
}}
foreach validation_error [validate_bd_design -quiet] {{ rfdc_probe_emit VALIDATE $validation_error }}
foreach {{severity vivado_severity}} {{WARNING WARNING CRITICAL_WARNING {{CRITICAL WARNING}} ERROR ERROR}} {{
    set total [get_msg_config -severity $vivado_severity -count]
    set delta [expr {{$total - $rfdc_probe_message_base($severity)}}]
    if {{$delta < 0}} {{ error "RFDC probe message count regressed" }}
    rfdc_probe_emit MESSAGE_COUNT $severity $delta
}}
rfdc_probe_emit END
close_project
'''


def _decode_raw(raw_output: bytes) -> dict[str, Any]:
    if not isinstance(raw_output, bytes) or not raw_output.endswith(b"\n"):
        raise ValueError("raw probe output must be LF-terminated bytes")
    try:
        lines = raw_output.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("raw probe output must be UTF-8") from error
    values: dict[str, Any] = {
        "cells": [], "applied_config": [], "interfaces": [], "scalar_pins": [],
        "messages": [], "validation_errors": [], "mts_property_inventory": [],
        "mts_value_readback": [], "mts_bindings": [],
    }
    seen: set[tuple[str, str]] = set(); ended = False
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 2 or fields[0] != "RFDC_PROBE" or ended:
            raise ValueError("invalid or partial RFDC probe record")
        if any(not _SAFE_RAW_FIELD.fullmatch(field) for field in fields[1:] if field):
            raise ValueError("unsafe RFDC probe record")
        kind = fields[1]
        if kind == "END" and len(fields) == 2: ended = True
        elif kind in {"VIVADO_VERSION", "DEVICE_PART"} and len(fields) == 3:
            if kind in values: raise ValueError(f"duplicate {kind}")
            values[kind] = fields[2]
        elif kind in {"CELL", "CONFIG"} and len(fields) == 4:
            key = (kind, fields[2])
            if key in seen: raise ValueError(f"duplicate {kind}")
            seen.add(key); values["cells" if kind == "CELL" else "applied_config"].append((fields[2], fields[3]))
        elif kind == "INTERFACE" and len(fields) == 9:
            key = (kind, fields[2])
            if key in seen: raise ValueError("duplicate INTERFACE")
            seen.add(key)
            values["interfaces"].append((
                fields[2], fields[3], fields[4], fields[5] or "0",
                fields[6] or "0", fields[7] or "unknown",
                fields[8] or "unknown",
            ))
        elif kind == "SCALAR_PIN" and len(fields) == 7:
            key = (kind, fields[2])
            if key in seen: raise ValueError("duplicate SCALAR_PIN")
            seen.add(key)
            values["scalar_pins"].append((
                fields[2], fields[3], fields[4] or "0", fields[5] or "0",
                fields[6] or "unknown",
            ))
        elif kind == "MTS_PROPERTY" and len(fields) == 7:
            key = (kind, fields[2])
            if key in seen: raise ValueError("duplicate MTS_PROPERTY")
            seen.add(key)
            values["mts_property_inventory"].append(tuple(fields[2:]))
        elif kind == "MTS_VALUE" and len(fields) == 5:
            key = (kind, f"{fields[2]}\0{fields[3]}")
            if key in seen: raise ValueError("duplicate MTS_VALUE")
            seen.add(key)
            values["mts_value_readback"].append(tuple(fields[2:]))
        elif kind == "MTS_BINDING" and len(fields) == 5:
            key = (kind, f"{fields[2]}\0{fields[3]}")
            if key in seen: raise ValueError("duplicate MTS_BINDING")
            seen.add(key)
            values["mts_bindings"].append(tuple(fields[2:]))
        elif kind == "MESSAGE_COUNT" and len(fields) == 4:
            severity, count = fields[2:]
            if severity not in _MESSAGE_SEVERITIES or not count.isascii() or not count.isdecimal():
                raise ValueError("invalid RFDC probe MESSAGE_COUNT")
            if any(prior[0] == severity for prior in values["messages"]):
                raise ValueError("duplicate MESSAGE_COUNT")
            values["messages"].append((severity, int(count)))
        elif kind == "VALIDATE" and len(fields) == 3: values["validation_errors"].append(fields[2])
        else: raise ValueError("invalid RFDC probe record")
    if not ended or "VIVADO_VERSION" not in values or "DEVICE_PART" not in values or not values["applied_config"]:
        raise ValueError("partial RFDC probe output")
    return values


def _result_from_raw(
    raw_output: bytes,
    probe_tcl: bytes,
    model: ModelConfig,
    architecture: HardwareArchitectureConfig,
    run_id: int,
    *,
    environment_manifest_sha256: str | None = None,
) -> RfdcProbeResult:
    values = _decode_raw(raw_output)
    if values["VIVADO_VERSION"] != _VIVADO_VERSION: raise ValueError("wrong Vivado version in RFDC probe")
    if values["DEVICE_PART"] != model.device_part or model.device_part != architecture.device_part: raise ValueError("wrong device part in RFDC probe")
    cells = tuple(values["cells"])
    if cells != (("rfdc_0", RFDC_PROBE_VLNV),): raise ValueError("RFDC probe must contain exactly one RFDC 2.6 cell")
    if values["validation_errors"]:
        raise ValueError("RFDC-only probe validation must have no errors")
    messages = _message_counts(tuple(values["messages"]))
    try:
        interfaces = tuple(RfdcProbeInterface(item[0], item[1], item[2], int(item[3]), int(item[4]), item[5], item[6]) for item in values["interfaces"])
        pins = tuple(RfdcProbeScalarPin(item[0], item[1], int(item[2]), int(item[3]), item[4]) for item in values["scalar_pins"])
    except ValueError as error:
        raise ValueError("invalid numeric RFDC probe record") from error
    observed_interfaces = tuple(sorted((item.name, item.mode, item.vlnv, item.width_bits) for item in interfaces))
    if observed_interfaces != _expected_interfaces():
        raise ValueError("RFDC probe interface inventory mismatch")
    observed_pins = tuple(sorted((item.name, item.direction, item.width_bits) for item in pins))
    if observed_pins != _expected_scalar_pins():
        raise ValueError("RFDC probe scalar pin inventory mismatch")
    applied_config = tuple(values["applied_config"])
    _validate_applied_config(applied_config, model, architecture)
    mts_inventory = tuple(sorted([
        RfdcProbeMtsProperty(
            item[0], item[1], _raw_boolean(item[2], "MTS property read_only"),
            item[3], () if item[4] == "NONE" else tuple(item[4].split(",")),
        )
        for item in values["mts_property_inventory"]
    ], key=lambda item: item.name))
    mts_readback = tuple(sorted(values["mts_value_readback"]))
    try:
        mts_bindings = tuple(sorted(
            (item[0], int(item[1]), item[2]) for item in values["mts_bindings"]
        ))
    except (TypeError, ValueError) as error:
        raise ValueError("invalid RFDC MTS binding record") from error
    _validate_mts_authority(
        mts_inventory, mts_readback, mts_bindings,
        _expected_mts_binding_keys(model),
    )
    return RfdcProbeResult(
        RfdcProbeProvenance(
            _VIVADO_VERSION,
            _sha256(probe_tcl),
            _sha256(raw_output),
            _integer(run_id, "run_id", 1),
            environment_manifest_sha256,
        ),
        model.device_part, RFDC_PROBE_VLNV, cells, applied_config, interfaces, pins,
        messages, (), mts_inventory, mts_readback, mts_bindings,
        False, False, False, False,
    )


def _validate_applied_config(applied_config: tuple[tuple[str, str], ...], model: ModelConfig, architecture: HardwareArchitectureConfig) -> None:
    """Bind measured writable CONFIG values to caller-owned RFDC semantics."""
    config = dict(applied_config)
    if len(config) != len(applied_config):
        raise ValueError("duplicate RFDC CONFIG property")
    # The probe records the complete writable CONFIG inventory returned by
    # Vivado.  It is normally larger than the requested semantic candidate
    # set, so the measured inventory must contain the candidate set rather
    # than equal it.  Connected realization applies the exact candidate
    # subset; the remaining measured properties stay evidence-only.
    expected = _candidate_properties(model, architecture)
    candidates = dict(expected)
    if len(candidates) != len(expected):
        raise ValueError("RFDC probe candidate properties must be unique")
    missing = sorted(set(candidates) - set(config))
    if missing:
        raise ValueError("RFDC applied CONFIG whitelist is incomplete: " + ",".join(missing))
    mismatches = sorted(name for name, value in candidates.items() if config[name] != value)
    if mismatches:
        raise ValueError("RFDC applied CONFIG semantic mismatch: " + ",".join(mismatches))


def _raw_boolean(value: str, field: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{field} must be canonical true or false")


def _validate_mts_authority(
    inventory: tuple[RfdcProbeMtsProperty, ...],
    readback: tuple[tuple[str, str, str], ...],
    bindings: tuple[tuple[str, int, str], ...],
    expected_binding_keys: frozenset[tuple[str, int]] | None = None,
) -> None:
    """Validate measured MTS metadata and its semantic tile-to-property binding.

    The probe is allowed to discover the vendor's exact property names.  The
    model only owns the semantic converter/tile keys, so a connected build can
    never substitute a guessed CONFIG name for a measured one.
    """
    if not isinstance(inventory, tuple) or any(not isinstance(item, RfdcProbeMtsProperty) for item in inventory):
        raise ValueError("mts_property_inventory must be immutable MTS property values")
    if not inventory or len({item.name for item in inventory}) != len(inventory):
        raise ValueError("RFDC MTS property inventory must be nonempty and unique")
    if any(
        item.value_type != "string"
        or not re.search(r"(?i)(multi.*tile.*sync|(?:^|_)mts(?:_|$)|sysref)", item.name)
        for item in inventory
    ):
        raise ValueError("Vivado 2025.2 RFDC MTS property metadata mismatch")
    if not isinstance(readback, tuple) or any(
        not isinstance(item, tuple) or len(item) != 3
        or any(not isinstance(field, str) or not field for field in item)
        for item in readback
    ):
        raise ValueError("mts_value_readback must be immutable three-field tuples")
    if not isinstance(bindings, tuple) or any(
        not isinstance(item, tuple) or len(item) != 3
        or item[0] not in {"adc", "dac"}
        or not isinstance(item[1], int) or isinstance(item[1], bool) or item[1] < 0
        or not isinstance(item[2], str) or not item[2]
        for item in bindings
    ):
        raise ValueError("mts_bindings must be immutable converter/tile/property tuples")
    binding_keys = {(converter, tile) for converter, tile, _ in bindings}
    binding_names = {name for _, _, name in bindings}
    if len(binding_keys) != len(bindings) or len(binding_names) != len(bindings):
        raise ValueError("mts_bindings must not contain duplicate semantic keys or properties")
    inventory_names = {item.name for item in inventory}
    if not binding_names <= inventory_names:
        raise ValueError("MTS binding refers to a property outside the measured inventory")
    metadata = {item.name: item for item in inventory}
    if any(metadata[name].read_only for name in binding_names):
        raise ValueError("MTS binding refers to a read-only property")
    expected_readback = tuple(sorted(
        (name, value, value)
        for _, _, name in bindings for value in ("false", "true")
    ))
    if readback != expected_readback:
        raise ValueError("Vivado 2025.2 RFDC MTS canonical value/readback mismatch")
    if expected_binding_keys is not None and binding_keys != set(expected_binding_keys):
        raise ValueError("RFDC MTS semantic tile binding does not match the model")


def _result_mapping(result: RfdcProbeResult) -> dict[str, object]:
    payload = {
        "probe_schema_version": 3 if result.provenance.environment_manifest_sha256 else 2,
        "vivado_version": result.provenance.vivado_version,
        "device_part": result.device_part,
        "rfdc_vlnv": result.rfdc_vlnv,
        "cells": [list(item) for item in result.cells],
        "applied_config": [list(item) for item in result.applied_config],
        "interfaces": [
            {"name": item.name, "mode": item.mode, "vlnv": item.vlnv,
             "width_bits": item.width_bits, "frequency_hz": item.frequency_hz,
             "clock_domain": item.clock_domain, "associated_reset": item.associated_reset}
            for item in result.interfaces
        ],
        "scalar_pins": [
            {"name": item.name, "direction": item.direction, "width_bits": item.width_bits,
             "frequency_hz": item.frequency_hz, "clock_domain": item.clock_domain}
            for item in result.scalar_pins
        ],
        "messages": [list(item) for item in result.messages],
        "validation_errors": list(result.validation_errors),
        "mts_property_inventory": [
            {"name": item.name, "value_type": item.value_type, "read_only": item.read_only,
             "current_value": item.current_value,
             "enumerated_values": list(item.enumerated_values)}
            for item in result.mts_property_inventory
        ],
        "mts_value_readback": [list(item) for item in result.mts_value_readback],
        "mts_bindings": [list(item) for item in result.mts_bindings],
        "probe_tcl_sha256": result.provenance.probe_tcl_sha256,
        "raw_output_sha256": result.provenance.raw_output_sha256,
        "run_id": result.provenance.run_id,
        "common_rx_clock_legality_verified": False,
        "common_tx_clock_legality_verified": False,
        "mts_configuration_verified": False,
        "mts_runtime_verified": False,
    }
    if result.provenance.environment_manifest_sha256 is not None:
        payload["environment_manifest_sha256"] = result.provenance.environment_manifest_sha256
    return payload


def canonical_rfdc_probe_json_bytes(result: RfdcProbeResult) -> bytes:
    if not isinstance(result, RfdcProbeResult): raise ValueError("result must be RfdcProbeResult")
    return json.dumps(_result_mapping(result), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def build_rfdc_probe_evidence(
    raw_output: bytes,
    probe_tcl: bytes,
    model: ModelConfig,
    architecture: HardwareArchitectureConfig,
    *,
    run_id: int,
    environment_manifest_bytes: bytes | None = None,
) -> bytes:
    environment_manifest_sha256 = None
    if environment_manifest_bytes is not None:
        from .environment import parse_environment_manifest

        environment_manifest_sha256 = parse_environment_manifest(
            environment_manifest_bytes
        ).sha256
    return canonical_rfdc_probe_json_bytes(_result_from_raw(
        raw_output, probe_tcl, model, architecture, run_id,
        environment_manifest_sha256=environment_manifest_sha256,
    ))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_rfdc_probe_evidence(
    evidence_bytes: bytes,
    probe_tcl: bytes,
    model: ModelConfig,
    architecture: HardwareArchitectureConfig,
    *,
    environment_manifest_sha256: str | None = None,
) -> RfdcProbeResult:
    if not isinstance(evidence_bytes, bytes) or not isinstance(probe_tcl, bytes): raise ValueError("probe evidence and Tcl must be bytes")
    try: values = json.loads(evidence_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("invalid RFDC probe JSON") from error
    if not isinstance(values, dict): raise ValueError("RFDC probe evidence must be an object")
    schema = values.get("probe_schema_version")
    if schema == 2:
        expected_keys = _EVIDENCE_KEYS
    elif schema == 3:
        expected_keys = _EVIDENCE_KEYS_V3
    else:
        raise ValueError("probe_schema_version must be 2 or 3")
    if set(values) != expected_keys: raise ValueError("RFDC probe evidence has unknown or missing keys")
    if environment_manifest_sha256 is not None:
        _sha(environment_manifest_sha256, "environment_manifest_sha256")
        if schema != 3 or values.get("environment_manifest_sha256") != environment_manifest_sha256:
            raise ValueError("RFDC probe environment manifest mismatch")
    interfaces_raw, pins_raw = values["interfaces"], values["scalar_pins"]
    if not isinstance(interfaces_raw, list) or not isinstance(pins_raw, list): raise ValueError("RFDC probe interface fields must be arrays")
    if any(not isinstance(item, dict) for item in interfaces_raw + pins_raw): raise ValueError("RFDC probe interface entries must be objects")
    messages = values["messages"]
    if not isinstance(messages, list) or any(
        not isinstance(item, list) or len(item) != 2
        or not isinstance(item[0], str) or not isinstance(item[1], int) or isinstance(item[1], bool)
        for item in messages
    ): raise ValueError("messages must be severity/count arrays")
    validation = values["validation_errors"]
    if not isinstance(validation, list) or any(not isinstance(item, str) for item in validation): raise ValueError("validation_errors must be string array")
    mts_inventory_raw = values["mts_property_inventory"]
    mts_readback_raw = values["mts_value_readback"]
    mts_bindings_raw = values["mts_bindings"]
    mts_keys = {"name", "value_type", "read_only", "current_value", "enumerated_values"}
    if not isinstance(mts_inventory_raw, list) or any(
        not isinstance(item, dict) or set(item) != mts_keys
        or not isinstance(item["enumerated_values"], list)
        for item in mts_inventory_raw
    ):
        raise ValueError("mts_property_inventory entries must use the exact schema")
    if not isinstance(mts_readback_raw, list) or any(
        not isinstance(item, list) or len(item) != 3 for item in mts_readback_raw
    ):
        raise ValueError("mts_value_readback entries must be three-element arrays")
    if not isinstance(mts_bindings_raw, list) or any(
        not isinstance(item, list) or len(item) != 3 for item in mts_bindings_raw
    ):
        raise ValueError("mts_bindings entries must be three-element arrays")
    result = RfdcProbeResult(
        RfdcProbeProvenance(
            _text(values["vivado_version"], "vivado_version"),
            _sha(values["probe_tcl_sha256"], "probe_tcl_sha256"),
            _sha(values["raw_output_sha256"], "raw_output_sha256"),
            _integer(values["run_id"], "run_id", 1),
            _sha(values["environment_manifest_sha256"], "environment_manifest_sha256")
            if schema == 3 else None,
        ),
        _text(values["device_part"], "device_part"),
        _text(values["rfdc_vlnv"], "rfdc_vlnv"),
        _pairs(values["cells"], "cells"),
        _pairs(values["applied_config"], "applied_config"),
        tuple(RfdcProbeInterface(**item) for item in interfaces_raw),
        tuple(RfdcProbeScalarPin(**item) for item in pins_raw),
        tuple(tuple(item) for item in messages),
        tuple(validation),
        tuple(RfdcProbeMtsProperty(
            name=_text(item["name"], "MTS property name"),
            value_type=_text(item["value_type"], "MTS property type"),
            read_only=_bool(item["read_only"], "MTS property read_only"),
            current_value=_text(item["current_value"], "MTS property current_value"),
            enumerated_values=tuple(item["enumerated_values"]),
        ) for item in mts_inventory_raw),
        tuple(tuple(item) for item in mts_readback_raw),
        tuple((item[0], item[1], item[2]) for item in mts_bindings_raw),
        _bool(values["common_rx_clock_legality_verified"], "common_rx_clock_legality_verified"),
        _bool(values["common_tx_clock_legality_verified"], "common_tx_clock_legality_verified"),
        _bool(values["mts_configuration_verified"], "mts_configuration_verified"),
        _bool(values["mts_runtime_verified"], "mts_runtime_verified"),
    )
    if evidence_bytes != canonical_rfdc_probe_json_bytes(result): raise ValueError("RFDC probe evidence bytes are not canonical")
    if result.provenance.probe_tcl_sha256 != _sha256(probe_tcl): raise ValueError("RFDC probe Tcl hash mismatch")
    if result.device_part != model.device_part or result.device_part != architecture.device_part: raise ValueError("RFDC probe device part mismatch")
    if result.validation_errors:
        raise ValueError("RFDC-only probe validation must have no errors")
    observed_interfaces = tuple(sorted((item.name, item.mode, item.vlnv, item.width_bits) for item in result.interfaces))
    if observed_interfaces != _expected_interfaces():
        raise ValueError("RFDC probe interface inventory mismatch")
    observed_pins = tuple(sorted((item.name, item.direction, item.width_bits) for item in result.scalar_pins))
    if observed_pins != _expected_scalar_pins():
        raise ValueError("RFDC probe scalar pin inventory mismatch")
    _validate_applied_config(result.applied_config, model, architecture)
    _validate_mts_authority(
        result.mts_property_inventory, result.mts_value_readback,
        result.mts_bindings, _expected_mts_binding_keys(model),
    )
    return result
