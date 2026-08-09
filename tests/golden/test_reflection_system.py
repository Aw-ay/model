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
from rfsoc_pulse_model.common.types import RangeId, SampleDomain
from rfsoc_pulse_model.golden.system import GoldenReflectionSource


class GoldenReflectionSystemTest(unittest.TestCase):
    def test_public_package_exports_reflection_source(self) -> None:
        from rfsoc_pulse_model import GoldenReflectionSource as PublicSource

        self.assertIs(PublicSource, GoldenReflectionSource)

    def make_input(self) -> EightChannelAdcFrame:
        samples = np.zeros((8, 512), dtype=np.complex128)
        samples[0:3, 80:160] = 1000.0
        samples[4:7, 80:160] = 500.0j
        return EightChannelAdcFrame(
            samples,
            np.zeros((8, 512), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

    def make_scenario(self) -> ReflectionScenario:
        return ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.8e9,
            targets=(TargetRequest(150.0, 0.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
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


if __name__ == "__main__":
    unittest.main()
