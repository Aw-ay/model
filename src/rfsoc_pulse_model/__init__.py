"""Independent Golden -> Cycle -> generated-Verilog RFSoC pulse model."""

from .common.config import DetectorConfig, ModelConfig
from .common.calibration_types import (
    CalibrationConditionError,
    CalibrationProfile,
    ComplexChannelCalibration,
    FixedInternalDelay,
    RcsCalibrationAnchor,
)
from .common.reflection_types import (
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
from .common.rfdc_axis import RfdcAxisWordFormat
from .common.types import (
    AuxOutputMode,
    ChannelRole,
    ChannelIdentity,
    GainRange,
    IQUnit,
    Polarization,
    PowerUnit,
    PulseEvent,
    PulseRecord,
    RangeId,
    RangeSelectionMode,
    SampleDomain,
)
from .golden.system import (
    GoldenReflectionSource,
    GoldenReflectionStream,
    ReflectionSourceResult,
)
from .golden.adc_frontend import AutoHoldState, GoldenEightChannelAdcFrontend

__all__ = [
    "DetectorConfig",
    "ModelConfig",
    "AuxOutputMode",
    "ChannelRole",
    "ChannelIdentity",
    "GainRange",
    "IQUnit",
    "Polarization",
    "PowerUnit",
    "PulseEvent",
    "PulseRecord",
    "RangeId",
    "RangeSelectionMode",
    "SampleDomain",
    "CalibrationConditionError",
    "CalibrationProfile",
    "ComplexChannelCalibration",
    "FixedInternalDelay",
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
    "GoldenReflectionSource",
    "GoldenEightChannelAdcFrontend",
    "AutoHoldState",
    "GoldenReflectionStream",
    "ReflectionSourceResult",
]
