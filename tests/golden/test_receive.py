import unittest

import numpy as np

from rfsoc_pulse_model.common.types import RangeId
from rfsoc_pulse_model.golden.detector import DetectorConfig
from rfsoc_pulse_model.golden.receive import (
    GoldenReceivePipeline,
    PulseSpec,
    SignalScenario,
    apply_range_gain,
    generate_iq,
    unpack_dual_iq_words,
)


class GoldenReceiveTest(unittest.TestCase):
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

        plus_20, clipped = apply_range_gain(source, 20.0)
        minus_20, lower_clipped = apply_range_gain(source, -20.0)

        np.testing.assert_array_equal(plus_20, np.array([32767.0 - 32768.0j]))
        self.assertTrue(clipped)
        np.testing.assert_array_equal(minus_20, np.array([400.0 - 400.0j]))
        self.assertFalse(lower_clipped)

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
