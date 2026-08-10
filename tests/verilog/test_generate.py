import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.generate import generate


class GenerateTest(unittest.TestCase):
    def test_registered_cycle_hardware_generates_rtl_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = generate(root)

            rx_rtl = (root / "rtl/rx_group_ingress_2spc.v").read_text(
                encoding="utf-8"
            )
            tx_rtl = (root / "rtl/tx_iq_axis_boundary_2spc.v").read_text(
                encoding="utf-8"
            )
            on_disk = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            architecture_on_disk = json.loads(
                (root / "metadata/ip_architecture.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(on_disk, manifest)
            self.assertEqual(architecture_on_disk, manifest["ip_architecture"])
            architecture_bytes = (
                root / "metadata/ip_architecture.json"
            ).read_bytes()
            self.assertEqual(
                manifest["ip_architecture_sha256"],
                hashlib.sha256(architecture_bytes).hexdigest(),
            )
            modules = {
                module["module_name"]: module for module in manifest["modules"]
            }
            self.assertEqual(
                set(modules),
                {"rx_group_ingress_2spc", "tx_iq_axis_boundary_2spc"},
            )
            self.assertEqual(modules["rx_group_ingress_2spc"]["latency_cycles"], 1)
            self.assertEqual(modules["tx_iq_axis_boundary_2spc"]["latency_cycles"], 0)
            self.assertEqual(modules["tx_iq_axis_boundary_2spc"]["samples_per_cycle"], 2)
            self.assertFalse(
                modules["tx_iq_axis_boundary_2spc"]["accepts_backpressure"]
            )
            self.assertEqual(
                {module["implementation_kind"] for module in manifest["modules"]},
                {"legacy_non_production"},
            )
            self.assertTrue(
                all(not module["production"] for module in manifest["modules"])
            )
            self.assertEqual(
                manifest["rfdc_adc_clocking_mode"],
                "common_pl_clock_mts",
            )
            self.assertEqual(
                manifest["rfdc_adc_clocking_proof_status"],
                "unverified",
            )
            self.assertFalse(manifest["single_clock_ingress_integration_ready"])
            self.assertEqual(
                manifest["rfdc_dac_clocking_mode"],
                "common_pl_clock_mts_sysref",
            )
            self.assertEqual(
                manifest["rfdc_dac_clocking_proof_status"],
                "unverified",
            )
            self.assertFalse(manifest["single_clock_tx_integration_ready"])
            self.assertEqual(manifest["rfdc_dac_pl_data_type"], "iq_interleaved")
            rfdc = manifest["ip_architecture"]["rfdc"]
            self.assertEqual(rfdc["vlnv"], "xilinx.com:ip:usp_rf_data_converter:2.6")
            self.assertEqual(rfdc["dac_analog_output_type"], "real")
            self.assertEqual(rfdc["dac_mixer_mode"], "iq_to_real")
            self.assertEqual(rfdc["dac_mixer_scale_mode"], "unity_0db")
            self.assertEqual(rfdc["dac_nco_frequency_hz"], 2_800_000_000)
            for old_name in (
                "rfdc_dac_analog_output_type",
                "rfdc_dac_mixer_mode",
                "rfdc_dac_mixer_scale_mode",
                "rfdc_dac_nco_frequency_hz",
            ):
                self.assertNotIn(old_name, manifest)
            self.assertEqual(manifest["rfdc_dac_axis_width_bits"], 64)
            self.assertEqual(manifest["rfdc_dac_complex_samples_per_cycle"], 2)
            self.assertEqual(
                manifest["golden_dac_time_reference"],
                "latency_normalized",
            )
            self.assertEqual(
                manifest["fractional_delay_kernel_center_samples"],
                31,
            )
            self.assertEqual(
                manifest["fixed_internal_delay_source"],
                "calibration_profile_measurement",
            )
            self.assertNotIn("fixed_internal_delay_samples", manifest)
            for rtl in (rx_rtl, tx_rtl):
                self.assertIn("always @(*)", rtl)
                self.assertIn("always @(posedge clk_i)", rtl)

    def test_unregistered_rtl_is_rejected_instead_of_silently_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rtl").mkdir(parents=True)
            (root / "rtl/hand_edited.v").write_text("module hand_edited; endmodule\n")

            with self.assertRaisesRegex(RuntimeError, "unregistered generated RTL"):
                generate(root)
