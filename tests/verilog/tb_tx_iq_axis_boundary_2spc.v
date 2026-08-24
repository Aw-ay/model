`timescale 1ns/1ps

module tb_tx_iq_axis_boundary_2spc;
    reg clk_i = 1'b0;
    reg rst_i = 1'b1;
    reg tx_enable_i = 1'b0;
    reg clear_status_i = 1'b0;
    reg source_valid_i = 1'b0;
    reg [127:0] dac_i_lane0_i = 128'd0;
    reg [127:0] dac_q_lane0_i = 128'd0;
    reg [127:0] dac_i_lane1_i = 128'd0;
    reg [127:0] dac_q_lane1_i = 128'd0;
    reg [7:0] dac_tready_i = 8'd0;
    wire [511:0] dac_tdata_o;
    wire [7:0] dac_tvalid_o;
    wire source_advance_o;
    wire stream_active_o;
    wire underrun_o;

    tx_iq_axis_boundary_2spc dut (
        .clk_i(clk_i),
        .rst_i(rst_i),
        .tx_enable_i(tx_enable_i),
        .clear_status_i(clear_status_i),
        .source_valid_i(source_valid_i),
        .dac_i_lane0_i(dac_i_lane0_i),
        .dac_q_lane0_i(dac_q_lane0_i),
        .dac_i_lane1_i(dac_i_lane1_i),
        .dac_q_lane1_i(dac_q_lane1_i),
        .dac_tready_i(dac_tready_i),
        .dac_tdata_o(dac_tdata_o),
        .dac_tvalid_o(dac_tvalid_o),
        .source_advance_o(source_advance_o),
        .stream_active_o(stream_active_o),
        .underrun_o(underrun_o)
    );

    always #2 clk_i = ~clk_i;

    task fail;
        input [8*80-1:0] message;
        begin
            $display("FAIL: %0s", message);
            $finish;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk_i);
        #1;
        rst_i = 1'b0;
        tx_enable_i = 1'b1;
        dac_tready_i = 8'hff;
        #1;
        if (dac_tvalid_o !== 8'hff) fail("TVALID must be high after reset");
        if (underrun_o !== 1'b0) fail("waiting before start is not underrun");

        dac_i_lane0_i[15:0] = 16'h8000;
        dac_q_lane0_i[15:0] = 16'hffff;
        dac_i_lane1_i[15:0] = 16'h3039;
        dac_q_lane1_i[15:0] = 16'h7fff;
        dac_i_lane0_i[127:112] = 16'h0007;
        dac_q_lane0_i[127:112] = 16'h0011;
        dac_i_lane1_i[127:112] = 16'h001b;
        dac_q_lane1_i[127:112] = 16'h0025;
        source_valid_i = 1'b1;
        #1;
        if (source_advance_o !== 1'b1) fail("complete group did not advance");
        if (dac_tdata_o[63:0] !== 64'h7fff3039ffff8000)
            fail("channel zero I/Q packing mismatch");
        if (dac_tdata_o[511:448] !== 64'h0025001b00110007)
            fail("channel seven I/Q packing mismatch");
        @(posedge clk_i);
        #1;
        if (stream_active_o !== 1'b1) fail("stream did not enter active state");

        dac_tready_i = 8'hfe;
        #1;
        if (dac_tdata_o !== 512'd0) fail("ready loss did not drive zero");
        if (source_advance_o !== 1'b0) fail("ready loss advanced the source");
        @(posedge clk_i);
        #1;
        if (underrun_o !== 1'b1) fail("ready loss did not latch underrun");
        if (stream_active_o !== 1'b0) fail("ready loss did not fail closed");

        dac_tready_i = 8'hff;
        #1;
        if (source_advance_o !== 1'b0) fail("faulted stream silently resumed");
        if (dac_tdata_o !== 512'd0) fail("faulted stream emitted data");

        tx_enable_i = 1'b0;
        clear_status_i = 1'b1;
        @(posedge clk_i);
        #1;
        if (underrun_o !== 1'b0) fail("disabled clear did not rearm status");

        $display("PASS: tx_iq_axis_boundary_2spc");
        $finish;
    end
endmodule
