"""Transactional lifecycle tests using an injected fake Vivado launcher."""

from __future__ import annotations

from dataclasses import replace
import hashlib
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
    lines += [f"CONNECTED_READBACK\tDATA\t{x.name}\t{'Master' if x.direction == 'master' else 'Slave'}\txilinx.com:interface:axis_rtl:1.0\t{x.width_bits // 8}" for x in request.interfaces]
    names = {x.name for x in request.interfaces}
    lines += [f"CONNECTED_READBACK\tRF\t{x.name}\t{x.mode}\t{x.vlnv}" for x in artifacts.rfdc_interfaces if x.name not in names and (x.name in {'adc0_clk','adc1_clk','adc2_clk','adc3_clk','dac0_clk','dac1_clk','sysref_in'} or x.name.startswith(('vin','vout')))]
    lines += [f"CONNECTED_READBACK\tCLOCK\t{x.domain}\t{member}\t{x.net}" for x in request.clocks for member in x.members]
    lines += [f"CONNECTED_READBACK\tRESET\t{x.domain}\t{member}\t{x.reset_net}" for x in request.resets for member in x.members]
    lines += [f"CONNECTED_READBACK\tLOCK\t{x.domain}\t{x.dcm_locked_pin}\t{x.dcm_locked_pin}" for x in request.resets]
    lines += ["CONNECTED_READBACK\tADDRESS\trfdc_0/s_axi/Reg\tsegment", "CONNECTED_READBACK\tIRQ\trfdc_0/irq\tirq_concat_0/In0\tirq_concat_0/dout\tzynq_ultra_ps_e_0/pl_ps_irq0"]
    lines += [f"CONNECTED_READBACK\tBOOL\t{name}\t{value}" for name, value in (("validate_bd_design_passed","true"),("synthesis_completed","true"),("cdc_safe","true"),("clock_safety_verified","true"),("mts_configuration_verified","true"),("mts_runtime_verified","false"))]
    return ("\n".join(lines) + "\nCONNECTED_READBACK\tEND\n").encode("utf-8")


class ConnectedRunnerTest(unittest.TestCase):
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
                for path in attempt.report_paths.values(): path.write_bytes(b"report\n")
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
                for name, path in attempt.report_paths.items():
                    path.write_bytes((name + " report\n").encode("utf-8"))
                report_hashes = tuple(
                    (name, hashlib.sha256(path.read_bytes()).hexdigest())
                    for name, path in attempt.report_paths.items()
                )
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


if __name__ == "__main__":
    unittest.main()
