`timescale 1ns/1ps

// Atomic clock-domain transfer for the control plane and counter snapshots.
// xpm_cdc_handshake keeps every payload bit stable until the destination has
// sampled it; the source state machines coalesce rapid writes to the newest
// complete payload without exposing a torn multiword configuration.
module calibrator_control_cdc (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 ctrl_clk CLK" *)
    input  wire          ctrl_clk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME ctrl_resetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 ctrl_resetn RST" *)
    input  wire          ctrl_resetn,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 rx_clk CLK" *)
    input  wire          rx_clk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME rx_resetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rx_resetn RST" *)
    input  wire          rx_resetn,

    input  wire          acquisition_enable_ctrl_i,
    input  wire          dac_loopback_enable_ctrl_i,
    input  wire          dac_mute_ctrl_i,
    input  wire [31:0]   detect_threshold_ctrl_i,
    input  wire [31:0]   config_version_ctrl_i,
    input  wire [87:0]   calibration_integer_delay_ctrl_i,
    input  wire [159:0]  calibration_fractional_delay_ctrl_i,
    input  wire [191:0]  calibration_gain_real_ctrl_i,
    input  wire [191:0]  calibration_gain_imag_ctrl_i,
    input  wire [7:0]    calibration_flags_ctrl_i,
    output reg           acquisition_enable_rx_o,
    output reg           dac_loopback_enable_rx_o,
    output reg           dac_mute_rx_o,
    output reg  [31:0]   detect_threshold_rx_o,
    output reg  [31:0]   config_version_rx_o,
    output reg  [87:0]   calibration_integer_delay_rx_o,
    output reg  [159:0]  calibration_fractional_delay_rx_o,
    output reg  [191:0]  calibration_gain_real_rx_o,
    output reg  [191:0]  calibration_gain_imag_rx_o,
    output reg  [7:0]    calibration_flags_rx_o,

    input  wire [63:0]   event_count_rx_i,
    input  wire [63:0]   drop_count_rx_i,
    input  wire [31:0]   stream_errors_rx_i,
    output reg  [63:0]   event_count_ctrl_o,
    output reg  [63:0]   drop_count_ctrl_o,
    output reg  [31:0]   stream_errors_ctrl_o
);

    wire [34:0] control_input = {detect_threshold_ctrl_i,
                                 dac_mute_ctrl_i,
                                 dac_loopback_enable_ctrl_i,
                                 acquisition_enable_ctrl_i};
    reg  [34:0] control_payload;
    reg  [34:0] control_committed;
    reg         control_send;
    wire        control_received;
    wire [34:0] control_dest_payload;
    wire        control_dest_req;

    wire [671:0] calibration_input = {config_version_ctrl_i,
                                      calibration_flags_ctrl_i,
                                      calibration_gain_imag_ctrl_i,
                                      calibration_gain_real_ctrl_i,
                                      calibration_fractional_delay_ctrl_i,
                                      calibration_integer_delay_ctrl_i};
    reg  [671:0] calibration_payload;
    reg  [671:0] calibration_committed;
    reg          calibration_send;
    wire         calibration_received;
    wire [671:0] calibration_dest_payload;
    wire         calibration_dest_req;

    wire [159:0] status_input = {stream_errors_rx_i,
                                 drop_count_rx_i,
                                 event_count_rx_i};
    reg  [159:0] status_payload;
    reg  [159:0] status_committed;
    reg          status_send;
    wire         status_received;
    wire [159:0] status_dest_payload;
    wire         status_dest_req;

    always @(posedge ctrl_clk) begin
        if (!ctrl_resetn) begin
            control_payload <= 35'd0;
            control_committed <= 35'd0;
            control_send <= 1'b0;
            calibration_payload <= 672'd0;
            calibration_committed <= 672'd0;
            calibration_send <= 1'b0;
            event_count_ctrl_o <= 64'd0;
            drop_count_ctrl_o <= 64'd0;
            stream_errors_ctrl_o <= 32'd0;
        end else begin
            if (control_send) begin
                if (control_received) begin
                    control_send <= 1'b0;
                    control_committed <= control_payload;
                end
            end else if (!control_received && control_input != control_committed) begin
                control_payload <= control_input;
                control_send <= 1'b1;
            end

            if (calibration_send) begin
                if (calibration_received) begin
                    calibration_send <= 1'b0;
                    calibration_committed <= calibration_payload;
                end
            end else if (!calibration_received && calibration_input != calibration_committed) begin
                calibration_payload <= calibration_input;
                calibration_send <= 1'b1;
            end

            if (status_dest_req) begin
                {stream_errors_ctrl_o, drop_count_ctrl_o, event_count_ctrl_o}
                    <= status_dest_payload;
            end
        end
    end

    always @(posedge rx_clk) begin
        if (!rx_resetn) begin
            acquisition_enable_rx_o <= 1'b0;
            dac_loopback_enable_rx_o <= 1'b0;
            dac_mute_rx_o <= 1'b0;
            detect_threshold_rx_o <= 32'd0;
            config_version_rx_o <= 32'd0;
            calibration_integer_delay_rx_o <= 88'd0;
            calibration_fractional_delay_rx_o <= 160'd0;
            calibration_gain_real_rx_o <= 192'd0;
            calibration_gain_imag_rx_o <= 192'd0;
            calibration_flags_rx_o <= 8'd0;
            status_payload <= 160'd0;
            status_committed <= 160'd0;
            status_send <= 1'b0;
        end else begin
            if (control_dest_req) begin
                {detect_threshold_rx_o, dac_mute_rx_o,
                 dac_loopback_enable_rx_o, acquisition_enable_rx_o}
                    <= control_dest_payload;
            end


            if (calibration_dest_req) begin
                {config_version_rx_o, calibration_flags_rx_o,
                 calibration_gain_imag_rx_o, calibration_gain_real_rx_o,
                 calibration_fractional_delay_rx_o, calibration_integer_delay_rx_o}
                    <= calibration_dest_payload;
            end

            if (status_send) begin
                if (status_received) begin
                    status_send <= 1'b0;
                    status_committed <= status_payload;
                end
            end else if (!status_received && status_input != status_committed) begin
                status_payload <= status_input;
                status_send <= 1'b1;
            end
        end
    end

    xpm_cdc_handshake #(
        .DEST_EXT_HSK(0),
        .DEST_SYNC_FF(4),
        .INIT_SYNC_FF(0),
        .SIM_ASSERT_CHK(1),
        .SRC_SYNC_FF(4),
        .WIDTH(35)
    ) control_handshake (
        .src_clk(ctrl_clk),
        .src_in(control_payload),
        .src_send(control_send),
        .src_rcv(control_received),
        .dest_clk(rx_clk),
        .dest_out(control_dest_payload),
        .dest_req(control_dest_req),
        .dest_ack(1'b0)
    );

    xpm_cdc_handshake #(
        .DEST_EXT_HSK(0),
        .DEST_SYNC_FF(4),
        .INIT_SYNC_FF(0),
        .SIM_ASSERT_CHK(1),
        .SRC_SYNC_FF(4),
        .WIDTH(672)
    ) calibration_handshake (
        .src_clk(ctrl_clk),
        .src_in(calibration_payload),
        .src_send(calibration_send),
        .src_rcv(calibration_received),
        .dest_clk(rx_clk),
        .dest_out(calibration_dest_payload),
        .dest_req(calibration_dest_req),
        .dest_ack(1'b0)
    );

    xpm_cdc_handshake #(
        .DEST_EXT_HSK(0),
        .DEST_SYNC_FF(4),
        .INIT_SYNC_FF(0),
        .SIM_ASSERT_CHK(1),
        .SRC_SYNC_FF(4),
        .WIDTH(160)
    ) status_handshake (
        .src_clk(rx_clk),
        .src_in(status_payload),
        .src_send(status_send),
        .src_rcv(status_received),
        .dest_clk(ctrl_clk),
        .dest_out(status_dest_payload),
        .dest_req(status_dest_req),
        .dest_ack(1'b0)
    );

endmodule
