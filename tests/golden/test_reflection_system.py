import dataclasses
import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    EightChannelAdcFrame,
    ReflectionScenario,
    TargetRequest,
)
from rfsoc_pulse_model.common.types import (
    ChannelRole,
    Polarization,
    RangeId,
    SampleDomain,
    SampleTimeReference,
)
from rfsoc_pulse_model.golden.system import (
    GoldenReflectionSource,
    GoldenReflectionStream,
)


class GoldenReflectionSystemTest(unittest.TestCase):
    def test_public_package_exports_reflection_source(self) -> None:
        from rfsoc_pulse_model import (
            GoldenReflectionSource as PublicSource,
            GoldenReflectionStream as PublicStream,
        )

        self.assertIs(PublicSource, GoldenReflectionSource)
        self.assertIs(PublicStream, GoldenReflectionStream)

    def make_input(self, start_sample: int = 0) -> EightChannelAdcFrame:
        samples = np.zeros((8, 512), dtype=np.complex128)
        samples[0, 80:160] = 1000.0
        samples[1, 80:160] = 100.0
        samples[2, 80:160] = 10.0
        samples[4, 80:160] = 5000.0j
        samples[5, 80:160] = 500.0j
        samples[6, 80:160] = 50.0j
        return EightChannelAdcFrame(
            samples,
            np.zeros((8, 512), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
            start_sample,
        )

    def make_scenario(self, start_sample: int = 0) -> ReflectionScenario:
        return ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.8e9,
            targets=(TargetRequest(150.0, 0.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=start_sample,
            length=512,
            require_absolute_rcs=False,
        )

    def test_one_call_returns_hv_reflection_dac_frame_and_monitor_records(self) -> None:
        config = ModelConfig.load_default()
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)

        result = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )

        self.assertEqual(result.incident.samples.shape, (2, 512))
        self.assertEqual(result.desired_reflection.samples.shape, (2, 512))
        self.assertEqual(
            result.predistorted_reflection.samples.shape, (2, 512)
        )
        self.assertEqual(result.dac_frame.samples.shape, (8, 512))
        self.assertEqual(len(result.compiled_targets), 1)

    def test_dac_frame_exposes_normalized_and_physical_sample_time(self) -> None:
        config = ModelConfig.load_default()
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)

        result = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )

        self.assertEqual(
            result.dac_frame.time_reference,
            SampleTimeReference.LATENCY_NORMALIZED,
        )
        self.assertIs(
            result.dac_frame.fixed_internal_delay,
            profile.fixed_internal_delay,
        )
        self.assertEqual(
            result.dac_frame.sample_index(60, SampleTimeReference.LATENCY_NORMALIZED),
            60.0,
        )
        self.assertEqual(
            result.dac_frame.sample_index(60, SampleTimeReference.PHYSICAL),
            124.0,
        )

    def test_detector_threshold_cannot_move_or_change_dac_output(self) -> None:
        config = ModelConfig.load_default()
        quiet_detector = dataclasses.replace(
            config.detector,
            threshold_scale=1.0e12,
        )
        quiet_config = dataclasses.replace(config, detector=quiet_detector)
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)

        normal = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )
        quiet = GoldenReflectionSource(quiet_config, profile).run(
            self.make_input(), self.make_scenario()
        )

        np.testing.assert_array_equal(
            normal.dac_frame.samples,
            quiet.dac_frame.samples,
        )

    def test_monitor_uses_six_echo_channels_and_excludes_references(self) -> None:
        config = ModelConfig.load_default()
        fast_detector = dataclasses.replace(
            config.detector,
            noise_boot_samples=16,
            threshold_scale=2.0,
            moving_average=1,
            vote_window=1,
            vote_required=1,
        )
        config = dataclasses.replace(config, detector=fast_detector)
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)

        result = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )

        self.assertTrue(result.pulse_records)
        channels = {record.channel for record in result.pulse_records}
        self.assertTrue(channels <= {0, 1, 2, 4, 5, 6})
        self.assertFalse({3, 7} & channels)
        self.assertTrue(
            {record.range_id for record in result.pulse_records}
            <= {
                RangeId.PLUS_20_DB,
                RangeId.ZERO_DB,
                RangeId.MINUS_20_DB,
            }
        )
        self.assertTrue(
            all(
                record.channel_identity is not None
                and record.channel_identity.role == ChannelRole.ECHO
                and record.channel_identity.physical_channel == record.channel
                for record in result.pulse_records
            )
        )
        self.assertEqual(
            {event.polarization for event in result.pulse_events},
            {Polarization.H, Polarization.V},
        )

    def test_monitor_toa_uses_global_detector_time(self) -> None:
        config = ModelConfig.load_default()
        fast_detector = dataclasses.replace(
            config.detector,
            noise_boot_samples=16,
            threshold_scale=2.0,
            moving_average=1,
            vote_window=1,
            vote_required=1,
        )
        config = dataclasses.replace(config, detector=fast_detector)
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)

        local = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )
        absolute = GoldenReflectionSource(config, profile).run(
            self.make_input(1000), self.make_scenario(1000)
        )

        self.assertTrue(local.pulse_records)
        self.assertEqual(len(local.pulse_records), len(absolute.pulse_records))
        self.assertEqual(
            [record.toa_samples + 500 for record in local.pulse_records],
            [record.toa_samples for record in absolute.pulse_records],
        )

    def test_end_to_end_impulse_has_expected_amplitude_and_phase(self) -> None:
        config = ModelConfig.load_default()
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        samples = np.zeros((8, 160), dtype=np.complex128)
        for index, gain in ((0, 10.0), (1, 1.0), (2, 0.1)):
            samples[index, 20] = gain
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 160), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        physical_range_m = 100.0
        device_delay_samples = 104.0
        apparent_range_m = physical_range_m + (
            299_792_458.0
            * device_delay_samples
            / config.reflection_sample_rate_hz
            / 2.0
        )
        initial_phase = 0.3
        scenario = ReflectionScenario(
            physical_range_m=physical_range_m,
            carrier_frequency_hz=2.8e9,
            targets=(
                TargetRequest(
                    apparent_range_m,
                    0.0,
                    1.0,
                    np.array([[1.0, 0.0], [0.5j, 0.0]]),
                    initial_phase_rad=initial_phase,
                ),
            ),
            temperature_c=25.0,
            start_sample=0,
            length=160,
            require_absolute_rcs=False,
        )

        result = GoldenReflectionSource(config, profile).run(frame, scenario)

        gain = (physical_range_m / apparent_range_m) ** 2
        range_phase = result.compiled_targets[0].range_carrier_phase_rad
        expected_h = gain * np.exp(1j * (initial_phase + range_phase))
        self.assertAlmostEqual(
            result.desired_reflection.samples[0, 60],
            expected_h,
            places=12,
        )
        self.assertAlmostEqual(
            result.desired_reflection.samples[1, 60],
            0.5j * expected_h,
            places=12,
        )
        for index in (1, 3, 5):
            self.assertAlmostEqual(result.dac_frame.samples[index, 60], expected_h)


if __name__ == "__main__":
    unittest.main()
