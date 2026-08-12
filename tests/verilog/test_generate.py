import json
import hashlib
import importlib
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rfsoc_pulse_model.generate import generate
from rfsoc_pulse_model.cycle.hardware.rx_group_ingress import RxGroupIngress2Spc
from rfsoc_pulse_model.ip.types import ImplementationKind


class GenerateTest(unittest.TestCase):
    @staticmethod
    def _legacy_registration(filename: str) -> SimpleNamespace:
        return SimpleNamespace(
            cycle_class=RxGroupIngress2Spc,
            verilog_filename=filename,
            implementation_kind=ImplementationKind.LEGACY_NON_PRODUCTION,
            production=False,
        )

    def test_registered_verilog_filename_rejects_path_escape_before_elaboration(self) -> None:
        generator_module = importlib.import_module("rfsoc_pulse_model.generate")
        for filename in ("../../escaped.v", "nested/file.v", r"nested\\file.v", "", ".", ".."):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "build"
                marker = Path(temporary) / "outside-marker.txt"
                marker.write_bytes(b"do not modify")
                with patch.object(
                    generator_module,
                    "HARDWARE_MODULES",
                    (self._legacy_registration(filename),),
                ):
                    with self.assertRaisesRegex(ValueError, "unsafe registered Verilog filename"):
                        generate(root)

                self.assertEqual(marker.read_bytes(), b"do not modify")
                self.assertFalse((Path(temporary) / "escaped.v").exists())

    def test_output_root_and_generated_directories_reject_symlinks(self) -> None:
        for scope in ("output", "rtl", "reference_rtl"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temporary:
                temporary_root = Path(temporary)
                output_root = temporary_root / "build"
                external = temporary_root / "external"
                external.mkdir()
                marker = external / "do-not-write.txt"
                marker.write_bytes(b"external data")
                link_path = output_root if scope == "output" else output_root / scope
                if scope != "output":
                    output_root.mkdir()
                try:
                    os.symlink(external, link_path, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"directory symlink creation unavailable: {error}")

                with self.assertRaisesRegex(RuntimeError, "unsafe.*(symlink|reparse)"):
                    generate(output_root)

                self.assertEqual(marker.read_bytes(), b"external data")
                self.assertFalse((external / "rx_group_ingress_2spc.v").exists())

    @unittest.skipUnless(os.name == "nt", "real NTFS junction probe")
    def test_output_root_and_generated_directories_reject_junctions(self) -> None:
        for scope in ("output", "rtl", "reference_rtl"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temporary:
                temporary_root = Path(temporary)
                output_root = temporary_root / "build"
                external = temporary_root / "external"
                external.mkdir()
                marker = external / "do-not-write.txt"
                marker.write_bytes(b"external data")
                link_path = output_root if scope == "output" else output_root / scope
                if scope != "output":
                    output_root.mkdir()
                completed = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link_path), str(external)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

                with self.assertRaisesRegex(RuntimeError, "unsafe.*reparse"):
                    generate(output_root)

                self.assertEqual(marker.read_bytes(), b"external data")
                self.assertFalse((external / "rx_group_ingress_2spc.v").exists())

    def test_registered_target_symlink_is_rejected_without_touching_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference_rtl = root / "reference_rtl"
            reference_rtl.mkdir()
            external = root / "external.v"
            external.write_bytes(b"external data")
            target = reference_rtl / "rx_group_ingress_2spc.v"
            try:
                os.symlink(external, target)
            except OSError as error:
                self.skipTest(f"file symlink creation unavailable: {error}")

            with self.assertRaisesRegex(RuntimeError, "unsafe.*symlink"):
                generate(root)

            self.assertEqual(external.read_bytes(), b"external data")

    def test_legacy_migration_rejects_symlink_without_touching_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rtl_root = root / "rtl"
            rtl_root.mkdir()
            external = root / "external.v"
            external.write_bytes(b"external data")
            target = rtl_root / "rx_group_ingress_2spc.v"
            try:
                os.symlink(external, target)
            except OSError as error:
                self.skipTest(f"file symlink creation unavailable: {error}")

            with self.assertRaisesRegex(RuntimeError, "unsafe.*symlink"):
                generate(root)

            self.assertEqual(external.read_bytes(), b"external data")

    def test_stale_rtl_symlink_is_rejected_without_touching_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rtl_root = root / "rtl"
            rtl_root.mkdir()
            external = root / "external.v"
            external.write_bytes(b"external data")
            stale = rtl_root / "unregistered.v"
            try:
                os.symlink(external, stale)
            except OSError as error:
                self.skipTest(f"file symlink creation unavailable: {error}")

            with self.assertRaisesRegex(RuntimeError, "unsafe generated RTL entry"):
                generate(root)

            self.assertEqual(external.read_bytes(), b"external data")

    def test_nonproduction_cycle_rtl_is_emitted_only_as_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = generate(root)

            self.assertFalse((root / "rtl/rx_group_ingress_2spc.v").exists())
            self.assertFalse((root / "rtl/tx_iq_axis_boundary_2spc.v").exists())
            rx_rtl = (root / "reference_rtl/rx_group_ingress_2spc.v").read_text(
                encoding="utf-8"
            )
            tx_rtl = (root / "reference_rtl/tx_iq_axis_boundary_2spc.v").read_text(
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
            self.assertEqual(manifest["production_rtl"], [])
            self.assertEqual(
                {item["verilog_file"] for item in manifest["reference_rtl"]},
                {
                    "reference_rtl/rx_group_ingress_2spc.v",
                    "reference_rtl/tx_iq_axis_boundary_2spc.v",
                },
            )
            self.assertEqual(
                manifest["modules"],
                manifest["production_rtl"] + manifest["reference_rtl"],
            )
            self.assertFalse(
                manifest["ip_architecture"]["production_integration_ready"]
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

    def test_unregistered_rtl_is_rejected_per_generated_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for scope in ("rtl", "reference_rtl"):
                with self.subTest(scope=scope):
                    scoped_root = root / scope
                    scoped_root.mkdir(parents=True, exist_ok=True)
                    (scoped_root / "hand_edited.v").write_text(
                        "module hand_edited; endmodule\n"
                    )

                    with self.assertRaisesRegex(
                        RuntimeError, f"unregistered generated RTL exists in {scope}"
                    ):
                        generate(root)

                    (scoped_root / "hand_edited.v").unlink()

    def test_legacy_rtl_migrates_only_when_old_production_bytes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fresh = generate(root)
            legacy = fresh["reference_rtl"]
            rtl_root = root / "rtl"
            rtl_root.mkdir(exist_ok=True)
            for item in legacy:
                source = root / item["verilog_file"]
                (rtl_root / source.name).write_bytes(source.read_bytes())

            manifest = generate(root)

            self.assertEqual(manifest["production_rtl"], [])
            self.assertEqual(list(rtl_root.glob("*.v")), [])

    def test_changed_legacy_rtl_in_old_production_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rtl").mkdir(parents=True)
            (root / "rtl/rx_group_ingress_2spc.v").write_text(
                "module hand_edited; endmodule\n"
            )

            with self.assertRaisesRegex(RuntimeError, "possible hand edit"):
                generate(root)

    def test_legacy_registration_in_production_manifest_blocks_readiness(self) -> None:
        legacy_as_production = SimpleNamespace(
            cycle_class=RxGroupIngress2Spc,
            verilog_filename="rx_group_ingress_2spc.v",
            implementation_kind=ImplementationKind.LEGACY_NON_PRODUCTION,
            production=True,
        )
        generator_module = importlib.import_module("rfsoc_pulse_model.generate")
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(
                generator_module, "HARDWARE_MODULES", (legacy_as_production,)
            ):
                manifest = generate(Path(temporary))

        self.assertEqual(
            [item["verilog_file"] for item in manifest["production_rtl"]],
            ["rtl/rx_group_ingress_2spc.v"],
        )
        self.assertFalse(manifest["ip_architecture"]["production_integration_ready"])
        self.assertIn(
            "reference_rtl_in_production_sources",
            manifest["ip_architecture"]["production_integration_blocking_reasons"],
        )
