"""Typed, immutable authority for Vivado and AMD IP integration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib import resources
import json
from typing import Any


RFDC_2_6_VLNV = "xilinx.com:ip:usp_rf_data_converter:2.6"
_RFDC_OWNED_FUNCTIONS = frozenset(
    {"adc", "dac", "ddc", "duc", "decimation", "interpolation", "mixer", "nco"}
)


class ImplementationKind(str, Enum):
    """Permitted implementation owners in the IP-first architecture."""

    AMD_IP = "amd_ip"
    XPM_MACRO = "xpm_macro"
    CUSTOM_RTL = "custom_rtl"
    CUSTOM_HLS = "custom_hls"
    SOFTWARE_ONLY = "software_only"
    LEGACY_NON_PRODUCTION = "legacy_non_production"


def _require_nonempty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be nonempty")


@dataclass(frozen=True)
class ExternalIpSpec:
    """One external IP requirement, optionally locked to an exact VLNV."""

    logical_name: str
    kind: ImplementationKind
    catalog_pattern: str
    vlnv: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.logical_name, "logical_name")
        _require_nonempty(self.catalog_pattern, "catalog_pattern")
        if self.vlnv is not None:
            _require_nonempty(self.vlnv, "vlnv")


@dataclass(frozen=True)
class RfdcIntegrationMetadata:
    """RFDC settings owned by Vivado Block Design, not by model arithmetic."""

    ip: ExternalIpSpec
    owned_functions: tuple[str, ...]
    configuration_authority: str
    dac_analog_output_type: str
    dac_mixer_mode: str
    dac_mixer_scale_mode: str
    dac_nco_frequency_hz: int
    proof_status: str

    def __post_init__(self) -> None:
        if self.ip.vlnv != RFDC_2_6_VLNV:
            raise ValueError(f"RFDC must use exact VLNV {RFDC_2_6_VLNV}")
        if self.ip.kind is not ImplementationKind.AMD_IP:
            raise ValueError("RFDC implementation kind must be amd_ip")
        if self.ip.catalog_pattern != RFDC_2_6_VLNV:
            raise ValueError(f"RFDC catalog pattern must be {RFDC_2_6_VLNV}")
        if len(self.owned_functions) != len(_RFDC_OWNED_FUNCTIONS) or set(
            self.owned_functions
        ) != _RFDC_OWNED_FUNCTIONS:
            raise ValueError(
                "RFDC owned_functions must be exactly adc, dac, ddc, duc, "
                "decimation, interpolation, mixer, and nco"
            )
        for field_name in (
            "configuration_authority",
            "dac_analog_output_type",
            "dac_mixer_mode",
            "dac_mixer_scale_mode",
            "proof_status",
        ):
            _require_nonempty(str(getattr(self, field_name)), field_name)
        if self.dac_nco_frequency_hz < 0:
            raise ValueError("dac_nco_frequency_hz must be nonnegative")


@dataclass(frozen=True)
class HardwareArchitectureConfig:
    """Validated source of truth for external hardware implementation."""

    architecture_schema_version: int
    architecture_config_version: int
    vivado_version: str
    generation_mode: str
    topology_status: str
    rfdc: RfdcIntegrationMetadata
    required_ip_families: tuple[ExternalIpSpec, ...]

    def __post_init__(self) -> None:
        if self.architecture_schema_version != 1:
            raise ValueError("architecture_schema_version must be 1")
        if self.architecture_config_version < 1:
            raise ValueError("architecture_config_version must be positive")
        if self.vivado_version != "2025.2":
            raise ValueError("vivado_version must be 2025.2")
        if self.generation_mode != "vivado_ip_first":
            raise ValueError("generation_mode must be vivado_ip_first")
        if self.topology_status != "unconnected_skeleton":
            raise ValueError("topology_status must be unconnected_skeleton")
        names = [self.rfdc.ip.logical_name]
        names.extend(spec.logical_name for spec in self.required_ip_families)
        if len(names) != len(set(names)):
            raise ValueError("IP logical names must be unique")
        if not self.required_ip_families:
            raise ValueError("required_ip_families must be nonempty")
        if any(
            spec.kind is not ImplementationKind.AMD_IP
            for spec in self.required_ip_families
        ):
            raise ValueError("required IP families must use amd_ip")

    @classmethod
    def from_mapping(
        cls, values: Mapping[str, object]
    ) -> "HardwareArchitectureConfig":
        root = _as_mapping(values, "architecture")
        rfdc_values = _as_mapping(root.get("rfdc"), "rfdc")
        rfdc_ip = _external_ip(_as_mapping(rfdc_values.get("ip"), "rfdc.ip"))
        owned_functions = tuple(
            _as_str(item, "rfdc.owned_functions item")
            for item in _as_sequence(
                rfdc_values.get("owned_functions"), "rfdc.owned_functions"
            )
        )
        rfdc = RfdcIntegrationMetadata(
            ip=rfdc_ip,
            owned_functions=owned_functions,
            configuration_authority=_as_str(
                rfdc_values.get("configuration_authority"),
                "rfdc.configuration_authority",
            ),
            dac_analog_output_type=_as_str(
                rfdc_values.get("dac_analog_output_type"),
                "rfdc.dac_analog_output_type",
            ),
            dac_mixer_mode=_as_str(
                rfdc_values.get("dac_mixer_mode"), "rfdc.dac_mixer_mode"
            ),
            dac_mixer_scale_mode=_as_str(
                rfdc_values.get("dac_mixer_scale_mode"),
                "rfdc.dac_mixer_scale_mode",
            ),
            dac_nco_frequency_hz=_as_int(
                rfdc_values.get("dac_nco_frequency_hz"),
                "rfdc.dac_nco_frequency_hz",
            ),
            proof_status=_as_str(
                rfdc_values.get("proof_status"), "rfdc.proof_status"
            ),
        )
        families = tuple(
            _external_ip(_as_mapping(item, "required_ip_families item"))
            for item in _as_sequence(
                root.get("required_ip_families"), "required_ip_families"
            )
        )
        return cls(
            architecture_schema_version=_as_int(
                root.get("architecture_schema_version"),
                "architecture_schema_version",
            ),
            architecture_config_version=_as_int(
                root.get("architecture_config_version"),
                "architecture_config_version",
            ),
            vivado_version=_as_str(root.get("vivado_version"), "vivado_version"),
            generation_mode=_as_str(
                root.get("generation_mode"), "generation_mode"
            ),
            topology_status=_as_str(
                root.get("topology_status"), "topology_status"
            ),
            rfdc=rfdc,
            required_ip_families=families,
        )

    @classmethod
    def load_default(cls) -> "HardwareArchitectureConfig":
        config_file = resources.files("rfsoc_pulse_model.config").joinpath(
            "ip_architecture.json"
        )
        with config_file.open("r", encoding="utf-8") as stream:
            values = json.load(stream)
        return cls.from_mapping(_as_mapping(values, "architecture"))


def _external_ip(values: Mapping[str, object]) -> ExternalIpSpec:
    raw_vlnv = values.get("vlnv")
    vlnv = None if raw_vlnv is None else _as_str(raw_vlnv, "vlnv")
    try:
        kind = ImplementationKind(_as_str(values.get("kind"), "kind"))
    except ValueError as error:
        raise ValueError(f"unsupported implementation kind: {values.get('kind')!r}") from error
    return ExternalIpSpec(
        logical_name=_as_str(values.get("logical_name"), "logical_name"),
        kind=kind,
        catalog_pattern=_as_str(
            values.get("catalog_pattern"), "catalog_pattern"
        ),
        vlnv=vlnv,
    )


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _as_sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence")
    return value


def _as_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _as_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value
