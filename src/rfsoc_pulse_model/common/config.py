from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import math
from typing import Mapping, Sequence, Tuple

from .tables import FIR_DECIMATOR_Q17
from .types import (
    ChannelRole,
    GainRange,
    IQUnit,
    Polarization,
    PowerUnit,
    SampleDomain,
)
from .fixed import PROJECT_ROUNDING_MODE, RoundingMode
from .reflection_types import PhysicalChannelMapEntry
from .rfdc_axis import RfdcAxisWordFormat


@dataclass(frozen=True)
class DetectorConfig:
    sample_domain: SampleDomain = SampleDomain.DETECTOR
    sample_rate_hz: int = 250_000_000
    iq_width_bits: int = 16
    iq_fraction_bits: int = 0
    iq_signed: bool = True
    iq_unit: IQUnit = IQUnit.ADC_CODE
    power_width_bits: int = 32
    power_fraction_bits: int = 0
    power_unit: PowerUnit = PowerUnit.ADC_CODE_SQUARED
    noise_boot_samples: int = 16_384
    threshold_scale: float = 13.815510557964274
    noise_update_shift: int = 8
    moving_average: int = 8
    vote_window: int = 5
    vote_required: int = 3
    pre_samples: int = 16
    post_samples: int = 16
    min_pulse_samples: int = 1
    max_pulse_samples: int = 65_535
    full_scale: int = 32_767

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "DetectorConfig":
        names = (
            "sample_domain",
            "sample_rate_hz",
            "iq_width_bits",
            "iq_fraction_bits",
            "iq_signed",
            "iq_unit",
            "power_width_bits",
            "power_fraction_bits",
            "power_unit",
            "noise_boot_samples",
            "threshold_scale",
            "noise_update_shift",
            "moving_average",
            "vote_window",
            "vote_required",
            "pre_samples",
            "post_samples",
            "min_pulse_samples",
            "max_pulse_samples",
            "full_scale",
        )
        selected = {name: values[name] for name in names if name in values}
        if "sample_rate_hz" not in selected and "detector_sample_rate_hz" in values:
            selected["sample_rate_hz"] = values["detector_sample_rate_hz"]
        if "iq_width_bits" not in selected and "iq_width" in values:
            selected["iq_width_bits"] = values["iq_width"]
        domain = selected.get("sample_domain")
        if domain is not None and not isinstance(domain, SampleDomain):
            selected["sample_domain"] = SampleDomain(str(domain))
        iq_unit = selected.get("iq_unit")
        if iq_unit is not None and not isinstance(iq_unit, IQUnit):
            selected["iq_unit"] = IQUnit(str(iq_unit))
        power_unit = selected.get("power_unit")
        if power_unit is not None and not isinstance(power_unit, PowerUnit):
            selected["power_unit"] = PowerUnit(str(power_unit))
        return cls(**selected)

    def __post_init__(self) -> None:
        if self.sample_domain != SampleDomain.DETECTOR:
            raise ValueError("pulse detector records must use the detector sample domain")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.iq_width_bits < 2:
            raise ValueError("iq_width_bits must be at least two")
        if not self.iq_signed:
            raise ValueError("complex detector IQ must use a signed representation")
        if not 0 <= self.iq_fraction_bits < self.iq_width_bits:
            raise ValueError("iq_fraction_bits must be within iq_width_bits")
        if self.iq_unit != IQUnit.ADC_CODE:
            raise ValueError("iq_unit must be adc_code")
        if self.iq_fraction_bits != 0:
            raise ValueError("raw ADC-code IQ must use zero fractional bits")
        if self.power_width_bits < 1:
            raise ValueError("power_width_bits must be positive")
        if not 0 <= self.power_fraction_bits < self.power_width_bits:
            raise ValueError("power_fraction_bits must be within power_width_bits")
        if self.power_unit != PowerUnit.ADC_CODE_SQUARED:
            raise ValueError("power_unit must be adc_code_squared")
        if self.power_fraction_bits != 0:
            raise ValueError("ADC-code-squared power must use zero fractional bits")
        if self.power_fraction_bits != 2 * self.iq_fraction_bits:
            raise ValueError("power_fraction_bits must equal twice iq_fraction_bits")
        required_power_width = 2 * self.iq_width_bits
        if self.power_width_bits < required_power_width:
            raise ValueError(
                "power_width_bits must hold the full I^2+Q^2 result"
            )
        if self.noise_boot_samples < 1:
            raise ValueError("noise_boot_samples must be positive")
        if self.threshold_scale <= 0.0:
            raise ValueError("threshold_scale must be positive")
        if not 1 <= self.noise_update_shift <= 31:
            raise ValueError("noise_update_shift must be between one and 31")
        if self.moving_average < 1:
            raise ValueError("moving_average must be positive")
        if not 1 <= self.vote_required <= self.vote_window:
            raise ValueError("vote_required must be within vote_window")
        if self.pre_samples < 0 or self.post_samples < 0:
            raise ValueError("guard sample counts cannot be negative")
        if self.min_pulse_samples < 1:
            raise ValueError("min_pulse_samples must be positive")
        if self.max_pulse_samples < self.min_pulse_samples:
            raise ValueError("max_pulse_samples must cover min_pulse_samples")
        if self.full_scale != (1 << (self.iq_width_bits - 1)) - 1:
            raise ValueError("full_scale must equal the positive signed-IQ rail")

    @property
    def iq_min_code(self) -> int:
        return -(1 << (self.iq_width_bits - 1))

    @property
    def iq_max_code(self) -> int:
        return (1 << (self.iq_width_bits - 1)) - 1

    @property
    def power_max_code(self) -> int:
        return (1 << self.power_width_bits) - 1


