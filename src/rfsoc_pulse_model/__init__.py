"""Independent Golden -> Cycle -> generated-Verilog RFSoC pulse model."""

from .common.config import DetectorConfig, ModelConfig
from .common.types import PulseEvent, PulseRecord, RangeId, SampleDomain

__all__ = [
    "DetectorConfig",
    "ModelConfig",
    "PulseEvent",
    "PulseRecord",
    "RangeId",
    "SampleDomain",
]
