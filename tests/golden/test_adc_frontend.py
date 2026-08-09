import dataclasses
import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import (
    CalibrationProfile,
    ComplexChannelCalibration,
)
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import EightChannelAdcFrame
from rfsoc_pulse_model.common.types import (
    GainRange,
    Polarization,
    RangeSelectionMode,
    SampleDomain,
)
from rfsoc_pulse_model.golden.adc_frontend import (
    GoldenEightChannelAdcFrontend,
)


class GoldenAdcFrontendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )

    def test_fixed_ranges_select_h_and_v_independently(self) -> None:
        samples = np.vstack(
            [np.full(32, index + 1.0) for index in range(8)]
        ).astype(np.complex128)
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 32), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

        result = GoldenEightChannelAdcFrontend(
            self.config, self.calibration
        ).reconstruct(
            frame,
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={
                Polarization.H: GainRange.MID,
                Polarization.V: GainRange.LOW,
            },
        )

        np.testing.assert_array_equal(result.incident.samples[0], samples[1])
        np.testing.assert_allclose(result.incident.samples[1], samples[6] / 0.1)

    def test_identity_calibration_removes_nominal_range_gain(self) -> None:
        true_hv = np.vstack(
            (np.full(32, 25.0 + 5.0j), np.full(32, -12.0 + 3.0j))
        ).astype(np.complex128)
        samples = np.zeros((8, 32), dtype=np.complex128)
        for index, nominal_gain in ((0, 10.0), (1, 1.0), (2, 0.1)):
            samples[index] = true_hv[0] * nominal_gain
        for index, nominal_gain in ((4, 10.0), (5, 1.0), (6, 0.1)):
            samples[index] = true_hv[1] * nominal_gain
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 32), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        frontend = GoldenEightChannelAdcFrontend(
            self.config, self.calibration
        )

        for gain_range in (GainRange.HIGH, GainRange.MID, GainRange.LOW):
            result = frontend.reconstruct(
                frame,
                mode=RangeSelectionMode.FIXED,
                fixed_ranges={
                    Polarization.H: gain_range,
                    Polarization.V: gain_range,
                },
            )
            np.testing.assert_allclose(result.incident.samples, true_hv)

    def test_rx_polarization_matrix_is_inverted_after_range_selection(self) -> None:
        true_hv = np.vstack(
            (np.full(32, 2.0), np.full(32, 3.0))
        ).astype(np.complex128)
        response = np.array(
            [[1.0, 0.25], [0.1j, 0.8]], dtype=np.complex128
        )
        measured = response @ true_hv
        samples = np.zeros((8, 32), dtype=np.complex128)
        for index in (0, 1, 2):
            samples[index] = measured[0]
        for index in (4, 5, 6):
            samples[index] = measured[1]
        samples[[0, 4]] *= 10.0
        samples[[2, 6]] *= 0.1
        profile = dataclasses.replace(
            self.calibration,
            rx_polarization_matrix=response,
        )
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 32), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

        result = GoldenEightChannelAdcFrontend(
            self.config, profile
        ).reconstruct(
            frame,
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={
                Polarization.H: GainRange.HIGH,
                Polarization.V: GainRange.HIGH,
            },
        )

        np.testing.assert_allclose(result.incident.samples, true_hv, atol=1e-12)

    def test_clipped_high_range_falls_to_mid_and_holds(self) -> None:
        samples = np.zeros((8, 96), dtype=np.complex128)
        samples[0] = 1000.0
        samples[1] = 100.0
        samples[2] = 10.0
        samples[4] = 200.0
        clipped = np.zeros((8, 96), dtype=np.bool_)
        clipped[0, 10] = True
        frame = EightChannelAdcFrame(
            samples,
            clipped,
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

        result = GoldenEightChannelAdcFrontend(
            self.config, self.calibration
        ).reconstruct(frame, mode=RangeSelectionMode.AUTO_HOLD)

        self.assertEqual(result.selected_ranges[0, 10], GainRange.MID)
        self.assertTrue(
            all(
                value == GainRange.MID
                for value in result.selected_ranges[0, 10:74]
            )
        )

    def test_fused_mode_is_rejected(self) -> None:
        frame = EightChannelAdcFrame(
            np.zeros((8, 8), dtype=np.complex128),
            np.zeros((8, 8), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

        with self.assertRaisesRegex(ValueError, "FUSED"):
            GoldenEightChannelAdcFrontend(
                self.config, self.calibration
            ).reconstruct(frame, mode=RangeSelectionMode.FUSED)

    def test_relative_channel_alignment_adds_no_filter_center_delay(self) -> None:
        samples = np.zeros((8, 96), dtype=np.complex128)
        samples[0, 10] = 10.0
        adc_channels = list(self.calibration.adc_channels)
        adc_channels[2] = ComplexChannelCalibration(
            response_delay_samples=1.0
        )
        profile = dataclasses.replace(
            self.calibration,
            adc_channels=tuple(adc_channels),
        )
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 96), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

        result = GoldenEightChannelAdcFrontend(
            self.config, profile
        ).reconstruct(
            frame,
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={
                Polarization.H: GainRange.HIGH,
                Polarization.V: GainRange.HIGH,
            },
        )

        self.assertAlmostEqual(result.incident.samples[0, 11], 1.0, places=12)
        self.assertLess(abs(result.incident.samples[0, 41]), 1e-12)


if __name__ == "__main__":
    unittest.main()
