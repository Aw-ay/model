"""Transactional lifecycle tests using an injected fake Vivado launcher."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

from tests.ip.test_connected import authority_fixture, fixture, sha


class ConnectedRunnerTest(unittest.TestCase):
    def test_success_replaces_old_success_before_launcher_and_validates_candidate(self) -> None:
        """Publishing after launch, or reusing stale evidence, must fail this."""

        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        request, evidence, context = fixture()
        _, _, platform, _, _, _ = context
        from rfsoc_pulse_model.ip.rfdc_probe import _candidate_properties
        model, architecture, _, _, _, _ = context
        artifacts = emit_connected_tcl(request, platform, _candidate_properties(model, architecture))
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
                attempt.candidate_evidence_path.write_bytes(
                    __import__("rfsoc_pulse_model.ip.connected", fromlist=["canonical_connected_json_bytes"])
                    .canonical_connected_json_bytes(replace(
                        evidence,
                        realization_tcl_sha256=artifacts.realization_tcl_sha256,
                        verification_tcl_sha256=artifacts.verification_tcl_sha256,
                        report_hashes=report_hashes,
                    ))
                )
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
        from rfsoc_pulse_model.ip.rfdc_probe import _candidate_properties
        model, architecture, _, _, _, _ = context
        artifacts = emit_connected_tcl(request, platform, _candidate_properties(model, architecture))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            with self.assertRaisesRegex(RuntimeError, "launcher failed"):
                runner.run(artifacts, *context, launcher=lambda _attempt: 7)
            with self.assertRaisesRegex(ValueError, "success"):
                runner.load_validated_success(*context)


if __name__ == "__main__":
    unittest.main()
