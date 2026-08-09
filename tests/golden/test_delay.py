import unittest

import numpy as np

from rfsoc_pulse_model.golden.delay import (
    CausalityError,
    apply_causal_delay,
    compile_target_delay,
)


class GoldenDelayTest(unittest.TestCase):
    def test_integer_delay_is_zero_filled_without_wraparound(self) -> None:
        source = np.zeros((2, 96), dtype=np.complex128)
        source[0, 10] = 1.0

        delayed = apply_causal_delay(source, 40, 0.0, taps=63)

        self.assertAlmostEqual(delayed[0, 50], 1.0, places=12)
        self.assertEqual(delayed[0, 0], 0.0)
        self.assertEqual(delayed[0, -1], 0.0)

    def test_noncausal_apparent_range_is_rejected(self) -> None:
        with self.assertRaises(CausalityError):
            compile_target_delay(
                apparent_range_m=100.0,
                physical_range_m=100.0,
                fixed_internal_delay_samples=64.0,
                sample_rate_hz=500_000_000,
                maximum_delay_samples=1_048_576,
                taps=63,
            )

    def test_fractional_delay_has_expected_tone_phase(self) -> None:
        n = np.arange(512)
        tone = np.exp(2j * np.pi * 0.05 * n)
        source = np.vstack((tone, np.zeros_like(tone)))

        delayed = apply_causal_delay(source, 48, 0.25, taps=63)

        valid = slice(128, 400)
        expected = tone[valid] * np.exp(-2j * np.pi * 0.05 * 48.25)
        np.testing.assert_allclose(delayed[0, valid], expected, atol=2e-3)


if __name__ == "__main__":
    unittest.main()
