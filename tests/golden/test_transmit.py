import unittest

import numpy as np

from rfsoc_pulse_model.golden.transmit import (
    GoldenLfmConfig,
    generate_lfm_samples,
    generate_lfm_waveform,
)


class GoldenTransmitTest(unittest.TestCase):
    def test_quarter_turn_tone_has_hand_derived_full_scale_samples(self) -> None:
        # This catches an incorrect phase-word scale or sample-update order.
        config = GoldenLfmConfig(
            phase_inc_0=0x40000000,
            phase_inc_step=0,
            pulse_samples=4,
            amplitude_q15=32767,
        )

        np.testing.assert_array_equal(
            generate_lfm_samples(config),
            np.array([0, 32767, 0, -32767], dtype=np.int16),
        )

    def test_chirp_updates_increment_after_each_emitted_sample(self) -> None:
        # For increments 1/8, 2/8, 3/8 turns, emitted phases are 0, 1/8,
        # and 3/8 turns. This catches updating the chirp step too early.
        config = GoldenLfmConfig(
            phase_inc_0=0x20000000,
            phase_inc_step=0x20000000,
            pulse_samples=3,
            amplitude_q15=32767,
        )

        waveform = generate_lfm_waveform(config)

        np.testing.assert_allclose(
            waveform,
            [0.0, 32767.0 / np.sqrt(2.0), 32767.0 / np.sqrt(2.0)],
            atol=1e-9,
        )

    def test_invalid_pulse_length_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pulse_samples"):
            GoldenLfmConfig(0, 0, 0, 32767)


if __name__ == "__main__":
    unittest.main()

