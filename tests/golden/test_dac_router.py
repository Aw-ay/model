import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    DacAuxRequest,
    PolarimetricWaveform,
)
from rfsoc_pulse_model.common.types import AuxOutputMode, SampleDomain
from rfsoc_pulse_model.golden.dac_router import GoldenEightChannelDacRouter


class GoldenDacRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.profile = CalibrationProfile.identity(
            2.8e9, 25.0, 64.0, None
        )
        self.waveform = PolarimetricWaveform(
            np.array([[1 + 2j, 3 + 4j], [5 + 6j, 7 + 8j]]),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

    def test_echo_routes_v_to_even_and_h_to_odd_range_channels(self) -> None:
        frame = GoldenEightChannelDacRouter(
            self.config, self.profile
        ).route(
            self.waveform,
            DacAuxRequest(AuxOutputMode.OFF, None),
        )

        for index in (0, 2, 4):
            np.testing.assert_array_equal(
                frame.samples[index], self.waveform.samples[1]
            )
        for index in (1, 3, 5):
            np.testing.assert_array_equal(
                frame.samples[index], self.waveform.samples[0]
            )
        np.testing.assert_array_equal(
            frame.samples[6:],
            np.zeros((2, 2), dtype=np.complex128),
        )

    def test_calibration_mode_routes_v_to_dac6_and_h_to_dac7(self) -> None:
        auxiliary = DacAuxRequest(
            AuxOutputMode.CALIBRATION,
            self.waveform,
        )

        frame = GoldenEightChannelDacRouter(
            self.config, self.profile
        ).route(self.waveform, auxiliary)

        np.testing.assert_array_equal(
            frame.samples[6], self.waveform.samples[1]
        )
        np.testing.assert_array_equal(
            frame.samples[7], self.waveform.samples[0]
        )


if __name__ == "__main__":
    unittest.main()
