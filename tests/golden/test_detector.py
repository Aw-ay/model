import math
import json
from pathlib import Path
import unittest

import numpy as np

from rfsoc_pulse_model.common.types import RangeId
from rfsoc_pulse_model.golden.detector import DetectorConfig, GoldenPulseDetector


class GoldenPulseDetectorTest(unittest.TestCase):
    def test_detector_config_loads_shared_default_mapping(self) -> None:
        # This catches a JSON configuration that exists only as documentation
        # and cannot actually drive the Golden layer.
        project_root = Path(__file__).resolve().parents[2]
        payload = json.loads(
            (project_root / "config/default.json").read_text(encoding="utf-8")
        )

        config = DetectorConfig.from_mapping(payload)

        self.assertEqual(config.noise_boot_samples, 16_384)
        self.assertEqual(config.moving_average, 8)
        self.assertEqual(config.vote_required, 3)

    def test_detect_accepts_complex_array_and_returns_ideal_pdw(self) -> None:
        # This catches a detector that reports the delayed vote edge instead of
        # the refined half-peak edge.
        iq = np.full(40, 3.0 - 2.0j, dtype=np.complex128)
        iq[16:23] = 1200.0 + 400.0j
        detector = GoldenPulseDetector(
            DetectorConfig(
                noise_boot_samples=8,
                threshold_scale=6.0,
                moving_average=2,
                vote_window=3,
                vote_required=2,
                pre_samples=2,
                post_samples=3,
            )
        )

        records = detector.detect(iq, channel=0, range_id=RangeId.PLUS_20_DB)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.toa_samples, 16)
        self.assertEqual(record.pw_samples, 7)
        self.assertEqual(record.peak_power, 1_600_000)
        self.assertEqual(record.mean_power, 1_600_000)
        self.assertEqual(len(record.iq), 12)

    def test_detect_estimates_signed_frequency_in_turns_and_q31(self) -> None:
        # This catches lost phase unwrap or a radians-versus-turns conversion.
        frequency = 0.125
        pulse = 10_000.0 * np.exp(2j * np.pi * frequency * np.arange(8))
        iq = np.concatenate(
            (
                np.zeros(8, dtype=np.complex128),
                pulse,
                np.zeros(8, dtype=np.complex128),
            )
        )
        detector = GoldenPulseDetector(
            DetectorConfig(
                noise_boot_samples=4,
                threshold_scale=2.0,
                moving_average=1,
                vote_window=1,
                vote_required=1,
            )
        )

        record = detector.detect(iq)[0]

        self.assertAlmostEqual(record.frequency_turns_per_sample, frequency, places=7)
        self.assertAlmostEqual(record.freq_word, 1 << 28, delta=2)

    def test_bootstrap_region_is_never_reported_as_a_pulse(self) -> None:
        # This catches accidental detection while the initial noise estimate is
        # still being learned.
        iq = np.array([1000.0 + 0.0j] * 4 + [0.0j] * 8)
        detector = GoldenPulseDetector(
            DetectorConfig(
                noise_boot_samples=4,
                threshold_scale=2.0,
                moving_average=1,
                vote_window=1,
                vote_required=1,
            )
        )

        self.assertEqual(detector.detect(iq), [])


if __name__ == "__main__":
    unittest.main()
