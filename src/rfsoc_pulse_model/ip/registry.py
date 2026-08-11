"""Validated production ownership and readiness for the IP architecture."""

from __future__ import annotations

from dataclasses import dataclass

from .types import (
    ArchitectureBlockSpec,
    ConnectionStatus,
    HardwareArchitectureConfig,
    ImplementationKind,
    IntegrationProofStatus,
    IpInstanceLifecycle,
    ParameterStatus,
)


_LEGACY_REFERENCE_PREFIX = "legacy_reference."
_CONTINUOUS_DUAL_POLAR_REFLECTION = (
    "rx_2spc_continuous_ingress",
    "adc_channel_alignment_and_calibration",
    "dual_polar_three_range_selection",
    "continuous_sample_time_and_stream_integrity",
    "integer_delay_processing",
    "fractional_delay_processing",
    "range_rcs_complex_gain_application",
    "polarimetric_scattering_matrix_2x2",
    "doppler_phase_generation",
    "doppler_complex_modulation",
    "multi_target_output_alignment",
    "multi_target_accumulation",
    "tx_polarization_predistortion",
    "eight_channel_dac_routing",
    "tx_iq16_quantization",
    "tx_2spc_continuous_egress",
)


@dataclass(frozen=True)
class ArchitectureReadiness:
    """Independent, machine-derived architecture completion state."""

    responsibility_complete: bool
    catalog_resolution_complete: bool
    production_lock_valid: bool
    production_integration_ready: bool
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureRegistry:
    """Exact responsibility ownership derived from schema-v2 configuration."""

    config: HardwareArchitectureConfig
    blocks: tuple[ArchitectureBlockSpec, ...]
    production_owner_map: dict[str, str]
    reference_responsibility_map: dict[str, str]
    reflection_chain_owner_map: tuple[tuple[str, str], ...]
    responsibility_complete: bool

    @classmethod
    def from_config(cls, config: HardwareArchitectureConfig) -> "ArchitectureRegistry":
        """Validate and derive ownership from one immutable architecture config."""

        names = [block.block_name for block in config.architecture_blocks]
        if len(names) != len(set(names)):
            duplicate = next(name for name in names if names.count(name) > 1)
            raise ValueError(f"duplicate architecture block name: {duplicate}")

        required = set(config.required_responsibilities.production)
        production_owner_map: dict[str, str] = {}
        reference_responsibility_map: dict[str, str] = {}

        for block in config.architecture_blocks:
            if block.implementation_kind is ImplementationKind.LEGACY_NON_PRODUCTION:
                for responsibility in block.reference_responsibilities:
                    if not responsibility.startswith(_LEGACY_REFERENCE_PREFIX):
                        raise ValueError(
                            "legacy reference responsibility must use "
                            "legacy_reference. prefix"
                        )
                    previous = reference_responsibility_map.get(responsibility)
                    if previous is not None:
                        raise ValueError(
                            f"{responsibility} has multiple reference owners: "
                            f"{previous}, {block.block_name}"
                        )
                    reference_responsibility_map[responsibility] = block.block_name
                continue

            for responsibility in block.responsibilities:
                if responsibility.startswith(_LEGACY_REFERENCE_PREFIX):
                    raise ValueError(
                        "production responsibility cannot use legacy_reference. prefix"
                    )
                if responsibility not in required:
                    raise ValueError(
                        f"unknown production responsibility: {responsibility}"
                    )
                previous = production_owner_map.get(responsibility)
                if previous is not None:
                    raise ValueError(
                        f"{responsibility} has multiple production owners: "
                        f"{previous}, {block.block_name}"
                    )
                production_owner_map[responsibility] = block.block_name

        missing = required - set(production_owner_map)
        if missing:
            raise ValueError(
                "missing production responsibility owners: "
                f"{', '.join(sorted(missing))}"
            )

        chain = config.required_responsibilities.continuous_dual_polar_reflection
        if chain != _CONTINUOUS_DUAL_POLAR_REFLECTION:
            raise ValueError(
                "continuous_dual_polar_reflection must exactly match the frozen "
                "continuous dual-polar reflection chain"
            )
        if any(responsibility not in required for responsibility in chain):
            raise ValueError(
                "continuous_dual_polar_reflection must exactly use production "
                "responsibilities"
            )

        reflection_chain_owner_map = tuple(
            (responsibility, production_owner_map[responsibility])
            for responsibility in chain
        )
        return cls(
            config=config,
            blocks=config.architecture_blocks,
            production_owner_map=production_owner_map,
            reference_responsibility_map=reference_responsibility_map,
            reflection_chain_owner_map=reflection_chain_owner_map,
            responsibility_complete=True,
        )

    @classmethod
    def default(cls) -> "ArchitectureRegistry":
        """Build the registry from the packaged architecture authority."""

        return cls.from_config(HardwareArchitectureConfig.load_default())

    def by_name(self, block_name: str) -> ArchitectureBlockSpec:
        """Return a configured architecture block by stable block name."""

        return self.config.block_by_name(block_name)

    def production_blocks(self) -> tuple[ArchitectureBlockSpec, ...]:
        """Return all non-legacy blocks in the production namespace."""

        return tuple(
            block
            for block in self.blocks
            if block.implementation_kind is not ImplementationKind.LEGACY_NON_PRODUCTION
        )

    def legacy_blocks(self) -> tuple[ArchitectureBlockSpec, ...]:
        """Return blocks that own legacy reference responsibilities only."""

        return tuple(
            block
            for block in self.blocks
            if block.implementation_kind is ImplementationKind.LEGACY_NON_PRODUCTION
        )

    def evaluate_readiness(
        self,
        *,
        catalog_resolution_complete: bool,
        production_lock_valid: bool,
        production_sources_contain_reference: bool,
    ) -> ArchitectureReadiness:
        """Evaluate the exact production-integration conjunction."""

        reasons: list[str] = []
        if not self.responsibility_complete:
            reasons.append("responsibility_incomplete")
        if not catalog_resolution_complete:
            reasons.append("catalog_resolution_incomplete")
        if not production_lock_valid:
            reasons.append("production_lock_invalid")

        required_blocks = tuple(
            self.config.block_by_name(block_name)
            for block_name in dict.fromkeys(self.production_owner_map.values())
        )
        if any(not block.production_accepted for block in required_blocks):
            reasons.append("production_block_not_accepted")
        if any(
            block.implementation_kind is ImplementationKind.ARCHITECTURE_PENDING
            for block in required_blocks
        ):
            reasons.append("architecture_pending")

        amd_blocks = tuple(
            block
            for block in required_blocks
            if block.implementation_kind is ImplementationKind.AMD_IP
        )
        if any(not block.instance_refs for block in amd_blocks):
            reasons.append("amd_ip_owner_missing_instance")

        amd_instances = tuple(
            self.config.instance_by_name(instance_name)
            for block in amd_blocks
            for instance_name in block.instance_refs
        )
        if any(
            instance.lifecycle is not IpInstanceLifecycle.MATERIALIZED
            for instance in amd_instances
        ):
            reasons.append("amd_ip_owner_instance_not_materialized")
        if any(
            instance.parameter_status is not ParameterStatus.VIVADO_VERIFIED
            for instance in amd_instances
        ):
            reasons.append("materialized_instance_parameters_not_vivado_verified")
        if any(
            instance.connection_status is not ConnectionStatus.VIVADO_VERIFIED
            for instance in amd_instances
        ):
            reasons.append("materialized_instance_connections_not_vivado_verified")

        accepted_custom_or_xpm_blocks = tuple(
            block
            for block in required_blocks
            if block.production_accepted
            and block.implementation_kind
            in (ImplementationKind.CUSTOM_RTL, ImplementationKind.XPM_MACRO)
        )
        if any(block.source is None for block in accepted_custom_or_xpm_blocks):
            reasons.append("accepted_custom_or_xpm_owner_missing_production_source")
        if (
            self.config.rfdc_integration.proof_status
            is not IntegrationProofStatus.VIVADO_VERIFIED
        ):
            reasons.append("rfdc_integration_not_vivado_verified")
        if production_sources_contain_reference:
            reasons.append("reference_rtl_in_production_sources")

        return ArchitectureReadiness(
            responsibility_complete=self.responsibility_complete,
            catalog_resolution_complete=catalog_resolution_complete,
            production_lock_valid=production_lock_valid,
            production_integration_ready=not reasons,
            blocking_reasons=tuple(reasons),
        )
