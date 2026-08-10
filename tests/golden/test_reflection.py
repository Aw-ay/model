import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import (
    CalibrationProfile,
    RcsCalibrationAnchor,
)
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    CompiledScatterer,
    PolarimetricWaveform,
    ReflectionScenario,
    TargetRequest,
)
from rfsoc_pulse_model.common.types import SampleDomain
from rfsoc_pulse_model.golden.reflection import (
    GoldenPolarimetricReflectionKernel,
    TargetCompiler,
)
from rfsoc_pulse_model.golden.rcs import RcsCalibrationError


class GoldenReflectionTest(unittest.TestCase):
    def test_compiler_fails_closed_when_absolute_anchor_is_out_of_frequency(self) -> None:
        config = ModelConfig.load_default()
        anchor = RcsCalibrationAnchor(
            calibration_id="anechoic-2026-08-10-a",
            valid=True,
            frequency_hz=2.8e9,
            frequency_tolerance_hz=1.0e6,
            temperature_c=25.0,
            temperature_tolerance_c=2.0,
            physical_range_m=100.0,
            physical_range_tolerance_m=0.1,
            equivalent_rcs_m2=1.0,
            digital_voltage_gain=0.5,
        )
        calibration = CalibrationProfile.identity(2.8e9, 25.0, 64.0, anchor)
        scenario = ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.802e9,
            targets=(TargetRequest(1000.0, 0.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
            length=256,
            require_absolute_rcs=True,
        )

        with self.assertRaisesRegex(RcsCalibrationError, "frequency"):
            TargetCompiler(config, calibration).compile(scenario)

    def test_compiler_fails_closed_when_profile_is_out_of_frequency(self) -> None:
        config = ModelConfig.load_default()
        anchor = RcsCalibrationAnchor(
            calibration_id="wide-anchor",
            valid=True,
            frequency_hz=2.8e9,
            frequency_tolerance_hz=10.0e6,
            temperature_c=25.0,
            temperature_tolerance_c=10.0,
            physical_range_m=100.0,
            physical_range_tolerance_m=1.0,
            equivalent_rcs_m2=1.0,
            digital_voltage_gain=0.5,
        )
        calibration = CalibrationProfile.identity(2.8e9, 25.0, 64.0, anchor)
        scenario = ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.802e9,
            targets=(TargetRequest(1000.0, 0.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
            length=256,
            require_absolute_rcs=True,
        )

        with self.assertRaisesRegex(RcsCalibrationError, "profile frequency"):
            TargetCompiler(config, calibration).compile(scenario)

    def test_h_input_produces_hh_and_vh_outputs(self) -> None:
        samples = np.zeros((2, 128), dtype=np.complex128)
        samples[0, 4] = 1.0
        incident = PolarimetricWaveform(
            samples,
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        scatterer = CompiledScatterer(
            integer_delay_samples=40,
            fractional_delay=0.0,
            doppler_hz=0.0,
            complex_scattering_matrix=np.array(
                [[2, 0], [3j, 0]], dtype=np.complex128
            ),
        )

        result = GoldenPolarimetricReflectionKernel(taps=63).process(
            incident, (scatterer,)
        )

        self.assertAlmostEqual(result.samples[0, 44], 2.0, places=12)
        self.assertAlmostEqual(result.samples[1, 44], 3.0j, places=12)

    def test_doppler_uses_absolute_sample_index(self) -> None:
        samples = np.ones((2, 256), dtype=np.complex128)
        samples[1] = 0.0
        incident = PolarimetricWaveform(
            samples,
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
            start_sample=1000,
        )
        scatterer = CompiledScatterer(
            40,
            0.0,
            5_000_000.0,
            np.eye(2, dtype=np.complex128),
        )

        output = GoldenPolarimetricReflectionKernel(63).process(
            incident, (scatterer,)
        )

        phase_step = np.angle(
            output.samples[0, 101] * np.conj(output.samples[0, 100])
        )
        self.assertAlmostEqual(
            phase_step,
            2 * np.pi * 5_000_000 / 500_000_000,
        )

    def test_compiler_uses_receding_negative_doppler_convention(self) -> None:
        config = ModelConfig.load_default()
        calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )
        scenario = ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.8e9,
            targets=(TargetRequest(1000.0, 10.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
            length=256,
            require_absolute_rcs=False,
        )

        result = TargetCompiler(config, calibration).compile(scenario)

        self.assertAlmostEqual(
            result[0].doppler_hz,
            -2.0 * 10.0 * 2.8e9 / 299_792_458.0,
        )

    def test_compiler_exposes_full_device_range_carrier_phase(self) -> None:
        config = ModelConfig.load_default()
        fixed_delay_samples = 64.0
        calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=fixed_delay_samples,
            rcs_anchor=None,
        )
        device_delay_samples = 96.125
        physical_range_m = 100.0
        apparent_range_m = physical_range_m + (
            299_792_458.0
            * device_delay_samples
            / config.reflection_sample_rate_hz
            / 2.0
        )
        scenario = ReflectionScenario(
            physical_range_m=physical_range_m,
            carrier_frequency_hz=2.8e9,
            targets=(
                TargetRequest(
                    apparent_range_m,
                    0.0,
                    1.0,
                    np.eye(2),
                ),
            ),
            temperature_c=25.0,
            start_sample=0,
            length=256,
            require_absolute_rcs=False,
        )

        scatterer = TargetCompiler(config, calibration).compile(scenario)[0]

        expected = np.remainder(
            -2.0
            * np.pi
            * scenario.carrier_frequency_hz
            * device_delay_samples
            / config.reflection_sample_rate_hz
            + np.pi,
            2.0 * np.pi,
        ) - np.pi
        self.assertAlmostEqual(scatterer.range_carrier_phase_rad, expected)

    def test_kernel_applies_compiled_range_carrier_phase(self) -> None:
        samples = np.zeros((2, 96), dtype=np.complex128)
        samples[0, 4] = 1.0
        incident = PolarimetricWaveform(
            samples,
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        scatterer = CompiledScatterer(
            integer_delay_samples=40,
            fractional_delay=0.0,
            doppler_hz=0.0,
            complex_scattering_matrix=np.eye(2, dtype=np.complex128),
            range_carrier_phase_rad=np.pi / 2.0,
        )

        result = GoldenPolarimetricReflectionKernel(taps=63).process(
            incident, (scatterer,)
        )

        self.assertAlmostEqual(result.samples[0, 44], 1.0j, places=12)

    def test_multiple_targets_add_linearly(self) -> None:
        incident = PolarimetricWaveform(
            np.vstack((np.ones(192), np.full(192, 2.0))).astype(
                np.complex128
            ),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        first = CompiledScatterer(
            40, 0.0, 0.0, np.eye(2, dtype=np.complex128)
        )
        second = CompiledScatterer(
            48,
            0.0,
            0.0,
            np.array([[0.5, 0.25], [0.0, -1.0]], dtype=np.complex128),
        )
        kernel = GoldenPolarimetricReflectionKernel(taps=63)

        first_only = kernel.process(incident, (first,)).samples
        second_only = kernel.process(incident, (second,)).samples
        combined = kernel.process(incident, (first, second)).samples

        np.testing.assert_allclose(
            combined,
            first_only + second_only,
            atol=1e-12,
        )


if __name__ == "__main__":
    unittest.main()
