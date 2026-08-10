"""Independent Golden -> Cycle -> generated-Verilog RFSoC pulse model."""

from .common.config import DetectorConfig, ModelConfig
from .common.calibration_types import (
    CalibrationConditionError,
    CalibrationProfile,
    ComplexChannelCalibration,
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
    "GoldenReflectionSource",
    "GoldenReflectionStream",
    "ReflectionSourceResult",
]
