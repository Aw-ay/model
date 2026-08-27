"""Single-source AXI-Lite control ABI and artifact generators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
import json


_REQUIRED_REGISTERS = frozenset(
    {
        "PROJECT_ID", "ABI_VERSION", "CONTROL", "STATUS", "RFDC_STATUS",
        "MTS_STATUS", "CONFIG_VERSION", "EVENT_COUNT_LO", "EVENT_COUNT_HI",
        "DROP_COUNT_LO", "DROP_COUNT_HI", "STREAM_ERRORS",
        "COMMIT_CALIBRATION", "DETECT_THRESHOLD", "NOISE_ALPHA_Q31",
        "RANGE_HOLD_SAMPLES", "RANGE_HIGH_WATER_Q16", "RANGE_LOW_WATER_Q16",
    }
)
_REQUIRED_CHANNEL_REGISTERS = frozenset(
    {"INTEGER_DELAY", "FRACTIONAL_DELAY_Q20", "GAIN_REAL", "GAIN_IMAG", "CALIBRATION_FLAGS"}
)


@dataclass(frozen=True)
class RegisterSpec:
    name: str
    offset: int
    access: str
    reset: int
    maximum: int

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum() or self.name.upper() != self.name:
            raise ValueError("register name must be uppercase identifier text")
        if self.offset < 0 or self.offset % 4:
            raise ValueError(f"register {self.name} offset must be 32-bit aligned")
        if self.access not in {"ro", "rw", "wo", "w1c"}:
            raise ValueError(f"register {self.name} has invalid access")
        if not 0 <= self.reset <= 0xFFFFFFFF or not 0 <= self.maximum <= 0xFFFFFFFF:
            raise ValueError(f"register {self.name} values must fit 32 bits")
        if self.reset > self.maximum:
            raise ValueError(f"register {self.name} reset exceeds maximum")


@dataclass(frozen=True)
class ControlAbi:
    control_abi_schema_version: int
    base_address: int
    span_bytes: int
    abi_version: int
    channel_base: int
    channel_stride: int
    channel_count: int
    registers: tuple[RegisterSpec, ...]
    channel_registers: tuple[RegisterSpec, ...]

    def __post_init__(self) -> None:
        if self.control_abi_schema_version != 1 or self.abi_version != 0x00010000:
            raise ValueError("control ABI and schema versions must be 1")
        if self.base_address != 0xA0000000 or self.span_bytes != 0x10000:
            raise ValueError("control ABI must occupy 64 KiB at 0xA0000000")
        if (self.channel_base, self.channel_stride, self.channel_count) != (0x100, 0x20, 8):
            raise ValueError("channel shadow layout must be base 0x100, stride 0x20, count 8")
        self._validate_group(self.registers, self.span_bytes, "register")
        self._validate_group(self.channel_registers, self.channel_stride, "channel register")
        if {reg.name for reg in self.registers} != _REQUIRED_REGISTERS:
            raise ValueError("required register set is incomplete")
        if {reg.name for reg in self.channel_registers} != _REQUIRED_CHANNEL_REGISTERS:
            raise ValueError("required channel register set is incomplete")
        channel_end = self.channel_base + self.channel_stride * self.channel_count
        if channel_end > self.span_bytes:
            raise ValueError("channel register windows exceed the ABI span")

    @staticmethod
    def _validate_group(registers: tuple[RegisterSpec, ...], limit: int, label: str) -> None:
        offsets: set[int] = set()
        names: set[str] = set()
        for register in registers:
            if register.offset in offsets or register.name in names:
                raise ValueError(f"{label} overlap or duplicate name")
            if register.offset + 4 > limit:
                raise ValueError(f"{label} exceeds its window")
            offsets.add(register.offset)
            names.add(register.name)

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "ControlAbi":
        expected = {
            "control_abi_schema_version", "base_address", "span_bytes", "abi_version",
            "channel_base", "channel_stride", "channel_count", "registers",
            "channel_registers",
        }
        if not isinstance(values, Mapping) or set(values) != expected:
            raise ValueError("control ABI has unknown or missing keys")
        return cls(
            control_abi_schema_version=_int(values["control_abi_schema_version"]),
            base_address=_int(values["base_address"]),
            span_bytes=_int(values["span_bytes"]),
            abi_version=_int(values["abi_version"]),
            channel_base=_int(values["channel_base"]),
            channel_stride=_int(values["channel_stride"]),
            channel_count=_int(values["channel_count"]),
            registers=_registers(values["registers"]),
            channel_registers=_registers(values["channel_registers"]),
        )

    @classmethod
    def load_default(cls) -> "ControlAbi":
        resource = resources.files("rfsoc_pulse_model.config").joinpath(
            "calibrator_registers.json"
        )
        values = json.loads(resource.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
        return cls.from_mapping(values)

    def register(self, name: str) -> RegisterSpec:
        return _find(self.registers, name)

    def channel_register(self, channel: int, name: str) -> RegisterSpec:
        if not 0 <= channel < self.channel_count:
            raise ValueError("channel must be in 0..7")
        relative = _find(self.channel_registers, name)
        return RegisterSpec(
            name=f"CH{channel}_{relative.name}",
            offset=self.channel_base + channel * self.channel_stride + relative.offset,
            access=relative.access,
            reset=relative.reset,
            maximum=relative.maximum,
        )

    def all_expanded_registers(self) -> tuple[RegisterSpec, ...]:
        channels = tuple(
            self.channel_register(channel, register.name)
            for channel in range(self.channel_count)
            for register in self.channel_registers
        )
        return self.registers + channels

    def require_complete(self) -> None:
        self.__post_init__()

    def emit_c_header(self) -> str:
        lines = ["#pragma once", "", f"#define CAL_BASE_ADDRESS 0x{self.base_address:08X}ULL"]
        lines.extend(
            f"#define CAL_{register.name}_OFFSET 0x{register.offset:08X}u"
            for register in self.all_expanded_registers()
        )
        return "\n".join(lines) + "\n"

    def emit_verilog_header(self) -> str:
        lines = ["`ifndef CALIBRATOR_REGISTERS_VH", "`define CALIBRATOR_REGISTERS_VH"]
        lines.extend(
            f"`define CAL_{register.name}_OFFSET 32'h{register.offset:08X}"
            for register in self.all_expanded_registers()
        )
        lines.append("`endif")
        return "\n".join(lines) + "\n"

    def emit_python_constants(self) -> str:
        lines = [f"BASE_ADDRESS = 0x{self.base_address:08X}"]
        lines.extend(
            f"{register.name}_OFFSET = 0x{register.offset:08X}"
            for register in self.all_expanded_registers()
        )
        return "\n".join(lines) + "\n"

    def emit_device_tree_binding(self) -> str:
        return (
            "calibrator@a0000000 {\n"
            '    compatible = "away,rfsoc-calibrator-1.0";\n'
            "    reg = <0x0 0xa0000000 0x0 0x10000>;\n"
            "};\n"
        )


def _registers(value: object) -> tuple[RegisterSpec, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("registers must be a sequence")
    result: list[RegisterSpec] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "offset", "access", "reset", "maximum"}:
            raise ValueError("register has unknown or missing keys")
        result.append(
            RegisterSpec(
                name=_str(item["name"]), offset=_int(item["offset"]),
                access=_str(item["access"]), reset=_int(item["reset"]),
                maximum=_int(item["maximum"]),
            )
        )
    return tuple(result)


def _find(registers: tuple[RegisterSpec, ...], name: str) -> RegisterSpec:
    for register in registers:
        if register.name == name:
            return register
    raise KeyError(name)


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("integer field required")
    return value


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("string field required")
    return value
