"""Definitions shared by all three model layers."""

from .config import DetectorConfig, ModelConfig
from .events import (
    associate_polarimetric_range_records,
    associate_range_records,
)
from .fixed import (
    PROJECT_ROUNDING_MODE,
    FixedFormat,
    RoundingMode,
    round_array_ties_away_from_zero,
    round_ties_away_from_zero,
)
from .types import (
    AuxOutputMode,
    ChannelRole,
    ChannelIdentity,
    GainRange,
    IQSample,
    IQUnit,
    Polarization,
    PowerUnit,
    PulseEvent,
    PulseRecord,
    RangeId,
    RangeSelectionMode,
    SampleDomain,
)
from .calibration_types import (
    CalibrationConditionError,
    CalibrationProfile,
    ComplexChannelCalibration,
    RcsCalibrationAnchor,
)
from .reflection_types import (
    CompiledScatterer,
    DacAuxRequest,
    EightChannelAdcFrame,
    EightChannelDacFrame,
    PhysicalChannelMapEntry,
    PolarimetricWaveform,
    ReflectionScenario,
    ReflectionStatus,
    TargetRequest,
)
from .rfdc_axis import RfdcAxisWordFormat

__all__ = [
    "FixedFormat",
    "PROJECT_ROUNDING_MODE",
    "RoundingMode",
    "DetectorConfig",
    "AuxOutputMode",
    "ChannelRole",
    "ChannelIdentity",
    "GainRange",
    "IQSample",
    "IQUnit",
    "PowerUnit",
    "PulseEvent",
    "PulseRecord",
    "Polarization",
    "RangeId",
    "RangeSelectionMode",
    "SampleDomain",
    "ModelConfig",
    "CalibrationConditionError",
    "CalibrationProfile",
    "ComplexChannelCalibration",
    "RcsCalibrationAnchor",
    "CompiledScatterer",
    "DacAuxRequest",
    "EightChannelAdcFrame",
    "EightChannelDacFrame",
    "PhysicalChannelMapEntry",
    "PolarimetricWaveform",
    "ReflectionScenario",
    "ReflectionStatus",
    "TargetRequest",
    "RfdcAxisWordFormat",
    "associate_range_records",
    "associate_polarimetric_range_records",
    "round_array_ties_away_from_zero",
    "round_ties_away_from_zero",
]
