import json
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.generate import generate


class GenerateTest(unittest.TestCase):
    def test_registered_cycle_hardware_generates_rtl_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = generate(root)

            rtl = (root / "rtl/rx_group_ingress_2spc.v").read_text(encoding="utf-8")
            on_disk = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, manifest)
            self.assertEqual(len(manifest["modules"]), 1)
            self.assertEqual(manifest["modules"][0]["latency_cycles"], 1)
            self.assertEqual(manifest["modules"][0]["samples_per_cycle"], 2)
            self.assertFalse(manifest["modules"][0]["accepts_backpressure"])
            self.assertEqual(
                manifest["rfdc_adc_clocking_mode"],
                "common_pl_clock_mts",
            )
            self.assertEqual(
                manifest["rfdc_adc_clocking_proof_status"],
                "unverified",
            )
            self.assertFalse(manifest["single_clock_ingress_integration_ready"])
            self.assertIn("always @(*)", rtl)
            self.assertIn("always @(posedge clk_i)", rtl)

    def test_unregistered_rtl_is_rejected_instead_of_silently_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rtl").mkdir(parents=True)
            (root / "rtl/hand_edited.v").write_text("module hand_edited; endmodule\n")

            with self.assertRaisesRegex(RuntimeError, "unregistered generated RTL"):
                generate(root)
