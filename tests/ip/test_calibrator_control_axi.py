"""Executable AXI-Lite calibration commit contract, when an HDL simulator exists."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

from rfsoc_pulse_model.common.control_abi import ControlAbi


ROOT = Path(__file__).resolve().parents[2]


class CalibratorControlAxiTest(unittest.TestCase):
    def test_shadow_values_commit_atomically_only_while_stopped(self) -> None:
        rtl = ROOT / "rtl/calibrator_control_axi.sv"
        vivado_bin_text = os.environ.get("CALIBRATOR_VIVADO_BIN")
        vivado_bin = Path(vivado_bin_text) if vivado_bin_text else None
        iverilog = shutil.which("iverilog")
        xvlog = str(vivado_bin / "xvlog.bat") if vivado_bin else shutil.which("xvlog")
        xelab = str(vivado_bin / "xelab.bat") if vivado_bin else shutil.which("xelab")
        xsim = str(vivado_bin / "xsim.bat") if vivado_bin else shutil.which("xsim")
        if vivado_bin and not all(Path(tool).is_file() for tool in (xvlog, xelab, xsim)):
            self.fail(f"CALIBRATOR_VIVADO_BIN does not contain the simulator tools: {vivado_bin}")
        if not vivado_bin and xvlog is not None and "2025.2" not in xvlog.replace("\\", "/"):
            self.skipTest("the simulator on PATH is not Vivado 2025.2")
        if iverilog is None and not all((xvlog, xelab, xsim)):
            self.skipTest("no supported HDL simulator is available")

        testbench = r'''`timescale 1ns/1ps
module testbench;
    reg S_AXI_aclk = 0;
    reg S_AXI_aresetn = 0;
    reg [11:0] S_AXI_awaddr = 0;
    reg [2:0] S_AXI_awprot = 0;
    reg S_AXI_awvalid = 0;
    wire S_AXI_awready;
    reg [31:0] S_AXI_wdata = 0;
    reg [3:0] S_AXI_wstrb = 4'hf;
    reg S_AXI_wvalid = 0;
    wire S_AXI_wready;
    wire [1:0] S_AXI_bresp;
    wire S_AXI_bvalid;
    reg S_AXI_bready = 1;
    reg [11:0] S_AXI_araddr = 0;
    reg [2:0] S_AXI_arprot = 0;
    reg S_AXI_arvalid = 0;
    wire S_AXI_arready;
    wire [31:0] S_AXI_rdata;
    wire [1:0] S_AXI_rresp;
    wire S_AXI_rvalid;
    reg S_AXI_rready = 1;
    reg [31:0] rfdc_status_i = 0;
    reg [31:0] mts_status_i = 0;
    reg [63:0] event_count_i = 0;
    reg [63:0] drop_count_i = 0;
    reg [31:0] stream_errors_i = 0;
    wire acquisition_enable_o;
    wire dac_loopback_enable_o;
    wire dac_mute_o;
    wire [31:0] detect_threshold_o;
    wire [87:0] calibration_integer_delay_o;
    wire [159:0] calibration_fractional_delay_o;
    wire [191:0] calibration_gain_real_o;
    wire [191:0] calibration_gain_imag_o;
    wire [7:0] calibration_flags_o;
    wire [31:0] config_version_o;

    always #5 S_AXI_aclk = ~S_AXI_aclk;
    calibrator_control_axi dut (.*);

    task axi_write(input [11:0] address, input [31:0] value);
        begin
            @(negedge S_AXI_aclk);
            S_AXI_awaddr = address;
            S_AXI_awvalid = 1;
            S_AXI_wdata = value;
            S_AXI_wvalid = 1;
            @(negedge S_AXI_aclk);
            S_AXI_awvalid = 0;
            S_AXI_wvalid = 0;
            wait (S_AXI_bvalid === 1'b1);
            @(negedge S_AXI_aclk);
        end
    endtask

    task axi_read(input [11:0] address, output [31:0] value);
        begin
            @(negedge S_AXI_aclk);
            S_AXI_araddr = address;
            S_AXI_arvalid = 1;
            @(negedge S_AXI_aclk);
            S_AXI_arvalid = 0;
            wait (S_AXI_rvalid === 1'b1);
            value = S_AXI_rdata;
            @(negedge S_AXI_aclk);
        end
    endtask

    reg [31:0] readback;
    initial begin
        repeat (3) @(negedge S_AXI_aclk);
        S_AXI_aresetn = 1;
        repeat (2) @(negedge S_AXI_aclk);
        if (config_version_o !== 0 || calibration_integer_delay_o[10:0] !== 0 ||
            calibration_gain_real_o[23:0] !== 24'h100000 || calibration_flags_o[0] !== 0)
            $fatal(1, "active reset calibration is incorrect");

        axi_write(12'h030, 32'd0);
        if (config_version_o !== 0)
            $fatal(1, "a cleared commit command changed the configuration");

        axi_write(12'h100, 32'd17);
        axi_write(12'h104, 32'h0008_0000);
        axi_write(12'h108, 32'hfff0_0000);
        axi_write(12'h10c, 32'h0000_0000);
        axi_write(12'h110, 32'd1);
        if (calibration_integer_delay_o[10:0] !== 0 || config_version_o !== 0)
            $fatal(1, "shadow write leaked into active calibration");

        axi_write(12'h030, 32'd1);
        if (config_version_o !== 1 || calibration_integer_delay_o[10:0] !== 17 ||
            calibration_fractional_delay_o[19:0] !== 20'h80000 ||
            calibration_gain_real_o[23:0] !== 24'hf00000 || calibration_flags_o[0] !== 1)
            $fatal(1, "stopped commit did not publish one complete snapshot");

        axi_write(12'h008, 32'd1);
        axi_write(12'h100, 32'd18);
        axi_write(12'h030, 32'd1);
        if (config_version_o !== 1 || calibration_integer_delay_o[10:0] !== 17)
            $fatal(1, "running commit changed active calibration");
        axi_read(12'h02c, readback);
        if ((readback & 32'h2) == 0)
            $fatal(1, "running commit did not set its sticky error");

        axi_write(12'h008, 32'd0);
        axi_write(12'h100, 32'd2048);
        axi_read(12'h100, readback);
        if (readback !== 18)
            $fatal(1, "invalid delay changed the shadow value");
        axi_read(12'h02c, readback);
        if ((readback & 32'h4) == 0)
            $fatal(1, "invalid calibration did not set its sticky error");
        $display("CALIBRATOR_CONTROL_AXI_TEST_PASS");
        $finish;
    end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "calibrator_registers.vh").write_text(
                ControlAbi.load_default().emit_verilog_header(), encoding="utf-8"
            )
            tb = work / "calibrator_control_axi_tb.sv"
            tb.write_text(testbench, encoding="utf-8")
            if iverilog is not None:
                executable = work / "calibrator_control_axi_tb"
                subprocess.run(
                    [
                        iverilog,
                        "-g2012",
                        "-I",
                        str(work),
                        "-s",
                        "testbench",
                        "-o",
                        str(executable),
                        str(rtl),
                        str(tb),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                result = subprocess.run(
                    [str(executable)], check=True, capture_output=True, text=True
                )
                self.assertIn("CALIBRATOR_CONTROL_AXI_TEST_PASS", result.stdout)
            else:
                assert xvlog is not None and xelab is not None and xsim is not None
                environment = os.environ.copy()
                environment["XILINX_VIVADO"] = str(Path(xvlog).resolve().parent.parent)
                subprocess.run(
                    [xvlog, "-sv", "-i", str(work), str(rtl), str(tb)],
                    cwd=work,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                snapshot = "calibrator_control_axi_tb"
                subprocess.run(
                    [xelab, "testbench", "-s", snapshot],
                    cwd=work,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                result = subprocess.run(
                    [xsim, snapshot, "-runall"],
                    cwd=work,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("xsim v2025.2", result.stdout)
                self.assertIn("CALIBRATOR_CONTROL_AXI_TEST_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
