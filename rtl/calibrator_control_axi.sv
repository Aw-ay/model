`timescale 1ns/1ps
`include "calibrator_registers.vh"

module calibrator_control_axi (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *) input wire [11:0] S_AXI_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] S_AXI_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire S_AXI_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire S_AXI_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] S_AXI_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] S_AXI_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire S_AXI_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire S_AXI_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] S_AXI_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg S_AXI_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire S_AXI_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [11:0] S_AXI_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] S_AXI_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire S_AXI_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire S_AXI_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] S_AXI_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] S_AXI_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg S_AXI_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire S_AXI_rready,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ACLK, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET S_AXI_aresetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 S_AXI_ACLK CLK" *) input wire S_AXI_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ARESETN, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 S_AXI_ARESETN RST" *) input wire S_AXI_aresetn,

    input wire [31:0] rfdc_status_i,
    input wire [31:0] mts_status_i,
    input wire [63:0] event_count_i,
    input wire [63:0] drop_count_i,
    input wire [31:0] stream_errors_i,
    output wire acquisition_enable_o,
    output wire dac_loopback_enable_o,
    output wire dac_mute_o,
    output wire [31:0] detect_threshold_o,
    output wire [87:0] calibration_integer_delay_o,
    output wire [159:0] calibration_fractional_delay_o,
    output wire [191:0] calibration_gain_real_o,
    output wire [191:0] calibration_gain_imag_o,
    output wire [7:0] calibration_flags_o,
    output reg [31:0] config_version_o
);

    localparam [31:0] ERROR_COMMIT_WHILE_RUNNING = 32'h00000002;
    localparam [31:0] ERROR_INVALID_CALIBRATION = 32'h00000004;

    reg [31:0] control_reg;
    reg [31:0] detect_threshold_reg;
    reg [31:0] noise_alpha_reg;
    reg [31:0] range_hold_reg;
    reg [31:0] range_high_reg;
    reg [31:0] range_low_reg;
    reg [31:0] local_error_reg;
    reg [31:0] channel_shadow [0:7][0:7];
    reg [31:0] channel_active [0:7][0:4];
    reg [11:0] awaddr_latch;
    reg [31:0] wdata_latch;
    reg [3:0] wstrb_latch;
    reg aw_pending;
    reg w_pending;
    integer channel_index;
    integer word_index;
    genvar output_channel;

    assign acquisition_enable_o = control_reg[0];
    assign dac_loopback_enable_o = control_reg[1];
    assign dac_mute_o = control_reg[2];
    assign detect_threshold_o = detect_threshold_reg;
    generate
        for (output_channel = 0; output_channel < 8; output_channel = output_channel + 1) begin : pack_active_calibration
            assign calibration_integer_delay_o[output_channel * 11 +: 11] =
                channel_active[output_channel][0][10:0];
            assign calibration_fractional_delay_o[output_channel * 20 +: 20] =
                channel_active[output_channel][1][19:0];
            assign calibration_gain_real_o[output_channel * 24 +: 24] =
                channel_active[output_channel][2][23:0];
            assign calibration_gain_imag_o[output_channel * 24 +: 24] =
                channel_active[output_channel][3][23:0];
            assign calibration_flags_o[output_channel] = channel_active[output_channel][4][0];
        end
    endgenerate
    assign S_AXI_awready = !aw_pending && !S_AXI_bvalid;
    assign S_AXI_wready = !w_pending && !S_AXI_bvalid;
    assign S_AXI_bresp = 2'b00;
    assign S_AXI_arready = !S_AXI_rvalid;
    assign S_AXI_rresp = 2'b00;

    function automatic [31:0] merge_wstrb(
        input [31:0] prior,
        input [31:0] value,
        input [3:0] strobes
    );
        integer byte_index;
        begin
            merge_wstrb = prior;
            for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
                if (strobes[byte_index])
                    merge_wstrb[byte_index * 8 +: 8] = value[byte_index * 8 +: 8];
        end
    endfunction

    task automatic write_register(
        input [11:0] address,
        input [31:0] value,
        input [3:0] strobes
    );
        integer selected_channel;
        integer selected_word;
        integer commit_channel;
        integer commit_word;
        reg [31:0] merged_value;
        reg calibration_value_valid;
        begin
            case (address)
                12'h008: control_reg <= merge_wstrb(control_reg, value, strobes) & 32'h00000007;
                12'h02C: local_error_reg <= local_error_reg & ~value;
                12'h030: begin
                    if (!(strobes[0] && value[0])) begin
                        // Writing a cleared command bit is a no-op.
                    end else if (!control_reg[0]) begin
                        for (commit_channel = 0; commit_channel < 8; commit_channel = commit_channel + 1)
                            for (commit_word = 0; commit_word < 5; commit_word = commit_word + 1)
                                channel_active[commit_channel][commit_word] <=
                                    channel_shadow[commit_channel][commit_word];
                        config_version_o <= config_version_o + 1'b1;
                    end else begin
                        local_error_reg <= local_error_reg | ERROR_COMMIT_WHILE_RUNNING;
                    end
                end
                12'h034: detect_threshold_reg <= merge_wstrb(detect_threshold_reg, value, strobes);
                12'h038: noise_alpha_reg <= merge_wstrb(noise_alpha_reg, value, strobes) & 32'h7FFFFFFF;
                12'h03C: range_hold_reg <= merge_wstrb(range_hold_reg, value, strobes) & 32'h0000FFFF;
                12'h040: range_high_reg <= merge_wstrb(range_high_reg, value, strobes) & 32'h0000FFFF;
                12'h044: range_low_reg <= merge_wstrb(range_low_reg, value, strobes) & 32'h0000FFFF;
                default: begin
                    if (address >= 12'h100 && address < 12'h200) begin
                        selected_channel = (address - 12'h100) >> 5;
                        selected_word = address[4:2];
                        merged_value = merge_wstrb(
                            channel_shadow[selected_channel][selected_word], value, strobes
                        );
                        calibration_value_valid = 1'b0;
                        case (selected_word)
                            0: calibration_value_valid = merged_value <= 32'd2047;
                            1: calibration_value_valid = merged_value <= 32'd1048575;
                            2, 3: calibration_value_valid =
                                merged_value[31:24] == {8{merged_value[23]}};
                            4: calibration_value_valid = merged_value[31:1] == 31'd0;
                            default: calibration_value_valid = 1'b0;
                        endcase
                        if (calibration_value_valid)
                            channel_shadow[selected_channel][selected_word] <= merged_value;
                        else
                            local_error_reg <= local_error_reg | ERROR_INVALID_CALIBRATION;
                    end
                end
            endcase
        end
    endtask

    function automatic [31:0] read_register(input [11:0] address);
        integer selected_channel;
        integer selected_word;
        begin
            case (address)
                12'h000: read_register = 32'h43414C31;
                12'h004: read_register = 32'h00010000;
                12'h008: read_register = control_reg;
                12'h00C: read_register = {29'd0, dac_mute_o, dac_loopback_enable_o, acquisition_enable_o};
                12'h010: read_register = rfdc_status_i;
                12'h014: read_register = mts_status_i;
                12'h018: read_register = config_version_o;
                12'h01C: read_register = event_count_i[31:0];
                12'h020: read_register = event_count_i[63:32];
                12'h024: read_register = drop_count_i[31:0];
                12'h028: read_register = drop_count_i[63:32];
                12'h02C: read_register = stream_errors_i | local_error_reg;
                12'h034: read_register = detect_threshold_reg;
                12'h038: read_register = noise_alpha_reg;
                12'h03C: read_register = range_hold_reg;
                12'h040: read_register = range_high_reg;
                12'h044: read_register = range_low_reg;
                default: begin
                    if (address >= 12'h100 && address < 12'h200) begin
                        selected_channel = (address - 12'h100) >> 5;
                        selected_word = address[4:2];
                        read_register = channel_shadow[selected_channel][selected_word];
                    end else begin
                        read_register = 32'd0;
                    end
                end
            endcase
        end
    endfunction

    function automatic [31:0] channel_reset(input integer word);
        begin
            case (word)
                0: channel_reset = `CAL_CHANNEL_INTEGER_DELAY_RESET;
                1: channel_reset = `CAL_CHANNEL_FRACTIONAL_DELAY_Q20_RESET;
                2: channel_reset = `CAL_CHANNEL_GAIN_REAL_RESET;
                3: channel_reset = `CAL_CHANNEL_GAIN_IMAG_RESET;
                4: channel_reset = `CAL_CHANNEL_CALIBRATION_FLAGS_RESET;
                default: channel_reset = 32'd0;
            endcase
        end
    endfunction

    always @(posedge S_AXI_aclk) begin
        if (!S_AXI_aresetn) begin
            control_reg <= `CAL_CONTROL_RESET;
            detect_threshold_reg <= `CAL_DETECT_THRESHOLD_RESET;
            noise_alpha_reg <= `CAL_NOISE_ALPHA_Q31_RESET;
            range_hold_reg <= `CAL_RANGE_HOLD_SAMPLES_RESET;
            range_high_reg <= `CAL_RANGE_HIGH_WATER_Q16_RESET;
            range_low_reg <= `CAL_RANGE_LOW_WATER_Q16_RESET;
            local_error_reg <= `CAL_STREAM_ERRORS_RESET;
            config_version_o <= `CAL_CONFIG_VERSION_RESET;
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            S_AXI_bvalid <= 1'b0;
            S_AXI_rvalid <= 1'b0;
            S_AXI_rdata <= 32'd0;
            for (channel_index = 0; channel_index < 8; channel_index = channel_index + 1)
                for (word_index = 0; word_index < 8; word_index = word_index + 1) begin
                    channel_shadow[channel_index][word_index] <= channel_reset(word_index);
                    if (word_index < 5)
                        channel_active[channel_index][word_index] <= channel_reset(word_index);
                end
        end else begin
            if (S_AXI_awready && S_AXI_awvalid) begin
                awaddr_latch <= S_AXI_awaddr;
                aw_pending <= 1'b1;
            end
            if (S_AXI_wready && S_AXI_wvalid) begin
                wdata_latch <= S_AXI_wdata;
                wstrb_latch <= S_AXI_wstrb;
                w_pending <= 1'b1;
            end
            if (aw_pending && w_pending && !S_AXI_bvalid) begin
                write_register(awaddr_latch, wdata_latch, wstrb_latch);
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                S_AXI_bvalid <= 1'b1;
            end else if (S_AXI_bvalid && S_AXI_bready) begin
                S_AXI_bvalid <= 1'b0;
            end

            if (S_AXI_arready && S_AXI_arvalid) begin
                S_AXI_rdata <= read_register(S_AXI_araddr);
                S_AXI_rvalid <= 1'b1;
            end else if (S_AXI_rvalid && S_AXI_rready) begin
                S_AXI_rvalid <= 1'b0;
            end
        end
    end

endmodule
