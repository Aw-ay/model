from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple

from .fixed import FixedFormat


# Changing any entry is a schema change. Intermediate formats use ``error`` so
# Cycle simulation cannot silently wrap or saturate a supposedly lossless node.
PROJECT_NUMERIC_FORMAT_TUPLES = MappingProxyType(
    {
        "adc_component": (16, True, 0, "error"),
        "decimator_coefficient": (18, True, 17, "error"),
        "decimator_product": (34, True, 17, "error"),
        "decimator_accumulator": (38, True, 17, "error"),
        "decimator_output": (16, True, 0, "saturate"),
        "power_square": (31, False, 0, "error"),
        "power": (32, False, 0, "error"),
        "moving_power_sum": (35, False, 0, "error"),
        "noise_boot_sum": (46, False, 0, "error"),
        "noise_estimate": (32, False, 0, "saturate"),
        "threshold_scale": (32, False, 16, "error"),
        "threshold_product": (64, False, 16, "error"),
        "threshold": (32, False, 0, "saturate"),
        "vote_count": (3, False, 0, "error"),
        "sample_index": (64, False, 0, "error"),
        "pulse_width": (32, False, 0, "error"),
        "range_id": (2, False, 0, "error"),
        "channel_index": (3, False, 0, "error"),
        "polarization": (1, False, 0, "error"),
        "selected_range": (2, False, 0, "error"),
        "event_id": (32, False, 0, "wrap"),
        "channel_mask": (8, False, 0, "error"),
        "flags": (16, False, 0, "error"),
        "frequency_word": (32, True, 31, "saturate"),
        "iq_count": (32, False, 0, "error"),
        "config_version": (32, False, 0, "error"),
        "reflection_sample": (24, True, 4, "saturate"),
        "target_count": (4, False, 0, "error"),
        "delay_integer": (21, False, 0, "error"),
        "delay_fraction": (18, False, 17, "error"),
        "fractional_delay_coefficient": (18, True, 17, "error"),
        "fractional_delay_product": (42, True, 21, "error"),
        "fractional_delay_accumulator": (48, True, 21, "error"),
        "calibration_coefficient": (24, True, 20, "saturate"),
        "calibration_product": (48, True, 24, "error"),
        "matrix_accumulator": (50, True, 24, "error"),
        "target_coefficient": (32, True, 20, "saturate"),
        "target_product": (56, True, 24, "error"),
        "multi_target_accumulator": (61, True, 24, "error"),
        "phase_accumulator": (32, False, 32, "wrap"),
        "phase_increment": (32, True, 31, "wrap"),
        "nco_phasor": (18, True, 17, "saturate"),
        "nco_product": (42, True, 21, "error"),
        "nco_complex_result": (43, True, 21, "error"),
        "tx_sine_lut": (16, True, 15, "saturate"),
        "tx_amplitude": (16, False, 15, "saturate"),
        "tx_product": (32, True, 30, "error"),
        "dac_sample": (16, True, 0, "saturate"),
    }
)


@dataclass(frozen=True)
class NumericFormatManifest:
    """Immutable, schema-checked numeric formats consumed by Cycle and RTL."""

    entries: Tuple[Tuple[str, FixedFormat], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "NumericFormatManifest":
        if set(values) != set(PROJECT_NUMERIC_FORMAT_TUPLES):
            missing = sorted(set(PROJECT_NUMERIC_FORMAT_TUPLES) - set(values))
            extra = sorted(set(values) - set(PROJECT_NUMERIC_FORMAT_TUPLES))
            raise ValueError(
                f"numeric format names do not match the project contract; "
                f"missing={missing}, extra={extra}"
            )
        entries = []
        for name in PROJECT_NUMERIC_FORMAT_TUPLES:
            raw = values[name]
            if not isinstance(raw, Mapping):
                raise ValueError(f"numeric format {name} must be an object")
            if not isinstance(raw.get("signed"), bool):
                raise ValueError(f"numeric format {name} signed must be boolean")
            try:
                fmt = FixedFormat(
                    width=int(raw["width"]),
                    signed=raw["signed"],
                    fraction_bits=int(raw["fraction_bits"]),
                    overflow=str(raw["overflow"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"invalid numeric format {name}: {error}") from error
            entries.append((name, fmt))
        manifest = cls(tuple(entries))
        if manifest.as_tuples() != dict(PROJECT_NUMERIC_FORMAT_TUPLES):
            raise ValueError("numeric format values differ from the frozen project contract")
        return manifest

    def __getitem__(self, name: str) -> FixedFormat:
        for entry_name, fmt in self.entries:
            if entry_name == name:
                return fmt
        raise KeyError(name)

    def as_tuples(self) -> dict[str, tuple[int, bool, int, str]]:
        return {
            name: (fmt.width, fmt.signed, fmt.fraction_bits, fmt.overflow)
            for name, fmt in self.entries
        }
