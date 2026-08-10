"""Single ownership registry for the target hardware architecture."""

from __future__ import annotations

from dataclasses import dataclass

from .types import HardwareArchitectureConfig, ImplementationKind


_AMD_IP_RESPONSIBILITIES: dict[str, tuple[str, ...]] = {
    "axis_register_slice": ("axis_register_pipeline",),
    "axis_data_fifo": ("axis_buffering",),
    "axis_clock_converter": ("axis_clock_domain_crossing",),
    "axis_dwidth_converter": ("axis_width_conversion",),
    "axis_combiner": ("axis_combining",),
    "axis_broadcaster": ("axis_broadcasting",),
    "axis_switch": ("axis_switching",),
    "fir_compiler": ("monitor_fir_dec2", "fractional_delay_fir"),
    "dds_compiler": ("doppler_phasor",),
    "complex_multiplier": ("complex_multiplication",),
    "cordic": ("frequency_estimator_atan2",),
    "axi_dma": ("event_to_ddr_transport",),
}


@dataclass(frozen=True)
class ArchitectureBlock:
    """One block and the architecture responsibilities it owns."""

    logical_name: str
    kind: ImplementationKind
    responsibilities: tuple[str, ...]
    production: bool
    vlnv: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.logical_name.strip():
            raise ValueError("block logical_name must be nonempty")
        if not isinstance(self.kind, ImplementationKind):
            raise ValueError("block kind must be an ImplementationKind")
        if not self.responsibilities or any(
            not responsibility.strip() for responsibility in self.responsibilities
        ):
            raise ValueError(
                f"{self.logical_name} responsibilities must be nonempty"
            )
        if len(self.responsibilities) != len(set(self.responsibilities)):
            raise ValueError(
                f"{self.logical_name} responsibilities must be unique"
            )
        if self.production and self.kind is ImplementationKind.LEGACY_NON_PRODUCTION:
            raise ValueError("legacy_non_production block cannot be production")
        if self.vlnv is not None and not self.vlnv.strip():
            raise ValueError("vlnv must be nonempty when present")
        if self.source is not None and not self.source.strip():
            raise ValueError("source must be nonempty when present")


@dataclass(frozen=True)
class ArchitectureRegistry:
    """Validated, immutable assignment of every architecture responsibility."""

    blocks: tuple[ArchitectureBlock, ...]

    def __post_init__(self) -> None:
        names = [block.logical_name for block in self.blocks]
        if len(names) != len(set(names)):
            duplicate = next(name for name in names if names.count(name) > 1)
            raise ValueError(f"duplicate architecture logical name: {duplicate}")

        owners: dict[str, str] = {}
        for block in self.production_blocks():
            for responsibility in block.responsibilities:
                previous = owners.get(responsibility)
                if previous is not None:
                    raise ValueError(
                        f"{responsibility} has multiple production owners: "
                        f"{previous}, {block.logical_name}"
                    )
                owners[responsibility] = block.logical_name

    @classmethod
    def default(cls) -> "ArchitectureRegistry":
        architecture = HardwareArchitectureConfig.load_default()
        blocks = [
            ArchitectureBlock(
                logical_name=architecture.rfdc.ip.logical_name,
                kind=architecture.rfdc.ip.kind,
                responsibilities=architecture.rfdc.owned_functions,
                production=True,
                vlnv=architecture.rfdc.ip.vlnv,
            )
        ]
        for spec in architecture.required_ip_families:
            blocks.append(
                ArchitectureBlock(
                    logical_name=spec.logical_name,
                    kind=spec.kind,
                    responsibilities=_AMD_IP_RESPONSIBILITIES[spec.logical_name],
                    production=True,
                    vlnv=spec.vlnv,
                    source=spec.catalog_pattern,
                )
            )
        blocks.extend(_PROJECT_AND_LEGACY_BLOCKS)
        return cls(tuple(blocks))

    def by_name(self, logical_name: str) -> ArchitectureBlock:
        for block in self.blocks:
            if block.logical_name == logical_name:
                return block
        raise KeyError(logical_name)

    def production_blocks(self) -> tuple[ArchitectureBlock, ...]:
        return tuple(block for block in self.blocks if block.production)

    def legacy_blocks(self) -> tuple[ArchitectureBlock, ...]:
        return tuple(
            block
            for block in self.blocks
            if block.kind is ImplementationKind.LEGACY_NON_PRODUCTION
        )


_PROJECT_AND_LEGACY_BLOCKS = (
    ArchitectureBlock(
        logical_name="integer_delay_memory",
        kind=ImplementationKind.XPM_MACRO,
        responsibilities=("integer_delay_storage",),
        production=True,
        source="xpm_memory_sdpram",
    ),
    ArchitectureBlock(
        logical_name="rx_stream_control",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=("acquisition_epoch", "stream_integrity_status"),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="auto_hold_range_selector",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=("auto_hold_range_selection",),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="target_scheduler",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=("target_scheduling", "maximum_target_control"),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="circular_delay_controller",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=("circular_delay_addressing", "lane_scheduling"),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="fractional_delay_scheduler",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=("fractional_delay_coefficient_set_scheduling",),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="target_alignment_accumulator",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=(
            "multi_target_output_alignment",
            "multi_target_accumulation",
        ),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="pulse_detector",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=(
            "adaptive_noise",
            "adaptive_threshold",
            "nm_voting",
            "toa",
            "contiguous_main_peak_fwhm",
            "coarse_pdw",
        ),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="event_control",
        kind=ImplementationKind.CUSTOM_RTL,
        responsibilities=(
            "hit_iq_event_framing",
            "overflow_status",
            "bit_status",
            "fault_management",
        ),
        production=True,
    ),
    ArchitectureBlock(
        logical_name="rx_group_ingress_2spc",
        kind=ImplementationKind.LEGACY_NON_PRODUCTION,
        responsibilities=("legacy_rx_group_ingress_reference",),
        production=False,
        source="src/rfsoc_pulse_model/cycle/hardware/rx_group_ingress.py",
    ),
    ArchitectureBlock(
        logical_name="tx_iq_axis_boundary_2spc",
        kind=ImplementationKind.LEGACY_NON_PRODUCTION,
        responsibilities=("legacy_tx_iq_axis_boundary_reference",),
        production=False,
        source="src/rfsoc_pulse_model/cycle/hardware/tx_iq_axis_boundary.py",
    ),
)
