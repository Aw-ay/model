"""Deployable XCZU27DR calibrator platform authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
import json


_ROOT_KEYS = frozenset(
    {
        "calibrator_platform_schema_version",
        "device_part",
        "vivado_version",
        "vitis_version",
        "petalinux_version",
        "maximum_channel_alignment_samples",
        "source_authority",
        "gem3",
        "emmc",
        "dma",
        "network",
    }
)


@dataclass(frozen=True)
class Gem3Config:
    enabled: bool
    controller: int
    phy_model: str
    phy_address: int
    interface: str
    mio_range: tuple[int, int]
    mdc_mio: int
    mdio_mio: int
    reset_source: str
    reset_active_low: bool
    optional_mio24_reset_populated: bool

    def __post_init__(self) -> None:
        if not self.enabled or self.controller != 3:
            raise ValueError("GEM3 controller must be enabled")
        if self.phy_model != "RTL8211FD" or self.phy_address != 7:
            raise ValueError("GEM3 PHY must be RTL8211FD at address 7")
        if self.interface != "rgmii-id":
            raise ValueError("GEM3 interface must be rgmii-id")
        if self.mio_range != (64, 77) or (self.mdc_mio, self.mdio_mio) != (76, 77):
            raise ValueError("GEM3 MIO range must be 64..77 with MDC/MDIO on 76/77")
        if self.reset_source != "PS_POR_B":
            raise ValueError("GEM3 reset source must be PS_POR_B")
        if not self.reset_active_low or self.optional_mio24_reset_populated:
            raise ValueError("GEM3 reset must be active-low and MIO24 reset must be unpopulated")


@dataclass(frozen=True)
class EmmcConfig:
    enabled: bool
    mio_range: tuple[int, int]
    bus_width_bits: int

    def __post_init__(self) -> None:
        if not self.enabled or self.mio_range != (13, 23):
            raise ValueError("eMMC must be enabled on MIO range 13..23")
        if self.bus_width_bits != 8:
            raise ValueError("eMMC bus width must be 8 bits")


@dataclass(frozen=True)
class DmaConfig:
    vlnv: str
    mode: str
    stream_width_bits: int
    address_width_bits: int
    ps_slave_port: str

    def __post_init__(self) -> None:
        if self.vlnv != "xilinx.com:ip:axi_dma:7.1":
            raise ValueError("DMA VLNV must be xilinx.com:ip:axi_dma:7.1")
        if self.mode != "scatter_gather_s2mm":
            raise ValueError("DMA mode must be scatter_gather_s2mm")
        if self.stream_width_bits != 128 or self.address_width_bits != 64:
            raise ValueError("DMA must use a 128-bit stream and 64-bit addresses")
        if self.ps_slave_port != "S_AXI_HP0_FPD":
            raise ValueError("DMA PS slave port must be S_AXI_HP0_FPD")


@dataclass(frozen=True)
class CalibratorPlatformConfig:
    calibrator_platform_schema_version: int
    device_part: str
    vivado_version: str
    vitis_version: str
    petalinux_version: str
    maximum_channel_alignment_samples: int
    source_authority: Mapping[str, object]
    gem3: Gem3Config
    emmc: EmmcConfig
    dma: DmaConfig
    network: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.calibrator_platform_schema_version != 1:
            raise ValueError("calibrator_platform_schema_version must be 1")
        if self.device_part != "xczu27dr-fsve1156-2-i":
            raise ValueError("device_part must be xczu27dr-fsve1156-2-i")
        if {self.vivado_version, self.vitis_version, self.petalinux_version} != {"2025.2"}:
            raise ValueError("tool versions must all be 2025.2")
        if self.maximum_channel_alignment_samples != 2047:
            raise ValueError("maximum_channel_alignment_samples must be 2047")
        _require_exact_keys(
            self.source_authority,
            {"schematic_path", "legacy_bd_path", "legacy_bd_sha256"},
            "source_authority",
        )
        _require_exact_keys(
            self.network,
            {"data_transport", "control_transport", "mtu_bytes"},
            "network",
        )
        if self.network != {
            "data_transport": "udp",
            "control_transport": "tcp",
            "mtu_bytes": 1500,
        }:
            raise ValueError("network must use UDP data, TCP control, and MTU 1500")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "CalibratorPlatformConfig":
        _require_exact_keys(values, _ROOT_KEYS, "calibrator platform")
        return cls(
            calibrator_platform_schema_version=_as_int(
                values["calibrator_platform_schema_version"],
                "calibrator_platform_schema_version",
            ),
            device_part=_as_str(values["device_part"], "device_part"),
            vivado_version=_as_str(values["vivado_version"], "vivado_version"),
            vitis_version=_as_str(values["vitis_version"], "vitis_version"),
            petalinux_version=_as_str(values["petalinux_version"], "petalinux_version"),
            maximum_channel_alignment_samples=_as_int(
                values["maximum_channel_alignment_samples"],
                "maximum_channel_alignment_samples",
            ),
            source_authority=_as_mapping(values["source_authority"], "source_authority"),
            gem3=_gem3(values["gem3"]),
            emmc=_emmc(values["emmc"]),
            dma=_dma(values["dma"]),
            network=_as_mapping(values["network"], "network"),
        )

    @classmethod
    def from_json_text(cls, text: str) -> "CalibratorPlatformConfig":
        try:
            values = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("invalid calibrator platform JSON") from error
        return cls.from_mapping(values)

    @classmethod
    def load_default(cls) -> "CalibratorPlatformConfig":
        resource = resources.files("rfsoc_pulse_model.config").joinpath(
            "calibrator_platform.json"
        )
        return cls.from_json_text(resource.read_text(encoding="utf-8"))

    def require_deployable(self) -> None:
        """Reassert the board-critical properties at deployment boundaries."""

        self.__post_init__()


def _gem3(value: object) -> Gem3Config:
    keys = {
        "enabled", "controller", "phy_model", "phy_address", "interface",
        "mio_range", "mdc_mio", "mdio_mio", "reset_source",
        "reset_active_low", "optional_mio24_reset_populated",
    }
    values = _as_mapping(value, "gem3")
    _require_exact_keys(values, keys, "gem3")
    return Gem3Config(
        enabled=_as_bool(values["enabled"], "gem3.enabled"),
        controller=_as_int(values["controller"], "gem3.controller"),
        phy_model=_as_str(values["phy_model"], "gem3.phy_model"),
        phy_address=_as_int(values["phy_address"], "gem3.phy_address"),
        interface=_as_str(values["interface"], "gem3.interface"),
        mio_range=_as_range(values["mio_range"], "gem3.mio_range"),
        mdc_mio=_as_int(values["mdc_mio"], "gem3.mdc_mio"),
        mdio_mio=_as_int(values["mdio_mio"], "gem3.mdio_mio"),
        reset_source=_as_str(values["reset_source"], "gem3.reset_source"),
        reset_active_low=_as_bool(values["reset_active_low"], "gem3.reset_active_low"),
        optional_mio24_reset_populated=_as_bool(
            values["optional_mio24_reset_populated"],
            "gem3.optional_mio24_reset_populated",
        ),
    )


def _emmc(value: object) -> EmmcConfig:
    values = _as_mapping(value, "emmc")
    _require_exact_keys(values, {"enabled", "mio_range", "bus_width_bits"}, "emmc")
    return EmmcConfig(
        enabled=_as_bool(values["enabled"], "emmc.enabled"),
        mio_range=_as_range(values["mio_range"], "emmc.mio_range"),
        bus_width_bits=_as_int(values["bus_width_bits"], "emmc.bus_width_bits"),
    )


def _dma(value: object) -> DmaConfig:
    values = _as_mapping(value, "dma")
    _require_exact_keys(
        values,
        {"vlnv", "mode", "stream_width_bits", "address_width_bits", "ps_slave_port"},
        "dma",
    )
    return DmaConfig(
        vlnv=_as_str(values["vlnv"], "dma.vlnv"),
        mode=_as_str(values["mode"], "dma.mode"),
        stream_width_bits=_as_int(values["stream_width_bits"], "dma.stream_width_bits"),
        address_width_bits=_as_int(values["address_width_bits"], "dma.address_width_bits"),
        ps_slave_port=_as_str(values["ps_slave_port"], "dma.ps_slave_port"),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_exact_keys(value: object, expected: set[str] | frozenset[str], name: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ValueError(f"{name} has unknown or missing keys")


def _as_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _as_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _as_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _as_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _as_range(value: object, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must contain two integers")
    return (_as_int(value[0], name), _as_int(value[1], name))
