import unittest

try:
    from rfsoc_pulse_model.cycle.hardware.calibrator_datapath import (
        CHANNEL_COUNT,
        FRACTIONAL_DELAY_TAPS,
        ActiveCalibrationBank,
        AutoRangeSelector2Spc,
        CalibratorChannelParameters,
        EightChannelCalibrationPipeline2Spc,
        apply_complex_gain,
    )
except ImportError:  # RED until the deployable calibration data path exists.
    CHANNEL_COUNT = FRACTIONAL_DELAY_TAPS = None  # type: ignore[assignment]
    ActiveCalibrationBank = AutoRangeSelector2Spc = None  # type: ignore[assignment,misc]
    CalibratorChannelParameters = EightChannelCalibrationPipeline2Spc = None  # type: ignore[assignment,misc]
    apply_complex_gain = None  # type: ignore[assignment]


ZERO_LANE = tuple((0, 0) for _ in range(8))


class CalibratorDatapathTest(unittest.TestCase):
    def test_parameter_bounds_taps_and_shadow_commit_are_atomic(self) -> None:
        self.assertEqual(CHANNEL_COUNT, 8)
        self.assertEqual(FRACTIONAL_DELAY_TAPS, 63)
        assert CalibratorChannelParameters is not None and ActiveCalibrationBank is not None

        with self.assertRaisesRegex(ValueError, "0..2047"):
            CalibratorChannelParameters(integer_delay=2048)
        with self.assertRaisesRegex(ValueError, "signed 24-bit"):
            CalibratorChannelParameters(gain_real=1 << 23)

        bank = ActiveCalibrationBank()
        bank.write_shadow(3, CalibratorChannelParameters(integer_delay=17, gain_imag=-2))
        self.assertEqual(bank.active[3].integer_delay, 0)
        with self.assertRaisesRegex(RuntimeError, "acquisition is stopped"):
            bank.commit(acquisition_enabled=True)
        self.assertEqual(bank.config_version, 0)
        bank.commit(acquisition_enabled=False)
        self.assertEqual(bank.active[3].integer_delay, 17)
        self.assertEqual(bank.active[3].gain_imag, -2)
        self.assertEqual(bank.config_version, 1)

    def test_complex_q20_gain_uses_ties_away_and_saturates_s24(self) -> None:
        assert apply_complex_gain is not None
        unity = 1 << 20
        self.assertEqual(apply_complex_gain((1, 1), unity // 2, 0), (1, 1))
        self.assertEqual(apply_complex_gain((-1, -1), unity // 2, 0), (-1, -1))
        self.assertEqual(apply_complex_gain((3, -5), 0, unity), (5, 3))
        self.assertEqual(
            apply_complex_gain(((1 << 23) - 1, 0), (1 << 23) - 1, 0),
            ((1 << 23) - 1, 0),
        )

    def test_integer_and_fractional_filter_preserve_2spc_lane_order(self) -> None:
        assert CalibratorChannelParameters is not None
        assert EightChannelCalibrationPipeline2Spc is not None
        params = [CalibratorChannelParameters() for _ in range(8)]
        params[0] = CalibratorChannelParameters(integer_delay=2)
        pipeline = EightChannelCalibrationPipeline2Spc(tuple(params))

        observed = []
        for sample_index in range(40):
            lane0 = list(ZERO_LANE)
            lane1 = list(ZERO_LANE)
            lane0[0] = (1000 if 2 * sample_index == 0 else 0, 0)
            lane1[0] = (1000 if 2 * sample_index + 1 == 0 else 0, 0)
            out0, out1 = pipeline.process_beat(tuple(lane0), tuple(lane1))
            observed.extend((out0[0][0], out1[0][0]))

        self.assertEqual(observed[2 + 31], 1000)
        self.assertEqual(sum(abs(value) for index, value in enumerate(observed) if index != 33), 0)

    def test_maximum_integer_delay_is_accepted(self) -> None:
        assert CalibratorChannelParameters is not None
        assert EightChannelCalibrationPipeline2Spc is not None
        params = (CalibratorChannelParameters(integer_delay=2047),) + tuple(
            CalibratorChannelParameters() for _ in range(7)
        )
        pipeline = EightChannelCalibrationPipeline2Spc(params)
        observed = []
        for index in range(1041):
            lane0 = list(ZERO_LANE)
            lane1 = list(ZERO_LANE)
            if index == 0:
                lane0[0] = (17, -19)
            out0, out1 = pipeline.process_beat(tuple(lane0), tuple(lane1))
            observed.extend((out0[0], out1[0]))
        self.assertEqual(observed[2047 + 31], (17, -19))

    def test_auto_range_is_independent_per_polarization_and_ignores_references(self) -> None:
        assert AutoRangeSelector2Spc is not None
        selector = AutoRangeSelector2Spc(high_water=29490, low_water=8192, hold_samples=64)
        samples = list(ZERO_LANE)
        samples[0] = (30000, 0)  # H high overloads, H mid is safe.
        samples[1] = (2000, 0)
        samples[4] = (1000, 0)   # V stays high.
        samples[7] = (32767, 32767)  # V reference must not participate.
        ranges0, ranges1 = selector.process_beat(tuple(samples), tuple(samples))
        self.assertEqual(ranges0, (1, 0))
        self.assertEqual(ranges1, (1, 0))

        safe = list(ZERO_LANE)
        safe[0] = safe[1] = safe[2] = (100, 100)
        safe[4] = safe[5] = safe[6] = (100, 100)
        for _ in range(31):
            selector.process_beat(tuple(safe), tuple(safe))
        self.assertEqual(selector.current_ranges, (1, 0))
        selector.process_beat(tuple(safe), tuple(safe))
        self.assertEqual(selector.current_ranges, (0, 0))


if __name__ == "__main__":
    unittest.main()
