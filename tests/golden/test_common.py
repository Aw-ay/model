import unittest

from rfsoc_pulse_model.common.events import associate_range_records
from rfsoc_pulse_model.common.fixed import (
    PROJECT_ROUNDING_MODE,
    FixedFormat,
    RoundingMode,
    round_ties_away_from_zero,
)
from rfsoc_pulse_model.common.types import (
    PulseEvent,
    PulseRecord,
    RangeId,
    SampleDomain,
)


def make_record(
    channel: int,
    range_id: RangeId,
    toa: int,
    width: int,
    *,
    saturated: bool = False,
    sample_rate_hz: int = 250_000_000,
) -> PulseRecord:
    return PulseRecord(
        channel=channel,
        range_id=range_id,
        sample_domain=SampleDomain.DETECTOR,
        sample_rate_hz=sample_rate_hz,
        toa_samples=toa,
        pw_samples=width,
        peak_power=100,
        mean_power=80,
        freq_word=0,
        iq=((1, -1),),
        saturated=saturated,
    )


class CommonContractTest(unittest.TestCase):
    def test_record_converts_detector_samples_to_seconds(self) -> None:
        record = make_record(0, RangeId.PLUS_20_DB, 100, 10)

        self.assertEqual(record.sample_domain, SampleDomain.DETECTOR)
        self.assertAlmostEqual(record.toa_seconds, 100 / 250_000_000)
        self.assertAlmostEqual(record.pw_seconds, 10 / 250_000_000)

    def test_event_rejects_records_from_different_sample_rates(self) -> None:
        # This catches associating numerically similar ToA values expressed in
        # incompatible sample domains or rates.
        with self.assertRaisesRegex(ValueError, "sample domain and rate"):
            PulseEvent.from_records(
                event_id=1,
                records=(
                    make_record(0, RangeId.PLUS_20_DB, 100, 10),
                    make_record(
                        1,
                        RangeId.ZERO_DB,
                        100,
                        10,
                        sample_rate_hz=125_000_000,
                    ),
                ),
                config_version=4,
            )

    def test_event_selects_highest_gain_unsaturated_range(self) -> None:
        # This catches selecting the nominal +20 dB record after it clips.
        event = PulseEvent.from_records(
            event_id=7,
            records=(
                make_record(0, RangeId.PLUS_20_DB, 100, 10, saturated=True),
                make_record(1, RangeId.ZERO_DB, 101, 11),
                make_record(2, RangeId.MINUS_20_DB, 99, 9),
            ),
            config_version=4,
        )

        self.assertEqual(event.selected_range, RangeId.ZERO_DB)
        self.assertEqual(event.channel_mask, 0b0111)
        self.assertEqual(event.toa_samples, 99)

    def test_association_uses_toa_and_width_tolerances(self) -> None:
        records = (
            make_record(0, RangeId.PLUS_20_DB, 100, 10),
            make_record(1, RangeId.ZERO_DB, 102, 11),
            make_record(2, RangeId.MINUS_20_DB, 120, 10),
        )

        events = associate_range_records(
            records,
            toa_tolerance=3,
            width_tolerance=2,
            config_version=5,
        )

        self.assertEqual([event.channel_mask for event in events], [0b0011, 0b0100])

    def test_fixed_format_saturates_signed_q15(self) -> None:
        fmt = FixedFormat(width=16, signed=True, fraction_bits=15)

        self.assertEqual(fmt.quantize(1.25), 32767)
        self.assertEqual(fmt.quantize(-1.25), -32768)

    def test_project_rounding_is_ties_away_from_zero(self) -> None:
        # This catches Python/NumPy ties-to-even leaking into Golden while RTL
        # uses signed round-to-nearest-away-from-zero.
        self.assertEqual(PROJECT_ROUNDING_MODE, RoundingMode.TIES_AWAY_FROM_ZERO)
        self.assertEqual(
            [round_ties_away_from_zero(value) for value in (0.5, 1.5, -0.5, -1.5)],
            [1, 2, -1, -2],
        )
        integer = FixedFormat(width=8, signed=True)
        self.assertEqual(integer.quantize(0.5), 1)
        self.assertEqual(integer.quantize(-0.5), -1)


if __name__ == "__main__":
    unittest.main()
