from __future__ import annotations

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.config import ModelConfig
from ..common.reflection_types import (
    DacAuxRequest,
    EightChannelDacFrame,
    PolarimetricWaveform,
)
from ..common.types import (
    AuxOutputMode,
    ChannelRole,
    Polarization,
    SampleTimeReference,
)
from .delay import apply_relative_delay


_POLARIZATION_ROW = {
    Polarization.H: 0,
    Polarization.V: 1,
}


class GoldenEightChannelDacRouter:
    """Route corrected H/V envelopes to the configured physical DAC paths."""

    def __init__(
        self,
        config: ModelConfig,
        calibration: CalibrationProfile,
    ) -> None:
        self.config = config
        self.calibration = calibration

    @staticmethod
    def _validate_auxiliary(
        reflected: PolarimetricWaveform,
        auxiliary: DacAuxRequest,
    ) -> None:
        if auxiliary.waveform is None:
            return
        waveform = auxiliary.waveform
        if (
            waveform.sample_domain != reflected.sample_domain
            or waveform.sample_rate_hz != reflected.sample_rate_hz
            or waveform.start_sample != reflected.start_sample
            or waveform.samples.shape[1] != reflected.samples.shape[1]
        ):
            raise ValueError("auxiliary waveform must match reflected metadata")

    def _apply_channel_compensation(
        self,
        source: np.ndarray,
        index: int,
        maximum_response_delay: float,
        all_delays_equal: bool,
    ) -> np.ndarray:
        channel = self.calibration.dac_channels[index]
        drive = (
            np.asarray(source, dtype=np.complex128)
            / channel.response_gain
        )
        if all_delays_equal:
            return drive

        taps = self.config.fractional_delay_taps
        compensation = (
            maximum_response_delay - channel.response_delay_samples
        )
        pair = np.vstack(
            (
                drive,
                np.zeros(drive.size, dtype=np.complex128),
            )
        )
        return apply_relative_delay(
            pair,
            compensation,
            taps,
        )[0]

    def route(
        self,
        reflected: PolarimetricWaveform,
        auxiliary: DacAuxRequest,
    ) -> EightChannelDacFrame:
        if reflected.sample_rate_hz != self.config.reflection_sample_rate_hz:
            raise ValueError("reflected rate does not match reflection_sample_rate_hz")
        self._validate_auxiliary(reflected, auxiliary)
        sample_count = reflected.samples.shape[1]
        output = np.zeros((8, sample_count), dtype=np.complex128)
        response_delays = np.array(
            [
                channel.response_delay_samples
                for channel in self.calibration.dac_channels
            ],
            dtype=np.float64,
        )
        maximum_response_delay = float(np.max(response_delays))
        all_delays_equal = (
            maximum_response_delay - float(np.min(response_delays)) <= 1e-15
        )
        requested_role = {
            AuxOutputMode.CALIBRATION: ChannelRole.CALIBRATION,
            AuxOutputMode.CANCELLATION: ChannelRole.CANCELLATION,
        }.get(auxiliary.mode)

        for entry in self.config.dac_channel_map:
            if not entry.enabled:
                continue
            source = None
            if ChannelRole.ECHO in entry.allowed_roles:
                source = reflected.samples[_POLARIZATION_ROW[entry.polarization]]
            elif requested_role is not None:
                if requested_role not in entry.allowed_roles:
                    raise ValueError(
                        f"DAC{entry.index} does not allow {requested_role.value}"
                    )
                if auxiliary.waveform is None:
                    raise ValueError("enabled auxiliary mode requires a waveform")
                source = auxiliary.waveform.samples[
                    _POLARIZATION_ROW[entry.polarization]
                ]
            if source is None:
                continue
            source = source * entry.digital_scale
            output[entry.index] = self._apply_channel_compensation(
                source,
                entry.index,
                maximum_response_delay,
                all_delays_equal,
            )

        return EightChannelDacFrame(
            samples=output,
            sample_domain=reflected.sample_domain,
            sample_rate_hz=reflected.sample_rate_hz,
            representation=self.config.dac_output_mode,
            fixed_internal_delay=self.calibration.fixed_internal_delay,
            time_reference=SampleTimeReference.LATENCY_NORMALIZED,
            start_sample=reflected.start_sample,
        )
