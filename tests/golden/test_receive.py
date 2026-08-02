import unittest

import numpy as np

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.types import RangeId
from rfsoc_pulse_model.golden.detector import DetectorConfig
from rfsoc_pulse_model.golden.receive import (
    AdcSampleBatch,
    GoldenReceivePipeline,
    PulseSpec,
    SignalScenario,
    apply_range_gain,
    generate_iq,
    unpack_dual_iq_words,
)


class GoldenReceiveTest(unittest.TestCase):
    def test_receive_pipeline_consumes_unified_model_config(self) -> None:
        model_config = ModelConfig.load_default()

        pipeline = GoldenReceivePipeline(model_config)

        self.assertIs(pipeline.detector.config, model_config.detector)

    def test_dual_adc_words_form_two_time_aligned_complex_samples(self) -> None:
        # This catches swapped I/Q or swapped early/late sample lanes.
        actual = unpack_dual_iq_words(0xFFFE0001, 0x0004FFFD)

        np.testing.assert_array_equal(actual, np.array([1 - 3j, -2 + 4j]))

    def test_ideal_fir_decimator_reports_filter_center_source_indices(self) -> None:
        # This catches using the newest sample index as ToA instead of the FIR
        # group-delay-corrected center index.
        source = np.full(20, 1000.0 - 500.0j, dtype=np.complex128)

        result = GoldenReceivePipeline().decimate(source)

        np.testing.assert_array_equal(result.source_sample_indices, [7, 9, 11])
        np.testing.assert_allclose(result.iq, [1000.0 - 500.0j] * 3, atol=1e-9)

    def test_range_gain_models_adc_clipping(self) -> None:
        # This catches a gain model that wraps rather than clips ADC values.
        source = np.array([4000.0 - 4000.0j])

        plus_result = apply_range_gain(source, 20.0)
        minus_result = apply_range_gain(source, -20.0)

        self.assertIsInstance(plus_result, AdcSampleBatch)
        np.testing.assert_array_equal(
            plus_result.iq,
            np.array([32767.0 - 32768.0j]),
        )
        np.testing.assert_array_equal(plus_result.clipped, [True])
        self.assertTrue(plus_result.any_clipped)
        np.testing.assert_array_equal(
            minus_result.iq,
            np.array([400.0 - 400.0j]),
        )
        np.testing.assert_array_equal(minus_result.clipped, [False])
        self.assertFalse(minus_result.any_clipped)

    def test_adc_clipping_propagates_through_fir_into_pulse_record(self) -> None:
        # This catches dropping the clipping sideband between gain modeling,
        # FIR decimation, and the final PulseRecord.
        source = np.concatenate(
            (
                np.full(40, 100.0 + 0.0j),
                np.full(40, 4000.0 + 0.0j),
                np.full(160, 100.0 + 0.0j),
            )
        )
        gained = apply_range_gain(source, 20.0)
        pipeline = GoldenReceivePipeline(
            DetectorConfig(
                noise_boot_samples=4,
                threshold_scale=3.0,
                moving_average=1,
                vote_window=1,
                vote_required=1,
            )
        )

        records = pipeline.detect(gained)

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].saturated)

    def test_adc_quantization_uses_project_ties_away_rounding(self) -> None:
        result = apply_range_gain(np.array([0.5 - 0.5j]), 0.0)

        np.testing.assert_array_equal(result.iq, np.array([1.0 - 1.0j]))

    def test_signal_scenario_places_requested_complex_tone_pulse(self) -> None:
        # This catches using absolute time instead of pulse-relative time in
        # the phase law.
        scenario = SignalScenario(
            length=8,
            pulses=(
                PulseSpec(
                    toa=2,
                    width=4,
                    amplitude=1000.0,
                    frequency_turns_per_sample=0.25,
                ),
            ),
        )

        iq = generate_iq(scenario)

        np.testing.assert_allclose(
            iq,
            [0, 0, 1000, 1000j, -1000, -1000j, 0, 0],
            atol=1e-9,
        )

    def test_receive_pipeline_detects_on_the_decimated_timebase(self) -> None:
        # This catches a receive facade that bypasses the FIR or never passes
        # its decimated array to the detector.
        source = np.concatenate(
            (
                np.full(40, 100.0 + 0.0j),
                np.full(40, 6000.0 + 0.0j),
                np.full(160, 100.0 + 0.0j),
            )
        )
        pipeline = GoldenReceivePipeline(
            DetectorConfig(
                noise_boot_samples=4,
                threshold_scale=3.0,
                moving_average=1,
                vote_window=1,
                vote_required=1,
                pre_samples=2,
                post_samples=2,
            )
        )

        records = pipeline.detect(source, channel=1, range_id=RangeId.ZERO_DB)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].channel, 1)
        self.assertEqual(records[0].range_id, RangeId.ZERO_DB)
        self.assertGreater(records[0].pw_samples, 0)


if __name__ == "__main__":
    unittest.main()
