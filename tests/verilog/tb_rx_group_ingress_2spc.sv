`timescale 1ns/1ps

module tb_rx_group_ingress_2spc;
    reg clk_i = 1'b0;
    reg rst_i = 1'b1;
    reg [255:0] adc_i_tdata_i = 256'd0;
    reg [255:0] adc_q_tdata_i = 256'd0;
    reg [7:0] adc_i_tvalid_i = 8'd0;
    reg [7:0] adc_q_tvalid_i = 8'd0;
    wire rx_valid_o;
    wire [127:0] rx_i_lane0_o;
    wire [127:0] rx_q_lane0_o;
    wire [127:0] rx_i_lane1_o;
    wire [127:0] rx_q_lane1_o;
    wire [63:0] sample_base_index_o;
    wire format_error_o;
    reg [127:0] expected_i0 = 128'd0;
    reg [127:0] expected_q0 = 128'd0;
    reg [127:0] expected_i1 = 128'd0;
    reg [127:0] expected_q1 = 128'd0;
    integer channel;

    rx_group_ingress_2spc dut (
        .clk_i(clk_i),
        .rst_i(rst_i),
        .adc_i_tdata_i(adc_i_tdata_i),
        .adc_q_tdata_i(adc_q_tdata_i),
        .adc_i_tvalid_i(adc_i_tvalid_i),
        .adc_q_tvalid_i(adc_q_tvalid_i),
        .rx_valid_o(rx_valid_o),
        .rx_i_lane0_o(rx_i_lane0_o),
        .rx_q_lane0_o(rx_q_lane0_o),
        .rx_i_lane1_o(rx_i_lane1_o),
        .rx_q_lane1_o(rx_q_lane1_o),
        .sample_base_index_o(sample_base_index_o),
        .format_error_o(format_error_o)
    );

    always #2 clk_i = ~clk_i;

    task check_complete_beat(input [63:0] expected_base);
        begin
            @(posedge clk_i);
            #1;
            if (!rx_valid_o) $fatal(1, "complete beat did not assert valid");
            if (sample_base_index_o !== expected_base) $fatal(1, "sample base mismatch");
            if (rx_i_lane0_o !== expected_i0) $fatal(1, "I lane0 mismatch");
            if (rx_q_lane0_o !== expected_q0) $fatal(1, "Q lane0 mismatch");
            if (rx_i_lane1_o !== expected_i1) $fatal(1, "I lane1 mismatch");
            if (rx_q_lane1_o !== expected_q1) $fatal(1, "Q lane1 mismatch");
        end
    endtask

    initial begin
        for (channel = 0; channel < 8; channel = channel + 1) begin
            adc_i_tdata_i[channel*32 +: 16] = 16'h8000 + channel;
            adc_i_tdata_i[channel*32 + 16 +: 16] = 16'd1000 + channel;
            adc_q_tdata_i[channel*32 +: 16] = 16'hffff - channel;
            adc_q_tdata_i[channel*32 + 16 +: 16] = 16'h7fff - channel;
            expected_i0[channel*16 +: 16] = 16'h8000 + channel;
            expected_i1[channel*16 +: 16] = 16'd1000 + channel;
            expected_q0[channel*16 +: 16] = 16'hffff - channel;
            expected_q1[channel*16 +: 16] = 16'h7fff - channel;
        end

        repeat (2) @(posedge clk_i);
        #1 rst_i = 1'b0;
        adc_i_tvalid_i = 8'hff;
        adc_q_tvalid_i = 8'hff;
        check_complete_beat(64'd0);
        check_complete_beat(64'd2);

        adc_q_tvalid_i = 8'h7f;
        @(posedge clk_i);
        #1;
        if (rx_valid_o) $fatal(1, "partial group was accepted");
        if (!format_error_o) $fatal(1, "partial group did not set sticky error");

        adc_q_tvalid_i = 8'hff;
        @(posedge clk_i);
        #1;
        if (rx_valid_o) $fatal(1, "sticky format error did not fail closed");
        if (sample_base_index_o !== 64'd2) $fatal(1, "failed group changed public index");
        if (!format_error_o) $fatal(1, "format error was not sticky");

        rst_i = 1'b1;
        @(posedge clk_i);
        #1 rst_i = 1'b0;
        check_complete_beat(64'd0);

        $display("PASS: rx_group_ingress_2spc Cycle-derived RTL");
        $finish;
    end
endmodule
