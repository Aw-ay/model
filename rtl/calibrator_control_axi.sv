`timescale 1ns/1ps

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
    output reg [31:0] config_version_o
);

    reg [31:0] control_reg;
    reg [31:0] detect_threshold_reg;
    reg [31:0] noise_alpha_reg;
    reg [31:0] range_hold_reg;
    reg [31:0] range_high_reg;
    reg [31:0] range_low_reg;
    reg [31:0] local_error_reg;
    reg [31:0] channel_shadow [0:7][0:7];
    reg [11:0] awaddr_latch;
    reg [31:0] wdata_latch;
    reg [3:0] wstrb_latch;
    reg aw_pending;
    reg w_pending;
    integer channel_index;
    integer word_index;

    assign acquisition_enable_o = control_reg[0];
    assign dac_loopback_enable_o = control_reg[1];
    assign dac_mute_o = control_reg[2];
    assign detect_threshold_o = detect_threshold_reg;
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
        begin
            case (address)
                12'h008: control_reg <= merge_wstrb(control_reg, value, strobes) & 32'h00000007;
                12'h02C: local_error_reg <= local_error_reg & ~value;
                12'h030: begin
                    if (!control_reg[0])
                        config_version_o <= config_version_o + 1'b1;
                    else
                        local_error_reg <= local_error_reg | 32'h00000002;
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
                        channel_shadow[selected_channel][selected_word] <=
                            merge_wstrb(channel_shadow[selected_channel][selected_word], value, strobes);
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

    always @(posedge S_AXI_aclk) begin
        if (!S_AXI_aresetn) begin
            control_reg <= 32'h00000004;
            detect_threshold_reg <= 32'd1000;
            noise_alpha_reg <= 32'd2147484;
            range_hold_reg <= 32'd64;
            range_high_reg <= 32'd58982;
            range_low_reg <= 32'd16384;
            local_error_reg <= 32'd0;
            config_version_o <= 32'd0;
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            S_AXI_bvalid <= 1'b0;
            S_AXI_rvalid <= 1'b0;
            S_AXI_rdata <= 32'd0;
            for (channel_index = 0; channel_index < 8; channel_index = channel_index + 1)
                for (word_index = 0; word_index < 8; word_index = word_index + 1)
                    channel_shadow[channel_index][word_index] <= (word_index == 2) ? 32'h00100000 : 32'd0;
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
