"""Contract tests for deterministic connected-shell Tcl generation."""

from __future__ import annotations

import hashlib
import unittest

from tests.ip.test_connected import authority_fixture


class ConnectedTclTest(unittest.TestCase):
    def test_emitter_derives_stable_complete_shell_without_data_plane_cells(self) -> None:
        """Deleting a required cell/route or adding a data plane must break this."""

        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(
            model, architecture, platform, lock, provenance, bundle
        )
        from rfsoc_pulse_model.ip.rfdc_probe import _candidate_properties
        properties = _candidate_properties(model, architecture)
        first = emit_connected_tcl(request, platform, properties)
        second = emit_connected_tcl(request, platform, properties)
        self.assertEqual(first, second)
        self.assertEqual(first.request_bytes, first.request_bytes)
        self.assertEqual(
            first.request_sha256,
            hashlib.sha256(first.request_bytes).hexdigest(),
        )
        text = first.realization_tcl.decode("utf-8")
        self.assertIn("create_bd_design {connected_rfdc_shell}", text)
        self.assertIn("xilinx.com:ip:usp_rf_data_converter:2.6", text)
        self.assertIn("ctrl_clock_locked", text)
        self.assertIn("rx_clock_locked", text)
        self.assertIn("tx_clock_locked", text)
        self.assertIn("M_AXI_HPM0_FPD", text)
        self.assertIn("rx_reset_0/ext_reset_in", text)
        self.assertIn("tx_reset_0/ext_reset_in", text)
        self.assertIn("validate_bd_design", text)
        self.assertIn("save_bd_design", text)
        for interface in request.interfaces:
            self.assertIn(interface.name, text)
        for forbidden in ("axi_dma", "detector", "automation"):
            self.assertNotIn(forbidden, text.lower())
        verification = first.verification_tcl.decode("utf-8")
        self.assertIn("CONNECTED_CANDIDATE_EVIDENCE", verification)
        self.assertNotIn("connected_rfdc_shell_state", verification)

    def test_emitter_rejects_tcl_metacharacters_in_authority_values(self) -> None:
        """Removing Tcl-token validation would make generated commands injectable."""

        from dataclasses import replace
        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(model, architecture, platform, lock, provenance, bundle)
        poisoned = replace(request.cells[0], name="rfdc_0; puts pwned")
        from rfsoc_pulse_model.ip.rfdc_probe import _candidate_properties
        with self.assertRaisesRegex(ValueError, "safe Tcl"):
            emit_connected_tcl(
                replace(request, cells=(poisoned, *request.cells[1:])), platform,
                _candidate_properties(model, architecture),
            )


if __name__ == "__main__":
    unittest.main()
