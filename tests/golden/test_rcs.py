import unittest

from rfsoc_pulse_model.common.calibration_types import RcsCalibrationAnchor
from rfsoc_pulse_model.golden.rcs import (
    RcsCalibrationError,
    digital_gain_for_target,
)


class GoldenRcsTest(unittest.TestCase):
    def test_doubling_apparent_range_divides_voltage_gain_by_four(self) -> None:
        anchor = RcsCalibrationAnchor(
            frequency_hz=2.8e9,
            physical_range_m=100.0,
            equivalent_rcs_m2=1.0,
            digital_voltage_gain=0.5,
        )

        near, calibrated = digital_gain_for_target(
            1.0, 100.0, 1000.0, anchor, True
        )
        far, _ = digital_gain_for_target(
            1.0, 100.0, 2000.0, anchor, True
        )

        self.assertTrue(calibrated)
        self.assertAlmostEqual(far / near, 0.25)

    def test_absolute_mode_requires_an_anchor(self) -> None:
        with self.assertRaises(RcsCalibrationError):
            digital_gain_for_target(1.0, 100.0, 1000.0, None, True)

    def test_relative_mode_is_explicitly_uncalibrated(self) -> None:
        gain, calibrated = digital_gain_for_target(
            4.0, 100.0, 1000.0, None, False
        )

        self.assertAlmostEqual(gain, 0.02)
        self.assertFalse(calibrated)


if __name__ == "__main__":
    unittest.main()
