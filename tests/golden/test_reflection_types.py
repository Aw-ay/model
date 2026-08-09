import unittest

import numpy as np

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    GainRange,
    Polarization,
    PolarimetricWaveform,
)
from rfsoc_pulse_model.common.types import SampleDomain


class ReflectionContractTest(unittest.TestCase):
    def test_polarimetric_waveform_uses_h_then_v(self) -> None:
        samples = np.array([[1 + 2j, 3 + 4j], [5 + 6j, 7 + 8j]])
        waveform = PolarimetricWaveform(
            samples=samples,
            sample_domain=SampleDomain.RFDC_COMPLEX_INPUT,
            sample_rate_hz=500_000_000,
        )

        np.testing.assert_array_equal(waveform.samples[0], samples[0])
        np.testing.assert_array_equal(waveform.samples[1], samples[1])

    def test_polarimetric_waveform_rejects_wrong_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape.*2"):
            PolarimetricWaveform(
                samples=np.zeros((8, 4), dtype=np.complex128),
                sample_domain=SampleDomain.RFDC_COMPLEX_INPUT,
                sample_rate_hz=500_000_000,
            )

    def test_default_physical_channel_maps_match_the_board_contract(self) -> None:
        config = ModelConfig.load_default()

        self.assertEqual(
            [
                (entry.index, entry.polarization, entry.gain_range)
                for entry in config.adc_channel_map
            ],
            [
                (0, Polarization.H, GainRange.HIGH),
                (1, Polarization.H, GainRange.MID),
                (2, Polarization.H, GainRange.LOW),
                (3, Polarization.H, GainRange.REFERENCE),
                (4, Polarization.V, GainRange.HIGH),
                (5, Polarization.V, GainRange.MID),
                (6, Polarization.V, GainRange.LOW),
                (7, Polarization.V, GainRange.REFERENCE),
            ],
        )
        self.assertEqual(
            [
                (entry.index, entry.polarization, entry.gain_range)
                for entry in config.dac_channel_map
            ],
            [
                (0, Polarization.V, GainRange.HIGH),
                (1, Polarization.H, GainRange.HIGH),
                (2, Polarization.V, GainRange.MID),
                (3, Polarization.H, GainRange.MID),
                (4, Polarization.V, GainRange.LOW),
                (5, Polarization.H, GainRange.LOW),
                (6, Polarization.V, GainRange.REFERENCE),
                (7, Polarization.H, GainRange.REFERENCE),
            ],
        )


if __name__ == "__main__":
    unittest.main()
