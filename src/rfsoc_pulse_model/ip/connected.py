"""Pure canonical request and final-evidence contract for the RFDC shell.

This module deliberately knows nothing about Tcl, Vivado invocation, attempt
directories, locks, or lifecycle state.  The runner introduced later owns all
of those side effects and feeds its final evidence bytes back through here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import re
from typing import Any

from rfsoc_pulse_model.common.config import ModelConfig

from .platform import PsPlatformConfig
from .types import HardwareArchitectureConfig


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_VIVADO_VERSION = "2025.2"
_EVIDENCE_KEYS = frozenset({
    "evidence_schema_version", "connected_request_sha256", "model_config_sha256",
    "architecture_config_sha256", "ps_platform_config_sha256", "production_lock_sha256",
    "realization_tcl_sha256", "verification_tcl_sha256", "vivado_version", "device_part",
    "cells", "interfaces", "clocks", "resets", "address_path", "irq_path",
    "rfdc_semantics", "mts_groups", "mts_configuration_verified", "mts_runtime_verified",
    "validate_bd_design_passed", "synthesis_completed", "cdc_safe", "clock_safety_verified",
    "report_hashes",
})
_REQUEST_KEYS = frozenset({
    "request_schema_version", "model_config_sha256", "architecture_config_sha256",
    "ps_platform_config_sha256", "production_lock_sha256", "vivado_version", "device_part",
    "probe_provenance", "cells", "interfaces", "clocks", "resets", "address_path",
    "irq_path", "rfdc_semantics", "mts_groups",
})


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _tuple_text(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be an array")
    result = tuple(_text(item, field) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True)
class RfdcProbeProvenance:
    vivado_version: str
    probe_tcl_sha256: str
    raw_output_sha256: str
    run_id: int

    def __post_init__(self) -> None:
        if self.vivado_version != _VIVADO_VERSION:
            raise ValueError("probe vivado_version must be 2025.2")
        _sha256(self.probe_tcl_sha256, "probe_tcl_sha256")
        _sha256(self.raw_output_sha256, "raw_output_sha256")
        _integer(self.run_id, "run_id", 1)


@dataclass(frozen=True)
class ConnectedAuthorityBytes:
    """Explicit caller-owned provenance bytes bound to validated authorities.

    Task 5 reads/package-locates these bytes.  Task 3 only receives and binds
    them, so it has no hidden installed-resource or filesystem input.
    """

    model_config_bytes: bytes
    architecture_config_bytes: bytes
    ps_platform_config_bytes: bytes
    production_lock_bytes: bytes

    def __post_init__(self) -> None:
        for field in (
            "model_config_bytes", "architecture_config_bytes", "ps_platform_config_bytes",
            "production_lock_bytes",
        ):
            if not isinstance(getattr(self, field), bytes):
                raise ValueError(f"{field} must be immutable bytes")


@dataclass(frozen=True)
class ConnectedCell:
    name: str
    vlnv: str

    def __post_init__(self) -> None:
        _text(self.name, "cell name")
        _text(self.vlnv, "cell vlnv")


@dataclass(frozen=True)
class AxisInterface:
    name: str
    direction: str
    kind: str
    channel: int
    rfdc_tile: int
    rfdc_slice: int
    iq_component: str
    width_bits: int
    clock_net: str
    reset_net: str

    def __post_init__(self) -> None:
        _text(self.name, "interface name")
        if self.direction not in {"master", "slave"}:
            raise ValueError("interface direction must be master or slave")
        if self.kind not in {"adc_component", "dac_complex"}:
            raise ValueError("interface kind is invalid")
        _integer(self.channel, "interface channel")
        _integer(self.rfdc_tile, "interface rfdc_tile")
        _integer(self.rfdc_slice, "interface rfdc_slice")
        if self.iq_component not in {"I", "Q", "IQ"}:
            raise ValueError("interface iq_component is invalid")
        _integer(self.width_bits, "interface width_bits", 1)
        _text(self.clock_net, "interface clock_net")
        _text(self.reset_net, "interface reset_net")


@dataclass(frozen=True)
class ClockNet:
    domain: str
    net: str
    frequency_hz: int
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.domain not in {"ctrl", "rx", "tx"}:
            raise ValueError("clock domain is invalid")
        _text(self.net, "clock net")
        _integer(self.frequency_hz, "clock frequency_hz", 1)
        object.__setattr__(self, "members", _tuple_text(self.members, "clock members"))


@dataclass(frozen=True)
class ResetNet:
    domain: str
    reset_net: str
    clock_net: str
    dcm_locked_pin: str
    dcm_locked_members: tuple[str, ...]
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.domain not in {"ctrl", "rx", "tx"}:
            raise ValueError("reset domain is invalid")
        for field in ("reset_net", "clock_net", "dcm_locked_pin"):
            _text(getattr(self, field), field)
        object.__setattr__(self, "dcm_locked_members", _tuple_text(
            self.dcm_locked_members, "dcm_locked_members"))
        object.__setattr__(self, "members", _tuple_text(self.members, "reset members"))


@dataclass(frozen=True)
class RfdcSemantics:
    adc_tiles: tuple[int, ...]
    adc_slices: tuple[tuple[int, int], ...]
    adc_sample_rate_hz: int
    adc_decimation: int
    dac_tiles: tuple[int, ...]
    dac_slices: tuple[tuple[int, int], ...]
    dac_sample_rate_hz: int
    dac_interpolation: int
    dac_nco_frequency_hz: int
    dac_mixer_mode: str

    def __post_init__(self) -> None:
        for field in ("adc_tiles", "dac_tiles"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(item, int) or isinstance(item, bool) for item in value
            ):
                raise ValueError(f"{field} must be an integer tuple")
        for field in ("adc_slices", "dac_slices"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(item, tuple) or len(item) != 2 or any(
                    not isinstance(part, int) or isinstance(part, bool) for part in item
                ) for item in value
            ):
                raise ValueError(f"{field} must be tile/slice tuples")
        for field in ("adc_sample_rate_hz", "adc_decimation", "dac_sample_rate_hz",
                      "dac_interpolation", "dac_nco_frequency_hz"):
            _integer(getattr(self, field), field, 1)
        if self.dac_mixer_mode != "iq_to_real":
            raise ValueError("dac_mixer_mode must be iq_to_real")


@dataclass(frozen=True)
class MtsGroup:
    converter: str
    tiles: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.converter not in {"adc", "dac"}:
            raise ValueError("MTS converter must be adc or dac")
        if not isinstance(self.tiles, tuple) or not self.tiles or any(
            not isinstance(tile, int) or isinstance(tile, bool) for tile in self.tiles
        ):
            raise ValueError("MTS tiles must be nonempty integer tuple")


@dataclass(frozen=True)
class ConnectedShellRequest:
    request_schema_version: int
    model_config_sha256: str
    architecture_config_sha256: str
    ps_platform_config_sha256: str
    production_lock_sha256: str
    vivado_version: str
    device_part: str
    probe_provenance: RfdcProbeProvenance
    cells: tuple[ConnectedCell, ...]
    interfaces: tuple[AxisInterface, ...]
    clocks: tuple[ClockNet, ...]
    resets: tuple[ResetNet, ...]
    address_path: tuple[str, ...]
    irq_path: tuple[str, ...]
    rfdc_semantics: RfdcSemantics
    mts_groups: tuple[MtsGroup, ...]

    def __post_init__(self) -> None:
        if self.request_schema_version != 1:
            raise ValueError("request_schema_version must be 1")
        for field in ("model_config_sha256", "architecture_config_sha256",
                      "ps_platform_config_sha256", "production_lock_sha256"):
            _sha256(getattr(self, field), field)
        if self.vivado_version != _VIVADO_VERSION:
            raise ValueError("request vivado_version must be 2025.2")
        _text(self.device_part, "request device_part")
        if not isinstance(self.probe_provenance, RfdcProbeProvenance):
            raise ValueError("probe_provenance must be RfdcProbeProvenance")
        _typed_tuple(self.cells, ConnectedCell, "cells")
        _typed_tuple(self.interfaces, AxisInterface, "interfaces")
        _typed_tuple(self.clocks, ClockNet, "clocks")
        _typed_tuple(self.resets, ResetNet, "resets")
        object.__setattr__(self, "address_path", _tuple_text(self.address_path, "address_path"))
        object.__setattr__(self, "irq_path", _tuple_text(self.irq_path, "irq_path"))
        if not isinstance(self.rfdc_semantics, RfdcSemantics):
            raise ValueError("rfdc_semantics must be RfdcSemantics")
        _typed_tuple(self.mts_groups, MtsGroup, "mts_groups")
        _validate_request_shape(self)


@dataclass(frozen=True)
class ConnectedShellEvidence:
    evidence_schema_version: int
    connected_request_sha256: str
    model_config_sha256: str
    architecture_config_sha256: str
    ps_platform_config_sha256: str
    production_lock_sha256: str
    realization_tcl_sha256: str
    verification_tcl_sha256: str
    vivado_version: str
    device_part: str
    cells: tuple[ConnectedCell, ...]
    interfaces: tuple[AxisInterface, ...]
    clocks: tuple[ClockNet, ...]
    resets: tuple[ResetNet, ...]
    address_path: tuple[str, ...]
    irq_path: tuple[str, ...]
    rfdc_semantics: RfdcSemantics
    mts_groups: tuple[MtsGroup, ...]
    mts_configuration_verified: bool
    mts_runtime_verified: bool
    validate_bd_design_passed: bool
    synthesis_completed: bool
    cdc_safe: bool
    clock_safety_verified: bool
    report_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.evidence_schema_version != 1:
            raise ValueError("evidence_schema_version must be 1")
        for field in ("connected_request_sha256", "model_config_sha256",
                      "architecture_config_sha256", "ps_platform_config_sha256",
                      "production_lock_sha256", "realization_tcl_sha256",
                      "verification_tcl_sha256"):
            _sha256(getattr(self, field), field)
        _text(self.vivado_version, "evidence vivado_version")
        _text(self.device_part, "evidence device_part")
        _typed_tuple(self.cells, ConnectedCell, "cells")
        _typed_tuple(self.interfaces, AxisInterface, "interfaces")
        _typed_tuple(self.clocks, ClockNet, "clocks")
        _typed_tuple(self.resets, ResetNet, "resets")
        object.__setattr__(self, "address_path", _tuple_text(self.address_path, "address_path"))
        object.__setattr__(self, "irq_path", _tuple_text(self.irq_path, "irq_path"))
        if not isinstance(self.rfdc_semantics, RfdcSemantics):
            raise ValueError("rfdc_semantics must be RfdcSemantics")
        _typed_tuple(self.mts_groups, MtsGroup, "mts_groups")
        for field in ("mts_configuration_verified", "mts_runtime_verified",
                      "validate_bd_design_passed", "synthesis_completed", "cdc_safe",
                      "clock_safety_verified"):
            _boolean(getattr(self, field), field)
        if not isinstance(self.report_hashes, tuple):
            raise ValueError("report_hashes must be a tuple")
        if any(
            not isinstance(item, tuple) or len(item) != 2
            for item in self.report_hashes
        ):
            raise ValueError("report_hashes must contain immutable name/hash tuples")
        report_hashes = tuple((_text(name, "report name"), _sha256(value, "report hash"))
                              for name, value in self.report_hashes)
        if {name for name, _ in report_hashes} != {
            "cdc", "clock_interaction", "timing_summary", "utilization"
        } or len(report_hashes) != 4:
            raise ValueError("report_hashes must contain exact report set")
        object.__setattr__(self, "report_hashes", tuple(sorted(report_hashes)))


@dataclass(frozen=True)
class ConnectedShellReadiness:
    rfdc_shell_structural_ready: bool
    production_integration_ready: bool
    blocking_reasons: tuple[str, ...]


def _typed_tuple(value: object, item_type: type[Any], field: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{field} must be a tuple of {item_type.__name__}")


def _expected_cells() -> tuple[ConnectedCell, ...]:
    return tuple(sorted((
        ConnectedCell("rfdc_0", "xilinx.com:ip:usp_rf_data_converter:2.6"),
        ConnectedCell("zynq_ultra_ps_e_0", "xilinx.com:ip:zynq_ultra_ps_e:3.5"),
        ConnectedCell("ctrl_smartconnect_0", "xilinx.com:ip:smartconnect:1.0"),
        ConnectedCell("reset_inverter_0", "xilinx.com:ip:util_vector_logic:2.0"),
        ConnectedCell("ctrl_reset_0", "xilinx.com:ip:proc_sys_reset:5.0"),
        ConnectedCell("rx_reset_0", "xilinx.com:ip:proc_sys_reset:5.0"),
        ConnectedCell("tx_reset_0", "xilinx.com:ip:proc_sys_reset:5.0"),
        ConnectedCell("irq_concat_0", "xilinx.com:ip:xlconcat:2.1"),
    ), key=lambda item: item.name))


def _expected_interfaces() -> tuple[AxisInterface, ...]:
    adc_i_names = ("m00_axis", "m02_axis", "m10_axis", "m12_axis", "m20_axis", "m22_axis", "m30_axis", "m32_axis")
    adc_q_names = ("m01_axis", "m03_axis", "m11_axis", "m13_axis", "m21_axis", "m23_axis", "m31_axis", "m33_axis")
    adc_routes = ((0, 0), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2))
    items: list[AxisInterface] = []
    for channel, (i_name, q_name) in enumerate(zip(adc_i_names, adc_q_names, strict=True)):
        tile, slice_number = adc_routes[channel]
        items.extend((
            AxisInterface(i_name, "master", "adc_component", channel, tile,
                          slice_number, "I", 32,
                          "rx_axis_clk", "rx_peripheral_aresetn"),
            AxisInterface(q_name, "master", "adc_component", channel, tile,
                          slice_number, "Q", 32,
                          "rx_axis_clk", "rx_peripheral_aresetn"),
        ))
    for channel, name in enumerate(("s00_axis", "s01_axis", "s02_axis", "s03_axis", "s10_axis", "s11_axis", "s12_axis", "s13_axis")):
        items.append(AxisInterface(name, "slave", "dac_complex", channel, channel // 4,
                                   channel % 4, "IQ", 64,
                                   "tx_axis_clk", "tx_peripheral_aresetn"))
    return tuple(sorted(items, key=lambda item: item.name))


def _expected_clocks() -> tuple[ClockNet, ...]:
    return (
        ClockNet("ctrl", "ctrl_axis_clk", 100_000_000, (
            "zynq_ultra_ps_e_0/pl_clk0", "ctrl_smartconnect_0/aclk", "rfdc_0/s_axi_aclk",
            "ctrl_reset_0/slowest_sync_clk")),
        ClockNet("rx", "rx_axis_clk", 250_000_000, (
            "rfdc_0/clk_adc0", "rfdc_0/m0_axis_aclk", "rfdc_0/m1_axis_aclk",
            "rfdc_0/m2_axis_aclk", "rfdc_0/m3_axis_aclk", "rx_reset_0/slowest_sync_clk")),
        ClockNet("tx", "tx_axis_clk", 250_000_000, (
            "rfdc_0/clk_dac0", "rfdc_0/s0_axis_aclk", "rfdc_0/s1_axis_aclk",
            "tx_reset_0/slowest_sync_clk")),
    )


def _expected_resets() -> tuple[ResetNet, ...]:
    return (
        ResetNet("ctrl", "ctrl_peripheral_aresetn", "ctrl_axis_clk", "ctrl_clock_locked",
                 ("ctrl_clock_locked", "ctrl_reset_0/dcm_locked"),
                 ("ctrl_smartconnect_0/aresetn", "rfdc_0/s_axi_aresetn")),
        ResetNet("rx", "rx_peripheral_aresetn", "rx_axis_clk", "rx_clock_locked",
                 ("rx_clock_locked", "rx_reset_0/dcm_locked"),
                 ("rfdc_0/m0_axis_aresetn", "rfdc_0/m1_axis_aresetn",
                  "rfdc_0/m2_axis_aresetn", "rfdc_0/m3_axis_aresetn")),
        ResetNet("tx", "tx_peripheral_aresetn", "tx_axis_clk", "tx_clock_locked",
                 ("tx_clock_locked", "tx_reset_0/dcm_locked"),
                 ("rfdc_0/s0_axis_aresetn", "rfdc_0/s1_axis_aresetn")),
    )


def _expected_semantics() -> RfdcSemantics:
    return RfdcSemantics(
        adc_tiles=(0, 1, 2, 3), adc_slices=((0, 0), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)),
        adc_sample_rate_hz=4_000_000_000, adc_decimation=8, dac_tiles=(0, 1),
        dac_slices=((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)),
        dac_sample_rate_hz=4_000_000_000, dac_interpolation=8,
        dac_nco_frequency_hz=2_800_000_000, dac_mixer_mode="iq_to_real",
    )


def build_connected_request(
    model: ModelConfig, architecture: HardwareArchitectureConfig, platform: PsPlatformConfig,
    production_lock: Mapping[str, object], probe_provenance: RfdcProbeProvenance,
    authority_bytes: ConnectedAuthorityBytes,
) -> ConnectedShellRequest:
    """Create the side-effect-free canonical shell request from frozen authority."""

    if not isinstance(model, ModelConfig) or not isinstance(architecture, HardwareArchitectureConfig):
        raise ValueError("model and architecture must be validated authority objects")
    if not isinstance(platform, PsPlatformConfig) or not isinstance(probe_provenance, RfdcProbeProvenance):
        raise ValueError("platform and probe_provenance must be validated authority objects")
    if not isinstance(authority_bytes, ConnectedAuthorityBytes):
        raise ValueError("authority_bytes must be ConnectedAuthorityBytes")
    if model.device_part != architecture.device_part or model.device_part != platform.device_part:
        raise ValueError("authority device parts must match")
    if architecture.vivado_version != platform.vivado_version or probe_provenance.vivado_version != architecture.vivado_version:
        raise ValueError("authority Vivado versions must match")
    _bind_authority_bytes(model, architecture, platform, production_lock, authority_bytes)
    return ConnectedShellRequest(
        request_schema_version=1,
        model_config_sha256=hashlib.sha256(authority_bytes.model_config_bytes).hexdigest(),
        architecture_config_sha256=hashlib.sha256(authority_bytes.architecture_config_bytes).hexdigest(),
        ps_platform_config_sha256=hashlib.sha256(authority_bytes.ps_platform_config_bytes).hexdigest(),
        production_lock_sha256=hashlib.sha256(authority_bytes.production_lock_bytes).hexdigest(),
        vivado_version=architecture.vivado_version, device_part=model.device_part,
        probe_provenance=probe_provenance, cells=_expected_cells(),
        interfaces=_expected_interfaces(), clocks=_expected_clocks(),
        resets=_expected_resets(),
        address_path=("zynq_ultra_ps_e_0/M_AXI_HPM0_FPD", "ctrl_smartconnect_0/S00_AXI",
                      "ctrl_smartconnect_0/M00_AXI", "rfdc_0/s_axi"),
        irq_path=("rfdc_0/irq", "irq_concat_0/In0", "irq_concat_0/dout", "zynq_ultra_ps_e_0/pl_ps_irq0"),
        rfdc_semantics=_expected_semantics(),
        mts_groups=(MtsGroup("adc", (0, 1, 2, 3)), MtsGroup("dac", (0, 1))),
    )


def _strict_json_mapping(raw_bytes: bytes, field: str) -> Mapping[str, object]:
    if not isinstance(raw_bytes, bytes):
        raise ValueError(f"{field} must be bytes")
    try:
        value = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{field} must be strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must contain a JSON object")
    return value


def _bind_authority_bytes(
    model: ModelConfig, architecture: HardwareArchitectureConfig, platform: PsPlatformConfig,
    production_lock: Mapping[str, object], authority_bytes: ConnectedAuthorityBytes,
) -> None:
    """Bind each explicit byte input to its caller-supplied validated object."""

    if not isinstance(production_lock, Mapping):
        raise ValueError("production_lock must be a mapping")
    model_payload = _strict_json_mapping(authority_bytes.model_config_bytes, "model_config_bytes")
    architecture_payload = _strict_json_mapping(authority_bytes.architecture_config_bytes, "architecture_config_bytes")
    platform_payload = _strict_json_mapping(authority_bytes.ps_platform_config_bytes, "ps_platform_config_bytes")
    lock_payload = _strict_json_mapping(authority_bytes.production_lock_bytes, "production_lock_bytes")
    try:
        parsed_model = ModelConfig.from_mapping(model_payload)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"model_config_bytes are invalid: {error}") from error
    try:
        parsed_architecture = HardwareArchitectureConfig.from_mapping(architecture_payload)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"architecture_config_bytes are invalid: {error}") from error
    try:
        parsed_platform = PsPlatformConfig.from_mapping(platform_payload)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"ps_platform_config_bytes are invalid: {error}") from error
    try:
        from .lock import decode_production_lock_json
        parsed_lock = decode_production_lock_json(authority_bytes.production_lock_bytes, "production_lock_bytes")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"production_lock_bytes are invalid: {error}") from error
    if parsed_model != model:
        raise ValueError("model_config_bytes do not bind to model authority")
    if parsed_architecture != architecture:
        raise ValueError("architecture_config_bytes do not bind to architecture authority")
    if parsed_platform != platform:
        raise ValueError("ps_platform_config_bytes do not bind to platform authority")
    if parsed_lock != production_lock or lock_payload != production_lock:
        raise ValueError("production_lock_bytes do not bind to production_lock")


def _validate_request_shape(request: ConnectedShellRequest) -> None:
    if len(request.cells) != 8 or len({item.name for item in request.cells}) != 8:
        raise ValueError("request must contain exactly eight unique cells")
    if len(request.interfaces) != 24 or len({item.name for item in request.interfaces}) != 24:
        raise ValueError("request must contain exactly 24 unique interfaces")
    if len(request.clocks) != 3 or {item.domain for item in request.clocks} != {"ctrl", "rx", "tx"}:
        raise ValueError("request must contain exact control/RX/TX clocks")
    if len(request.resets) != 3 or {item.domain for item in request.resets} != {"ctrl", "rx", "tx"}:
        raise ValueError("request must contain exact control/RX/TX resets")
    if len({item.reset_net for item in request.resets}) != 3:
        raise ValueError("request reset domains must be separate")
    if request.device_part != "xczu27dr-fsve1156-2-i":
        raise ValueError("request device part must match frozen connected shell")
    if request.cells != _expected_cells():
        raise ValueError("request cells must match frozen connected shell contract")
    if request.interfaces != _expected_interfaces():
        raise ValueError("request interfaces must match frozen connected shell contract")
    if request.clocks != _expected_clocks():
        raise ValueError("request clocks must match frozen connected shell contract")
    if request.resets != _expected_resets():
        raise ValueError("request resets must match frozen connected shell contract")
    if request.address_path != (
        "zynq_ultra_ps_e_0/M_AXI_HPM0_FPD", "ctrl_smartconnect_0/S00_AXI",
        "ctrl_smartconnect_0/M00_AXI", "rfdc_0/s_axi",
    ):
        raise ValueError("request address path must match frozen connected shell contract")
    if request.irq_path != (
        "rfdc_0/irq", "irq_concat_0/In0", "irq_concat_0/dout", "zynq_ultra_ps_e_0/pl_ps_irq0",
    ):
        raise ValueError("request IRQ path must match frozen connected shell contract")
    if request.rfdc_semantics != _expected_semantics():
        raise ValueError("request RFDC semantics must match frozen connected shell contract")
    if request.mts_groups != (MtsGroup("adc", (0, 1, 2, 3)), MtsGroup("dac", (0, 1))):
        raise ValueError("request MTS groups must match frozen connected shell contract")


def _normalise(value: object) -> object:
    if is_dataclass(value):
        return _normalise(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_normalise(item) for item in value]
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def canonical_connected_json_bytes(value: object) -> bytes:
    """Encode a request/evidence mapping with the project canonical JSON rules."""

    normalised = _normalise(value)
    if not isinstance(normalised, Mapping):
        raise ValueError("connected JSON root must be an object")
    return json.dumps(
        normalised, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode(raw_bytes: bytes, label: str) -> Mapping[str, object]:
    if not isinstance(raw_bytes, bytes):
        raise ValueError(f"{label} must be bytes")
    try:
        payload = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"unable to decode {label}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], keys: set[str] | frozenset[str], field: str) -> None:
    if set(value) != set(keys):
        raise ValueError(f"{field} has unknown or missing keys")


def _object_tuple(value: object, parser: Any, field: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return tuple(parser(_mapping(item, field)) for item in value)


def _cell(value: Mapping[str, object]) -> ConnectedCell:
    _exact_keys(value, {"name", "vlnv"}, "cell")
    return ConnectedCell(_text(value["name"], "cell.name"), _text(value["vlnv"], "cell.vlnv"))


def _interface(value: Mapping[str, object]) -> AxisInterface:
    keys = {"name", "direction", "kind", "channel", "rfdc_tile", "rfdc_slice",
            "iq_component", "width_bits", "clock_net", "reset_net"}
    _exact_keys(value, keys, "interface")
    return AxisInterface(_text(value["name"], "interface.name"), _text(value["direction"], "interface.direction"),
                         _text(value["kind"], "interface.kind"), _integer(value["channel"], "interface.channel"),
                         _integer(value["rfdc_tile"], "interface.rfdc_tile"), _integer(value["rfdc_slice"], "interface.rfdc_slice"),
                         _text(value["iq_component"], "interface.iq_component"), _integer(value["width_bits"], "interface.width_bits", 1),
                         _text(value["clock_net"], "interface.clock_net"), _text(value["reset_net"], "interface.reset_net"))


def _clock(value: Mapping[str, object]) -> ClockNet:
    _exact_keys(value, {"domain", "net", "frequency_hz", "members"}, "clock")
    return ClockNet(_text(value["domain"], "clock.domain"), _text(value["net"], "clock.net"),
                    _integer(value["frequency_hz"], "clock.frequency_hz", 1), _tuple_text(value["members"], "clock.members"))


def _reset(value: Mapping[str, object]) -> ResetNet:
    keys = {"domain", "reset_net", "clock_net", "dcm_locked_pin", "dcm_locked_members", "members"}
    _exact_keys(value, keys, "reset")
    return ResetNet(_text(value["domain"], "reset.domain"), _text(value["reset_net"], "reset.reset_net"),
                    _text(value["clock_net"], "reset.clock_net"), _text(value["dcm_locked_pin"], "reset.dcm_locked_pin"),
                    _tuple_text(value["dcm_locked_members"], "reset.dcm_locked_members"),
                    _tuple_text(value["members"], "reset.members"))


def _semantics(value: Mapping[str, object]) -> RfdcSemantics:
    keys = {"adc_tiles", "adc_slices", "adc_sample_rate_hz", "adc_decimation", "dac_tiles", "dac_slices", "dac_sample_rate_hz", "dac_interpolation", "dac_nco_frequency_hz", "dac_mixer_mode"}
    _exact_keys(value, keys, "rfdc_semantics")
    def ints(name: str) -> tuple[int, ...]:
        raw = value[name]
        if not isinstance(raw, list): raise ValueError(f"rfdc_semantics.{name} must be an array")
        return tuple(_integer(item, f"rfdc_semantics.{name}") for item in raw)
    def pairs(name: str) -> tuple[tuple[int, int], ...]:
        raw = value[name]
        if not isinstance(raw, list): raise ValueError(f"rfdc_semantics.{name} must be an array")
        result=[]
        for item in raw:
            if not isinstance(item, list) or len(item) != 2: raise ValueError(f"rfdc_semantics.{name} must contain pairs")
            result.append((_integer(item[0], name), _integer(item[1], name)))
        return tuple(result)
    return RfdcSemantics(ints("adc_tiles"), pairs("adc_slices"), _integer(value["adc_sample_rate_hz"], "adc_sample_rate_hz", 1),
                         _integer(value["adc_decimation"], "adc_decimation", 1), ints("dac_tiles"), pairs("dac_slices"),
                         _integer(value["dac_sample_rate_hz"], "dac_sample_rate_hz", 1), _integer(value["dac_interpolation"], "dac_interpolation", 1),
                         _integer(value["dac_nco_frequency_hz"], "dac_nco_frequency_hz", 1), _text(value["dac_mixer_mode"], "dac_mixer_mode"))


def _mts(value: Mapping[str, object]) -> MtsGroup:
    _exact_keys(value, {"converter", "tiles"}, "mts_group")
    raw = value["tiles"]
    if not isinstance(raw, list): raise ValueError("mts_group.tiles must be an array")
    return MtsGroup(_text(value["converter"], "mts_group.converter"), tuple(_integer(item, "mts_group.tiles") for item in raw))


def _probe(value: Mapping[str, object]) -> RfdcProbeProvenance:
    _exact_keys(value, {"vivado_version", "probe_tcl_sha256", "raw_output_sha256", "run_id"}, "probe_provenance")
    return RfdcProbeProvenance(_text(value["vivado_version"], "probe.vivado_version"), _sha256(value["probe_tcl_sha256"], "probe_tcl_sha256"),
                               _sha256(value["raw_output_sha256"], "raw_output_sha256"), _integer(value["run_id"], "probe.run_id", 1))


def parse_connected_request(raw_bytes: bytes) -> ConnectedShellRequest:
    payload = _decode(raw_bytes, "connected request")
    _exact_keys(payload, _REQUEST_KEYS, "connected request")
    request = ConnectedShellRequest(
        _integer(payload["request_schema_version"], "request_schema_version", 1),
        _sha256(payload["model_config_sha256"], "model_config_sha256"), _sha256(payload["architecture_config_sha256"], "architecture_config_sha256"),
        _sha256(payload["ps_platform_config_sha256"], "ps_platform_config_sha256"), _sha256(payload["production_lock_sha256"], "production_lock_sha256"),
        _text(payload["vivado_version"], "vivado_version"), _text(payload["device_part"], "device_part"), _probe(_mapping(payload["probe_provenance"], "probe_provenance")),
        _object_tuple(payload["cells"], _cell, "cells"), _object_tuple(payload["interfaces"], _interface, "interfaces"),
        _object_tuple(payload["clocks"], _clock, "clocks"), _object_tuple(payload["resets"], _reset, "resets"),
        _tuple_text(payload["address_path"], "address_path"), _tuple_text(payload["irq_path"], "irq_path"),
        _semantics(_mapping(payload["rfdc_semantics"], "rfdc_semantics")), _object_tuple(payload["mts_groups"], _mts, "mts_groups"))
    if raw_bytes != canonical_connected_json_bytes(request):
        raise ValueError("connected request bytes are not canonical")
    return request


def parse_connected_evidence(raw_bytes: bytes) -> ConnectedShellEvidence:
    payload = _decode(raw_bytes, "connected evidence")
    _exact_keys(payload, _EVIDENCE_KEYS, "connected evidence")
    reports = payload["report_hashes"]
    if not isinstance(reports, list): raise ValueError("report_hashes must be an array")
    report_pairs=[]
    for item in reports:
        if not isinstance(item, list) or len(item) != 2: raise ValueError("report_hashes must contain pairs")
        report_pairs.append((_text(item[0], "report name"), _sha256(item[1], "report hash")))
    evidence = ConnectedShellEvidence(
        _integer(payload["evidence_schema_version"], "evidence_schema_version", 1),
        *(_sha256(payload[field], field) for field in ("connected_request_sha256", "model_config_sha256", "architecture_config_sha256", "ps_platform_config_sha256", "production_lock_sha256", "realization_tcl_sha256", "verification_tcl_sha256")),
        _text(payload["vivado_version"], "vivado_version"), _text(payload["device_part"], "device_part"),
        _object_tuple(payload["cells"], _cell, "cells"), _object_tuple(payload["interfaces"], _interface, "interfaces"),
        _object_tuple(payload["clocks"], _clock, "clocks"), _object_tuple(payload["resets"], _reset, "resets"),
        _tuple_text(payload["address_path"], "address_path"), _tuple_text(payload["irq_path"], "irq_path"),
        _semantics(_mapping(payload["rfdc_semantics"], "rfdc_semantics")), _object_tuple(payload["mts_groups"], _mts, "mts_groups"),
        *(_boolean(payload[field], field) for field in ("mts_configuration_verified", "mts_runtime_verified", "validate_bd_design_passed", "synthesis_completed", "cdc_safe", "clock_safety_verified")),
        tuple(report_pairs))
    if raw_bytes != canonical_connected_json_bytes(evidence):
        raise ValueError("connected evidence bytes are not canonical")
    return evidence


def validate_connected_evidence(request: ConnectedShellRequest, evidence: ConnectedShellEvidence) -> ConnectedShellReadiness:
    """Return deterministic structural readiness; never elevate global readiness."""

    if not isinstance(request, ConnectedShellRequest) or not isinstance(evidence, ConnectedShellEvidence):
        raise ValueError("request and evidence must use connected contract types")
    reasons: list[str] = []
    expected_request_sha = hashlib.sha256(canonical_connected_json_bytes(request)).hexdigest()
    if evidence.connected_request_sha256 != expected_request_sha: reasons.append("request_hash_mismatch")
    for field in ("model_config_sha256", "architecture_config_sha256", "ps_platform_config_sha256", "production_lock_sha256"):
        if getattr(evidence, field) != getattr(request, field): reasons.append(f"{field}_mismatch")
    if evidence.device_part != request.device_part: reasons.append("part_mismatch")
    if evidence.vivado_version != request.vivado_version: reasons.append("vivado_version_mismatch")
    if evidence.cells != request.cells: reasons.append("cell_set_mismatch")
    if {item.name for item in evidence.interfaces} != {item.name for item in request.interfaces}:
        reasons.append("interface_set_mismatch")
    elif evidence.interfaces != request.interfaces:
        by_name = {item.name: item for item in evidence.interfaces}
        expected = {item.name: item for item in request.interfaces}
        if any(by_name[name].iq_component != expected[name].iq_component for name in expected): reasons.append("iq_identity_mismatch")
        elif any(by_name[name].width_bits != expected[name].width_bits for name in expected): reasons.append("interface_width_mismatch")
        else: reasons.append("interface_contract_mismatch")
    if evidence.clocks != request.clocks: reasons.append("clock_membership_mismatch")
    if evidence.resets != request.resets:
        if len({item.reset_net for item in evidence.resets}) != len(evidence.resets): reasons.append("reset_domain_reuse")
        elif any(item.dcm_locked_pin != next(expected.dcm_locked_pin for expected in request.resets if expected.domain == item.domain) or item.dcm_locked_members != next(expected.dcm_locked_members for expected in request.resets if expected.domain == item.domain) for item in evidence.resets if item.domain in {"ctrl", "rx", "tx"}): reasons.append("dcm_locked_membership_mismatch")
        else: reasons.append("reset_membership_mismatch")
    if evidence.address_path != request.address_path: reasons.append("address_path_mismatch")
    if evidence.irq_path != request.irq_path: reasons.append("irq_path_mismatch")
    if evidence.rfdc_semantics != request.rfdc_semantics: reasons.append("rfdc_semantics_mismatch")
    if evidence.mts_groups != request.mts_groups: reasons.append("mts_group_mismatch")
    if not evidence.mts_configuration_verified: reasons.append("mts_configuration_unverified")
    if evidence.mts_runtime_verified: reasons.append("mts_runtime_overclaim")
    if not evidence.validate_bd_design_passed: reasons.append("validate_bd_design_failed")
    if not evidence.synthesis_completed: reasons.append("synthesis_failed")
    if not evidence.cdc_safe: reasons.append("cdc_unsafe")
    if not evidence.clock_safety_verified: reasons.append("clock_safety_failed")
    return ConnectedShellReadiness(not reasons, False, tuple(reasons))
