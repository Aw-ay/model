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

    def test_default_channel_maps_freeze_rfdc_and_board_routes(self) -> None:
        config = ModelConfig.load_default()

        self.assertEqual(
            [
                (
                    entry.index,
                    getattr(entry, "rfdc_tile", None),
                    getattr(entry, "rfdc_slice", None),
                    getattr(entry, "package_bank", None),
                    getattr(entry, "board_net", None),
                    getattr(entry, "board_endpoint", None),
                )
                for entry in config.adc_channel_map
            ],
            [
                (0, 0, 0, 224, "ADC224_VIN01", "U13"),
                (1, 0, 2, 224, "ADC224_VIN23", "U11"),
                (2, 1, 0, 225, "ADC225_VIN01", "UY7"),
                (3, 1, 2, 225, "ADC225_VIN23", "UY18"),
                (4, 2, 0, 226, "ADC226_VIN01", "J4-1:P31/N33"),
                (5, 2, 2, 226, "ADC226_VIN23", "J4-1:P39/N41"),
                (6, 3, 0, 227, "ADC227_VIN01", "J4-1:P49/N47"),
                (7, 3, 2, 227, "ADC227_VIN23", "J4-1:P57/N55"),
            ],
        )
        self.assertEqual(
            [
                (
                    entry.index,
                    getattr(entry, "rfdc_tile", None),
                    getattr(entry, "rfdc_slice", None),
                    getattr(entry, "package_bank", None),
                    getattr(entry, "board_net", None),
                    getattr(entry, "board_endpoint", None),
                )
                for entry in config.dac_channel_map
            ],
            [
                (0, 0, 0, 228, "DAC228_VOUT0", "J4-2:N63/P65"),
                (1, 0, 1, 228, "DAC228_VOUT1", "J4-2:N71/P73"),
                (2, 0, 2, 228, "DAC228_VOUT2", "J4-2:N79/P81"),
                (3, 0, 3, 228, "DAC228_VOUT3", "J4-2:N87/P89"),
                (4, 1, 0, 229, "DAC229_VOUT0", "UY3"),
                (5, 1, 1, 229, "DAC229_VOUT1", "UY5"),
                (6, 1, 2, 229, "DAC229_VOUT2", "U10"),
                (7, 1, 3, 229, "DAC229_VOUT3", "U16"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
