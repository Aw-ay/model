import json
from pathlib import Path
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.fixed import RoundingMode
from rfsoc_pulse_model.common.types import SampleDomain


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
        self.assertEqual(config.detector_sample_rate_hz, 250_000_000)
        self.assertEqual(config.detector.sample_domain, SampleDomain.DETECTOR)
        self.assertEqual(config.detector.sample_rate_hz, 250_000_000)
        self.assertEqual(config.source_sample_index(3), 13)
        self.assertAlmostEqual(config.detector_sample_period_seconds, 4e-9)
        self.assertEqual(config.rounding_mode, RoundingMode.TIES_AWAY_FROM_ZERO)

    def test_inconsistent_detector_rate_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["detector_sample_rate_hz"] = 125_000_000

        with self.assertRaisesRegex(ValueError, "detector_sample_rate_hz"):
            ModelConfig.from_mapping(payload)

    def test_inconsistent_fabric_parallelism_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["rfdc_iq_stream_words_per_cycle"] = 1

        with self.assertRaisesRegex(ValueError, "rx_fabric_clock_hz"):
            ModelConfig.from_mapping(payload)

    def test_installed_package_loads_its_default_config_resource(self) -> None:
        config = ModelConfig.load_default()

        self.assertEqual(config.config_version, 5)
        self.assertEqual(config.channels, 4)


if __name__ == "__main__":
    unittest.main()
