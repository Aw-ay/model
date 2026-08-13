"""Frozen, board-derived ZU27DR processing-system platform authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
import json
import re
from types import MappingProxyType

from rfsoc_pulse_model.common.config import ModelConfig


PS_VLNV = "xilinx.com:ip:zynq_ultra_ps_e:3.5"
_ROOT_KEYS = frozenset(
    {
        "platform_schema_version",
        "device_part",
        "ps_vlnv",
        "control_clock_hz",
        "source_bd_path",
        "source_bd_sha256",
        "vivado_version",
        "properties",
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REVIEWED_PROPERTY_KEYS = frozenset(
    {
        "CONFIG.PSU__CRF_APB__DDR_CTRL__DIVISOR0",
        "CONFIG.PSU__CRF_APB__DDR_CTRL__FREQMHZ",
        "CONFIG.PSU__CRF_APB__DDR_CTRL__SRCSEL",
        "CONFIG.PSU__CRF_APB__DPLL_CTRL__DIV2",
        "CONFIG.PSU__CRF_APB__DPLL_CTRL__FBDIV",
        "CONFIG.PSU__CRF_APB__DPLL_CTRL__FRACDATA",
        "CONFIG.PSU__CRF_APB__DPLL_CTRL__SRCSEL",
        "CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR0",
        "CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR1",
        "CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__FREQMHZ",
        "CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__SRCSEL",
        "CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ",
        "CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL",
        "CONFIG.PSU__DDRC__ADDR_MIRROR",
        "CONFIG.PSU__DDRC__AL",
        "CONFIG.PSU__DDRC__BANK_ADDR_COUNT",
        "CONFIG.PSU__DDRC__BG_ADDR_COUNT",
        "CONFIG.PSU__DDRC__BRC_MAPPING",
        "CONFIG.PSU__DDRC__BUS_WIDTH",
        "CONFIG.PSU__DDRC__CL",
        "CONFIG.PSU__DDRC__CLOCK_STOP_EN",
        "CONFIG.PSU__DDRC__COL_ADDR_COUNT",
        "CONFIG.PSU__DDRC__COMPONENTS",
        "CONFIG.PSU__DDRC__CWL",
        "CONFIG.PSU__DDRC__DDR4_ADDR_MAPPING",
        "CONFIG.PSU__DDRC__DDR4_CAL_MODE_ENABLE",
        "CONFIG.PSU__DDRC__DDR4_CRC_CONTROL",
        "CONFIG.PSU__DDRC__DDR4_MAXPWR_SAVING_EN",
        "CONFIG.PSU__DDRC__DDR4_T_REF_MODE",
        "CONFIG.PSU__DDRC__DDR4_T_REF_RANGE",
        "CONFIG.PSU__DDRC__DEVICE_CAPACITY",
        "CONFIG.PSU__DDRC__DM_DBI",
        "CONFIG.PSU__DDRC__DRAM_WIDTH",
        "CONFIG.PSU__DDRC__ECC",
        "CONFIG.PSU__DDRC__ECC_SCRUB",
        "CONFIG.PSU__DDRC__ENABLE",
        "CONFIG.PSU__DDRC__ENABLE_2T_TIMING",
        "CONFIG.PSU__DDRC__EN_2ND_CLK",
        "CONFIG.PSU__DDRC__FGRM",
        "CONFIG.PSU__DDRC__LP_ASR",
        "CONFIG.PSU__DDRC__MEMORY_TYPE",
        "CONFIG.PSU__DDRC__PARITY_ENABLE",
        "CONFIG.PSU__DDRC__PER_BANK_REFRESH",
        "CONFIG.PSU__DDRC__PHY_DBI_MODE",
        "CONFIG.PSU__DDRC__PLL_BYPASS",
        "CONFIG.PSU__DDRC__PWR_DOWN_EN",
        "CONFIG.PSU__DDRC__RANK_ADDR_COUNT",
        "CONFIG.PSU__DDRC__RD_DQS_CENTER",
        "CONFIG.PSU__DDRC__ROW_ADDR_COUNT",
        "CONFIG.PSU__DDRC__SPEED_BIN",
        "CONFIG.PSU__DDRC__STATIC_RD_MODE",
        "CONFIG.PSU__DDRC__TRAIN_DATA_EYE",
        "CONFIG.PSU__DDRC__TRAIN_READ_GATE",
        "CONFIG.PSU__DDRC__TRAIN_WRITE_LEVEL",
        "CONFIG.PSU__DDRC__T_FAW",
        "CONFIG.PSU__DDRC__T_RAS_MIN",
        "CONFIG.PSU__DDRC__T_RC",
        "CONFIG.PSU__DDRC__T_RCD",
        "CONFIG.PSU__DDRC__T_RP",
        "CONFIG.PSU__DDRC__VREF",
        "CONFIG.PSU__DDR__INTERFACE__FREQMHZ",
        "CONFIG.PSU__FPGA_PL0_ENABLE",
        "CONFIG.PSU__HPM0_FPD__NUM_READ_THREADS",
        "CONFIG.PSU__HPM0_FPD__NUM_WRITE_THREADS",
        "CONFIG.PSU__QSPI__PERIPHERAL__DATA_MODE",
        "CONFIG.PSU__QSPI__PERIPHERAL__ENABLE",
        "CONFIG.PSU__QSPI__PERIPHERAL__IO",
        "CONFIG.PSU__QSPI__PERIPHERAL__MODE",
        "CONFIG.PSU__SD0__CLK_100_SDR_OTAP_DLY",
        "CONFIG.PSU__SD0__CLK_200_SDR_OTAP_DLY",
        "CONFIG.PSU__SD0__CLK_50_DDR_ITAP_DLY",
        "CONFIG.PSU__SD0__CLK_50_DDR_OTAP_DLY",
        "CONFIG.PSU__SD0__CLK_50_SDR_ITAP_DLY",
        "CONFIG.PSU__SD0__CLK_50_SDR_OTAP_DLY",
        "CONFIG.PSU__SD0__DATA_TRANSFER_MODE",
        "CONFIG.PSU__SD0__GRP_POW__ENABLE",
        "CONFIG.PSU__SD0__GRP_POW__IO",
        "CONFIG.PSU__SD0__PERIPHERAL__ENABLE",
        "CONFIG.PSU__SD0__PERIPHERAL__IO",
        "CONFIG.PSU__SD0__RESET__ENABLE",
        "CONFIG.PSU__SD0__SLOT_TYPE",
        "CONFIG.PSU__UART0__BAUD_RATE",
        "CONFIG.PSU__UART0__MODEM__ENABLE",
        "CONFIG.PSU__UART0__PERIPHERAL__ENABLE",
        "CONFIG.PSU__UART0__PERIPHERAL__IO",
        "CONFIG.PSU__USE__CLK0",
        "CONFIG.PSU__USE__FABRIC__RST",
        "CONFIG.PSU__USE__IRQ0",
        "CONFIG.PSU__USE__M_AXI_GP0",
    }
)


@dataclass(frozen=True)
class PsPlatformConfig:
    """Strict installed authority for reproducible ZU27DR PS configuration."""

    platform_schema_version: int
    device_part: str
    ps_vlnv: str
    control_clock_hz: int
    source_bd_path: str
    source_bd_sha256: str
    vivado_version: str
    properties: Mapping[str, str]

    REVIEWED_PROPERTY_KEYS = _REVIEWED_PROPERTY_KEYS

    def __post_init__(self) -> None:
        if self.platform_schema_version != 1:
            raise ValueError("platform_schema_version must be 1")
        _require_nonempty_str(self.device_part, "device_part")
        if self.device_part != ModelConfig.load_default().device_part:
            raise ValueError("device_part must equal ModelConfig.device_part")
        if self.ps_vlnv != PS_VLNV:
            raise ValueError(f"ps_vlnv must be {PS_VLNV}")
        if (
            not isinstance(self.control_clock_hz, int)
            or isinstance(self.control_clock_hz, bool)
        ):
            raise ValueError("control_clock_hz must be an integer")
        if self.control_clock_hz != 100_000_000:
            raise ValueError("control_clock_hz must be 100000000")
        _require_nonempty_str(self.source_bd_path, "source_bd_path")
        _require_nonempty_str(self.source_bd_sha256, "source_bd_sha256")
        if not _SHA256_RE.fullmatch(self.source_bd_sha256):
            raise ValueError("source_bd_sha256 must be lowercase SHA-256")
        if self.vivado_version != "2025.2":
            raise ValueError("vivado_version must be 2025.2")
        if not isinstance(self.properties, Mapping):
            raise ValueError("properties must be a mapping")
        copied = dict(self.properties)
        if set(copied) != _REVIEWED_PROPERTY_KEYS:
            unknown = set(copied) - _REVIEWED_PROPERTY_KEYS
            if unknown:
                raise ValueError(f"unknown PS property: {sorted(unknown)}")
            raise ValueError("PS property keys must equal the reviewed allowlist")
        for property_name, value in copied.items():
            if not isinstance(property_name, str):
                raise ValueError("PS property name must be a string")
            _require_nonempty_str(value, "PS property value")
        object.__setattr__(self, "properties", MappingProxyType(copied))

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "PsPlatformConfig":
        if not isinstance(values, Mapping):
            raise ValueError("platform must be a mapping")
        if set(values) != _ROOT_KEYS:
            raise ValueError("platform has unknown or missing keys")
        properties = values["properties"]
        if not isinstance(properties, Mapping):
            raise ValueError("properties must be a mapping")
        return cls(
            platform_schema_version=_as_int(
                values["platform_schema_version"], "platform_schema_version"
            ),
            device_part=_as_str(values["device_part"], "device_part"),
            ps_vlnv=_as_str(values["ps_vlnv"], "ps_vlnv"),
            control_clock_hz=_as_int(
                values["control_clock_hz"], "control_clock_hz"
            ),
            source_bd_path=_as_str(values["source_bd_path"], "source_bd_path"),
            source_bd_sha256=_as_str(
                values["source_bd_sha256"], "source_bd_sha256"
            ),
            vivado_version=_as_str(values["vivado_version"], "vivado_version"),
            properties=properties,
        )

    @classmethod
    def from_json_text(cls, text: str) -> "PsPlatformConfig":
        if not isinstance(text, str):
            raise ValueError("platform JSON must be text")
        try:
            values = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as error:
            raise ValueError("invalid platform JSON") from error
        return cls.from_mapping(values)

    @classmethod
    def load_default(cls) -> "PsPlatformConfig":
        resource = resources.files("rfsoc_pulse_model.config").joinpath(
            "ps_platform.json"
        )
        return cls.from_json_text(resource.read_text(encoding="utf-8"))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _as_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _as_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _require_nonempty_str(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be nonempty")