@dataclass(frozen=True)
class ModelConfig:
    """Single rate, numeric, detector, range, and TX configuration authority."""

    model_schema_version: int
    config_version: int
    board_revision: str
    device_part: str
    center_frequency_hz: int
    adc_sample_rate_hz: int
    dac_sample_rate_hz: int
    rfdc_decimation: int
    rfdc_interpolation: int
    rx_fabric_clock_hz: int
    rfdc_complex_samples_per_cycle: int
    rfdc_complex_sample_rate_hz: int
    pl_decimation: int
    detector_sample_rate_hz: int
    detector_sample_period_seconds: float
    group_delay_input_samples: int
    adc_channels: int
    dac_channels: int
    polarizations: int
    reflection_sample_rate_hz: int
    maximum_targets: int
    maximum_delay_samples: int
    fractional_delay_taps: int
    processing_representation: str
    dac_output_mode: str
    dac_nominal_gain_policy: str
    auto_range_high_water_fraction: float
    auto_range_low_water_fraction: float
    auto_range_hold_samples: int
    rfdc_axis: RfdcAxisWordFormat
    adc_channel_map: Tuple[PhysicalChannelMapEntry, ...]
    dac_channel_map: Tuple[PhysicalChannelMapEntry, ...]
    channels: int
    ranges_db: Tuple[int, ...]
    loopback_channel: int
    toa_tolerance: int
    width_tolerance: int
    tx_data_type: str
    tx_samples_per_cycle: int
    rounding_mode: RoundingMode
    detector: DetectorConfig

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "ModelConfig":
        if "rfdc_iq_stream_words_per_cycle" in values:
            raise ValueError(
                "rfdc_iq_stream_words_per_cycle was removed; use "
                "rfdc_complex_samples_per_cycle"
            )
        detector = DetectorConfig.from_mapping(values)
        config = cls(
            model_schema_version=int(values["model_schema_version"]),
            config_version=int(values["config_version"]),
            board_revision=str(values["board_revision"]),
            device_part=str(values["device_part"]),
            center_frequency_hz=int(values["center_frequency_hz"]),
            adc_sample_rate_hz=int(values["adc_sample_rate_hz"]),
            dac_sample_rate_hz=int(values["dac_sample_rate_hz"]),
            rfdc_decimation=int(values["rfdc_decimation"]),
            rfdc_interpolation=int(values["rfdc_interpolation"]),
            rx_fabric_clock_hz=int(values["rx_fabric_clock_hz"]),
            rfdc_complex_samples_per_cycle=int(
                values["rfdc_complex_samples_per_cycle"]
            ),
            rfdc_complex_sample_rate_hz=int(values["rfdc_complex_sample_rate_hz"]),
            pl_decimation=int(values["pl_decimation"]),
            detector_sample_rate_hz=int(values["detector_sample_rate_hz"]),
            detector_sample_period_seconds=float(
                values["detector_sample_period_seconds"]
            ),
            group_delay_input_samples=int(values["group_delay_input_samples"]),
            adc_channels=int(values["adc_channels"]),
            dac_channels=int(values["dac_channels"]),
            polarizations=int(values["polarizations"]),
            reflection_sample_rate_hz=int(values["reflection_sample_rate_hz"]),
            maximum_targets=int(values["maximum_targets"]),
            maximum_delay_samples=int(values["maximum_delay_samples"]),
            fractional_delay_taps=int(values["fractional_delay_taps"]),
            processing_representation=str(values["processing_representation"]),
            dac_output_mode=str(values["dac_output_mode"]),
            dac_nominal_gain_policy=str(values["dac_nominal_gain_policy"]),
            auto_range_high_water_fraction=float(
                values["auto_range_high_water_fraction"]
            ),
            auto_range_low_water_fraction=float(
                values["auto_range_low_water_fraction"]
            ),
            auto_range_hold_samples=int(values["auto_range_hold_samples"]),
            rfdc_axis=RfdcAxisWordFormat.from_mapping(values["rfdc_axis_format"]),
            adc_channel_map=cls._channel_map(values["adc_channel_map"], "adc"),
            dac_channel_map=cls._channel_map(values["dac_channel_map"], "dac"),
            channels=int(values["channels"]),
            ranges_db=tuple(int(value) for value in values["ranges_db"]),
            loopback_channel=int(values["loopback_channel"]),
            toa_tolerance=int(values["toa_tolerance"]),
            width_tolerance=int(values["width_tolerance"]),
            tx_data_type=str(values["tx_data_type"]),
            tx_samples_per_cycle=int(values["tx_samples_per_cycle"]),
            rounding_mode=RoundingMode(str(values["rounding_mode"])),
            detector=detector,
        )
        return config

    @staticmethod
    def _channel_map(
        values: object,
        kind: str,
    ) -> Tuple[PhysicalChannelMapEntry, ...]:
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError(f"{kind}_channel_map must be a sequence")
        return tuple(
            PhysicalChannelMapEntry.from_mapping(value)
            for value in values
            if isinstance(value, Mapping)
        )

    @property
    def iq_width_bits(self) -> int:
        return self.detector.iq_width_bits

    @property
    def iq_width(self) -> int:
        """Compatibility alias; new code must use iq_width_bits."""

        return self.iq_width_bits

    @property
    def iq_fraction_bits(self) -> int:
        return self.detector.iq_fraction_bits

    @property
    def iq_signed(self) -> bool:
        return self.detector.iq_signed

    @property
    def iq_unit(self) -> IQUnit:
        return self.detector.iq_unit

    @property
    def power_width_bits(self) -> int:
        return self.detector.power_width_bits

    @property
    def power_fraction_bits(self) -> int:
        return self.detector.power_fraction_bits

    @property
    def power_unit(self) -> PowerUnit:
        return self.detector.power_unit

    @classmethod
    def load_default(cls) -> "ModelConfig":
        resource = resources.files("rfsoc_pulse_model.config").joinpath("default.json")
        return cls.from_mapping(json.loads(resource.read_text(encoding="utf-8")))

    def validate(self) -> None:
        if self.rfdc_decimation < 1 or self.rfdc_interpolation < 1:
            raise ValueError("RFDC interpolation and decimation must be positive")
        if self.adc_sample_rate_hz % self.rfdc_decimation:
            raise ValueError("adc_sample_rate_hz must divide exactly by rfdc_decimation")
        expected_rfdc = self.adc_sample_rate_hz // self.rfdc_decimation
        if self.rfdc_complex_sample_rate_hz != expected_rfdc:
            raise ValueError(
                "rfdc_complex_sample_rate_hz must equal adc_sample_rate_hz / rfdc_decimation"
            )
        expected_from_fabric = (
            self.rx_fabric_clock_hz * self.rfdc_complex_samples_per_cycle
        )
        if self.rfdc_complex_sample_rate_hz != expected_from_fabric:
            raise ValueError(
                "rfdc_complex_sample_rate_hz must equal rx_fabric_clock_hz "
                "* rfdc_complex_samples_per_cycle"
            )
        if self.rfdc_complex_sample_rate_hz % self.pl_decimation:
            raise ValueError("rfdc_complex_sample_rate_hz must divide by pl_decimation")
        expected_detector = self.rfdc_complex_sample_rate_hz // self.pl_decimation
        if self.detector_sample_rate_hz != expected_detector:
            raise ValueError(
                "detector_sample_rate_hz must equal rfdc_complex_sample_rate_hz / pl_decimation"
            )
        if self.detector.sample_rate_hz != self.detector_sample_rate_hz:
            raise ValueError("detector configuration sample rate is inconsistent")
        expected_period = 1.0 / self.detector_sample_rate_hz
        if not math.isclose(
            self.detector_sample_period_seconds,
            expected_period,
            rel_tol=0.0,
            abs_tol=1e-18,
        ):
            raise ValueError(
                "detector_sample_period_seconds must equal 1 / detector_sample_rate_hz"
            )
        expected_group_delay = (len(FIR_DECIMATOR_Q17) - 1) // 2
        if self.group_delay_input_samples != expected_group_delay:
            raise ValueError("group_delay_input_samples does not match the FIR table")
        if self.adc_channels != 8:
            raise ValueError("adc_channels must equal eight")
        if self.dac_channels != 8:
            raise ValueError("dac_channels must equal eight")
        if self.polarizations != 2:
            raise ValueError("polarizations must equal two")
        if self.reflection_sample_rate_hz != self.rfdc_complex_sample_rate_hz:
            raise ValueError(
                "reflection_sample_rate_hz must equal rfdc_complex_sample_rate_hz"
            )
        if self.maximum_targets < 1 or self.maximum_delay_samples < 1:
            raise ValueError("reflection target and delay capacities must be positive")
        if self.fractional_delay_taps < 1 or self.fractional_delay_taps % 2 == 0:
            raise ValueError("fractional_delay_taps must be a positive odd value")
        if self.processing_representation != "complex_baseband":
            raise ValueError("processing_representation must be complex_baseband")
        if self.dac_output_mode != "complex_baseband_reference":
            raise ValueError("dac_output_mode must be complex_baseband_reference")
        if self.dac_nominal_gain_policy != "external_analog_path":
            raise ValueError(
                "dac_nominal_gain_policy must be external_analog_path"
            )
        if not (
            0.0
            < self.auto_range_low_water_fraction
            < self.auto_range_high_water_fraction
            < 1.0
        ):
            raise ValueError("auto-range water marks must satisfy 0 < low < high < 1")
        if self.auto_range_hold_samples < 1:
            raise ValueError("auto_range_hold_samples must be positive")
        if (
            self.rfdc_axis.adc_component_samples_per_cycle
            != self.rfdc_complex_samples_per_cycle
        ):
            raise ValueError("RFDC ADC AXI samples/cycle must match the sample-rate contract")
        if self.rfdc_axis.dac_samples_per_cycle != self.tx_samples_per_cycle:
            raise ValueError("RFDC DAC AXI samples/cycle must match the TX rate contract")
        self._validate_channel_map(self.adc_channel_map, self.adc_channels, "adc")
        self._validate_channel_map(self.dac_channel_map, self.dac_channels, "dac")
        if self.channels < 1 or len(self.ranges_db) != self.channels:
            raise ValueError("ranges_db must contain one entry per channel")
        if not 0 <= self.loopback_channel < self.channels:
            raise ValueError("loopback_channel must name an enabled channel")
        if self.dac_sample_rate_hz % self.rfdc_interpolation:
            raise ValueError("dac_sample_rate_hz must divide by rfdc_interpolation")
        expected_tx_baseband = self.dac_sample_rate_hz // self.rfdc_interpolation
        if expected_tx_baseband != self.rx_fabric_clock_hz * self.tx_samples_per_cycle:
            raise ValueError(
                "DAC baseband rate must equal rx_fabric_clock_hz * tx_samples_per_cycle"
            )
        if self.tx_data_type != "real":
            raise ValueError("tx_data_type must be real")
        if self.rounding_mode != PROJECT_ROUNDING_MODE:
            raise ValueError(
                f"rounding_mode must be {PROJECT_ROUNDING_MODE.value}"
            )

    @staticmethod
    def _validate_channel_map(
        entries: Tuple[PhysicalChannelMapEntry, ...],
        expected_count: int,
        kind: str,
    ) -> None:
        indices = [entry.index for entry in entries]
        if len(entries) != expected_count or sorted(indices) != list(range(expected_count)):
            raise ValueError(
                f"{kind}_channel_map index values must contain each channel exactly once"
            )
        rfdc_routes = [
            (entry.rfdc_tile, entry.rfdc_slice)
            for entry in entries
        ]
        if len(set(rfdc_routes)) != expected_count:
            raise ValueError(
                f"{kind}_channel_map RFDC route values must be unique"
            )
        if kind == "adc":
            expected_routes = {
                (tile, rfdc_slice)
                for tile in range(4)
                for rfdc_slice in (0, 2)
            }
            if set(rfdc_routes) != expected_routes:
                raise ValueError(
                    "adc_channel_map must cover the canonical RFDC routes"
                )
            expected_by_index = {
                index: (index // 2, 2 * (index % 2))
                for index in range(expected_count)
            }
            if any(
                (entry.rfdc_tile, entry.rfdc_slice)
                != expected_by_index[entry.index]
                for entry in entries
            ):
                raise ValueError(
                    "adc_channel_map index must match its canonical RFDC route"
                )
        if kind == "dac":
            expected_routes = {
                (tile, rfdc_slice)
                for tile in range(2)
                for rfdc_slice in range(4)
            }
            if set(rfdc_routes) != expected_routes:
                raise ValueError(
                    "dac_channel_map must cover the canonical RFDC routes"
                )
            expected_by_index = {
                index: (index // 4, index % 4)
                for index in range(expected_count)
            }
            if any(
                (entry.rfdc_tile, entry.rfdc_slice)
                != expected_by_index[entry.index]
                for entry in entries
            ):
                raise ValueError(
                    "dac_channel_map index must match its canonical RFDC route"
                )
        if kind in ("adc", "dac"):
            for polarization in (Polarization.H, Polarization.V):
                for gain_range in (GainRange.HIGH, GainRange.MID, GainRange.LOW):
                    matches = [
                        entry
                        for entry in entries
                        if entry.polarization == polarization
                        and entry.gain_range == gain_range
                        and ChannelRole.ECHO in entry.allowed_roles
                        and entry.enabled
                    ]
                    if len(matches) != 1:
                        raise ValueError(
                            f"{kind}_channel_map must contain one echo path per "
                            "polarization and gain range"
                        )
        if kind == "dac":
            reference = {
                entry.index: entry.polarization
                for entry in entries
                if entry.gain_range == GainRange.REFERENCE
            }
            if reference != {6: Polarization.V, 7: Polarization.H}:
                raise ValueError("dac_channel_map reference paths must be DAC6 V and DAC7 H")

    def source_sample_index(self, detector_sample_index: int) -> int:
        if detector_sample_index < 0:
            raise ValueError("detector_sample_index cannot be negative")
        return self.group_delay_input_samples + self.pl_decimation * detector_sample_index
