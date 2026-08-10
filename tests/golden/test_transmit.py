import unittest

import numpy as np

from rfsoc_pulse_model.golden.transmit import (
    DacIq16Codes,
    GoldenLfmConfig,
    generate_lfm_samples,
    generate_lfm_waveform,
    quantize_complex_iq16,
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

    def test_complex_dac_boundary_rounds_and_saturates_i_and_q_separately(self) -> None:
        samples = np.array(
            [
                [
                    32767.49 + 0.5j,
                    32767.5 - 0.5j,
                    -32768.49 + 1.5j,
                    -32768.5 - 1.5j,
                ]
            ],
            dtype=np.complex128,
        )

        codes = quantize_complex_iq16(samples)

        np.testing.assert_array_equal(
            codes.i,
            np.array([[32767, 32767, -32768, -32768]], dtype=np.int16),
        )
        np.testing.assert_array_equal(
            codes.q,
            np.array([[1, -1, 2, -2]], dtype=np.int16),
        )
        np.testing.assert_array_equal(
            codes.clipped,
            np.array([[False, True, False, True]], dtype=np.bool_),
        )

    def test_complex_dac_boundary_rejects_nonfinite_codes(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            quantize_complex_iq16(np.array([[complex(np.nan, 0.0)]]))

    def test_dac_iq_code_container_rejects_implicit_integer_wrap(self) -> None:
        with self.assertRaisesRegex(ValueError, "int16"):
            DacIq16Codes(
                i=np.array([[65_535]], dtype=np.int64),
                q=np.array([[0]], dtype=np.int16),
                clipped=np.array([[False]], dtype=np.bool_),
            )


if __name__ == "__main__":
    unittest.main()
