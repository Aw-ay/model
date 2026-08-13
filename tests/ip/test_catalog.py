import unittest

from rfsoc_pulse_model.ip.catalog import validate_resolved_catalog
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig, RFDC_2_6_VLNV


class ResolvedIpCatalogTest(unittest.TestCase):
    def test_connected_platform_identities_are_exact(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        resolved = {
            family.family_id: (
                family.vlnv
                if family.vlnv is not None
                else family.catalog_pattern[:-1] + "1.0"
            )
            for family in config.required_families()
        }
        self.assertEqual(
            {key: resolved[key] for key in (
                "zynq_ultra_ps_e",
                "smartconnect",
                "proc_sys_reset",
                "util_vector_logic",
                "xlconcat",
            )},
            {
                "zynq_ultra_ps_e": "xilinx.com:ip:zynq_ultra_ps_e:3.5",
                "smartconnect": "xilinx.com:ip:smartconnect:1.0",
                "proc_sys_reset": "xilinx.com:ip:proc_sys_reset:5.0",
                "util_vector_logic": "xilinx.com:ip:util_vector_logic:2.0",
                "xlconcat": "xilinx.com:ip:xlconcat:2.1",
            },
        )
        validate_resolved_catalog(config, resolved)

    def test_catalog_requires_exact_complete_required_family_set(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        resolved = {
            family.family_id: (
                family.vlnv
                if family.vlnv is not None
                else family.catalog_pattern[:-1] + "1.0"
            )
            for family in config.required_families()
        }

        validate_resolved_catalog(config, resolved)

    def test_catalog_rejects_missing_and_extra_families(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        resolved = {
            family.family_id: (
                family.vlnv
                if family.vlnv is not None
                else family.catalog_pattern[:-1] + "1.0"
            )
            for family in config.required_families()
        }
        missing = dict(resolved)
        missing.pop("axi_dma")
        with self.assertRaisesRegex(ValueError, "family set"):
            validate_resolved_catalog(config, missing)

        extra = dict(resolved)
        extra["not_required"] = "xilinx.com:ip:xlconstant:1.1"
        with self.assertRaisesRegex(ValueError, "family set"):
            validate_resolved_catalog(config, extra)

    def test_catalog_rejects_wrong_rfdc_and_family_identity(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        resolved = {
            family.family_id: (
                family.vlnv
                if family.vlnv is not None
                else family.catalog_pattern[:-1] + "1.0"
            )
            for family in config.required_families()
        }
        wrong_rfdc = dict(resolved)
        wrong_rfdc["rfdc"] = "xilinx.com:ip:usp_rf_data_converter:2.7"
        with self.assertRaisesRegex(ValueError, "RF Data Converter 2.6"):
            validate_resolved_catalog(config, wrong_rfdc)

        wrong_identity = dict(resolved)
        wrong_identity["fir_compiler"] = "xilinx.com:ip:dds_compiler:6.0"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_resolved_catalog(config, wrong_identity)


if __name__ == "__main__":
    unittest.main()
