import unittest

try:
    from rfsoc_pulse_model.ip.calibrator_vivado import emit_calibrator_vivado_tcl
except ImportError:  # RED until the complete deployment script exists.
    emit_calibrator_vivado_tcl = None  # type: ignore[assignment]


class CalibratorVivadoTclTest(unittest.TestCase):
    def test_script_is_version_gated_and_builds_all_required_ip(self) -> None:
        self.assertIsNotNone(emit_calibrator_vivado_tcl)
        assert emit_calibrator_vivado_tcl is not None
        script = emit_calibrator_vivado_tcl()

        self.assertIn("Vivado 2025.2 is required", script)
        self.assertIn("xczu27dr-fsve1156-2-i", script)
        self.assertIn("xilinx.com:ip:usp_rf_data_converter:2.6", script)
        self.assertIn("xilinx.com:ip:axi_dma:7.1", script)
        self.assertIn("c_include_sg", script.lower())
        self.assertIn("C_S_AXIS_S2MM_TDATA_WIDTH", script)
        self.assertIn("128", script)
        self.assertIn("S_AXI_HP0_FPD", script)
        self.assertIn("M_AXI_HPM0_FPD", script)

        for channel in range(8):
            self.assertIn(f"adc{channel}_iq_combiner", script)
            self.assertIn(f"adc{channel}_iq_subset", script)
            self.assertIn(f"adc{channel}_rx_slice", script)
            self.assertIn(f"adc{channel}_broadcaster", script)
            self.assertIn(f"dac{channel}_mute_gate", script)
            self.assertNotIn(f"adc{channel}_to_dac_cdc", script)

        self.assertIn("calibrator_control_cdc.sv", script)
        self.assertIn("axis_dac_mute_gate.sv", script)
        self.assertIn("calibrator_control_cdc_0", script)

    def test_script_locks_board_io_loopback_mapping_interrupts_and_final_reports(self) -> None:
        assert emit_calibrator_vivado_tcl is not None
        script = emit_calibrator_vivado_tcl()
        self.assertIn("PSU__ENET3__PERIPHERAL__ENABLE", script)
        self.assertIn("PSU__ENET3__PERIPHERAL__IO", script)
        self.assertIn("MIO 64 .. 77", script)
        self.assertIn("PSU__SD0__PERIPHERAL__IO", script)
        self.assertIn("MIO 13 .. 22", script)
        self.assertIn("PSU__SD0__GRP_POW__IO", script)
        self.assertIn("MIO 23", script)
        self.assertIn("FILE_TYPE {Verilog}", script)

        expected = {0: "s01_axis", 1: "s03_axis", 2: "s11_axis", 3: "s13_axis", 4: "s00_axis", 5: "s02_axis", 6: "s10_axis", 7: "s12_axis"}
        for adc, dac_axis in expected.items():
            self.assertIn(
                f"adc{adc}_broadcaster/M00_AXIS}}] [get_bd_intf_pins {{dac{adc}_mute_gate/s_axis}}",
                script,
            )
            self.assertIn(
                f"dac{adc}_mute_gate/m_axis}}] [get_bd_intf_pins {{rfdc_0/{dac_axis}}}",
                script,
            )
            self.assertNotIn(
                f"adc{adc}_broadcaster/M00_AXIS}}] [get_bd_intf_pins {{rfdc_0/{dac_axis}}}",
                script,
            )
        self.assertIn("rfdc_0/irq", script)
        self.assertIn("axi_dma_0/s2mm_introut", script)
        self.assertIn("pl_ps_irq0", script)
        self.assertIn("report_timing_summary", script)
        self.assertIn("report_cdc", script)
        self.assertIn("report_drc", script)
        self.assertIn("report_bus_skew", script)
        self.assertIn("-delay_type min", script)
        self.assertIn("CDC Critical violations remain", script)
        self.assertIn("synth_design -top calibrator_wrapper", script)
        self.assertIn("place_design", script)
        self.assertIn("route_design", script)
        self.assertIn("write_bitstream", script)
        self.assertIn("write_hw_platform -fixed -force", script)
        self.assertIn("calibrator_no_bit.xsa", script)
        self.assertIn("-offset 0xA0000000 -range 0x00010000", script)
        self.assertIn("-offset 0xA0040000 -range 0x00040000", script)
        self.assertIn("-offset 0xA0080000 -range 0x00010000", script)
        self.assertIn("ps_0/pl_clk1", script)
        self.assertIn("rfdc_0/m0_axis_aclk", script)
        self.assertIn("rfdc_0/s0_axis_aclk", script)
        self.assertIn("ctrl_reset_0/peripheral_aresetn", script)
        self.assertIn("rx_reset_0/peripheral_aresetn", script)
        self.assertIn("tx_reset_0/peripheral_aresetn", script)
        for tile in range(1, 4):
            self.assertIn(f"rfdc_adc{tile}_reset", script)
        self.assertIn("rfdc_dac1_reset", script)
        self.assertIn("calibrator_control_cdc_0/event_count_rx_i", script)
        self.assertIn("calibrator_control_cdc_0/acquisition_enable_rx_o", script)
        self.assertIn("calibrator_control_0/dac_loopback_enable_o", script)
        self.assertIn("calibrator_control_0/dac_mute_o", script)
        self.assertIn("calibrator_control_cdc_0/dac_loopback_enable_rx_o", script)
        self.assertIn("calibrator_control_cdc_0/dac_mute_rx_o", script)
        self.assertIn("dac${channel}_mute_gate/loopback_enable_i", script)
        self.assertIn("dac${channel}_mute_gate/mute_i", script)
        self.assertIn("dac${channel}_mute_gate/aclk", script)
        self.assertIn("dac${channel}_mute_gate/aresetn", script)
        self.assertNotIn(
            "calibrator_control_0/acquisition_enable_o}] [get_bd_pins {calibrator_core_0/acquisition_enable_i}",
            script,
        )
        self.assertIn("make_bd_intf_pins_external", script)


if __name__ == "__main__":
    unittest.main()
