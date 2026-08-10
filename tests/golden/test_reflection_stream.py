import dataclasses
import unittest

import numpy as np

from rfsoc_pulse_model.common.calibration_types import (
    CalibrationProfile,
    ComplexChannelCalibration,
)
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    EightChannelAdcFrame,
    ReflectionScenario,
    TargetRequest,
)
from rfsoc_pulse_model.common.types import RangeSelectionMode, SampleDomain
from rfsoc_pulse_model.golden.system import (
    GoldenReflectionSource,
    GoldenReflectionStream,
)


class GoldenReflectionStreamTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        base = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        adc_channels = list(base.adc_channels)
        dac_channels = list(base.dac_channels)
        adc_channels[2] = ComplexChannelCalibration(response_delay_samples=0.25)
        dac_channels[0] = ComplexChannelCalibration(response_delay_samples=0.5)
        self.profile = dataclasses.replace(
            base,
            adc_channels=tuple(adc_channels),
            dac_channels=tuple(dac_channels),
        )

    @staticmethod
    def make_frame(length: int = 1024, start_sample: int = 0) -> EightChannelAdcFrame:
        absolute = start_sample + np.arange(length, dtype=np.float64)
        h = np.exp(2j * np.pi * 0.017 * absolute)
        v = 0.5j * np.exp(2j * np.pi * 0.011 * absolute)
        gate = ((absolute >= 180) & (absolute < 700)).astype(np.float64)
        samples = np.zeros((8, length), dtype=np.complex128)
        for index, gain in ((0, 10.0), (1, 1.0), (2, 0.1)):
            samples[index] = h * gate * gain
        for index, gain in ((4, 10.0), (5, 1.0), (6, 0.1)):
            samples[index] = v * gate * gain
        return EightChannelAdcFrame(
            samples,
            np.zeros((8, length), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
            start_sample,
        )

    def make_scenario(self, length: int, start_sample: int) -> ReflectionScenario:
        physical_range_m = 100.0
        device_delay_samples = 164.375
        apparent_range_m = physical_range_m + (
            299_792_458.0
            * device_delay_samples
            / self.config.reflection_sample_rate_hz
            / 2.0
        )
        return ReflectionScenario(
            physical_range_m=physical_range_m,
            carrier_frequency_hz=2.8e9,
            targets=(
                TargetRequest(
                    apparent_range_m,
                    15.0,
                    1.0,
                    np.array([[1.0, 0.2j], [-0.1j, 0.8]]),
                ),
            ),
            temperature_c=25.0,
            start_sample=start_sample,
            length=length,
            require_absolute_rcs=False,
        )

    def test_chunked_stream_matches_one_shot_reference(self) -> None:
        frame = self.make_frame()
        whole = GoldenReflectionSource(self.config, self.profile).run(
            frame,
            self.make_scenario(frame.samples.shape[1], 0),
        )
        stream = GoldenReflectionStream(self.config, self.profile)
        chunks = []
        for start in range(0, frame.samples.shape[1], 256):
            stop = min(start + 256, frame.samples.shape[1])
            chunk_frame = EightChannelAdcFrame(
                frame.samples[:, start:stop],
                frame.clipped[:, start:stop],
                frame.sample_domain,
                frame.sample_rate_hz,
                start,
            )
            chunks.append(
                stream.process_chunk(
                    chunk_frame,
                    self.make_scenario(stop - start, start),
                    final=stop == frame.samples.shape[1],
                )
            )

        for field in (
            "incident",
            "desired_reflection",
            "actual_uncompensated",
            "predistorted_reflection",
        ):
            combined = np.concatenate(
                [getattr(chunk, field).samples for chunk in chunks], axis=1
            )
            np.testing.assert_allclose(combined, getattr(whole, field).samples)
        np.testing.assert_allclose(
            np.concatenate([chunk.dac_frame.samples for chunk in chunks], axis=1),
            whole.dac_frame.samples,
        )
        self.assertEqual(
            tuple(record for chunk in chunks for record in chunk.pulse_records),
            whole.pulse_records,
        )

    def test_stream_rejects_a_gap_in_absolute_input_samples(self) -> None:
        stream = GoldenReflectionStream(self.config, self.profile)
        stream.process_chunk(
            self.make_frame(128, 1000),
            self.make_scenario(128, 1000),
        )

        with self.assertRaisesRegex(ValueError, "contiguous"):
            stream.process_chunk(
                self.make_frame(128, 1200),
                self.make_scenario(128, 1200),
                final=True,
            )

    def test_stream_preserves_auto_hold_state_across_chunk_boundaries(self) -> None:
        length = 512
        samples = np.zeros((8, length), dtype=np.complex128)
        clipped = np.zeros((8, length), dtype=np.bool_)
        for high, mid, low in ((0, 1, 2), (4, 5, 6)):
            samples[high] = 32_767.0
            samples[mid] = 4_000.0
            samples[low] = 400.0
            clipped[high] = True
        frame = EightChannelAdcFrame(
            samples,
            clipped,
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        whole = GoldenReflectionSource(
            self.config,
            self.profile,
            range_selection_mode=RangeSelectionMode.AUTO_HOLD,
        ).run(frame, self.make_scenario(length, 0))
        stream = GoldenReflectionStream(
            self.config,
            self.profile,
            range_selection_mode=RangeSelectionMode.AUTO_HOLD,
        )

        first = stream.process_chunk(
            EightChannelAdcFrame(
                samples[:, :256],
                clipped[:, :256],
                SampleDomain.RFDC_COMPLEX_INPUT,
                500_000_000,
                0,
            ),
            self.make_scenario(256, 0),
        )
        second = stream.process_chunk(
            EightChannelAdcFrame(
                samples[:, 256:],
                clipped[:, 256:],
                SampleDomain.RFDC_COMPLEX_INPUT,
                500_000_000,
                256,
            ),
            self.make_scenario(256, 256),
            final=True,
        )

        np.testing.assert_allclose(
            np.concatenate((first.incident.samples, second.incident.samples), axis=1),
            whole.incident.samples,
        )

    def test_stream_monitor_records_match_one_shot_fir_and_detector(self) -> None:
        detector = dataclasses.replace(
            self.config.detector,
            noise_boot_samples=16,
            threshold_scale=2.0,
            moving_average=1,
            vote_window=1,
            vote_required=1,
        )
        config = dataclasses.replace(self.config, detector=detector)
        frame = self.make_frame()
        whole = GoldenReflectionSource(config, self.profile).run(
            frame,
            self.make_scenario(frame.samples.shape[1], 0),
        )
        stream = GoldenReflectionStream(config, self.profile)
        records = []
        for start in range(0, 1024, 256):
            stop = start + 256
            result = stream.process_chunk(
                EightChannelAdcFrame(
                    frame.samples[:, start:stop],
                    frame.clipped[:, start:stop],
                    frame.sample_domain,
                    frame.sample_rate_hz,
                    start,
                ),
                self.make_scenario(256, start),
                final=stop == 1024,
            )
            self.assertEqual(
                result.status.monitor_pulse_count,
                len(result.pulse_records),
            )
            records.extend(result.pulse_records)

        self.assertTrue(whole.pulse_records)
        self.assertEqual(tuple(records), whole.pulse_records)


if __name__ == "__main__":
    unittest.main()
