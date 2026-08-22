"""Contract tests for deterministic connected-shell Tcl generation."""

from __future__ import annotations

import hashlib
import unittest

from tests.ip.test_connected import authority_fixture


def probe_result(model, architecture):
    from rfsoc_pulse_model.ip.rfdc_probe import (
        build_rfdc_probe_evidence, emit_rfdc_probe_tcl, parse_rfdc_probe_evidence,
    )
    from tests.ip.test_rfdc_probe import RfdcProbeContractTests
    tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
    return parse_rfdc_probe_evidence(
        build_rfdc_probe_evidence(RfdcProbeContractTests._measured_raw_fixture(), tcl, model, architecture, run_id=17),
        tcl, model, architecture,
    )


class ConnectedTclTest(unittest.TestCase):
    def test_emitter_derives_stable_complete_shell_without_data_plane_cells(self) -> None:
        """Deleting a required cell/route or adding a data plane must break this."""

        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(
            model, architecture, platform, lock, provenance, bundle
        )
        probe = probe_result(model, architecture)
        first = emit_connected_tcl(request, platform, probe)
        second = emit_connected_tcl(request, platform, probe)
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
        self.assertIn("CONFIG.C_OPERATION", text)
        self.assertIn(
            "set_property -dict [list {CONFIG.NUM_PORTS} {1}] [get_bd_cells {irq_concat_0}]",
            text,
        )
        self.assertIn("{CONFIG.PSU__USE__M_AXI_GP2} {0}", text)
        self.assertIn("maxihpm0_fpd_aclk", text)
        self.assertIn(
            "set rfdc_adc_axis_freq_mhz [get_property CONFIG.ADC0_Outclk_Freq [get_bd_cells {rfdc_0}]]",
            text,
        )
        self.assertIn(
            "set_property CONFIG.FREQ_HZ [expr {int(round(1000000.0 * $rfdc_adc_axis_freq_mhz))}] [get_bd_intf_ports {m00_axis_0}]",
            text,
        )
        self.assertIn(
            "set_property CONFIG.FREQ_HZ [expr {int(round(1000000.0 * $rfdc_dac_axis_freq_mhz))}] [get_bd_intf_ports {s00_axis_0}]",
            text,
        )
        self.assertIn("create_project connected_rfdc_shell $::env(CONNECTED_PROJECT_DIR)", text)
        self.assertIn("validate_bd_design", text)
        self.assertIn("save_bd_design", text)
        for interface in request.interfaces:
            self.assertIn(interface.name, text)
        for interface in probe.interfaces:
            if interface.name in {"adc0_clk", "adc1_clk", "adc2_clk", "adc3_clk", "dac0_clk", "dac1_clk", "sysref_in"} or interface.name.startswith(("vin", "vout")):
                self.assertIn(f"rfdc_0/{interface.name}", text)
        for forbidden in ("axi_dma", "detector", "automation"):
            self.assertNotIn(forbidden, text.lower())
        verification = first.verification_tcl.decode("utf-8")
        self.assertIn(
            "connected_emit PORT m00_axis [get_property NAME [get_bd_intf_ports {m00_axis_0}]]",
            verification,
        )
        self.assertIn("CONNECTED_READBACK_TSV", verification)
        self.assertIn("generate_target all", verification)
        self.assertIn(
            "set connected_bd_design [get_bd_designs -quiet connected_rfdc_shell]",
            verification,
        )
        self.assertIn(
            "set connected_bd_file [get_files -quiet [get_property FILE_NAME $connected_bd_design]]",
            verification,
        )
        self.assertIn("make_wrapper -files $connected_bd_file -top", verification)
        self.assertIn(
            "set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects $synth_run",
            verification,
        )
        self.assertIn("connected_emit META synthesis_mode out_of_context", verification)
        self.assertIn("connected_emit META axis_boundary bd_external_interfaces", verification)
        self.assertIn("connected_emit META timing_scope ooc_boundary_only", verification)
        self.assertIn("create_waiver -user $vendor_waiver_user -type CDC -id CDC-13", verification)
        self.assertIn("create_waiver -user $vendor_waiver_user -type CDC -id CDC-15", verification)
        self.assertIn("AMD RFDC CDC-13 waiver endpoint discovery mismatch", verification)
        self.assertIn("AMD RFDC CDC-15 waiver endpoint inventory mismatch", verification)
        self.assertIn("open_run synth_1", verification)
        self.assertIn(
            'connected_emit BOOL validate_bd_design_passed [expr {[llength $validate_result] == 0 ? "true" : "false"}]',
            verification,
        )
        self.assertIn(
            'connected_emit BOOL synthesis_completed [expr {$synth_status eq {synth_design Complete!} ? "true" : "false"}]',
            verification,
        )
        self.assertNotIn("connected_rfdc_shell_state", verification)
        self.assertNotIn("BOOL cdc_safe true", verification)
        self.assertNotIn("BOOL clock_safety_verified true", verification)
        self.assertNotIn("BOOL mts_configuration_verified true", verification)
        for name, value in first.mts_properties:
            self.assertEqual(value, "true")
            self.assertIn(f"connected_emit MTS {name} [get_property CONFIG.{name}", verification)
        self.assertEqual(
            first.mts_properties,
            tuple(
                (name, "true")
                for name in (
                    "ADC0_Multi_Tile_Sync", "ADC1_Multi_Tile_Sync",
                    "ADC2_Multi_Tile_Sync", "ADC3_Multi_Tile_Sync",
                    "DAC0_Multi_Tile_Sync", "DAC1_Multi_Tile_Sync",
                )
            ),
        )
        self.assertIn("report_cdc -details -show_waiver -file", verification)
        self.assertIn(
            "report_timing_summary -report_unconstrained -no_detailed_paths -file",
            verification,
        )
        self.assertIn(
            "connected_emit PS_CONFIG CONFIG.PSU__USE__M_AXI_GP2",
            verification,
        )
        self.assertIn(("CONFIG.PSU__USE__M_AXI_GP2", "0"), first.ps_properties)

    def test_emitter_rejects_tcl_metacharacters_in_authority_values(self) -> None:
        """Removing Tcl-token validation would make generated commands injectable."""

        from dataclasses import replace
        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(model, architecture, platform, lock, provenance, bundle)
        poisoned = replace(request.cells[0], name="rfdc_0; puts pwned")
        probe = probe_result(model, architecture)
        with self.assertRaisesRegex(ValueError, "safe Tcl"):
            emit_connected_tcl(
                replace(request, cells=(poisoned, *request.cells[1:])), platform,
                probe,
            )

        with self.assertRaisesRegex(ValueError, "Task-4 RfdcProbeResult"):
            emit_connected_tcl(request, platform, object())

    def test_property_lists_use_tcl_line_continuations(self) -> None:
        """Vivado must parse each generated multi-line property list as one command."""

        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(model, architecture, platform, lock, provenance, bundle)
        text = emit_connected_tcl(request, platform, probe_result(model, architecture)).realization_tcl.decode("utf-8")
        lines = text.splitlines()
        starts = [
            index for index, line in enumerate(lines)
            if line.startswith("set_property -dict [list") and line.endswith("\\")
        ]
        self.assertEqual(len(starts), 2)
        for start in starts:
            self.assertTrue(lines[start].endswith("\\"))
            end = next(index for index in range(start + 1, len(lines)) if lines[index].startswith("] [get_bd_cells"))
            self.assertGreater(end, start + 1)
            for line in lines[start + 1:end]:
                self.assertTrue(line.endswith("\\"), line)

    def test_emitter_does_not_promote_unrequested_measured_config(self) -> None:
        """Full probe readback is evidence; connected Tcl uses the exact whitelist."""

        from dataclasses import replace
        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        (model, architecture, platform, lock), bundle, provenance = authority_fixture()
        request = build_connected_request(model, architecture, platform, lock, provenance, bundle)
        probe = probe_result(model, architecture)
        baseline = emit_connected_tcl(request, platform, probe)
        measured_with_extra = replace(
            probe,
            applied_config=probe.applied_config + (("Unexpected_Property", "0"),),
        )
        artifacts = emit_connected_tcl(request, platform, measured_with_extra)
        realization = artifacts.realization_tcl.decode("utf-8")
        self.assertNotIn("CONFIG.Unexpected_Property", realization)
        self.assertEqual(artifacts.rfdc_properties, baseline.rfdc_properties)


if __name__ == "__main__":
    unittest.main()
