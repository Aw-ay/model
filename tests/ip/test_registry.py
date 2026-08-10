import unittest

from rfsoc_pulse_model.cycle.registry import HARDWARE_MODULES
from rfsoc_pulse_model.ip.registry import (
    ArchitectureBlock,
    ArchitectureRegistry,
)
from rfsoc_pulse_model.ip.types import ImplementationKind


class ArchitectureRegistryTest(unittest.TestCase):
    def test_rfdc_functions_have_one_amd_ip_owner(self) -> None:
        registry = ArchitectureRegistry.default()
        rfdc = registry.by_name("rfdc")

        self.assertEqual(rfdc.kind, ImplementationKind.AMD_IP)
        self.assertEqual(rfdc.vlnv, "xilinx.com:ip:usp_rf_data_converter:2.6")

    def test_current_generated_adapters_are_explicitly_legacy(self) -> None:
        registry = ArchitectureRegistry.default()

        self.assertEqual(
            {block.logical_name for block in registry.legacy_blocks()},
            {"rx_group_ingress_2spc", "tx_iq_axis_boundary_2spc"},
        )
        self.assertEqual(
            {registration.implementation_kind for registration in HARDWARE_MODULES},
            {ImplementationKind.LEGACY_NON_PRODUCTION},
        )
        self.assertFalse(any(registration.production for registration in HARDWARE_MODULES))

    def test_duplicate_production_function_owner_is_rejected(self) -> None:
        duplicate = ArchitectureBlock(
            logical_name="custom_nco",
            kind=ImplementationKind.CUSTOM_RTL,
            responsibilities=("nco",),
            production=True,
        )

        with self.assertRaisesRegex(ValueError, "nco.*multiple production owners"):
            ArchitectureRegistry(
                (*ArchitectureRegistry.default().blocks, duplicate)
            )


if __name__ == "__main__":
    unittest.main()
