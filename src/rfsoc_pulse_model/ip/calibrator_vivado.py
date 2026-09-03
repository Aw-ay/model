"""Deterministic Vivado 2025.2 production-design Tcl emission."""

from __future__ import annotations

from ..common.config import ModelConfig
from .calibrator_platform import CalibratorPlatformConfig
from .types import HardwareArchitectureConfig


_ADC_I_AXIS = ("m00_axis", "m02_axis", "m10_axis", "m12_axis", "m20_axis", "m22_axis", "m30_axis", "m32_axis")
_ADC_Q_AXIS = ("m01_axis", "m03_axis", "m11_axis", "m13_axis", "m21_axis", "m23_axis", "m31_axis", "m33_axis")
_ADC_TO_DAC = ("s01_axis", "s03_axis", "s11_axis", "s13_axis", "s00_axis", "s02_axis", "s10_axis", "s12_axis")


def emit_calibrator_vivado_tcl() -> str:
    """Emit the complete BD/build script, refusing every non-2025.2 tool."""

    platform = CalibratorPlatformConfig.load_default()
    platform.require_deployable()
    model = ModelConfig.load_default()
    architecture = HardwareArchitectureConfig.load_default()
    lines = [
        "# Generated from calibrator_platform.json and calibrator_registers.json.",
        "if {[version -short] ne {2025.2}} { error {Vivado 2025.2 is required} }",
        "if {![info exists ::env(CALIBRATOR_BUILD_DIR)]} { error {CALIBRATOR_BUILD_DIR is required} }",
        "if {![info exists ::env(CALIBRATOR_SOURCE_DIR)]} { error {CALIBRATOR_SOURCE_DIR is required} }",
        "set build_dir [file normalize $::env(CALIBRATOR_BUILD_DIR)]",
        "set source_dir [file normalize $::env(CALIBRATOR_SOURCE_DIR)]",
        "set generated_dir [file dirname [info script]]",
        f"create_project calibrator $build_dir -part {{{platform.device_part}}} -force",
        "set_property target_language Verilog [current_project]",
        "add_files -norecurse [list [file join $generated_dir calibrator_registers.vh] [file join $source_dir rtl calibrator_core.sv] [file join $source_dir rtl calibrator_control_axi.sv] [file join $source_dir rtl calibrator_control_cdc.sv] [file join $source_dir rtl axis_dac_mute_gate.sv]]",
        "set_property FILE_TYPE {Verilog Header} [get_files calibrator_registers.vh]",
        "set_property include_dirs [list $generated_dir] [current_fileset]",
        "set_property FILE_TYPE {Verilog} [get_files [list calibrator_core.sv calibrator_control_axi.sv calibrator_control_cdc.sv axis_dac_mute_gate.sv]]",
        "create_bd_design {calibrator}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:zynq_ultra_ps_e:3.5} {ps_0}",
        "# Board authority: RTL8211FD address 7, RGMII TXDLY/RXDLY strapped; MIO 64 .. 77.",
        "# PHY reset is active-low PS_POR_B. The optional MIO24/ETH_RSTN route is not populated.",
        "set_property -dict [list \\",
        "  {CONFIG.PSU__ENET3__PERIPHERAL__ENABLE} {1} \\",
        "  {CONFIG.PSU__ENET3__PERIPHERAL__IO} {MIO 64 .. 75} \\",
        "  {CONFIG.PSU__ENET3__GRP_MDIO__ENABLE} {1} \\",
        "  {CONFIG.PSU__ENET3__GRP_MDIO__IO} {MIO 76 .. 77} \\",
        "  {CONFIG.PSU__SD0__PERIPHERAL__ENABLE} {1} \\",
        "  {CONFIG.PSU__SD0__PERIPHERAL__IO} {MIO 13 .. 22} \\",
        "  {CONFIG.PSU__SD0__RESET__ENABLE} {1} \\",
        "  {CONFIG.PSU__SD0__GRP_POW__ENABLE} {1} \\",
        "  {CONFIG.PSU__SD0__GRP_POW__IO} {MIO 23} \\",
        "  {CONFIG.PSU__SD0__DATA_TRANSFER_MODE} {8Bit} \\",
        "  {CONFIG.PSU__SD0__SLOT_TYPE} {eMMC} \\",
        "  {CONFIG.PSU__USE__M_AXI_GP0} {1} \\",
        "  {CONFIG.PSU__USE__M_AXI_GP2} {0} \\",
        "  {CONFIG.PSU__USE__S_AXI_GP2} {1} \\",
        "  {CONFIG.PSU__USE__IRQ0} {1} \\",
        "  {CONFIG.PSU__FPGA_PL1_ENABLE} {1} \\",
        "  {CONFIG.PSU__CRL_APB__RPLL_CTRL__FBDIV} {48} \\",
        "  {CONFIG.PSU__CRL_APB__IOPLL_CTRL__FBDIV} {90} \\",
        "  {CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL} {RPLL} \\",
        "  {CONFIG.PSU__CRL_APB__PL0_REF_CTRL__DIVISOR0} {8} \\",
        "  {CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ} {100} \\",
        "  {CONFIG.PSU__CRL_APB__PL1_REF_CTRL__SRCSEL} {IOPLL} \\",
        "  {CONFIG.PSU__CRL_APB__PL1_REF_CTRL__DIVISOR0} {6} \\",
        "  {CONFIG.PSU__CRL_APB__PL1_REF_CTRL__FREQMHZ} {250} \\",
        "] [get_bd_cells {ps_0}]",
        "# PS interfaces: M_AXI_HPM0_FPD controls RFDC/DMA/custom ABI; S_AXI_HP0_FPD receives DMA writes.",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:usp_rf_data_converter:2.6} {rfdc_0}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:smartconnect:1.0} {control_smc}",
        "set_property -dict [list {CONFIG.NUM_SI} {1} {CONFIG.NUM_MI} {3}] [get_bd_cells {control_smc}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:smartconnect:1.0} {memory_smc}",
        "set_property -dict [list {CONFIG.NUM_SI} {2} {CONFIG.NUM_MI} {1}] [get_bd_cells {memory_smc}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:axi_dma:7.1} {axi_dma_0}",
        "set_property -dict [list \\",
        "  {CONFIG.c_include_sg} {1} \\",
        "  {CONFIG.c_include_mm2s} {0} \\",
        "  {CONFIG.c_include_s2mm} {1} \\",
        "  {CONFIG.c_sg_length_width} {26} \\",
        "  {CONFIG.c_addr_width} {64} \\",
        "  {CONFIG.C_S_AXIS_S2MM_TDATA_WIDTH} {128} \\",
        "] [get_bd_cells {axi_dma_0}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:axis_data_fifo:2.0} {event_fifo_0}",
        "set_property -dict [list {CONFIG.TDATA_NUM_BYTES} {16} {CONFIG.FIFO_DEPTH} {4096} {CONFIG.HAS_TKEEP} {1} {CONFIG.HAS_TLAST} {1}] [get_bd_cells {event_fifo_0}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:axis_clock_converter:1.1} {event_cdc_0}",
        "set_property -dict [list {CONFIG.TDATA_NUM_BYTES} {16}] [get_bd_cells {event_cdc_0}]",
        "create_bd_cell -type module -reference {calibrator_core} {calibrator_core_0}",
        "create_bd_cell -type module -reference {calibrator_control_axi} {calibrator_control_0}",
        "create_bd_cell -type module -reference {calibrator_control_cdc} {calibrator_control_cdc_0}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:xlconcat:2.1} {irq_concat_0}",
        "set_property -dict [list {CONFIG.NUM_PORTS} {2}] [get_bd_cells {irq_concat_0}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:proc_sys_reset:5.0} {ctrl_reset_0}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:proc_sys_reset:5.0} {rx_reset_0}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:proc_sys_reset:5.0} {tx_reset_0}",
        "foreach tile {1 2 3} { create_bd_cell -type ip -vlnv {xilinx.com:ip:proc_sys_reset:5.0} rfdc_adc${tile}_reset }",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:proc_sys_reset:5.0} {rfdc_dac1_reset}",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:xlconstant:1.1} {const_zero_0}",
        "set_property -dict [list {CONFIG.CONST_VAL} {0}] [get_bd_cells {const_zero_0}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:xlconstant:1.1} {const_one_0}",
        "set_property -dict [list {CONFIG.CONST_VAL} {1}] [get_bd_cells {const_one_0}]",
        "create_bd_cell -type ip -vlnv {xilinx.com:ip:xlconstant:1.1} {const_status_0}",
        "set_property -dict [list {CONFIG.CONST_WIDTH} {32} {CONFIG.CONST_VAL} {0}] [get_bd_cells {const_status_0}]",
    ]
    rfdc_properties: dict[str, str] = {}
    for tile in range(4):
        rfdc_properties.update(
            {
                f"ADC{tile}_Enable": "1",
                f"ADC{tile}_PLL_Enable": "true",
                f"ADC{tile}_Sampling_Rate": f"{model.adc_sample_rate_hz / 1_000_000_000:.3f}",
                f"ADC{tile}_Fabric_Freq": f"{model.rx_fabric_clock_hz / 1_000_000:.3f}",
            }
        )
    for entry in model.adc_channel_map:
        suffix = f"{entry.rfdc_tile}{entry.rfdc_slice}"
        rfdc_properties.update(
            {
                f"ADC_Slice{suffix}_Enable": "true",
                f"ADC_Data_Type{suffix}": "1",
                f"ADC_Decimation_Mode{suffix}": str(model.rfdc_decimation),
                f"ADC_Data_Width{suffix}": "2",
                f"ADC_Mixer_Type{suffix}": "2",
                f"ADC_Mixer_Mode{suffix}": "0",
                f"ADC_NCO_Freq{suffix}": f"{model.center_frequency_hz / 1_000_000_000:.3f}",
            }
        )
    for tile in range(2):
        rfdc_properties.update(
            {
                f"DAC{tile}_Enable": "1",
                f"DAC{tile}_PLL_Enable": "true",
                f"DAC{tile}_Sampling_Rate": f"{model.dac_sample_rate_hz / 1_000_000_000:.3f}",
                f"DAC{tile}_Fabric_Freq": f"{model.rx_fabric_clock_hz / 1_000_000:.3f}",
            }
        )
    for entry in model.dac_channel_map:
        suffix = f"{entry.rfdc_tile}{entry.rfdc_slice}"
        rfdc_properties.update(
            {
                f"DAC_Slice{suffix}_Enable": "true",
                f"DAC_Data_Type{suffix}": "0",
                f"DAC_Interpolation_Mode{suffix}": str(model.rfdc_interpolation),
                f"DAC_Data_Width{suffix}": "4",
                f"DAC_Mixer_Type{suffix}": "2",
                f"DAC_Mixer_Mode{suffix}": "0",
                f"DAC_NCO_Freq{suffix}": f"{architecture.rfdc_integration.dac_nco_frequency_hz / 1_000_000_000:.3f}",
            }
        )
    lines.append("set_property -dict [list \\")
    lines.extend(
        f"  {{CONFIG.{name}}} {{{value}}} " + "\\"
        for name, value in sorted(rfdc_properties.items())
    )
    lines.append("] [get_bd_cells {rfdc_0}]")
    for channel in range(8):
        lines.extend(
            [
                f"create_bd_cell -type ip -vlnv {{xilinx.com:ip:axis_combiner:1.1}} {{adc{channel}_iq_combiner}}",
                f"set_property -dict [list {{CONFIG.NUM_SI}} {{2}} {{CONFIG.TDATA_NUM_BYTES}} {{4}}] [get_bd_cells {{adc{channel}_iq_combiner}}]",
                f"create_bd_cell -type ip -vlnv {{xilinx.com:ip:axis_subset_converter:1.1}} {{adc{channel}_iq_subset}}",
                f"set_property -dict [list {{CONFIG.S_TDATA_NUM_BYTES}} {{8}} {{CONFIG.M_TDATA_NUM_BYTES}} {{8}} {{CONFIG.TDATA_REMAP}} {{tdata[63:48],tdata[31:16],tdata[47:32],tdata[15:0]}}] [get_bd_cells {{adc{channel}_iq_subset}}]",
                f"create_bd_cell -type ip -vlnv {{xilinx.com:ip:axis_register_slice:1.1}} {{adc{channel}_rx_slice}}",
                f"create_bd_cell -type ip -vlnv {{xilinx.com:ip:axis_broadcaster:1.1}} {{adc{channel}_broadcaster}}",
                f"set_property -dict [list {{CONFIG.NUM_MI}} {{2}} {{CONFIG.S_TDATA_NUM_BYTES}} {{8}}] [get_bd_cells {{adc{channel}_broadcaster}}]",
                f"create_bd_cell -type module -reference {{axis_dac_mute_gate}} {{dac{channel}_mute_gate}}",
                f"connect_bd_intf_net [get_bd_intf_pins {{rfdc_0/{_ADC_I_AXIS[channel]}}}] [get_bd_intf_pins {{adc{channel}_iq_combiner/S00_AXIS}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{rfdc_0/{_ADC_Q_AXIS[channel]}}}] [get_bd_intf_pins {{adc{channel}_iq_combiner/S01_AXIS}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{adc{channel}_iq_combiner/M_AXIS}}] [get_bd_intf_pins {{adc{channel}_iq_subset/S_AXIS}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{adc{channel}_iq_subset/M_AXIS}}] [get_bd_intf_pins {{adc{channel}_rx_slice/S_AXIS}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{adc{channel}_rx_slice/M_AXIS}}] [get_bd_intf_pins {{adc{channel}_broadcaster/S_AXIS}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{adc{channel}_broadcaster/M00_AXIS}}] [get_bd_intf_pins {{dac{channel}_mute_gate/s_axis}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{dac{channel}_mute_gate/m_axis}}] [get_bd_intf_pins {{rfdc_0/{_ADC_TO_DAC[channel]}}}]",
                f"connect_bd_intf_net [get_bd_intf_pins {{adc{channel}_broadcaster/M01_AXIS}}] [get_bd_intf_pins {{calibrator_core_0/s{channel:02d}_axis}}]",
            ]
        )
    lines.extend(
        [
            "connect_bd_intf_net [get_bd_intf_pins {ps_0/M_AXI_HPM0_FPD}] [get_bd_intf_pins {control_smc/S00_AXI}]",
            "connect_bd_intf_net [get_bd_intf_pins {control_smc/M00_AXI}] [get_bd_intf_pins {rfdc_0/s_axi}]",
            "connect_bd_intf_net [get_bd_intf_pins {control_smc/M01_AXI}] [get_bd_intf_pins {axi_dma_0/S_AXI_LITE}]",
            "connect_bd_intf_net [get_bd_intf_pins {control_smc/M02_AXI}] [get_bd_intf_pins {calibrator_control_0/S_AXI}]",
            "connect_bd_intf_net [get_bd_intf_pins {axi_dma_0/M_AXI_S2MM}] [get_bd_intf_pins {memory_smc/S00_AXI}]",
            "connect_bd_intf_net [get_bd_intf_pins {axi_dma_0/M_AXI_SG}] [get_bd_intf_pins {memory_smc/S01_AXI}]",
            "connect_bd_intf_net [get_bd_intf_pins {memory_smc/M00_AXI}] [get_bd_intf_pins {ps_0/S_AXI_HP0_FPD}]",
            "connect_bd_intf_net [get_bd_intf_pins {calibrator_core_0/m_event_axis}] [get_bd_intf_pins {event_fifo_0/S_AXIS}]",
            "connect_bd_intf_net [get_bd_intf_pins {event_fifo_0/M_AXIS}] [get_bd_intf_pins {event_cdc_0/S_AXIS}]",
            "connect_bd_intf_net [get_bd_intf_pins {event_cdc_0/M_AXIS}] [get_bd_intf_pins {axi_dma_0/S_AXIS_S2MM}]",
            "connect_bd_net [get_bd_pins {rfdc_0/irq}] [get_bd_pins {irq_concat_0/In0}]",
            "connect_bd_net [get_bd_pins {axi_dma_0/s2mm_introut}] [get_bd_pins {irq_concat_0/In1}]",
            "connect_bd_net [get_bd_pins {irq_concat_0/dout}] [get_bd_pins {ps_0/pl_ps_irq0}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/acquisition_enable_o}] [get_bd_pins {calibrator_control_cdc_0/acquisition_enable_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/dac_loopback_enable_o}] [get_bd_pins {calibrator_control_cdc_0/dac_loopback_enable_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/dac_mute_o}] [get_bd_pins {calibrator_control_cdc_0/dac_mute_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/detect_threshold_o}] [get_bd_pins {calibrator_control_cdc_0/detect_threshold_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/config_version_o}] [get_bd_pins {calibrator_control_cdc_0/config_version_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/calibration_integer_delay_o}] [get_bd_pins {calibrator_control_cdc_0/calibration_integer_delay_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/calibration_fractional_delay_o}] [get_bd_pins {calibrator_control_cdc_0/calibration_fractional_delay_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/calibration_gain_real_o}] [get_bd_pins {calibrator_control_cdc_0/calibration_gain_real_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/calibration_gain_imag_o}] [get_bd_pins {calibrator_control_cdc_0/calibration_gain_imag_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_0/calibration_flags_o}] [get_bd_pins {calibrator_control_cdc_0/calibration_flags_ctrl_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/acquisition_enable_rx_o}] [get_bd_pins {calibrator_core_0/acquisition_enable_i}]",
            "foreach channel {0 1 2 3 4 5 6 7} {",
            "  connect_bd_net [get_bd_pins {calibrator_control_cdc_0/dac_loopback_enable_rx_o}] [get_bd_pins dac${channel}_mute_gate/loopback_enable_i]",
            "  connect_bd_net [get_bd_pins {calibrator_control_cdc_0/dac_mute_rx_o}] [get_bd_pins dac${channel}_mute_gate/mute_i]",
            "}",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/detect_threshold_rx_o}] [get_bd_pins {calibrator_core_0/detect_threshold_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/config_version_rx_o}] [get_bd_pins {calibrator_core_0/config_version_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/calibration_integer_delay_rx_o}] [get_bd_pins {calibrator_core_0/calibration_integer_delay_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/calibration_fractional_delay_rx_o}] [get_bd_pins {calibrator_core_0/calibration_fractional_delay_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/calibration_gain_real_rx_o}] [get_bd_pins {calibrator_core_0/calibration_gain_real_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/calibration_gain_imag_rx_o}] [get_bd_pins {calibrator_core_0/calibration_gain_imag_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/calibration_flags_rx_o}] [get_bd_pins {calibrator_core_0/calibration_flags_i}]",
            "connect_bd_net [get_bd_pins {calibrator_core_0/event_count_o}] [get_bd_pins {calibrator_control_cdc_0/event_count_rx_i}]",
            "connect_bd_net [get_bd_pins {calibrator_core_0/drop_count_o}] [get_bd_pins {calibrator_control_cdc_0/drop_count_rx_i}]",
            "connect_bd_net [get_bd_pins {calibrator_core_0/stream_errors_o}] [get_bd_pins {calibrator_control_cdc_0/stream_errors_rx_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/event_count_ctrl_o}] [get_bd_pins {calibrator_control_0/event_count_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/drop_count_ctrl_o}] [get_bd_pins {calibrator_control_0/drop_count_i}]",
            "connect_bd_net [get_bd_pins {calibrator_control_cdc_0/stream_errors_ctrl_o}] [get_bd_pins {calibrator_control_0/stream_errors_i}]",
            "connect_bd_net [get_bd_pins {const_status_0/dout}] [get_bd_pins {calibrator_control_0/rfdc_status_i}] [get_bd_pins {calibrator_control_0/mts_status_i}]",
            "connect_bd_net [get_bd_pins {const_zero_0/dout}] [get_bd_pins {ctrl_reset_0/aux_reset_in}] [get_bd_pins {rx_reset_0/aux_reset_in}] [get_bd_pins {tx_reset_0/aux_reset_in}]",
            "connect_bd_net [get_bd_pins {const_one_0/dout}] [get_bd_pins {ctrl_reset_0/dcm_locked}] [get_bd_pins {rx_reset_0/dcm_locked}] [get_bd_pins {tx_reset_0/dcm_locked}]",
            "connect_bd_net [get_bd_pins {ps_0/pl_resetn0}] [get_bd_pins {ctrl_reset_0/ext_reset_in}] [get_bd_pins {rx_reset_0/ext_reset_in}] [get_bd_pins {tx_reset_0/ext_reset_in}]",
            "foreach reset_name {rfdc_adc1_reset rfdc_adc2_reset rfdc_adc3_reset rfdc_dac1_reset} {",
            "  connect_bd_net [get_bd_pins {const_zero_0/dout}] [get_bd_pins ${reset_name}/aux_reset_in]",
            "  connect_bd_net [get_bd_pins {const_one_0/dout}] [get_bd_pins ${reset_name}/dcm_locked]",
            "  connect_bd_net [get_bd_pins {ps_0/pl_resetn0}] [get_bd_pins ${reset_name}/ext_reset_in]",
            "  connect_bd_net [get_bd_pins {ps_0/pl_clk1}] [get_bd_pins ${reset_name}/slowest_sync_clk]",
            "}",
            "# RX/TX data planes use the common 250 MHz tile clocks selected for MTS.",
            "connect_bd_net [get_bd_pins {ps_0/pl_clk1}] [get_bd_pins {calibrator_core_0/rx_clk}] [get_bd_pins {calibrator_control_cdc_0/rx_clk}] [get_bd_pins {rx_reset_0/slowest_sync_clk}] [get_bd_pins {tx_reset_0/slowest_sync_clk}] [get_bd_pins {rfdc_0/m0_axis_aclk}] [get_bd_pins {rfdc_0/m1_axis_aclk}] [get_bd_pins {rfdc_0/m2_axis_aclk}] [get_bd_pins {rfdc_0/m3_axis_aclk}] [get_bd_pins {rfdc_0/s0_axis_aclk}] [get_bd_pins {rfdc_0/s1_axis_aclk}] [get_bd_pins {event_fifo_0/s_axis_aclk}] [get_bd_pins {event_cdc_0/s_axis_aclk}]",
            "connect_bd_net [get_bd_pins {ps_0/pl_clk0}] [get_bd_pins {calibrator_control_cdc_0/ctrl_clk}] [get_bd_pins {ctrl_reset_0/slowest_sync_clk}] [get_bd_pins {ps_0/maxihpm0_fpd_aclk}] [get_bd_pins {ps_0/saxihp0_fpd_aclk}] [get_bd_pins {rfdc_0/s_axi_aclk}] [get_bd_pins {control_smc/aclk}] [get_bd_pins {memory_smc/aclk}] [get_bd_pins {calibrator_control_0/S_AXI_aclk}] [get_bd_pins {axi_dma_0/s_axi_lite_aclk}] [get_bd_pins {axi_dma_0/m_axi_sg_aclk}] [get_bd_pins {axi_dma_0/m_axi_s2mm_aclk}] [get_bd_pins {event_cdc_0/m_axis_aclk}]",
            "connect_bd_net [get_bd_pins {ctrl_reset_0/peripheral_aresetn}] [get_bd_pins {calibrator_control_cdc_0/ctrl_resetn}] [get_bd_pins {control_smc/aresetn}] [get_bd_pins {memory_smc/aresetn}] [get_bd_pins {rfdc_0/s_axi_aresetn}] [get_bd_pins {calibrator_control_0/S_AXI_aresetn}] [get_bd_pins {axi_dma_0/axi_resetn}] [get_bd_pins {event_cdc_0/m_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {rx_reset_0/peripheral_aresetn}] [get_bd_pins {calibrator_core_0/rx_resetn}] [get_bd_pins {calibrator_control_cdc_0/rx_resetn}] [get_bd_pins {rfdc_0/m0_axis_aresetn}] [get_bd_pins {event_fifo_0/s_axis_aresetn}] [get_bd_pins {event_cdc_0/s_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {rfdc_adc1_reset/peripheral_aresetn}] [get_bd_pins {rfdc_0/m1_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {rfdc_adc2_reset/peripheral_aresetn}] [get_bd_pins {rfdc_0/m2_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {rfdc_adc3_reset/peripheral_aresetn}] [get_bd_pins {rfdc_0/m3_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {tx_reset_0/peripheral_aresetn}] [get_bd_pins {rfdc_0/s0_axis_aresetn}]",
            "connect_bd_net [get_bd_pins {rfdc_dac1_reset/peripheral_aresetn}] [get_bd_pins {rfdc_0/s1_axis_aresetn}]",
            "foreach channel {0 1 2 3 4 5 6 7} {",
            "  connect_bd_net [get_bd_pins {ps_0/pl_clk1}] [get_bd_pins adc${channel}_iq_combiner/aclk] [get_bd_pins adc${channel}_iq_subset/aclk] [get_bd_pins adc${channel}_rx_slice/aclk] [get_bd_pins adc${channel}_broadcaster/aclk] [get_bd_pins dac${channel}_mute_gate/aclk]",
            "  connect_bd_net [get_bd_pins {rx_reset_0/peripheral_aresetn}] [get_bd_pins adc${channel}_iq_combiner/aresetn] [get_bd_pins adc${channel}_iq_subset/aresetn] [get_bd_pins adc${channel}_rx_slice/aresetn] [get_bd_pins adc${channel}_broadcaster/aresetn]",
            "}",
            "foreach channel {0 1 4 5} { connect_bd_net [get_bd_pins {tx_reset_0/peripheral_aresetn}] [get_bd_pins dac${channel}_mute_gate/aresetn] }",
            "foreach channel {2 3 6 7} { connect_bd_net [get_bd_pins {rfdc_dac1_reset/peripheral_aresetn}] [get_bd_pins dac${channel}_mute_gate/aresetn] }",
            "make_bd_intf_pins_external [get_bd_intf_pins {ps_0/DDR}]",
            "make_bd_intf_pins_external [get_bd_intf_pins {ps_0/FIXED_IO}]",
            "foreach intf_name {adc0_clk adc1_clk adc2_clk adc3_clk dac0_clk dac1_clk sysref_in vin0_01 vin0_23 vin1_01 vin1_23 vin2_01 vin2_23 vin3_01 vin3_23 vout00 vout01 vout02 vout03 vout10 vout11 vout12 vout13} {",
            "  make_bd_intf_pins_external [get_bd_intf_pins rfdc_0/$intf_name]",
            "}",
            "assign_bd_address -offset 0xA0000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces {ps_0/Data}] [get_bd_addr_segs {calibrator_control_0/S_AXI/reg0}] -force",
            "assign_bd_address -offset 0xA0040000 -range 0x00040000 -target_address_space [get_bd_addr_spaces {ps_0/Data}] [get_bd_addr_segs {rfdc_0/s_axi/Reg}] -force",
            "assign_bd_address -offset 0xA0080000 -range 0x00010000 -target_address_space [get_bd_addr_spaces {ps_0/Data}] [get_bd_addr_segs {axi_dma_0/S_AXI_LITE/Reg}] -force",
            "assign_bd_address",
            "save_bd_design",
            "validate_bd_design",
            "save_bd_design",
            "set bd_file [get_files [get_property FILE_NAME [get_bd_designs calibrator]]]",
            "set_property synth_checkpoint_mode None $bd_file",
            "generate_target all $bd_file",
            "set wrapper [make_wrapper -files $bd_file -top]",
            "add_files -norecurse $wrapper",
            "set_property top calibrator_wrapper [current_fileset]",
            "synth_design -top calibrator_wrapper -part {" + platform.device_part + "}",
            "write_checkpoint -force [file join $build_dir post_synth.dcp]",
            "report_cdc -details -file [file join $build_dir post_synth_cdc.rpt]",
            "report_drc -file [file join $build_dir post_synth_drc.rpt]",
            "opt_design",
            "place_design",
            "phys_opt_design",
            "route_design",
            "write_checkpoint -force [file join $build_dir post_route.dcp]",
            "report_timing_summary -delay_type max -max_paths 50 -file [file join $build_dir post_route_timing.rpt]",
            "report_timing_summary -delay_type min -max_paths 50 -file [file join $build_dir post_route_hold_timing.rpt]",
            "report_bus_skew -file [file join $build_dir post_route_bus_skew.rpt]",
            "set cdc_report [file join $build_dir post_route_cdc.rpt]",
            "report_cdc -details -file $cdc_report",
            "report_drc -file [file join $build_dir post_route_drc.rpt]",
            "set setup_paths [get_timing_paths -delay_type max -max_paths 1 -slack_lesser_than 0]",
            "if {[llength $setup_paths] != 0} { error {negative setup timing slack remains} }",
            "set hold_paths [get_timing_paths -delay_type min -max_paths 1 -slack_lesser_than 0]",
            "if {[llength $hold_paths] != 0} { error {negative hold timing slack remains} }",
            "set cdc_handle [open $cdc_report r]",
            "set cdc_text [read $cdc_handle]",
            "close $cdc_handle",
            "if {[regexp {CDC-[0-9]+[[:space:]]+Critical[[:space:]]+[1-9][0-9]*} $cdc_text]} { error {CDC Critical violations remain} }",
            "write_bitstream -force [file join $build_dir calibrator.bit]",
            "# Foreground implementation has no impl_1 run for -include_bit; the Python build finalizer adds and verifies this exact bitstream.",
            "write_hw_platform -fixed -force -file [file join $build_dir calibrator_no_bit.xsa]",
            "exit",
        ]
    )
    return "\n".join(lines) + "\n"
