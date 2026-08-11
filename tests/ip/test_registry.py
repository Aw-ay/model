import dataclasses
import unittest

from rfsoc_pulse_model.ip.registry import ArchitectureRegistry
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig, ImplementationKind


class ArchitectureRegistryTest(unittest.TestCase):
    def test_production_owner_map_exactly_matches_required_set(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        registry = ArchitectureRegistry.from_config(config)
        self.assertTrue(registry.responsibility_complete)
        self.assertEqual(
            set(registry.production_owner_map),
            set(config.required_responsibilities.production),
        )

    def test_legacy_reference_responsibilities_are_out_of_production_scope(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        registry = ArchitectureRegistry.from_config(config)
        self.assertNotIn(
            "legacy_reference.rx_group_ingress_2spc",
            registry.production_owner_map,
        )
        self.assertEqual(
            set(registry.reference_responsibility_map),
            {
                "legacy_reference.rx_group_ingress_2spc",
                "legacy_reference.tx_iq_axis_boundary_2spc",
            },
        )

    def test_frozen_reflection_chain_has_one_nonlegacy_owner_per_item(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        registry = ArchitectureRegistry.from_config(config)
        self.assertEqual(
            registry.reflection_chain_owner_map,
            tuple(
                (responsibility, registry.production_owner_map[responsibility])
                for responsibility in config.required_responsibilities.continuous_dual_polar_reflection
            ),
        )
        for responsibility, block_name in registry.reflection_chain_owner_map:
            self.assertIn(responsibility, config.required_responsibilities.production)
            self.assertNotEqual(
                config.block_by_name(block_name).implementation_kind,
                ImplementationKind.LEGACY_NON_PRODUCTION,
            )

    def test_unknown_and_duplicate_production_responsibilities_fail(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        unknown_fault_management = dataclasses.replace(
            config,
            required_responsibilities=dataclasses.replace(
                config.required_responsibilities,
                production=tuple(
                    responsibility
                    for responsibility in config.required_responsibilities.production
                    if responsibility != "fault_management"
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "unknown production responsibility"):
            ArchitectureRegistry.from_config(unknown_fault_management)

        duplicate_block = dataclasses.replace(
            config.architecture_blocks[0],
            block_name="duplicate_adc",
            responsibilities=("adc",),
        )
        with self.assertRaisesRegex(ValueError, "multiple production owners"):
            ArchitectureRegistry.from_config(
                dataclasses.replace(
                    config,
                    architecture_blocks=(*config.architecture_blocks, duplicate_block),
                )
            )

    def test_missing_and_reordered_chain_fail_in_registry_and_legacy_prefix_fails_at_type_boundary(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        chain = config.required_responsibilities.continuous_dual_polar_reflection
        missing = dataclasses.replace(
            config,
            required_responsibilities=dataclasses.replace(
                config.required_responsibilities,
                continuous_dual_polar_reflection=chain[:-1],
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "continuous_dual_polar_reflection.*exact"
        ):
            ArchitectureRegistry.from_config(missing)

        reordered = dataclasses.replace(
            config,
            required_responsibilities=dataclasses.replace(
                config.required_responsibilities,
                continuous_dual_polar_reflection=(chain[1], chain[0], *chain[2:]),
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "continuous_dual_polar_reflection.*exact"
        ):
            ArchitectureRegistry.from_config(reordered)

        with self.assertRaisesRegex(ValueError, "legacy_reference"):
            dataclasses.replace(
                config.required_responsibilities,
                continuous_dual_polar_reflection=(
                    "legacy_reference.rx_group_ingress_2spc",
                    *chain[1:],
                ),
            )

    def test_default_is_complete_but_not_production_ready(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        registry = ArchitectureRegistry.from_config(config)
        readiness = registry.evaluate_readiness(
            catalog_resolution_complete=True,
            production_lock_valid=True,
            production_sources_contain_reference=False,
        )
        self.assertTrue(readiness.responsibility_complete)
        self.assertTrue(readiness.catalog_resolution_complete)
        self.assertFalse(readiness.production_integration_ready)
        self.assertIn("architecture_pending", readiness.blocking_reasons)

    def test_each_external_readiness_gate_has_a_stable_blocking_reason(self) -> None:
        registry = ArchitectureRegistry.default()
        cases = (
            (
                {
                    "catalog_resolution_complete": False,
                    "production_lock_valid": True,
                    "production_sources_contain_reference": False,
                },
                "catalog_resolution_incomplete",
            ),
            (
                {
                    "catalog_resolution_complete": True,
                    "production_lock_valid": False,
                    "production_sources_contain_reference": False,
                },
                "production_lock_invalid",
            ),
            (
                {
                    "catalog_resolution_complete": True,
                    "production_lock_valid": True,
                    "production_sources_contain_reference": True,
                },
                "reference_rtl_in_production_sources",
            ),
        )
        for arguments, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason):
                result = registry.evaluate_readiness(**arguments)
                self.assertFalse(result.production_integration_ready)
                self.assertIn(expected_reason, result.blocking_reasons)

    def test_default_instance_and_block_maturity_reasons_are_explicit(self) -> None:
        result = ArchitectureRegistry.default().evaluate_readiness(
            catalog_resolution_complete=True,
            production_lock_valid=True,
            production_sources_contain_reference=False,
        )
        self.assertIn("architecture_pending", result.blocking_reasons)
        self.assertIn("production_block_not_accepted", result.blocking_reasons)
        self.assertIn(
            "materialized_instance_parameters_not_vivado_verified",
            result.blocking_reasons,
        )
        self.assertIn(
            "materialized_instance_connections_not_vivado_verified",
            result.blocking_reasons,
        )
        self.assertIn("rfdc_integration_not_vivado_verified", result.blocking_reasons)


if __name__ == "__main__":
    unittest.main()
