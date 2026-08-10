import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import (
    CalibrationConditionError,
    CalibrationProfile,
    FixedInternalDelay,
)
from rfsoc_pulse_model.common.reflection_types import PolarimetricWaveform
from rfsoc_pulse_model.common.types import SampleDomain
from rfsoc_pulse_model.golden.calibration import GoldenTxPredistorter


class GoldenCalibrationTest(unittest.TestCase):
    def test_fixed_internal_delay_has_an_explicit_physical_contract(self) -> None:
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.25, None)

        self.assertIsInstance(profile.fixed_internal_delay, FixedInternalDelay)
        self.assertEqual(profile.fixed_internal_delay.samples, 64.25)
        self.assertEqual(
            profile.fixed_internal_delay.sample_domain,
            SampleDomain.RFDC_COMPLEX_INPUT,
        )
        self.assertEqual(profile.fixed_internal_delay.sample_rate_hz, 500_000_000)
        self.assertEqual(
            profile.fixed_internal_delay.reference_boundary,
            "rfdc_adc_complex_input_to_dac_baseband_output",
        )
        self.assertTrue(profile.fixed_internal_delay.includes_common_hardware_latency)
        self.assertFalse(profile.fixed_internal_delay.includes_programmable_target_delay)
        self.assertFalse(
            profile.fixed_internal_delay.includes_golden_fractional_kernel_center
        )

    def test_predistortion_recovers_desired_hv_after_forward_matrix(self) -> None:
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        profile = CalibrationProfile(
            **{
                **profile.__dict__,
                "tx_polarization_matrix": np.array(
                    [[1.0, 0.1j], [0.2, 0.8]], dtype=np.complex128
                ),
            }
        )
        desired = PolarimetricWaveform(
            np.array([[1 + 2j, 3 + 4j], [5 - 1j, 2 + 0j]]),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        model = GoldenTxPredistorter(profile)

        drive = model.predistort(desired)

        np.testing.assert_allclose(
            model.forward(drive).samples,
            desired.samples,
            atol=1e-12,
        )

    def test_singular_tx_matrix_is_rejected(self) -> None:
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        singular = np.array(
            [[1.0, 2.0], [2.0, 4.0]], dtype=np.complex128
        )

        with self.assertRaises(CalibrationConditionError):
            CalibrationProfile(
                **{
                    **profile.__dict__,
                    "tx_polarization_matrix": singular,
                }
            )


if __name__ == "__main__":
    unittest.main()
