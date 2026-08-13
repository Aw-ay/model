"""Transactional lifecycle tests using an injected fake Vivado launcher."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from tests.ip.test_connected import authority_fixture, fixture, sha
from tests.ip.test_connected_tcl import probe_result


def readback_bytes(artifacts):
    """Fake Vivado protocol output, derived from generated request/artifacts."""
    from rfsoc_pulse_model.ip.connected import parse_connected_request
    request = parse_connected_request(artifacts.request_bytes)
    lines = [
        f"CONNECTED_READBACK\tMETA\trequest_sha256\t{artifacts.request_sha256}",
        f"CONNECTED_READBACK\tMETA\trealization_tcl_sha256\t{artifacts.realization_tcl_sha256}",
        f"CONNECTED_READBACK\tMETA\tverification_tcl_sha256\t{artifacts.verification_tcl_sha256}",
        f"CONNECTED_READBACK\tMETA\tvivado_version\t{request.vivado_version}",
        f"CONNECTED_READBACK\tMETA\tdevice_part\t{request.device_part}",
    ]
    lines += [f"CONNECTED_READBACK\tCELL\t{x.name}\t{x.vlnv}" for x in request.cells]
    lines += [f"CONNECTED_READBACK\tCONFIG\t{k}\t{v}" for k, v in artifacts.rfdc_properties]
    lines += [f"CONNECTED_READBACK\tPS_CONFIG\t{k}\t{v}" for k, v in artifacts.ps_properties]
    lines += [f"CONNECTED_READBACK\tDATA\t{x.name}\t{'Master' if x.direction == 'master' else 'Slave'}\txilinx.com:interface:axis_rtl:1.0\t{x.width_bits // 8}" for x in request.interfaces]
    names = {x.name for x in request.interfaces}
    lines += [f"CONNECTED_READBACK\tRF\t{x.name}\t{x.mode}\t{x.vlnv}" for x in artifacts.rfdc_interfaces if x.name not in names and (x.name in {'adc0_clk','adc1_clk','adc2_clk','adc3_clk','dac0_clk','dac1_clk','sysref_in'} or x.name.startswith(('vin','vout')))]
    lines += [f"CONNECTED_READBACK\tPORT\t{x.name}\t{x.name}" for x in request.interfaces]
    lines += [f"CONNECTED_READBACK\tPORT\t{x.name}\t{x.name}" for x in artifacts.external_rf_interfaces]
    lines += ["CONNECTED_READBACK\tINVERTER\tC_OPERATION\tnot\tC_SIZE\t1", "CONNECTED_READBACK\tCONCAT\tNUM_PORTS\t1"]
    lines += [f"CONNECTED_READBACK\tCLOCK\t{x.domain}\t{member}\t{x.net}" for x in request.clocks for member in x.members]
    lines += [f"CONNECTED_READBACK\tRESET\t{x.domain}\t{member}\t{x.reset_net}" for x in request.resets for member in x.members]
    lines += [f"CONNECTED_READBACK\tLOCK\t{x.domain}\t{x.dcm_locked_pin}\t{x.dcm_locked_pin}" for x in request.resets]
    lines += ["CONNECTED_READBACK\tADDRESS\trfdc_0/s_axi/Reg\tsegment", "CONNECTED_READBACK\tIRQ\trfdc_0/irq\tirq_concat_0/In0\tirq_concat_0/dout\tzynq_ultra_ps_e_0/pl_ps_irq0"]
    lines += [f"CONNECTED_READBACK\tMTS\t{k}\t{v}" for k, v in artifacts.mts_properties]
    lines += [f"CONNECTED_READBACK\tBOOL\t{name}\t{value}" for name, value in (("validate_bd_design_passed","true"),("synthesis_completed","true"),("mts_runtime_verified","false"))]
    return ("\n".join(lines) + "\nCONNECTED_READBACK\tEND\n").encode("utf-8")


def write_clean_reports(attempt) -> None:
    """Minimal bounded report fixtures accepted by the fail-closed parser."""
    contents = {
        "cdc": b"CDC_SAFE\n",
        "clock_interaction": b"CLOCK_SAFE\n",
        "timing_summary": b"TIMING_CONSTRAINED\n",
        "utilization": b"UTILIZATION_OK\n",
    }
    for name, path in attempt.report_paths.items():
        path.write_bytes(contents[name])


class ConnectedRunnerTest(unittest.TestCase):
    def _artifacts_context(self):
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        request, _, context = fixture()
        model, architecture, platform, _, _, _ = context
        probe = probe_result(model, architecture)
        return emit_connected_tcl(request, platform, probe.applied_config, probe.interfaces), context

    @staticmethod
    def _successful_fake(artifacts, *, mutate_readback=None, mutate_reports=None):
        def fake(attempt):
            write_clean_reports(attempt)
            if mutate_reports is not None:
                mutate_reports(attempt)
            raw = readback_bytes(artifacts)
            if mutate_readback is not None:
                raw = mutate_readback(raw)
            attempt.readback_path.write_bytes(raw)
            return 0
        return fake

    def test_runner_rejects_partial_machine_readback_and_exposes_disk_command_contract(self) -> None:
        """Accepting partial readback would let a fake hide missing Vivado facts."""
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner, build_vivado_command

        request, _, context = fixture()
        model, architecture, platform, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe.applied_config, probe.interfaces)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            observed = []
            def fake(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(b"CONNECTED_READBACK\tEND\n")
                return 0
            with self.assertRaisesRegex(RuntimeError, "readback"):
                runner.run(artifacts, *context, launcher=fake)
            command = build_vivado_command(observed[0], Path("D:/app/AMD/2025.2/Vivado/bin/vivado.bat"))
            self.assertEqual(command[1:4], ("-mode", "batch", "-source"))
            self.assertEqual(observed[0].project_dir.parent, observed[0].root)
            self.assertEqual(observed[0].vivado_environment(artifacts.verification_tcl_sha256)["CONNECTED_READBACK_TSV"], str(observed[0].readback_path))

    def test_success_replaces_old_success_before_launcher_and_validates_candidate(self) -> None:
        """Publishing after launch, or reusing stale evidence, must fail this."""

        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        request, evidence, context = fixture()
        _, _, platform, _, _, _ = context
        model, architecture, _, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe.applied_config, probe.interfaces)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            old_state = root / "build" / "metadata" / "connected_rfdc_shell_state.json"
            old_state.parent.mkdir(parents=True)
            old_state.write_text('{"stale":true}\n', encoding="utf-8")

            def fake(attempt):
                state = old_state.read_bytes()
                self.assertIn(b'"state":"in_progress"', state)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0

            accepted = runner.run(artifacts, *context, launcher=fake)
            self.assertTrue(accepted.rfdc_shell_structural_ready)
            self.assertFalse(accepted.production_integration_ready)
            loaded = runner.load_validated_success(*context)
            self.assertEqual(loaded.connected_request_sha256, evidence.connected_request_sha256)
            with self.assertRaisesRegex(RuntimeError, "launcher failed"):
                runner.run(artifacts, *context, launcher=lambda _attempt: 9)
            with self.assertRaisesRegex(ValueError, "success"):
                runner.load_validated_success(*context)

    def test_failed_launcher_leaves_old_success_unauthorized(self) -> None:
        """Leaving old success consumable after a failed run must fail this."""

        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        request, _, context = fixture()
        _, _, platform, _, _, _ = context
        model, architecture, _, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe.applied_config, probe.interfaces)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            with self.assertRaisesRegex(RuntimeError, "launcher failed"):
                runner.run(artifacts, *context, launcher=lambda _attempt: 7)
            with self.assertRaisesRegex(ValueError, "success"):
                runner.load_validated_success(*context)

    def test_report_and_mts_evidence_fail_closed(self) -> None:
        """Unsafe reports or absent/wrong per-tile RFDC MTS readback never ready."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        mutations = {
            "critical_cdc": lambda attempt: attempt.report_paths["cdc"].write_bytes(b"CRITICAL WARNING: unsafe CDC\nCDC_SAFE\n"),
            "unsafe_clock": lambda attempt: attempt.report_paths["clock_interaction"].write_bytes(b"CLOCK_SAFE\nUNSAFE CLOCK\n"),
            "unconstrained_timing": lambda attempt: attempt.report_paths["timing_summary"].write_bytes(b"TIMING_CONSTRAINED\nUNCONSTRAINED PATH\n"),
            "oversized_report": lambda attempt: attempt.report_paths["cdc"].write_bytes(b"CDC_SAFE\n" + b"x" * 1_000_000),
            "missing_mts": lambda raw: raw.replace(b"CONNECTED_READBACK\tMTS\tADC0_Multi_Tile_Sync\ttrue\n", b""),
            "wrong_mts": lambda raw: raw.replace(b"CONNECTED_READBACK\tMTS\tDAC0_Multi_Tile_Sync\ttrue", b"CONNECTED_READBACK\tMTS\tDAC0_Multi_Tile_Sync\tfalse"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutation in mutations.items():
                with self.subTest(name=name):
                    runner = ConnectedShellRunner(root, root / "build")
                    if name in {"missing_mts", "wrong_mts"}:
                        fake = self._successful_fake(artifacts, mutate_readback=mutation)
                    else:
                        fake = self._successful_fake(artifacts, mutate_reports=mutation)
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        runner.run(artifacts, *context, launcher=fake)

    def test_readback_proves_reset_ps_concat_and_external_port_inventory(self) -> None:
        """A realised shell may not silently ignore reviewed wiring/configuration."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        ps_name, ps_value = artifacts.ps_properties[0]
        wrong_ps_value = "0" if ps_value != "0" else "1"
        mutations = {
            "ps": lambda raw: raw.replace(
                f"CONNECTED_READBACK\tPS_CONFIG\t{ps_name}\t{ps_value}".encode(),
                f"CONNECTED_READBACK\tPS_CONFIG\t{ps_name}\t{wrong_ps_value}".encode(),
            ),
            "inverter": lambda raw: raw.replace(b"C_OPERATION\tnot", b"C_OPERATION\tor"),
            "concat": lambda raw: raw.replace(b"CONCAT\tNUM_PORTS\t1", b"CONCAT\tNUM_PORTS\t2"),
            "port": lambda raw: raw.replace(b"PORT\tvin0_01\tvin0_01", b"PORT\tvin0_01\twrong_port"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutation in mutations.items():
                with self.subTest(name=name):
                    runner = ConnectedShellRunner(root, root / "build")
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        runner.run(artifacts, *context, launcher=self._successful_fake(artifacts, mutate_readback=mutation))

    def test_runner_lock_rejects_concurrent_and_recovers_stale_advisory_file(self) -> None:
        """Only an acquired advisory lock blocks; a stale file itself does not."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner, _repository_lock

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            lock = root / ".connected_rfdc_shell.runner.lock"
            lock.write_bytes(b"stale advisory content")
            accepted = runner.run(artifacts, *context, launcher=self._successful_fake(artifacts))
            self.assertTrue(accepted.rfdc_shell_structural_ready)
            with _repository_lock(lock):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    ConnectedShellRunner(root, root / "build").run(artifacts, *context, launcher=self._successful_fake(artifacts))

    def test_interrupted_evidence_or_success_publication_leaves_failed_authority(self) -> None:
        """Both publish boundaries fail closed instead of leaving a usable success."""
        import rfsoc_pulse_model.ip.connected_runner as runner_module

        artifacts, context = self._artifacts_context()
        original = runner_module._atomic_write
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for boundary in ("evidence", "success"):
                with self.subTest(boundary=boundary):
                    runner = runner_module.ConnectedShellRunner(root, root / "build")
                    def interrupted(path, payload, *, target=boundary):
                        if target == "evidence" and path == runner.evidence_path:
                            raise OSError("simulated evidence publish interruption")
                        if target == "success" and path == runner.state_path and b'"state":"success"' in payload:
                            raise OSError("simulated state publish interruption")
                        return original(path, payload)
                    with patch.object(runner_module, "_atomic_write", side_effect=interrupted):
                        with self.assertRaisesRegex(RuntimeError, "interruption"):
                            runner.run(artifacts, *context, launcher=self._successful_fake(artifacts))
                    self.assertIn(b'"state":"failed"', runner.state_path.read_bytes())
                    with self.assertRaisesRegex(ValueError, "success"):
                        runner.load_validated_success(*context)

    def test_attempt_report_reparse_and_launch_path_attacks_fail_closed(self) -> None:
        """Junction/symlink report substitution and `}` paths cannot alter Tcl execution."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary) / "legal}component"
            root.mkdir()
            runner = ConnectedShellRunner(root, root / "build")
            observed = []
            def brace_fake(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            runner.run(artifacts, *context, launcher=brace_fake)
            launch = observed[0].launch_tcl_path.read_text(encoding="utf-8")
            self.assertEqual(launch, "source $::env(CONNECTED_REALIZATION_TCL)\nsource $::env(CONNECTED_VERIFICATION_TCL)\n")
            self.assertEqual(observed[0].vivado_environment(artifacts.verification_tcl_sha256)["CONNECTED_REALIZATION_TCL"], str(observed[0].realization_tcl_path))

            attack_runner = ConnectedShellRunner(root, root / "build_attack")
            outside_report = Path(outside) / "cdc.rpt"
            outside_report.write_bytes(b"CDC_SAFE\n")
            def symlink_fake(attempt):
                write_clean_reports(attempt)
                attempt.report_paths["cdc"].unlink()
                try:
                    os.symlink(outside_report, attempt.report_paths["cdc"])
                except OSError as error:
                    self.skipTest(f"symlink capability unavailable: {error}")
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            with self.assertRaisesRegex(RuntimeError, "failed"):
                attack_runner.run(artifacts, *context, launcher=symlink_fake)

    def test_report_directory_junction_is_rejected_before_readback(self) -> None:
        """A Windows junction in an attempt cannot redirect trusted report reads."""
        if os.name != "nt":
            self.skipTest("junction semantics are Windows-specific")
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            external_reports = Path(outside) / "reports"
            external_reports.mkdir()
            runner = ConnectedShellRunner(root, root / "build")
            def junction_fake(attempt):
                reports = next(iter(attempt.report_paths.values())).parent
                reports.rmdir()
                result = subprocess.run(
                    ["cmd.exe", "/c", "mklink", "/J", str(reports), str(external_reports)],
                    capture_output=True, text=True, check=False,
                )
                if result.returncode != 0:
                    self.skipTest(f"junction capability unavailable: {result.stderr or result.stdout}")
                contents = {
                    "cdc": b"CDC_SAFE\n", "clock_interaction": b"CLOCK_SAFE\n",
                    "timing_summary": b"TIMING_CONSTRAINED\n", "utilization": b"UTILIZATION_OK\n",
                }
                for name, path in attempt.report_paths.items():
                    path.write_bytes(contents[name])
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            with self.assertRaisesRegex(RuntimeError, "reparse"):
                runner.run(artifacts, *context, launcher=junction_fake)


if __name__ == "__main__":
    unittest.main()
