"""Clock-free NumPy Golden references."""

from .detector import DetectorConfig, GoldenPulseDetector
from .receive import (
    AdcSampleBatch,
    GoldenReceivePipeline,
    GoldenReceiveResult,
    PulseSpec,
    SignalScenario,
    apply_range_gain,
    generate_iq,
    unpack_dual_iq_words,
)
from .transmit import GoldenLfmConfig, generate_lfm_samples, generate_lfm_waveform
from .adc_frontend import AutoHoldState, GoldenEightChannelAdcFrontend
from .system import (
    GoldenReflectionSource,
    GoldenReflectionStream,
    ReflectionSourceResult,
)

__all__ = [
    "DetectorConfig",
    "AdcSampleBatch",
    "AutoHoldState",
    "GoldenLfmConfig",
    "GoldenPulseDetector",
    "GoldenEightChannelAdcFrontend",
    "GoldenReceivePipeline",
    "GoldenReceiveResult",
    "GoldenReflectionSource",
    "GoldenReflectionStream",
    "ReflectionSourceResult",
    "PulseSpec",
    "SignalScenario",
    "apply_range_gain",
    "generate_iq",
    "generate_lfm_samples",
    "generate_lfm_waveform",
    "unpack_dual_iq_words",
]
