import dataclasses
import unittest

from rfsoc_pulse_model.ip.registry import ArchitectureRegistry
from rfsoc_pulse_model.ip.types import (
    ArchitectureStatus,
    ConnectionStatus,
    HardwareArchitectureConfig,
    ImplementationKind,
    IntegrationProofStatus,
    IpInstanceLifecycle,
    ParameterStatus,
)


class ArchitectureRegistryTest(unittest.TestCase):
    @staticmethod
    def mature_config() -> HardwareArchitectureConfig:
        config = HardwareArchitectureConfig.load_default()
        instances = tuple(
            dataclasses.replace(
                instance,
                lifecycle=IpInstanceLifecycle.MATERIALIZED,
                parameter_status=ParameterStatus.VIVADO_VERIFIED,
                connection_status=ConnectionStatus.VIVADO_VERIFIED,
            )
            for instance in config.ip_instances
        )
        blocks = tuple(
            dataclasses.replace(
                block,
                implementation_kind=(
                    ImplementationKind.CUSTOM_RTL
                    if block.implementation_kind
                    is ImplementationKind.ARCHITECTURE_PENDING
                    else block.implementation_kind
                ),
                architecture_status=ArchitectureStatus.FROZEN,
                production_accepted=(
                    block.implementation_kind
                    is not ImplementationKind.LEGACY_NON_PRODUCTION
                ),
                source=(
                    f"rtl/{block.block_name}.v"
                    if block.implementation_kind
                    is ImplementationKind.ARCHITECTURE_PENDING
                    else block.source
                ),
            )
            for block in config.architecture_blocks
        )
        return dataclasses.replace(
            config,
            ip_instances=instances,
            architecture_blocks=blocks,
            rfdc_integration=dataclasses.replace(
                config.rfdc_integration,
                proof_status=IntegrationProofStatus.VIVADO_VERIFIED,
            ),
        )

    @staticmethod
    def replace_block(
        config: HardwareArchitectureConfig,
        block_name: str,
        **changes: object,
    ) -> HardwareArchitectureConfig:
        return dataclasses.replace(
            config,
            architecture_blocks=tuple(
                dataclasses.replace(block, **changes)
                if block.block_name == block_name
                else block
                for block in config.architecture_blocks
            ),
        )

    @staticmethod
    def replace_instance(
        config: HardwareArchitectureConfig,
        instance_name: str,
        **changes: object,
    ) -> HardwareArchitectureConfig:
        return dataclasses.replace(
            config,
            ip_instances=tuple(
                dataclasses.replace(instance, **changes)
                if instance.instance_name == instance_name
                else instance
                for instance in config.ip_instances
            ),
        )

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

    def test_connected_shell_keeps_rfdc_and_all_pending_production_owners_unaccepted(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        registry = ArchitectureRegistry.from_config(config)
        self.assertFalse(config.block_by_name("rfdc_frontend").production_accepted)
        self.assertTrue(
            all(
                not block.production_accepted
                for block in registry.production_blocks()
                if block.implementation_kind is ImplementationKind.ARCHITECTURE_PENDING
            )
        )
        readiness = registry.evaluate_readiness(
            catalog_resolution_complete=True,
            production_lock_valid=True,
            production_sources_contain_reference=False,
        )
        self.assertFalse(readiness.production_integration_ready)

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

    def test_owner_maps_are_immutable_validated_snapshots(self) -> None:
        registry = ArchitectureRegistry.from_config(self.mature_config())
        self.assertTrue(
            registry.evaluate_readiness(
                catalog_resolution_complete=True,
                production_lock_valid=True,
                production_sources_contain_reference=False,
            ).production_integration_ready
        )

        with self.assertRaises(TypeError):
            registry.production_owner_map["adc"] = "wrong_owner"
        with self.assertRaises(TypeError):
            registry.reference_responsibility_map[
                "legacy_reference.rx_group_ingress_2spc"
            ] = "wrong_owner"
        with self.assertRaises(ValueError):
            dataclasses.replace(registry, production_owner_map={})

        readiness = registry.evaluate_readiness(
            catalog_resolution_complete=True,
            production_lock_valid=True,
            production_sources_contain_reference=False,
        )
        self.assertTrue(readiness.responsibility_complete)
        self.assertTrue(readiness.production_integration_ready)

    def test_missing_required_owner_is_rejected_before_readiness(self) -> None:
        config = self.mature_config()
        incomplete = dataclasses.replace(
            config,
            architecture_blocks=tuple(
                block
                for block in config.architecture_blocks
                if block.block_name != "system_status"
            ),
        )
        with self.assertRaisesRegex(ValueError, "missing production responsibility"):
            ArchitectureRegistry.from_config(incomplete)

    def test_each_readiness_gate_blocks_an_otherwise_mature_architecture(self) -> None:
        mature = self.mature_config()
        external = {
            "catalog_resolution_complete": True,
            "production_lock_valid": True,
            "production_sources_contain_reference": False,
        }
        cases = (
            (
                "architecture pending",
                self.replace_block(
                    mature,
                    "fractional_delay_bank",
                    implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
                    architecture_status=ArchitectureStatus.ARCHITECTURE_PENDING,
                    production_accepted=False,
                    source=None,
                ),
                external,
                "architecture_pending",
            ),
            (
                "production acceptance",
                self.replace_block(
                    mature,
                    "fractional_delay_bank",
                    production_accepted=False,
                ),
                external,
                "production_block_not_accepted",
            ),
            (
                "AMD instance missing",
                self.replace_block(mature, "rfdc_frontend", instance_refs=()),
                external,
                "amd_ip_owner_missing_instance",
            ),
            (
                "AMD instance not materialized",
                self.replace_instance(
                    mature,
                    "rfdc_0",
                    lifecycle=IpInstanceLifecycle.PLANNED,
                ),
                external,
                "amd_ip_owner_instance_not_materialized",
            ),
            (
                "AMD parameters unverified",
                self.replace_instance(
                    mature,
                    "rfdc_0",
                    parameter_status=ParameterStatus.DRAFTED,
                ),
                external,
                "materialized_instance_parameters_not_vivado_verified",
            ),
            (
                "AMD connections unverified",
                self.replace_instance(
                    mature,
                    "rfdc_0",
                    connection_status=ConnectionStatus.PARTIAL,
                ),
                external,
                "materialized_instance_connections_not_vivado_verified",
            ),
            (
                "custom source missing",
                self.replace_block(mature, "fractional_delay_bank", source=None),
                external,
                "accepted_custom_or_xpm_owner_missing_production_source",
            ),
            (
                "RFDC proof unverified",
                dataclasses.replace(
                    mature,
                    rfdc_integration=dataclasses.replace(
                        mature.rfdc_integration,
                        proof_status=IntegrationProofStatus.UNVERIFIED,
                    ),
                ),
                external,
                "rfdc_integration_not_vivado_verified",
            ),
            (
                "catalog incomplete",
                mature,
                {**external, "catalog_resolution_complete": False},
                "catalog_resolution_incomplete",
            ),
            (
                "production lock invalid",
                mature,
                {**external, "production_lock_valid": False},
                "production_lock_invalid",
            ),
            (
                "reference RTL included",
                mature,
                {**external, "production_sources_contain_reference": True},
                "reference_rtl_in_production_sources",
            ),
        )
        for label, config, arguments, expected_reason in cases:
            with self.subTest(label=label):
                result = ArchitectureRegistry.from_config(config).evaluate_readiness(
                    **arguments
                )
                self.assertTrue(result.responsibility_complete)
                self.assertFalse(result.production_integration_ready)
                self.assertIn(expected_reason, result.blocking_reasons)


if __name__ == "__main__":
    unittest.main()
