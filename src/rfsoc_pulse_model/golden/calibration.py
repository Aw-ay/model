from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..common.calibration_types import CalibrationProfile
from ..common.reflection_types import PolarimetricWaveform


class GoldenTxPredistorter:
    """Clock-free TX polarization forward model and inverse predistorter."""

    def __init__(self, profile: CalibrationProfile) -> None:
        self.profile = profile
        self.matrix = profile.tx_polarization_matrix
        self.inverse = np.linalg.inv(self.matrix)

    def forward(
        self,
        drive: PolarimetricWaveform,
    ) -> PolarimetricWaveform:
        return replace(drive, samples=self.matrix @ drive.samples)

    def predistort(
        self,
        desired: PolarimetricWaveform,
    ) -> PolarimetricWaveform:
        return replace(desired, samples=self.inverse @ desired.samples)

    def forward_predistorted(
        self,
        desired: PolarimetricWaveform,
    ) -> PolarimetricWaveform:
        return self.forward(self.predistort(desired))
