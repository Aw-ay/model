from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import math
from typing import Mapping, Tuple

from .tables import FIR_DECIMATOR_Q17
from .types import SampleDomain
from .fixed import PROJECT_ROUNDING_MODE, RoundingMode


@dataclass(frozen=True)
class DetectorConfig:
    sample_domain: SampleDomain = SampleDomain.DETECTOR
    sample_rate_hz: int = 250_000_000
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
        domain = selected.get("sample_domain")
        if domain is not None and not isinstance(domain, SampleDomain):
            selected["sample_domain"] = SampleDomain(str(domain))
        return cls(**selected)

    def __post_init__(self) -> None:
        if self.sample_domain != SampleDomain.DETECTOR:
            raise ValueError("pulse detector records must use the detector sample domain")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
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
    rfdc_iq_stream_words_per_cycle: int
    rfdc_complex_sample_rate_hz: int
    pl_decimation: int
    detector_sample_rate_hz: int
    detector_sample_period_seconds: float
    group_delay_input_samples: int
    channels: int
    iq_width: int
    ranges_db: Tuple[int, ...]
    loopback_channel: int
    toa_tolerance: int
    width_tolerance: int
    tx_data_type: str
    tx_samples_per_cycle: int
    rounding_mode: RoundingMode
    detector: DetectorConfig

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "ModelConfig":
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
            rfdc_iq_stream_words_per_cycle=int(
                values["rfdc_iq_stream_words_per_cycle"]
            ),
            rfdc_complex_sample_rate_hz=int(values["rfdc_complex_sample_rate_hz"]),
            pl_decimation=int(values["pl_decimation"]),
            detector_sample_rate_hz=int(values["detector_sample_rate_hz"]),
            detector_sample_period_seconds=float(
                values["detector_sample_period_seconds"]
            ),
            group_delay_input_samples=int(values["group_delay_input_samples"]),
            channels=int(values["channels"]),
            iq_width=int(values["iq_width"]),
            ranges_db=tuple(int(value) for value in values["ranges_db"]),
            loopback_channel=int(values["loopback_channel"]),
            toa_tolerance=int(values["toa_tolerance"]),
            width_tolerance=int(values["width_tolerance"]),
            tx_data_type=str(values["tx_data_type"]),
            tx_samples_per_cycle=int(values["tx_samples_per_cycle"]),
            rounding_mode=RoundingMode(str(values["rounding_mode"])),
            detector=detector,
        )
        config.validate()
        return config

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
            self.rx_fabric_clock_hz * self.rfdc_iq_stream_words_per_cycle
        )
        if self.rfdc_complex_sample_rate_hz != expected_from_fabric:
            raise ValueError(
                "rfdc_complex_sample_rate_hz must equal rx_fabric_clock_hz "
                "* rfdc_iq_stream_words_per_cycle"
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

    def source_sample_index(self, detector_sample_index: int) -> int:
        if detector_sample_index < 0:
            raise ValueError("detector_sample_index cannot be negative")
        return self.group_delay_input_samples + self.pl_decimation * detector_sample_index
