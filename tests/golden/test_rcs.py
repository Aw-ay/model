import unittest

from rfsoc_pulse_model.common.calibration_types import RcsCalibrationAnchor
from rfsoc_pulse_model.golden.rcs import (
    RcsCalibrationError,
    digital_gain_for_target,
)


class GoldenRcsTest(unittest.TestCase):
    @staticmethod
    def anchor(*, valid: bool = True) -> RcsCalibrationAnchor:
        return RcsCalibrationAnchor(
            calibration_id="anechoic-2026-08-10-a",
            valid=valid,
            frequency_hz=2.8e9,
            frequency_tolerance_hz=1.0e6,
            temperature_c=25.0,
            temperature_tolerance_c=2.0,
            physical_range_m=100.0,
            physical_range_tolerance_m=0.1,
            equivalent_rcs_m2=1.0,
            digital_voltage_gain=0.5,
        )

    def test_doubling_apparent_range_divides_voltage_gain_by_four(self) -> None:
        anchor = self.anchor()

        near, calibrated = digital_gain_for_target(
            1.0,
            100.0,
            1000.0,
            anchor,
            True,
            operating_frequency_hz=2.8e9,
            operating_temperature_c=25.0,
        )
        far, _ = digital_gain_for_target(
            1.0,
            100.0,
            2000.0,
            anchor,
            True,
            operating_frequency_hz=2.8e9,
            operating_temperature_c=25.0,
        )

        self.assertTrue(calibrated)
        self.assertAlmostEqual(far / near, 0.25)

    def test_absolute_mode_requires_an_anchor(self) -> None:
        with self.assertRaises(RcsCalibrationError):
            digital_gain_for_target(
                1.0,
                100.0,
                1000.0,
                None,
                True,
                operating_frequency_hz=2.8e9,
                operating_temperature_c=25.0,
            )

    def test_absolute_mode_rejects_an_anchor_marked_invalid(self) -> None:
        with self.assertRaisesRegex(RcsCalibrationError, "marked invalid"):
            digital_gain_for_target(
                1.0,
                100.0,
                1000.0,
                self.anchor(valid=False),
                True,
                operating_frequency_hz=2.8e9,
                operating_temperature_c=25.0,
            )

    def test_absolute_mode_rejects_out_of_condition_anchor(self) -> None:
        for name, frequency, temperature, physical_range in (
            ("frequency", 2.802e9, 25.0, 100.0),
            ("temperature", 2.8e9, 28.0, 100.0),
            ("physical range", 2.8e9, 25.0, 100.2),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RcsCalibrationError, name):
                    digital_gain_for_target(
                        1.0,
                        physical_range,
                        1000.0,
                        self.anchor(),
                        True,
                        operating_frequency_hz=frequency,
                        operating_temperature_c=temperature,
                    )

    def test_relative_mode_is_explicitly_uncalibrated(self) -> None:
        gain, calibrated = digital_gain_for_target(
            4.0,
            100.0,
            1000.0,
            None,
            False,
            operating_frequency_hz=2.8e9,
            operating_temperature_c=25.0,
        )

        self.assertAlmostEqual(gain, 0.02)
        self.assertFalse(calibrated)

    def test_relative_mode_ignores_an_invalid_anchor(self) -> None:
        gain, calibrated = digital_gain_for_target(
            4.0,
            100.0,
            1000.0,
            self.anchor(valid=False),
            False,
            operating_frequency_hz=2.8e9,
            operating_temperature_c=25.0,
        )

        self.assertAlmostEqual(gain, 0.02)
        self.assertFalse(calibrated)


if __name__ == "__main__":
    unittest.main()
