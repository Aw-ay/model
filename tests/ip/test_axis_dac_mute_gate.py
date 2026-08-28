"""Executable AXIS safety-gate contract, when an HDL simulator is available."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AxisDacMuteGateTest(unittest.TestCase):
    def test_reset_mute_and_disabled_loopback_are_safe(self) -> None:
        rtl = ROOT / "rtl/axis_dac_mute_gate.sv"
        self.assertTrue(rtl.is_file(), "the DAC AXIS safety gate must be a tracked RTL source")
        iverilog = shutil.which("iverilog")
        xvlog = shutil.which("xvlog")
        xelab = shutil.which("xelab")
        xsim = shutil.which("xsim")
        if iverilog is None and not all((xvlog, xelab, xsim)):
            self.skipTest("no supported HDL simulator is available")
        testbench = r'''`timescale 1ns/1ps
module testbench;
    reg aclk = 0;
    reg aresetn = 0;
    reg loopback_enable_i = 0;
    reg mute_i = 0;
    reg [63:0] s_axis_tdata = 64'h0123_4567_89ab_cdef;
    reg s_axis_tvalid = 1;
    wire s_axis_tready;
    wire [63:0] m_axis_tdata;
    wire m_axis_tvalid;
    reg m_axis_tready = 0;
    always #5 aclk = ~aclk;
    axis_dac_mute_gate dut (.*);
    task expect_safe;
        begin
            #1;
            if (m_axis_tvalid !== 0 || m_axis_tdata !== 0 || s_axis_tready !== 1) $fatal(1, "unsafe DAC AXIS output");
        end
    endtask
    initial begin
        expect_safe();
        aresetn = 1;
        loopback_enable_i = 1;
        mute_i = 0;
        #1;
        if (m_axis_tvalid !== 1 || m_axis_tdata !== 64'h0123_4567_89ab_cdef || s_axis_tready !== 0) $fatal(1, "enabled path did not preserve backpressure");
        // A control change while a beat is stalled must immediately enter the
        // documented drop-safe state and must not retain a stale output beat.
        @(negedge aclk);
        mute_i = 1;
        expect_safe();
        s_axis_tdata = 64'hfedc_ba98_7654_3210;
        @(negedge aclk);
        mute_i = 0;
        #1;
        if (m_axis_tvalid !== 1 || m_axis_tdata !== 64'hfedc_ba98_7654_3210 || s_axis_tready !== 0) $fatal(1, "unmute replayed a stale stalled beat");
        @(negedge aclk);
        loopback_enable_i = 0;
        expect_safe();
        @(negedge aclk);
        loopback_enable_i = 1;
        #1;
        if (m_axis_tvalid !== 1 || m_axis_tdata !== 64'hfedc_ba98_7654_3210 || s_axis_tready !== 0) $fatal(1, "loopback re-enable did not restore live input");
        m_axis_tready = 1;
        #1;
        if (s_axis_tready !== 1) $fatal(1, "enabled path did not propagate ready");
        mute_i = 1;
        expect_safe();
        mute_i = 0;
        loopback_enable_i = 0;
        expect_safe();
        $finish;
    end
endmodule
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            tb = work / "axis_dac_mute_gate_tb.sv"
            executable = work / "axis_dac_mute_gate_tb"
            tb.write_text(testbench, encoding="utf-8")
            if iverilog is not None:
                subprocess.run(
                    [iverilog, "-g2012", "-s", "testbench", "-o", str(executable), str(rtl), str(tb)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run([str(executable)], check=True, capture_output=True, text=True)
            else:
                assert xvlog is not None and xelab is not None and xsim is not None
                snapshot = "axis_dac_mute_gate_tb"
                subprocess.run([xvlog, "-sv", str(rtl), str(tb)], cwd=work, check=True, capture_output=True, text=True)
                subprocess.run([xelab, "testbench", "-s", snapshot], cwd=work, check=True, capture_output=True, text=True)
                subprocess.run([xsim, snapshot, "-runall"], cwd=work, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
