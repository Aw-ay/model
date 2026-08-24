import unittest
from typing import Optional

from rfsoc_pulse_model.common.events import (
    associate_polarimetric_range_records,
    associate_range_records,
)
from rfsoc_pulse_model.common.fixed import (
    PROJECT_ROUNDING_MODE,
    FixedFormat,
    RoundingMode,
    round_ties_away_from_zero,
)
from rfsoc_pulse_model.common.types import (
    ChannelIdentity,
    ChannelRole,
    GainRange,
    IQUnit,
    Polarization,
    PowerUnit,
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
    iq_width_bits: int = 16,
    channel_identity: Optional[ChannelIdentity] = None,
) -> PulseRecord:
    return PulseRecord(
        channel=channel,
        range_id=range_id,
        sample_domain=SampleDomain.DETECTOR,
        sample_rate_hz=sample_rate_hz,
        iq_width_bits=iq_width_bits,
        iq_fraction_bits=0,
        iq_signed=True,
        iq_unit=IQUnit.ADC_CODE,
        power_width_bits=32,
        power_fraction_bits=0,
        power_unit=PowerUnit.ADC_CODE_SQUARED,
        toa_samples=toa,
        pw_samples=width,
        peak_power=100,
        mean_power=80,
        freq_word=0,
        iq=((1, -1),),
        saturated=saturated,
        channel_identity=channel_identity,
    )


class CommonContractTest(unittest.TestCase):
    def test_record_carries_complete_iq_and_power_format(self) -> None:
        record = make_record(0, RangeId.PLUS_20_DB, 100, 10)

        self.assertEqual(record.iq_width_bits, 16)
        self.assertEqual(record.iq_fraction_bits, 0)
        self.assertTrue(record.iq_signed)
        self.assertEqual(record.iq_unit, IQUnit.ADC_CODE)
        self.assertEqual(record.power_width_bits, 32)
        self.assertEqual(record.power_fraction_bits, 0)
        self.assertEqual(record.power_unit, PowerUnit.ADC_CODE_SQUARED)
        self.assertEqual(record.power_definition, "I^2+Q^2")

    def test_record_rejects_iq_outside_declared_width(self) -> None:
        with self.assertRaisesRegex(ValueError, "IQ sample"):
            PulseRecord(
                **{
                    **make_record(0, RangeId.PLUS_20_DB, 100, 10).__dict__,
                    "iq": ((32_768, 0),),
                }
            )

    def test_record_rejects_power_outside_declared_width(self) -> None:
        with self.assertRaisesRegex(ValueError, "peak_power"):
            PulseRecord(
                **{
                    **make_record(0, RangeId.PLUS_20_DB, 100, 10).__dict__,
                    "peak_power": 1 << 32,
                }
            )

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

    def test_event_rejects_records_with_different_physical_formats(self) -> None:
        with self.assertRaisesRegex(ValueError, "physical format"):
            PulseEvent.from_records(
                event_id=1,
                records=(
                    make_record(0, RangeId.PLUS_20_DB, 100, 10),
                    make_record(
                        1,
                        RangeId.ZERO_DB,
                        100,
                        10,
                        iq_width_bits=15,
                    ),
                ),
                config_version=5,
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

    def test_polarimetric_association_never_mixes_h_and_v_ranges(self) -> None:
        records = (
            make_record(
                0,
                RangeId.PLUS_20_DB,
                100,
                10,
                channel_identity=ChannelIdentity(
                    Polarization.H, GainRange.HIGH, ChannelRole.ECHO, 0
                ),
            ),
            make_record(
                5,
                RangeId.ZERO_DB,
                100,
                10,
                channel_identity=ChannelIdentity(
                    Polarization.V, GainRange.MID, ChannelRole.ECHO, 5
                ),
            ),
            make_record(
                2,
                RangeId.MINUS_20_DB,
                101,
                10,
                channel_identity=ChannelIdentity(
                    Polarization.H, GainRange.LOW, ChannelRole.ECHO, 2
                ),
            ),
        )

        events = associate_polarimetric_range_records(
            records,
            toa_tolerance=2,
            width_tolerance=1,
            config_version=9,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(
            [event.polarization for event in events],
            [Polarization.H, Polarization.V],
        )
        self.assertEqual(events[0].channel_mask, (1 << 0) | (1 << 2))
        self.assertEqual(events[1].channel_mask, 1 << 5)

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

    def test_error_overflow_policy_never_hides_internal_width_loss(self) -> None:
        exact = FixedFormat(width=8, signed=True, overflow="error")

        self.assertEqual(exact.cast_integer(127), 127)
        with self.assertRaises(OverflowError):
            exact.cast_integer(128)


if __name__ == "__main__":
    unittest.main()
