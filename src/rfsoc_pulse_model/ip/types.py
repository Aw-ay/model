"""Typed, immutable authority for Vivado and AMD IP integration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib import resources
import json

from rfsoc_pulse_model.common.config import ModelConfig


RFDC_2_6_VLNV = "xilinx.com:ip:usp_rf_data_converter:2.6"
_CONNECTED_PLATFORM_VLNVS = {
    "zynq_ultra_ps_e": "xilinx.com:ip:zynq_ultra_ps_e:3.5",
    "smartconnect": "xilinx.com:ip:smartconnect:1.0",
    "proc_sys_reset": "xilinx.com:ip:proc_sys_reset:5.0",
    "util_vector_logic": "xilinx.com:ip:util_vector_logic:2.0",
    "xlconcat": "xilinx.com:ip:xlconcat:2.1",
}
_CONNECTED_MATERIALIZED_INSTANCE_CONTRACT = {
    "rfdc_0": ("rfdc", "rfdc_frontend"),
    "zynq_ultra_ps_e_0": ("zynq_ultra_ps_e", "ps_platform_control"),
    "ctrl_smartconnect_0": ("smartconnect", "control_axi_interconnect"),
    "reset_inverter_0": ("util_vector_logic", "control_reset_inverter"),
    "ctrl_reset_0": ("proc_sys_reset", "control_reset_domain"),
    "rx_reset_0": ("proc_sys_reset", "rx_reset_domain"),
    "tx_reset_0": ("proc_sys_reset", "tx_reset_domain"),
    "irq_concat_0": ("xlconcat", "rfdc_irq_concat"),
}
_CONNECTED_SHELL_FAMILIES = frozenset(
    family_id
    for family_id, _ in _CONNECTED_MATERIALIZED_INSTANCE_CONTRACT.values()
)
_CONNECTED_AMD_OWNER_INSTANCE_CONTRACT = {
    "rfdc_frontend": ("rfdc", ("rfdc_0",)),
    "monitor_branch": ("fir_compiler", ("monitor_fir_dec2_0",)),
}
_CONNECTED_REQUIRED_FAMILY_IDS = frozenset(
    {
        "rfdc",
        "zynq_ultra_ps_e",
        "smartconnect",
        "proc_sys_reset",
        "util_vector_logic",
        "xlconcat",
        "axis_register_slice",
        "axis_data_fifo",
        "axis_clock_converter",
        "axis_dwidth_converter",
        "axis_combiner",
        "axis_broadcaster",
        "axis_switch",
        "fir_compiler",
        "dds_compiler",
        "complex_multiplier",
        "cordic",
        "axi_dma",
    }
)
_LEGACY_REFERENCE_PREFIX = "legacy_reference."
_RFDC_OWNED_FUNCTIONS = frozenset(
    {"adc", "dac", "ddc", "duc", "decimation", "interpolation", "mixer", "nco"}
)


class ImplementationKind(str, Enum):
    """Permitted implementation owners in the IP-first architecture."""

    AMD_IP = "amd_ip"
    XPM_MACRO = "xpm_macro"
    CUSTOM_RTL = "custom_rtl"
    ARCHITECTURE_PENDING = "architecture_pending"
    LEGACY_NON_PRODUCTION = "legacy_non_production"


class IpInstanceLifecycle(str, Enum):
    PLANNED = "planned"
    MATERIALIZED = "materialized"
    RETIRED = "retired"


class ParameterStatus(str, Enum):
    UNSPECIFIED = "unspecified"
    DRAFTED = "drafted"
    FROZEN = "frozen"
    VIVADO_VERIFIED = "vivado_verified"


class ConnectionStatus(str, Enum):
    UNCONNECTED = "unconnected"
    PARTIAL = "partial"
    CONNECTED = "connected"
    VIVADO_VERIFIED = "vivado_verified"


class ArchitectureStatus(str, Enum):
    FROZEN = "frozen"
    ARCHITECTURE_PENDING = "architecture_pending"


class IntegrationProofStatus(str, Enum):
    UNVERIFIED = "unverified"
    VIVADO_VERIFIED = "vivado_verified"


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be nonempty")


def _require_distinct_nonempty(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not values or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain nonempty values")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


@dataclass(frozen=True)
class IpFamilySpec:
    family_id: str
    implementation_kind: ImplementationKind
    catalog_pattern: str
    required: bool
    vlnv: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.family_id, "family_id")
        if not isinstance(self.implementation_kind, ImplementationKind):
            raise ValueError("implementation_kind must be an ImplementationKind")
        _require_nonempty(self.catalog_pattern, "catalog_pattern")
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")
        if self.vlnv is not None:
            _require_nonempty(self.vlnv, "vlnv")


@dataclass(frozen=True)
class IpInstanceSpec:
    instance_name: str
    family_ref: str
    logical_role: str
    lifecycle: IpInstanceLifecycle
    parameter_status: ParameterStatus
    connection_status: ConnectionStatus

    def __post_init__(self) -> None:
        _require_nonempty(self.instance_name, "instance_name")
        _require_nonempty(self.family_ref, "family_ref")
        _require_nonempty(self.logical_role, "logical_role")
        if not isinstance(self.lifecycle, IpInstanceLifecycle):
            raise ValueError("lifecycle must be an IpInstanceLifecycle")
        if not isinstance(self.parameter_status, ParameterStatus):
            raise ValueError("parameter_status must be a ParameterStatus")
        if not isinstance(self.connection_status, ConnectionStatus):
            raise ValueError("connection_status must be a ConnectionStatus")


@dataclass(frozen=True)
class RfdcIntegrationMetadata:
    instance_ref: str
    configuration_authority: str
    dac_analog_output_type: str
    dac_mixer_mode: str
    dac_mixer_scale_mode: str
    dac_nco_frequency_hz: int
    proof_status: IntegrationProofStatus

    def __post_init__(self) -> None:
        for field_name in (
            "instance_ref",
            "configuration_authority",
            "dac_analog_output_type",
            "dac_mixer_mode",
            "dac_mixer_scale_mode",
        ):
            _require_nonempty(getattr(self, field_name), field_name)
        if (
            not isinstance(self.dac_nco_frequency_hz, int)
            or isinstance(self.dac_nco_frequency_hz, bool)
            or self.dac_nco_frequency_hz < 0
        ):
            raise ValueError("dac_nco_frequency_hz must be a nonnegative integer")
        if not isinstance(self.proof_status, IntegrationProofStatus):
            raise ValueError("proof_status must be an IntegrationProofStatus")


@dataclass(frozen=True)
class ArchitectureBlockSpec:
    block_name: str
    implementation_kind: ImplementationKind
    responsibilities: tuple[str, ...]
    reference_responsibilities: tuple[str, ...]
    instance_refs: tuple[str, ...]
    architecture_status: ArchitectureStatus
    production_accepted: bool
    source: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.block_name, "block_name")
        if not isinstance(self.implementation_kind, ImplementationKind):
            raise ValueError("implementation_kind must be an ImplementationKind")
        if not isinstance(self.architecture_status, ArchitectureStatus):
            raise ValueError("architecture_status must be an ArchitectureStatus")
        if not isinstance(self.production_accepted, bool):
            raise ValueError("production_accepted must be a boolean")
        if self.source is not None:
            _require_nonempty(self.source, "source")
        _require_tuple_of_nonempty_strings(
            self.responsibilities, "responsibilities", allow_empty=True
        )
        _require_tuple_of_nonempty_strings(
            self.reference_responsibilities,
            "reference_responsibilities",
            allow_empty=True,
        )
        _require_tuple_of_nonempty_strings(
            self.instance_refs, "instance_refs", allow_empty=True
        )

        pending_kind = (
            self.implementation_kind is ImplementationKind.ARCHITECTURE_PENDING
        )
        pending_status = (
            self.architecture_status is ArchitectureStatus.ARCHITECTURE_PENDING
        )
        if pending_kind != pending_status:
            raise ValueError("architecture_pending kind and status must be equivalent")
        if pending_kind and (
            self.production_accepted or self.instance_refs or self.source is not None
        ):
            raise ValueError(
                "architecture_pending block cannot be production accepted or implemented"
            )

        if self.implementation_kind is ImplementationKind.LEGACY_NON_PRODUCTION:
            if self.responsibilities:
                raise ValueError("legacy block responsibilities must be empty")
            if not self.reference_responsibilities:
                raise ValueError("legacy block reference_responsibilities must be nonempty")
            if self.production_accepted:
                raise ValueError("legacy block cannot be production accepted")
            if any(
                not responsibility.startswith(_LEGACY_REFERENCE_PREFIX)
                for responsibility in self.reference_responsibilities
            ):
                raise ValueError("legacy reference responsibilities require legacy_reference. prefix")
            return

        if not self.responsibilities:
            raise ValueError("non-legacy block responsibilities must be nonempty")
        if self.reference_responsibilities:
            raise ValueError("non-legacy block reference_responsibilities must be empty")
        if any(
            responsibility.startswith(_LEGACY_REFERENCE_PREFIX)
            for responsibility in self.responsibilities
        ):
            raise ValueError("production responsibilities cannot use legacy_reference. prefix")


@dataclass(frozen=True)
class RequiredResponsibilitiesSpec:
    production: tuple[str, ...]
    continuous_dual_polar_reflection: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_distinct_nonempty(self.production, "production")
        _require_distinct_nonempty(
            self.continuous_dual_polar_reflection,
            "continuous_dual_polar_reflection",
        )
        production = set(self.production)
        for responsibility in self.continuous_dual_polar_reflection:
            if responsibility.startswith(_LEGACY_REFERENCE_PREFIX):
                raise ValueError(
                    "continuous_dual_polar_reflection cannot use legacy_reference. prefix"
                )
            if responsibility not in production:
                raise ValueError(
                    "continuous_dual_polar_reflection values must be in production"
                )


@dataclass(frozen=True)
class HardwareArchitectureConfig:
    architecture_schema_version: int
    architecture_config_version: int
    vivado_version: str
    device_part: str
    generation_mode: str
    topology_status: str
    rfdc_integration: RfdcIntegrationMetadata
    ip_families: tuple[IpFamilySpec, ...]
    ip_instances: tuple[IpInstanceSpec, ...]
    architecture_blocks: tuple[ArchitectureBlockSpec, ...]
    required_responsibilities: RequiredResponsibilitiesSpec

    def __post_init__(self) -> None:
        if self.architecture_schema_version != 2:
            raise ValueError("architecture_schema_version must be 2")
        if self.architecture_config_version != 3:
            raise ValueError("architecture_config_version must be 3")
        if self.vivado_version != "2025.2":
            raise ValueError("vivado_version must be 2025.2")
        _require_nonempty(self.device_part, "device_part")
        if self.device_part != ModelConfig.load_default().device_part:
            raise ValueError("device_part must equal ModelConfig.device_part")
        if self.generation_mode != "vivado_ip_first":
            raise ValueError("generation_mode must be vivado_ip_first")
        if self.topology_status != "connected_rfdc_shell":
            raise ValueError("topology_status must be connected_rfdc_shell")
        if not isinstance(self.rfdc_integration, RfdcIntegrationMetadata):
            raise ValueError("rfdc_integration must be RfdcIntegrationMetadata")
        if not isinstance(self.required_responsibilities, RequiredResponsibilitiesSpec):
            raise ValueError("required_responsibilities must be RequiredResponsibilitiesSpec")
        _require_tuple_of_elements(
            self.ip_families, IpFamilySpec, "ip_families"
        )
        _require_tuple_of_elements(
            self.ip_instances, IpInstanceSpec, "ip_instances"
        )
        _require_tuple_of_elements(
            self.architecture_blocks, ArchitectureBlockSpec, "architecture_blocks"
        )
        _require_unique_ids(
            self.ip_families, "family_id", "ip family identifiers"
        )
        _require_unique_ids(
            self.ip_instances, "instance_name", "IP instance names"
        )
        _require_unique_ids(
            self.architecture_blocks, "block_name", "architecture block names"
        )

        required_family_ids = {family.family_id for family in self.required_families()}
        if required_family_ids != _CONNECTED_REQUIRED_FAMILY_IDS:
            raise ValueError(
                "required family set must exactly match connected RFDC shell: "
                f"missing={sorted(_CONNECTED_REQUIRED_FAMILY_IDS - required_family_ids)}, "
                f"extra={sorted(required_family_ids - _CONNECTED_REQUIRED_FAMILY_IDS)}"
            )
        rfdc_family = self.family_by_id("rfdc")
        if (
            rfdc_family.implementation_kind is not ImplementationKind.AMD_IP
            or rfdc_family.catalog_pattern != RFDC_2_6_VLNV
            or rfdc_family.vlnv != RFDC_2_6_VLNV
        ):
            raise ValueError(f"RFDC must use exact VLNV {RFDC_2_6_VLNV}")
        if not rfdc_family.required:
            raise ValueError("RFDC family must be required")
        for family_id, expected_vlnv in _CONNECTED_PLATFORM_VLNVS.items():
            family = self.family_by_id(family_id)
            if (
                not family.required
                or family.implementation_kind is not ImplementationKind.AMD_IP
                or family.catalog_pattern != expected_vlnv
                or family.vlnv != expected_vlnv
            ):
                raise ValueError(
                    f"{family_id} must use exact required VLNV {expected_vlnv}"
                )
        for family in self.required_families():
            if family.implementation_kind is not ImplementationKind.AMD_IP:
                raise ValueError("required IP families must use amd_ip")

        family_ids = {family.family_id for family in self.ip_families}
        for instance in self.ip_instances:
            if instance.family_ref not in family_ids:
                raise ValueError(f"unknown family_ref: {instance.family_ref}")
        shell_instances = tuple(
            instance
            for instance in self.ip_instances
            if instance.family_ref in _CONNECTED_SHELL_FAMILIES
        )
        shell_instance_names = {instance.instance_name for instance in shell_instances}
        expected_shell_instance_names = set(_CONNECTED_MATERIALIZED_INSTANCE_CONTRACT)
        if shell_instance_names != expected_shell_instance_names:
            raise ValueError(
                "connected shell instance set mismatch: "
                f"missing={sorted(expected_shell_instance_names - shell_instance_names)}, "
                f"extra={sorted(shell_instance_names - expected_shell_instance_names)}"
            )
        for instance in shell_instances:
            expected_family, expected_role = _CONNECTED_MATERIALIZED_INSTANCE_CONTRACT[
                instance.instance_name
            ]
            if (
                instance.family_ref != expected_family
                or instance.logical_role != expected_role
                or instance.lifecycle is not IpInstanceLifecycle.MATERIALIZED
            ):
                raise ValueError(
                    "connected shell materialized instance contract mismatch: "
                    f"{instance.instance_name}"
                )
        instance_names = {instance.instance_name for instance in self.ip_instances}
        if self.rfdc_integration.instance_ref != "rfdc_0":
            raise ValueError("rfdc_integration.instance_ref must be rfdc_0")
        rfdc_instance = self.instance_by_name(self.rfdc_integration.instance_ref)
        if rfdc_instance.family_ref != "rfdc":
            raise ValueError("rfdc_integration instance_ref must reference rfdc")
        if rfdc_instance.lifecycle is IpInstanceLifecycle.RETIRED:
            raise ValueError("rfdc_integration instance_ref cannot be retired")
        for block in self.architecture_blocks:
            unknown_refs = set(block.instance_refs) - instance_names
            if unknown_refs:
                raise ValueError(
                    f"{block.block_name} has unknown instance_refs: {sorted(unknown_refs)}"
                )
            if block.implementation_kind is not ImplementationKind.AMD_IP:
                continue
            expected_owner = _CONNECTED_AMD_OWNER_INSTANCE_CONTRACT.get(
                block.block_name
            )
            if expected_owner is None:
                raise ValueError(
                    f"connected shell AMD owner has no declared family contract: "
                    f"{block.block_name}"
                )
            expected_family, expected_refs = expected_owner
            if block.instance_refs != expected_refs:
                raise ValueError(
                    f"{block.block_name} AMD owner instance_refs must exactly match "
                    f"{expected_refs}"
                )
            if any(
                self.instance_by_name(instance_name).family_ref != expected_family
                for instance_name in block.instance_refs
            ):
                raise ValueError(
                    f"{block.block_name} AMD owner instances must use "
                    f"family {expected_family}"
                )

    def family_by_id(self, family_id: str) -> IpFamilySpec:
        for family in self.ip_families:
            if family.family_id == family_id:
                return family
        raise KeyError(family_id)

    def instance_by_name(self, instance_name: str) -> IpInstanceSpec:
        for instance in self.ip_instances:
            if instance.instance_name == instance_name:
                return instance
        raise KeyError(instance_name)

    def block_by_name(self, block_name: str) -> ArchitectureBlockSpec:
        for block in self.architecture_blocks:
            if block.block_name == block_name:
                return block
        raise KeyError(block_name)

    def required_families(self) -> tuple[IpFamilySpec, ...]:
        return tuple(family for family in self.ip_families if family.required)

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "HardwareArchitectureConfig":
        root = _as_mapping(values, "architecture")
        _require_exact_keys(
            root,
            {
                "architecture_schema_version",
                "architecture_config_version",
                "vivado_version",
                "device_part",
                "generation_mode",
                "topology_status",
                "rfdc_integration",
                "ip_families",
                "ip_instances",
                "architecture_blocks",
                "required_responsibilities",
            },
            "architecture",
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
            device_part=_as_str(root.get("device_part"), "device_part"),
            generation_mode=_as_str(root.get("generation_mode"), "generation_mode"),
            topology_status=_as_str(root.get("topology_status"), "topology_status"),
            rfdc_integration=_rfdc_integration(
                _as_mapping(root.get("rfdc_integration"), "rfdc_integration")
            ),
            ip_families=tuple(
                _ip_family(_as_mapping(item, "ip_families item"))
                for item in _as_sequence(root.get("ip_families"), "ip_families")
            ),
            ip_instances=tuple(
                _ip_instance(_as_mapping(item, "ip_instances item"))
                for item in _as_sequence(root.get("ip_instances"), "ip_instances")
            ),
            architecture_blocks=tuple(
                _architecture_block(_as_mapping(item, "architecture_blocks item"))
                for item in _as_sequence(
                    root.get("architecture_blocks"), "architecture_blocks"
                )
            ),
            required_responsibilities=_required_responsibilities(
                _as_mapping(
                    root.get("required_responsibilities"),
                    "required_responsibilities",
                )
            ),
        )

    @classmethod
    def load_default(cls) -> "HardwareArchitectureConfig":
        config_file = resources.files("rfsoc_pulse_model.config").joinpath(
            "ip_architecture.json"
        )
        with config_file.open("r", encoding="utf-8") as stream:
            values = json.load(stream)
        return cls.from_mapping(_as_mapping(values, "architecture"))


def _ip_family(values: Mapping[str, object]) -> IpFamilySpec:
    _require_exact_keys(
        values,
        {"family_id", "implementation_kind", "catalog_pattern", "required", "vlnv"},
        "ip family",
    )
    return IpFamilySpec(
        family_id=_as_str(values.get("family_id"), "family_id"),
        implementation_kind=_as_enum(
            ImplementationKind, values.get("implementation_kind"), "implementation_kind"
        ),
        catalog_pattern=_as_str(values.get("catalog_pattern"), "catalog_pattern"),
        required=_as_bool(values.get("required"), "required"),
        vlnv=_as_optional_str(values.get("vlnv"), "vlnv"),
    )


def _ip_instance(values: Mapping[str, object]) -> IpInstanceSpec:
    _require_exact_keys(
        values,
        {
            "instance_name",
            "family_ref",
            "logical_role",
            "lifecycle",
            "parameter_status",
            "connection_status",
        },
        "ip instance",
    )
    return IpInstanceSpec(
        instance_name=_as_str(values.get("instance_name"), "instance_name"),
        family_ref=_as_str(values.get("family_ref"), "family_ref"),
        logical_role=_as_str(values.get("logical_role"), "logical_role"),
        lifecycle=_as_enum(
            IpInstanceLifecycle, values.get("lifecycle"), "lifecycle"
        ),
        parameter_status=_as_enum(
            ParameterStatus, values.get("parameter_status"), "parameter_status"
        ),
        connection_status=_as_enum(
            ConnectionStatus, values.get("connection_status"), "connection_status"
        ),
    )


def _rfdc_integration(values: Mapping[str, object]) -> RfdcIntegrationMetadata:
    _require_exact_keys(
        values,
        {
            "instance_ref",
            "configuration_authority",
            "dac_analog_output_type",
            "dac_mixer_mode",
            "dac_mixer_scale_mode",
            "dac_nco_frequency_hz",
            "proof_status",
        },
        "rfdc_integration",
    )
    return RfdcIntegrationMetadata(
        instance_ref=_as_str(values.get("instance_ref"), "instance_ref"),
        configuration_authority=_as_str(
            values.get("configuration_authority"), "configuration_authority"
        ),
        dac_analog_output_type=_as_str(
            values.get("dac_analog_output_type"), "dac_analog_output_type"
        ),
        dac_mixer_mode=_as_str(values.get("dac_mixer_mode"), "dac_mixer_mode"),
        dac_mixer_scale_mode=_as_str(
            values.get("dac_mixer_scale_mode"), "dac_mixer_scale_mode"
        ),
        dac_nco_frequency_hz=_as_int(
            values.get("dac_nco_frequency_hz"), "dac_nco_frequency_hz"
        ),
        proof_status=_as_enum(
            IntegrationProofStatus, values.get("proof_status"), "proof_status"
        ),
    )


def _architecture_block(values: Mapping[str, object]) -> ArchitectureBlockSpec:
    _require_exact_keys(
        values,
        {
            "block_name",
            "implementation_kind",
            "responsibilities",
            "reference_responsibilities",
            "instance_refs",
            "architecture_status",
            "production_accepted",
            "source",
        },
        "architecture block",
    )
    return ArchitectureBlockSpec(
        block_name=_as_str(values.get("block_name"), "block_name"),
        implementation_kind=_as_enum(
            ImplementationKind, values.get("implementation_kind"), "implementation_kind"
        ),
        responsibilities=_as_string_tuple(values.get("responsibilities"), "responsibilities"),
        reference_responsibilities=_as_string_tuple(
            values.get("reference_responsibilities"), "reference_responsibilities"
        ),
        instance_refs=_as_string_tuple(values.get("instance_refs"), "instance_refs"),
        architecture_status=_as_enum(
            ArchitectureStatus, values.get("architecture_status"), "architecture_status"
        ),
        production_accepted=_as_bool(
            values.get("production_accepted"), "production_accepted"
        ),
        source=_as_optional_str(values.get("source"), "source"),
    )


def _required_responsibilities(
    values: Mapping[str, object],
) -> RequiredResponsibilitiesSpec:
    _require_exact_keys(
        values,
        {"production", "continuous_dual_polar_reflection"},
        "required_responsibilities",
    )
    return RequiredResponsibilitiesSpec(
        production=_as_string_tuple(values.get("production"), "production"),
        continuous_dual_polar_reflection=_as_string_tuple(
            values.get("continuous_dual_polar_reflection"),
            "continuous_dual_polar_reflection",
        ),
    )


def _require_tuple_of_nonempty_strings(
    values: tuple[str, ...], field_name: str, *, allow_empty: bool
) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not allow_empty and not values:
        raise ValueError(f"{field_name} must be nonempty")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain nonempty strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _require_unique_ids(
    values: tuple[object, ...], attribute: str, label: str
) -> None:
    identifiers = [getattr(value, attribute) for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} must be unique")


def _require_tuple_of_elements(
    values: tuple[object, ...], element_type: type[object], field_name: str
) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if any(not isinstance(value, element_type) for value in values):
        raise ValueError(f"{field_name} entries have the wrong type")


def _require_exact_keys(
    values: Mapping[str, object], expected: set[str], field_name: str
) -> None:
    actual = set(values)
    if actual != expected:
        raise ValueError(
            f"{field_name} keys must be exactly {sorted(expected)}; got {sorted(actual)}"
        )


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _as_sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence")
    return value


def _as_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_as_str(item, f"{field_name} item") for item in _as_sequence(value, field_name))


def _as_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _as_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field_name)


def _as_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _as_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _as_enum(enum_type: type[Enum], value: object, field_name: str) -> Enum:
    try:
        return enum_type(_as_str(value, field_name))
    except ValueError as error:
        raise ValueError(f"unsupported {field_name}: {value!r}") from error
