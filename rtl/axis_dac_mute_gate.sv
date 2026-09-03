`timescale 1ns/1ps

// AXI4-Stream safety gate for one RFDC DAC fabric input.  The control bits
// arrive through calibrator_control_cdc in this same stream-clock domain.  A
// disabled or reset gate consumes input beats but never presents a valid DAC
// transfer; its data pins are held at zero as an additional electrical-safe
// invariant.
module axis_dac_mute_gate (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF s_axis:m_axis, ASSOCIATED_RESET aresetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    input  wire          aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    input  wire          aresetn,
    input  wire          loopback_enable_i,
    input  wire          mute_i,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TDATA" *) input  wire [63:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TVALID" *) input  wire        s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TREADY" *) output wire        s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TDATA" *) output wire [63:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TVALID" *) output wire        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TREADY" *) input  wire        m_axis_tready
);

    wire stream_enabled = aresetn && loopback_enable_i && !mute_i;

    assign m_axis_tdata = stream_enabled ? s_axis_tdata : 64'd0;
    assign m_axis_tvalid = stream_enabled ? s_axis_tvalid : 1'b0;
    // Consume only the intentionally muted stream.  When enabled, preserve
    // normal AXIS backpressure and therefore the ordering of emitted beats.
    assign s_axis_tready = stream_enabled ? m_axis_tready : 1'b1;

endmodule
