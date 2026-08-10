from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple


def _string_tuple(values: object, name: str) -> Tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    result = tuple(str(value) for value in values)
    if any(not value for value in result):
        raise ValueError(f"{name} cannot contain an empty interface name")
    return result


def _signed16(value: int) -> int:
    if not -32_768 <= value <= 32_767:
        raise ValueError("RFDC sample must fit signed 16-bit")
    return value & 0xFFFF


def _decode_signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x1_0000 if value & 0x8000 else value


@dataclass(frozen=True)
class RfdcAxisWordFormat:
    """Word-level RFDC/PL contract for the XCZU27DR dual-ADC device."""

    adc_data_type: str
    adc_component_width_bits: int
    adc_component_stream_width_bits: int
    adc_component_samples_per_cycle: int
    adc_sample_order: str
    adc_i_axis_names: Tuple[str, ...]
    adc_q_axis_names: Tuple[str, ...]
    complex_packed_width_bits: int
    complex_packed_order: str
    dac_data_type: str
    dac_analog_output_type: str
    dac_mixer_mode: str
    dac_mixer_scale_mode: str
    dac_nco_frequency_hz: int
    dac_component_width_bits: int
    dac_axis_width_bits: int
    dac_complex_samples_per_cycle: int
    dac_component_order: str
    dac_axis_names: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "RfdcAxisWordFormat":
        return cls(
            adc_data_type=str(values["adc_data_type"]),
            adc_component_width_bits=int(values["adc_component_width_bits"]),
            adc_component_stream_width_bits=int(
                values["adc_component_stream_width_bits"]
            ),
            adc_component_samples_per_cycle=int(
                values["adc_component_samples_per_cycle"]
            ),
            adc_sample_order=str(values["adc_sample_order"]),
            adc_i_axis_names=_string_tuple(
                values["adc_i_axis_names"], "adc_i_axis_names"
            ),
            adc_q_axis_names=_string_tuple(
                values["adc_q_axis_names"], "adc_q_axis_names"
            ),
            complex_packed_width_bits=int(values["complex_packed_width_bits"]),
            complex_packed_order=str(values["complex_packed_order"]),
            dac_data_type=str(values["dac_data_type"]),
            dac_analog_output_type=str(values["dac_analog_output_type"]),
            dac_mixer_mode=str(values["dac_mixer_mode"]),
            dac_mixer_scale_mode=str(values["dac_mixer_scale_mode"]),
            dac_nco_frequency_hz=int(values["dac_nco_frequency_hz"]),
            dac_component_width_bits=int(values["dac_component_width_bits"]),
            dac_axis_width_bits=int(values["dac_axis_width_bits"]),
            dac_complex_samples_per_cycle=int(
                values["dac_complex_samples_per_cycle"]
            ),
            dac_component_order=str(values["dac_component_order"]),
            dac_axis_names=_string_tuple(values["dac_axis_names"], "dac_axis_names"),
        )

    def __post_init__(self) -> None:
        expected_i = tuple(
            f"m{tile}{rfdc_slice}_axis"
            for tile in range(4)
            for rfdc_slice in (0, 2)
        )
        expected_q = tuple(
            f"m{tile}{rfdc_slice + 1}_axis"
            for tile in range(4)
            for rfdc_slice in (0, 2)
        )
        expected_dac = tuple(
            f"s{tile}{rfdc_slice}_axis"
            for tile in range(2)
            for rfdc_slice in range(4)
        )
        if self.adc_data_type != "iq_separate_streams":
            raise ValueError("ADC data type must be iq_separate_streams")
        if (
            self.adc_component_width_bits != 16
            or self.adc_component_stream_width_bits != 32
            or self.adc_component_samples_per_cycle != 2
        ):
            raise ValueError("ADC AXI format must be two signed-16 samples per 32-bit stream")
        if self.adc_sample_order != "sample0_lsb_sample1_msb":
            raise ValueError("ADC sample order must place the earlier sample in bits 15:0")
        if self.adc_i_axis_names != expected_i or self.adc_q_axis_names != expected_q:
            raise ValueError("ADC I/Q AXI interface names must match all eight dual-ADC routes")
        if self.complex_packed_width_bits != 64:
            raise ValueError("packed complex ADC beat must be 64 bits")
        if self.complex_packed_order != "q1_i1_q0_i0_msb_to_lsb":
            raise ValueError("packed complex ADC order must be {Q1,I1,Q0,I0}")
        if self.dac_data_type != "iq_interleaved":
            raise ValueError("DAC PL data type must be iq_interleaved")
        if self.dac_analog_output_type != "real":
            raise ValueError("DAC analog output type must be real")
        if self.dac_mixer_mode != "iq_to_real":
            raise ValueError("DAC mixer mode must be iq_to_real")
        if self.dac_mixer_scale_mode != "unity_0db":
            raise ValueError("DAC mixer scale mode must be unity_0db")
        if self.dac_nco_frequency_hz <= 0:
            raise ValueError("DAC NCO frequency must be positive")
        if (
            self.dac_component_width_bits != 16
            or self.dac_axis_width_bits != 64
            or self.dac_complex_samples_per_cycle != 2
        ):
            raise ValueError(
                "DAC AXI format must be two signed-I16/Q16 complex samples "
                "per 64-bit stream"
            )
        if self.dac_component_order != "q1_i1_q0_i0_msb_to_lsb":
            raise ValueError("DAC component order must be {Q1,I1,Q0,I0}")
        if self.dac_axis_names != expected_dac:
            raise ValueError("DAC AXI interface names must match all eight physical DAC routes")

    def adc_i_axis(self, adc_index: int) -> str:
        return self.adc_i_axis_names[adc_index]

    def adc_q_axis(self, adc_index: int) -> str:
        return self.adc_q_axis_names[adc_index]

    def dac_axis(self, dac_index: int) -> str:
        return self.dac_axis_names[dac_index]

    def pack_adc_component_samples(self, samples: Sequence[int]) -> int:
        if len(samples) != 2:
            raise ValueError("ADC component stream requires exactly two samples")
        return _signed16(int(samples[0])) | (_signed16(int(samples[1])) << 16)

    def pack_complex_samples(self, i_word: int, q_word: int) -> int:
        if not 0 <= i_word <= 0xFFFF_FFFF or not 0 <= q_word <= 0xFFFF_FFFF:
            raise ValueError("ADC component words must be unsigned 32-bit containers")
        i0 = i_word & 0xFFFF
        i1 = (i_word >> 16) & 0xFFFF
        q0 = q_word & 0xFFFF
        q1 = (q_word >> 16) & 0xFFFF
        return i0 | (q0 << 16) | (i1 << 32) | (q1 << 48)

    def unpack_complex_samples(self, word: int) -> Tuple[Tuple[int, int], ...]:
        if not 0 <= word <= 0xFFFF_FFFF_FFFF_FFFF:
            raise ValueError("packed complex word must be an unsigned 64-bit container")
        return (
            (_decode_signed16(word), _decode_signed16(word >> 16)),
            (_decode_signed16(word >> 32), _decode_signed16(word >> 48)),
        )

    def pack_dac_complex_samples(
        self,
        samples: Sequence[Sequence[int]],
    ) -> int:
        if len(samples) != 2 or any(len(sample) != 2 for sample in samples):
            raise ValueError("DAC stream requires exactly two I/Q sample pairs")
        (i0, q0), (i1, q1) = samples
        return (
            _signed16(int(i0))
            | (_signed16(int(q0)) << 16)
            | (_signed16(int(i1)) << 32)
            | (_signed16(int(q1)) << 48)
        )

    def unpack_dac_complex_samples(
        self,
        word: int,
    ) -> Tuple[Tuple[int, int], ...]:
        if not 0 <= word <= 0xFFFF_FFFF_FFFF_FFFF:
            raise ValueError("packed DAC complex word must be unsigned 64-bit")
        return (
            (_decode_signed16(word), _decode_signed16(word >> 16)),
            (_decode_signed16(word >> 32), _decode_signed16(word >> 48)),
        )
