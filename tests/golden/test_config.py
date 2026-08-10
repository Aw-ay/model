import dataclasses
import json
from pathlib import Path
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.fixed import RoundingMode
from rfsoc_pulse_model.common.types import IQUnit, PowerUnit, SampleDomain


class ModelConfigTest(unittest.TestCase):
    @staticmethod
    def root_payload() -> dict:
        project_root = Path(__file__).resolve().parents[2]
        return json.loads(
            (project_root / "config/default.json").read_text(encoding="utf-8")
        )

    def test_default_config_validates_all_sample_rate_relationships(self) -> None:
        config = ModelConfig.from_mapping(self.root_payload())

        self.assertEqual(config.rfdc_complex_sample_rate_hz, 500_000_000)
        self.assertEqual(config.rfdc_complex_samples_per_cycle, 2)
        self.assertEqual(
            config.dac_nominal_gain_policy,
            "external_analog_path",
        )
        self.assertEqual(config.detector_sample_rate_hz, 250_000_000)
        self.assertEqual(config.detector.sample_domain, SampleDomain.DETECTOR)
        self.assertEqual(config.detector.sample_rate_hz, 250_000_000)
        self.assertEqual(config.source_sample_index(3), 13)
        self.assertAlmostEqual(config.detector_sample_period_seconds, 4e-9)
        self.assertEqual(config.rounding_mode, RoundingMode.TIES_AWAY_FROM_ZERO)
        self.assertEqual(config.iq_width_bits, 16)
        self.assertTrue(config.iq_signed)
        self.assertEqual(config.iq_fraction_bits, 0)
        self.assertEqual(config.iq_unit, IQUnit.ADC_CODE)
        self.assertEqual(config.power_width_bits, 32)
        self.assertEqual(config.power_fraction_bits, 0)
        self.assertEqual(config.power_unit, PowerUnit.ADC_CODE_SQUARED)
        self.assertEqual(config.detector.iq_width_bits, config.iq_width_bits)
        self.assertEqual(config.detector.power_unit, config.power_unit)

    def test_rfdc_axis_format_freezes_dual_adc_iq_and_real_dac_words(self) -> None:
        config = ModelConfig.from_mapping(self.root_payload())
        axis = config.rfdc_axis

        self.assertEqual(axis.adc_data_type, "iq_separate_streams")
        self.assertEqual(axis.adc_component_width_bits, 16)
        self.assertEqual(axis.adc_component_stream_width_bits, 32)
        self.assertEqual(axis.adc_component_samples_per_cycle, 2)
        self.assertEqual(axis.adc_i_axis(0), "m00_axis")
        self.assertEqual(axis.adc_q_axis(0), "m01_axis")
        self.assertEqual(axis.adc_i_axis(7), "m32_axis")
        self.assertEqual(axis.adc_q_axis(7), "m33_axis")
        self.assertEqual(axis.dac_data_type, "real")
        self.assertEqual(axis.dac_sample_width_bits, 16)
        self.assertEqual(axis.dac_axis_width_bits, 32)
        self.assertEqual(axis.dac_samples_per_cycle, 2)
        self.assertEqual(axis.dac_axis(0), "s00_axis")
        self.assertEqual(axis.dac_axis(7), "s13_axis")

    def test_rfdc_axis_known_words_have_sample_zero_in_least_significant_bits(self) -> None:
        axis = ModelConfig.from_mapping(self.root_payload()).rfdc_axis

        i_word = axis.pack_adc_component_samples((-32_768, 12_345))
        q_word = axis.pack_adc_component_samples((-1, 32_767))
        self.assertEqual(i_word, 0x3039_8000)
        self.assertEqual(q_word, 0x7FFF_FFFF)
        self.assertEqual(
            axis.pack_complex_samples(i_word, q_word),
            0x7FFF_3039_FFFF_8000,
        )
        self.assertEqual(
            axis.unpack_complex_samples(0x7FFF_3039_FFFF_8000),
            ((-32_768, -1), (12_345, 32_767)),
        )
        self.assertEqual(axis.pack_dac_samples((-32_768, 32_767)), 0x7FFF_8000)

    def test_rfdc_axis_rejects_old_64_bit_125_mhz_component_stream_contract(self) -> None:
        payload = self.root_payload()
        payload["rfdc_axis_format"]["adc_component_stream_width_bits"] = 64
        payload["rfdc_axis_format"]["adc_component_samples_per_cycle"] = 4

        with self.assertRaisesRegex(ValueError, "two signed-16 samples"):
            ModelConfig.from_mapping(payload)

    def test_rfdc_axis_rejects_q_stream_detached_from_physical_adc(self) -> None:
        payload = self.root_payload()
        payload["rfdc_axis_format"]["adc_q_axis_names"][0] = "m02_axis"

        with self.assertRaisesRegex(ValueError, "I/Q AXI interface names"):
            ModelConfig.from_mapping(payload)

    def test_inconsistent_detector_rate_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["detector_sample_rate_hz"] = 125_000_000

        with self.assertRaisesRegex(ValueError, "detector_sample_rate_hz"):
            ModelConfig.from_mapping(payload)

    def test_inconsistent_fabric_parallelism_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["rfdc_complex_samples_per_cycle"] = 1

        with self.assertRaisesRegex(ValueError, "rx_fabric_clock_hz"):
            ModelConfig.from_mapping(payload)

    def test_ambiguous_rfdc_words_per_cycle_name_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["rfdc_iq_stream_words_per_cycle"] = payload.pop(
            "rfdc_complex_samples_per_cycle"
        )

        with self.assertRaisesRegex(
            ValueError,
            "rfdc_iq_stream_words_per_cycle.*removed",
        ):
            ModelConfig.from_mapping(payload)

    def test_installed_package_loads_its_default_config_resource(self) -> None:
        config = ModelConfig.load_default()

        self.assertEqual(config.model_schema_version, 8)
        self.assertEqual(config.config_version, 12)
        self.assertEqual(config.channels, 4)

    def test_unknown_power_unit_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["power_unit"] = "watt"

        with self.assertRaisesRegex(ValueError, "watt"):
            ModelConfig.from_mapping(payload)

    def test_adc_code_iq_rejects_an_undeclared_fractional_scale(self) -> None:
        payload = self.root_payload()
        payload["iq_fraction_bits"] = 1
        payload["power_fraction_bits"] = 2

        with self.assertRaisesRegex(ValueError, "zero fractional bits"):
            ModelConfig.from_mapping(payload)

    def test_reflection_rate_and_capacity_are_static_contracts(self) -> None:
        config = ModelConfig.load_default()

        self.assertEqual(config.adc_channels, 8)
        self.assertEqual(config.dac_channels, 8)
        self.assertEqual(config.polarizations, 2)
        self.assertEqual(config.reflection_sample_rate_hz, 500_000_000)
        self.assertEqual(config.maximum_targets, 8)
        self.assertEqual(config.maximum_delay_samples, 1_048_576)
        self.assertEqual(config.fractional_delay_taps, 63)

    def test_duplicate_adc_index_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["adc_channel_map"][1]["index"] = 0

        with self.assertRaisesRegex(ValueError, "adc_channel_map.*index"):
            ModelConfig.from_mapping(payload)

    def test_duplicate_adc_rfdc_route_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["adc_channel_map"][1]["rfdc_tile"] = 0
        payload["adc_channel_map"][1]["rfdc_slice"] = 0

        with self.assertRaisesRegex(ValueError, "adc_channel_map.*RFDC route"):
            ModelConfig.from_mapping(payload)

    def test_noncanonical_adc_rfdc_route_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["adc_channel_map"][0]["rfdc_slice"] = 1

        with self.assertRaisesRegex(ValueError, "adc_channel_map.*canonical"):
            ModelConfig.from_mapping(payload)

    def test_noncanonical_dac_rfdc_route_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["dac_channel_map"][0]["rfdc_tile"] = 2

        with self.assertRaisesRegex(ValueError, "dac_channel_map.*canonical"):
            ModelConfig.from_mapping(payload)

    def test_channel_index_cannot_be_detached_from_its_rfdc_route(self) -> None:
        for kind in ("adc", "dac"):
            with self.subTest(kind=kind):
                payload = self.root_payload()
                channel_map = payload[f"{kind}_channel_map"]
                first_route = (
                    channel_map[0]["rfdc_tile"],
                    channel_map[0]["rfdc_slice"],
                )
                channel_map[0]["rfdc_tile"] = channel_map[1]["rfdc_tile"]
                channel_map[0]["rfdc_slice"] = channel_map[1]["rfdc_slice"]
                channel_map[1]["rfdc_tile"] = first_route[0]
                channel_map[1]["rfdc_slice"] = first_route[1]

                with self.assertRaisesRegex(
                    ValueError,
                    f"{kind}_channel_map.*index.*RFDC",
                ):
                    ModelConfig.from_mapping(payload)

    def test_dataclass_replace_cannot_bypass_model_validation(self) -> None:
        config = ModelConfig.load_default()

        with self.assertRaisesRegex(ValueError, "detector_sample_rate_hz"):
            dataclasses.replace(
                config,
                detector_sample_rate_hz=123_000_000,
            )

    def test_dac_echo_map_requires_every_polarization_and_range(self) -> None:
        payload = self.root_payload()
        payload["dac_channel_map"][5]["polarization"] = "V"
        payload["dac_channel_map"][5]["gain_range"] = "mid"

        with self.assertRaisesRegex(
            ValueError,
            "dac_channel_map.*polarization and gain range",
        ):
            ModelConfig.from_mapping(payload)

    def test_unknown_dac_nominal_gain_policy_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["dac_nominal_gain_policy"] = "implicit_guess"

        with self.assertRaisesRegex(ValueError, "dac_nominal_gain_policy"):
            ModelConfig.from_mapping(payload)

    def test_default_json_mirror_is_byte_identical(self) -> None:
        project_root = Path(__file__).resolve().parents[2]

        self.assertEqual(
            (project_root / "config/default.json").read_bytes(),
            (
                project_root
                / "src/rfsoc_pulse_model/config/default.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
