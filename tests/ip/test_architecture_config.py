import dataclasses
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.types import (
    ArchitectureBlockSpec,
    ArchitectureStatus,
    HardwareArchitectureConfig,
    ImplementationKind,
    IpInstanceLifecycle,
)


EXPECTED_FAMILIES = {
    "rfdc",
    "axis_register_slice",
    "axis_data_fifo",
    "axis_clock_converter",
    "axis_dwidth_converter",
    "axis_combiner",
    "axis_broadcaster",
    "axis_switch",
    "fir_compiler",
    "dds_compiler",
    "complex_multiplier",
    "cordic",
    "axi_dma",
    "zynq_ultra_ps_e",
    "smartconnect",
    "proc_sys_reset",
    "util_vector_logic",
    "xlconcat",
}

EXPECTED_CONNECTED_PLATFORM_INSTANCES = {
    "zynq_ultra_ps_e_0",
    "ctrl_smartconnect_0",
    "reset_inverter_0",
    "ctrl_reset_0",
    "rx_reset_0",
    "tx_reset_0",
    "irq_concat_0",
}


class HardwareArchitectureConfigTest(unittest.TestCase):
    @staticmethod
    def root_payload() -> dict:
        root = Path(__file__).resolve().parents[2]
        return json.loads(
            (root / "config/ip_architecture.json").read_text(encoding="utf-8")
        )

    def test_default_uses_schema_v2_and_separates_family_instance_block(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        self.assertEqual(config.architecture_schema_version, 2)
        self.assertEqual(config.architecture_config_version, 3)
        self.assertEqual(config.topology_status, "connected_rfdc_shell")
        self.assertEqual(config.device_part, ModelConfig.load_default().device_part)
        self.assertEqual(config.device_part, "xczu27dr-fsve1156-2-i")
        self.assertEqual(
            {family.family_id for family in config.ip_families}, EXPECTED_FAMILIES
        )
        self.assertEqual(
            {instance.instance_name for instance in config.ip_instances},
            {
                "rfdc_0",
                "monitor_fir_dec2_0",
                *EXPECTED_CONNECTED_PLATFORM_INSTANCES,
            },
        )
        self.assertEqual(config.rfdc_integration.instance_ref, "rfdc_0")
        self.assertEqual(config.instance_by_name("rfdc_0").family_ref, "rfdc")

    def test_connected_platform_families_and_instances_are_exact_and_unaccepted(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        expected_vlnvs = {
            "zynq_ultra_ps_e": "xilinx.com:ip:zynq_ultra_ps_e:3.5",
            "smartconnect": "xilinx.com:ip:smartconnect:1.0",
            "proc_sys_reset": "xilinx.com:ip:proc_sys_reset:5.0",
            "util_vector_logic": "xilinx.com:ip:util_vector_logic:2.0",
            "xlconcat": "xilinx.com:ip:xlconcat:2.1",
        }
        self.assertEqual(
            {
                family_id: config.family_by_id(family_id).vlnv
                for family_id in expected_vlnvs
            },
            expected_vlnvs,
        )
        self.assertTrue(
            all(config.family_by_id(family_id).required for family_id in expected_vlnvs)
        )
        self.assertEqual(
            {
                instance.instance_name
                for instance in config.ip_instances
                if instance.instance_name in EXPECTED_CONNECTED_PLATFORM_INSTANCES
            },
            EXPECTED_CONNECTED_PLATFORM_INSTANCES,
        )
        self.assertFalse(config.block_by_name("rfdc_frontend").production_accepted)

    def test_connected_shell_has_exact_eight_materialized_cell_contracts(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        expected = {
            "rfdc_0": ("rfdc", "rfdc_frontend"),
            "zynq_ultra_ps_e_0": ("zynq_ultra_ps_e", "ps_platform_control"),
            "ctrl_smartconnect_0": ("smartconnect", "control_axi_interconnect"),
            "reset_inverter_0": ("util_vector_logic", "control_reset_inverter"),
            "ctrl_reset_0": ("proc_sys_reset", "control_reset_domain"),
            "rx_reset_0": ("proc_sys_reset", "rx_reset_domain"),
            "tx_reset_0": ("proc_sys_reset", "tx_reset_domain"),
            "irq_concat_0": ("xlconcat", "rfdc_irq_concat"),
        }
        self.assertEqual(
            {
                instance.instance_name: (instance.family_ref, instance.logical_role)
                for instance in config.ip_instances
                if instance.family_ref
                in {
                    "rfdc",
                    "zynq_ultra_ps_e",
                    "smartconnect",
                    "proc_sys_reset",
                    "util_vector_logic",
                    "xlconcat",
                }
                and instance.lifecycle is IpInstanceLifecycle.MATERIALIZED
            },
            expected,
        )

    def test_connected_shell_rejects_materialized_cell_name_family_role_and_lifecycle_drift(self) -> None:
        config = HardwareArchitectureConfig.load_default()

        def replace_instance(instance_name: str, **changes: object) -> HardwareArchitectureConfig:
            return dataclasses.replace(
                config,
                ip_instances=tuple(
                    dataclasses.replace(instance, **changes)
                    if instance.instance_name == instance_name
                    else instance
                    for instance in config.ip_instances
                ),
            )

        with self.assertRaisesRegex(ValueError, "materialized instance set"):
            dataclasses.replace(
                config,
                ip_instances=tuple(
                    instance
                    for instance in config.ip_instances
                    if instance.instance_name != "rfdc_0"
                ),
            )
        with self.assertRaisesRegex(ValueError, "materialized instance set"):
            dataclasses.replace(
                config,
                ip_instances=(
                    *config.ip_instances,
                    dataclasses.replace(
                        config.instance_by_name("rfdc_0"),
                        instance_name="extra_rfdc_0",
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "materialized instance"):
            replace_instance("rfdc_0", lifecycle=IpInstanceLifecycle.PLANNED)
        with self.assertRaisesRegex(ValueError, "materialized instance contract"):
            replace_instance("zynq_ultra_ps_e_0", logical_role="not_the_ps")
        with self.assertRaisesRegex(ValueError, "materialized instance contract"):
            replace_instance("ctrl_reset_0", family_ref="rfdc")

    def test_connected_shell_rejects_amd_owner_reference_family_bypass(self) -> None:
        config = HardwareArchitectureConfig.load_default()

        def replace_block(block_name: str, **changes: object) -> HardwareArchitectureConfig:
            return dataclasses.replace(
                config,
                architecture_blocks=tuple(
                    dataclasses.replace(block, **changes)
                    if block.block_name == block_name
                    else block
                    for block in config.architecture_blocks
                ),
            )

        with self.assertRaisesRegex(ValueError, "rfdc_frontend.*AMD owner"):
            replace_block("rfdc_frontend", instance_refs=("ctrl_reset_0",))
        with self.assertRaisesRegex(ValueError, "rfdc_frontend.*AMD owner"):
            replace_block("rfdc_frontend", instance_refs=())
        with self.assertRaisesRegex(ValueError, "monitor_branch.*AMD owner"):
            replace_block("monitor_branch", instance_refs=("rfdc_0",))

    def test_connected_authority_rejects_missing_or_extra_required_platform_families(self) -> None:
        missing = self.root_payload()
        missing["ip_families"] = [
            family
            for family in missing["ip_families"]
            if family["family_id"] != "xlconcat"
        ]
        with self.assertRaisesRegex(ValueError, "required family set"):
            HardwareArchitectureConfig.from_mapping(missing)

        extra = self.root_payload()
        extra["ip_families"].append(
            {
                "family_id": "undeclared_platform_ip",
                "implementation_kind": "amd_ip",
                "catalog_pattern": "xilinx.com:ip:xlconstant:1.1",
                "required": True,
                "vlnv": "xilinx.com:ip:xlconstant:1.1",
            }
        )
        with self.assertRaisesRegex(ValueError, "required family set"):
            HardwareArchitectureConfig.from_mapping(extra)

    def test_default_locks_exact_rfdc_2_6_black_box(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        rfdc = config.family_by_id("rfdc")
        self.assertEqual(rfdc.vlnv, "xilinx.com:ip:usp_rf_data_converter:2.6")
        self.assertEqual(rfdc.implementation_kind, ImplementationKind.AMD_IP)
        self.assertEqual(config.vivado_version, "2025.2")
        self.assertEqual(config.generation_mode, "vivado_ip_first")
        self.assertEqual(config.rfdc_integration.instance_ref, "rfdc_0")

    def test_other_rfdc_version_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["ip_families"][0]["vlnv"] = "xilinx.com:ip:usp_rf_data_converter:2.7"
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            HardwareArchitectureConfig.from_mapping(payload)

    def test_installed_and_root_config_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "config/ip_architecture.json").read_bytes(),
            (root / "src/rfsoc_pulse_model/config/ip_architecture.json").read_bytes(),
        )

    def test_promoted_default_lock_copies_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "config/ip_lock.json").read_bytes(),
            (root / "src/rfsoc_pulse_model/config/ip_lock.json").read_bytes(),
        )

    def test_architecture_device_part_rejects_blank_or_model_config_mismatch(self) -> None:
        blank = self.root_payload()
        blank["device_part"] = " "
        with self.assertRaisesRegex(ValueError, "device_part.*nonempty"):
            HardwareArchitectureConfig.from_mapping(blank)

        mismatch = self.root_payload()
        mismatch["device_part"] = "xczu28dr-ffvg1517-2-e"
        with self.assertRaisesRegex(ValueError, "device_part.*ModelConfig"):
            HardwareArchitectureConfig.from_mapping(mismatch)

    def test_dataclass_replace_cannot_bypass_model_config_device_part_authority(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        with self.assertRaisesRegex(ValueError, "device_part.*ModelConfig"):
            dataclasses.replace(config, device_part="xczu28dr-ffvg1517-2-e")

    def test_device_part_is_a_config_byte_and_not_a_second_request_field(self) -> None:
        root = Path(__file__).resolve().parents[2]
        root_bytes = (root / "config/ip_architecture.json").read_bytes()
        self.assertIn(b'"device_part": "xczu27dr-fsve1156-2-i"', root_bytes)
        self.assertEqual(
            root_bytes,
            (root / "src/rfsoc_pulse_model/config/ip_architecture.json").read_bytes(),
        )

    def test_dataclass_replace_cannot_bypass_rfdc_gate(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        bad_rfdc = dataclasses.replace(
            config.family_by_id("rfdc"),
            vlnv="xilinx.com:ip:usp_rf_data_converter:2.5",
        )
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            dataclasses.replace(
                config,
                ip_families=(bad_rfdc, *config.ip_families[1:]),
            )

    def test_fractional_delay_is_pending_without_fake_instances(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        block = config.block_by_name("fractional_delay_bank")
        self.assertEqual(
            block.implementation_kind, ImplementationKind.ARCHITECTURE_PENDING
        )
        self.assertEqual(
            block.architecture_status, ArchitectureStatus.ARCHITECTURE_PENDING
        )
        self.assertFalse(block.production_accepted)
        self.assertEqual(block.instance_refs, ())
        self.assertFalse(
            any(
                instance.instance_name.startswith("fractional_delay_fir_")
                for instance in config.ip_instances
            )
        )

    def test_default_declares_the_frozen_continuous_reflection_chain(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        chain = config.required_responsibilities.continuous_dual_polar_reflection
        self.assertEqual(
            chain,
            (
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
            ),
        )
        self.assertTrue(set(chain) <= set(config.required_responsibilities.production))

    def test_2spc_production_boundaries_are_pending_not_legacy_aliases(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        for block_name, responsibility in (
            ("rx_2spc_continuous_ingress", "rx_2spc_continuous_ingress"),
            ("tx_2spc_continuous_egress", "tx_2spc_continuous_egress"),
        ):
            block = config.block_by_name(block_name)
            self.assertEqual(block.responsibilities, (responsibility,))
            self.assertEqual(
                block.implementation_kind,
                ImplementationKind.ARCHITECTURE_PENDING,
            )
            self.assertEqual(
                block.architecture_status, ArchitectureStatus.ARCHITECTURE_PENDING
            )
            self.assertFalse(block.production_accepted)
            self.assertEqual(block.instance_refs, ())
            self.assertIsNone(block.source)
            self.assertEqual(block.reference_responsibilities, ())
        self.assertEqual(
            config.block_by_name("rx_group_ingress_2spc").reference_responsibilities,
            ("legacy_reference.rx_group_ingress_2spc",),
        )
        self.assertEqual(
            config.block_by_name("tx_iq_axis_boundary_2spc").reference_responsibilities,
            ("legacy_reference.tx_iq_axis_boundary_2spc",),
        )

    def test_monitor_branch_is_the_only_monitor_and_pdw_owner(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        monitor_branch = config.block_by_name("monitor_branch")
        self.assertEqual(monitor_branch.instance_refs, ("monitor_fir_dec2_0",))
        self.assertEqual(
            set(monitor_branch.responsibilities),
            {
                "monitor_fir_dec2",
                "adaptive_noise",
                "adaptive_threshold",
                "nm_voting",
                "toa",
                "contiguous_main_peak_fwhm",
                "coarse_pdw",
                "hit_iq_event_framing",
            },
        )
        self.assertEqual(
            config.instance_by_name("monitor_fir_dec2_0").logical_role,
            "monitor_decimator",
        )
        self.assertEqual(
            config.instance_by_name("monitor_fir_dec2_0").lifecycle,
            IpInstanceLifecycle.PLANNED,
        )
        self.assertFalse(
            any(
                block.block_name == "monitor_decimator"
                for block in config.architecture_blocks
            )
        )

    def test_pending_kind_and_status_cannot_disagree(self) -> None:
        with self.assertRaisesRegex(ValueError, "architecture_pending.*equivalent"):
            ArchitectureBlockSpec(
                block_name="bad_pending",
                implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
                responsibilities=("fractional_delay_processing",),
                reference_responsibilities=(),
                instance_refs=(),
                architecture_status=ArchitectureStatus.FROZEN,
                production_accepted=False,
                source=None,
            )

    def test_dataclass_replace_rejects_mutable_responsibility_collections(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        with self.assertRaisesRegex(ValueError, "production must be a tuple"):
            dataclasses.replace(
                config.required_responsibilities,
                production=list(config.required_responsibilities.production),
            )
        with self.assertRaisesRegex(
            ValueError, "continuous_dual_polar_reflection must be a tuple"
        ):
            dataclasses.replace(
                config.required_responsibilities,
                continuous_dual_polar_reflection=list(
                    config.required_responsibilities.continuous_dual_polar_reflection
                ),
            )

    def test_dataclass_replace_rejects_mutable_architecture_collections(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        for field_name in ("ip_families", "ip_instances", "architecture_blocks"):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, f"{field_name} must be a tuple"):
                    dataclasses.replace(
                        config,
                        **{field_name: list(getattr(config, field_name))},
                    )

    def test_architecture_collections_reject_wrong_declared_element_types(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        for field_name in ("ip_families", "ip_instances", "architecture_blocks"):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(
                    ValueError, f"{field_name} entries have the wrong type"
                ):
                    dataclasses.replace(config, **{field_name: (object(),)})

    def test_rfdc_internal_settings_live_only_in_architecture_config(self) -> None:
        rfdc_integration = HardwareArchitectureConfig.load_default().rfdc_integration
        self.assertEqual(rfdc_integration.dac_analog_output_type, "real")
        self.assertEqual(rfdc_integration.dac_mixer_mode, "iq_to_real")
        self.assertEqual(rfdc_integration.dac_mixer_scale_mode, "unity_0db")
        self.assertEqual(rfdc_integration.dac_nco_frequency_hz, 2_800_000_000)


if __name__ == "__main__":
    unittest.main()
