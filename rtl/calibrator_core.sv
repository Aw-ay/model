`timescale 1ns/1ps

module calibrator_core (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME rx_clk, ASSOCIATED_BUSIF s00_axis:s01_axis:s02_axis:s03_axis:s04_axis:s05_axis:s06_axis:s07_axis:m_event_axis, ASSOCIATED_RESET rx_resetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 rx_clk CLK" *)
    input  wire          rx_clk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME rx_resetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rx_resetn RST" *)
    input  wire          rx_resetn,
    input  wire          acquisition_enable_i,
    input  wire [31:0]   detect_threshold_i,
    input  wire [31:0]   config_version_i,
    input  wire [87:0]   calibration_integer_delay_i,
    input  wire [159:0]  calibration_fractional_delay_i,
    input  wire [191:0]  calibration_gain_real_i,
    input  wire [191:0]  calibration_gain_imag_i,
    input  wire [7:0]    calibration_flags_i,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s00_axis TDATA" *) input  wire [63:0]  s00_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s00_axis TVALID" *) input  wire         s00_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s00_axis TREADY" *) output wire         s00_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s01_axis TDATA" *) input  wire [63:0]  s01_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s01_axis TVALID" *) input  wire         s01_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s01_axis TREADY" *) output wire         s01_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s02_axis TDATA" *) input  wire [63:0]  s02_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s02_axis TVALID" *) input  wire         s02_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s02_axis TREADY" *) output wire         s02_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s03_axis TDATA" *) input  wire [63:0]  s03_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s03_axis TVALID" *) input  wire         s03_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s03_axis TREADY" *) output wire         s03_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s04_axis TDATA" *) input  wire [63:0]  s04_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s04_axis TVALID" *) input  wire         s04_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s04_axis TREADY" *) output wire         s04_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s05_axis TDATA" *) input  wire [63:0]  s05_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s05_axis TVALID" *) input  wire         s05_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s05_axis TREADY" *) output wire         s05_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s06_axis TDATA" *) input  wire [63:0]  s06_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s06_axis TVALID" *) input  wire         s06_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s06_axis TREADY" *) output wire         s06_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s07_axis TDATA" *) input  wire [63:0]  s07_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s07_axis TVALID" *) input  wire         s07_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s07_axis TREADY" *) output wire         s07_axis_tready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_event_axis TDATA" *) output reg  [127:0] m_event_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_event_axis TKEEP" *) output reg  [15:0]  m_event_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_event_axis TLAST" *) output reg          m_event_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_event_axis TVALID" *) output wire         m_event_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_event_axis TREADY" *) input  wire         m_event_axis_tready,

    output reg  [63:0]   event_count_o,
    output reg  [63:0]   drop_count_o,
    output reg  [31:0]   stream_errors_o
);

    localparam [1:0] STATE_IDLE = 2'd0;
    localparam [1:0] STATE_CAPTURE = 2'd1;
    localparam [1:0] STATE_STREAM = 2'd2;
    localparam [31:0] ERROR_EVENT_BUSY = 32'h00000001;
    localparam [31:0] DMA_MAGIC = 32'h31414D44;

    wire [63:0] axis_data [0:7];
    wire [7:0] axis_valid;
    reg [31:0] history [0:7][0:31];
    reg [31:0] event_iq [0:31];
    reg [4:0] history_write_ptr;
    reg [1:0] state;
    reg [3:0] event_channel;
    reg [1:0] event_range;
    reg [7:0] event_polarization;
    reg [7:0] event_flags;
    reg [63:0] event_toa;
    reg [31:0] event_width;
    reg [31:0] event_peak;
    reg [31:0] event_mean;
    reg [31:0] event_frequency;
    reg [31:0] event_channel_mask;
    reg [4:0] event_sample_ptr;
    reg [31:0] active_config_version;
    reg [31:0] active_event_id;
    reg [31:0] next_event_id;
    reg [63:0] sample_counter;
    reg [3:0] stream_index;

    // Fully pipelined DSP chain: registered I/Q inputs, multiplier MREG,
    // multiplier PREG, power sum, then four-way group priority.
    reg signed [15:0] detector_i_pipe [0:15];
    reg signed [15:0] detector_q_pipe [0:15];
    (* use_dsp = "yes" *) reg [31:0] power_i_mult [0:15];
    (* use_dsp = "yes" *) reg [31:0] power_q_mult [0:15];
    (* use_dsp = "yes" *) reg [31:0] power_i_pipe [0:15];
    (* use_dsp = "yes" *) reg [31:0] power_q_pipe [0:15];
    reg [31:0] power_i_sum_input [0:15];
    reg [31:0] power_q_sum_input [0:15];
    reg [32:0] power_sum_pipe [0:15];
    reg [15:0] detector_valid_pipe;
    reg [15:0] power_valid_mult;
    reg [15:0] power_valid_product;
    reg [15:0] power_valid_sum_input;
    reg [15:0] power_valid_pipe;
    reg [4:0] detector_ptr_pipe [0:15];
    reg [4:0] power_ptr_mult [0:15];
    reg [4:0] power_ptr_product [0:15];
    reg [4:0] power_ptr_sum_input [0:15];
    reg [4:0] power_ptr_pipe [0:15];
    reg [63:0] detector_toa_pipe [0:15];
    reg [63:0] power_toa_mult [0:15];
    reg [63:0] power_toa_product [0:15];
    reg [63:0] power_toa_sum_input [0:15];
    reg [63:0] power_toa_pipe [0:15];

    reg group_valid_next [0:3];
    reg [2:0] group_channel_next [0:3];
    reg group_lane_next [0:3];
    reg [32:0] group_power_next [0:3];
    reg [4:0] group_ptr_next [0:3];
    reg [63:0] group_toa_next [0:3];
    reg group_valid [0:3];
    reg [2:0] group_channel [0:3];
    reg group_lane [0:3];
    reg [32:0] group_power [0:3];
    reg [4:0] group_ptr [0:3];
    reg [63:0] group_toa [0:3];

    reg hit_valid;
    reg [2:0] hit_channel;
    reg hit_lane;
    reg [32:0] hit_power;
    reg [4:0] hit_sample_ptr;
    reg [63:0] hit_toa;
    integer group_index;
    integer lane_index;
    integer reset_channel;
    integer reset_sample;
    integer history_index;
    integer stream_sample_base;

    assign axis_data[0] = s00_axis_tdata;
    assign axis_data[1] = s01_axis_tdata;
    assign axis_data[2] = s02_axis_tdata;
    assign axis_data[3] = s03_axis_tdata;
    assign axis_data[4] = s04_axis_tdata;
    assign axis_data[5] = s05_axis_tdata;
    assign axis_data[6] = s06_axis_tdata;
    assign axis_data[7] = s07_axis_tdata;
    assign axis_valid = {s07_axis_tvalid, s06_axis_tvalid, s05_axis_tvalid, s04_axis_tvalid,
                         s03_axis_tvalid, s02_axis_tvalid, s01_axis_tvalid, s00_axis_tvalid};

    // The RFDC boundary is deliberately non-backpressuring, including reset/mute/error states.
    assign s00_axis_tready = 1'b1;
    assign s01_axis_tready = 1'b1;
    assign s02_axis_tready = 1'b1;
    assign s03_axis_tready = 1'b1;
    assign s04_axis_tready = 1'b1;
    assign s05_axis_tready = 1'b1;
    assign s06_axis_tready = 1'b1;
    assign s07_axis_tready = 1'b1;
    assign m_event_axis_tvalid = (state == STATE_STREAM);

    // Select the first lane in each four-lane group.  Channel then lane order
    // implements the global (ToA, channel) tie break for a shared sample beat.
    always @* begin
        for (group_index = 0; group_index < 4; group_index = group_index + 1) begin
            group_valid_next[group_index] = 1'b0;
            group_channel_next[group_index] = 3'd0;
            group_lane_next[group_index] = 1'b0;
            group_power_next[group_index] = 33'd0;
            group_ptr_next[group_index] = 5'd0;
            group_toa_next[group_index] = 64'd0;
            for (lane_index = 0; lane_index < 4; lane_index = lane_index + 1) begin
                if (!group_valid_next[group_index] &&
                    power_valid_pipe[group_index * 4 + lane_index] &&
                    power_sum_pipe[group_index * 4 + lane_index] >= {1'b0, detect_threshold_i}) begin
                    group_valid_next[group_index] = 1'b1;
                    group_channel_next[group_index] = (group_index * 4 + lane_index) >> 1;
                    group_lane_next[group_index] = lane_index[0];
                    group_power_next[group_index] = power_sum_pipe[group_index * 4 + lane_index];
                    group_ptr_next[group_index] = power_ptr_pipe[group_index * 4 + lane_index];
                    group_toa_next[group_index] = power_toa_pipe[group_index * 4 + lane_index];
                end
            end
        end
    end

    always @* begin
        hit_valid = 1'b0;
        hit_channel = 3'd0;
        hit_lane = 1'b0;
        hit_power = 33'd0;
        hit_sample_ptr = 5'd0;
        hit_toa = 64'd0;
        for (group_index = 0; group_index < 4; group_index = group_index + 1) begin
            if (!hit_valid && group_valid[group_index]) begin
                hit_valid = 1'b1;
                hit_channel = group_channel[group_index];
                hit_lane = group_lane[group_index];
                hit_power = group_power[group_index];
                hit_sample_ptr = group_ptr[group_index];
                hit_toa = group_toa[group_index];
            end
        end
    end

    always @* begin
        m_event_axis_tdata = 128'd0;
        m_event_axis_tkeep = 16'hFFFF;
        m_event_axis_tlast = 1'b0;
        stream_sample_base = 0;
        case (stream_index)
            4'd0: m_event_axis_tdata = {active_config_version, active_event_id, 32'd192, DMA_MAGIC};
            4'd1: m_event_axis_tdata = {16'd0, 16'd1, event_channel_mask, event_toa};
            4'd2: m_event_axis_tdata = {event_width, event_toa, event_flags,
                                        event_polarization, {6'd0, event_range},
                                        {4'd0, event_channel}};
            4'd3: m_event_axis_tdata = {16'd0, 16'd32, event_frequency,
                                        event_mean, event_peak};
            4'd4, 4'd5, 4'd6, 4'd7, 4'd8, 4'd9, 4'd10, 4'd11: begin
                stream_sample_base = (stream_index - 4) * 4;
                m_event_axis_tdata = {event_iq[stream_sample_base + 3],
                                      event_iq[stream_sample_base + 2],
                                      event_iq[stream_sample_base + 1],
                                      event_iq[stream_sample_base]};
                if (stream_index == 11)
                    m_event_axis_tlast = 1'b1;
            end
            default: begin
                m_event_axis_tkeep = 16'd0;
                m_event_axis_tlast = 1'b1;
            end
        endcase
    end

    always @(posedge rx_clk) begin
        if (!rx_resetn) begin
            history_write_ptr <= 5'd0;
            state <= STATE_IDLE;
            event_count_o <= 64'd0;
            drop_count_o <= 64'd0;
            stream_errors_o <= 32'd0;
            sample_counter <= 64'd0;
            stream_index <= 4'd0;
            next_event_id <= 32'd1;
            active_event_id <= 32'd0;
            active_config_version <= 32'd0;
            event_sample_ptr <= 5'd0;
            for (reset_channel = 0; reset_channel < 8; reset_channel = reset_channel + 1)
                for (reset_sample = 0; reset_sample < 32; reset_sample = reset_sample + 1)
                    history[reset_channel][reset_sample] <= 32'd0;
            for (reset_sample = 0; reset_sample < 32; reset_sample = reset_sample + 1)
                event_iq[reset_sample] <= 32'd0;
            detector_valid_pipe <= 16'd0;
            power_valid_mult <= 16'd0;
            power_valid_product <= 16'd0;
            power_valid_sum_input <= 16'd0;
            power_valid_pipe <= 16'd0;
            for (reset_sample = 0; reset_sample < 16; reset_sample = reset_sample + 1) begin
                detector_i_pipe[reset_sample] <= 16'sd0;
                detector_q_pipe[reset_sample] <= 16'sd0;
                power_i_mult[reset_sample] <= 32'd0;
                power_q_mult[reset_sample] <= 32'd0;
                power_i_pipe[reset_sample] <= 32'd0;
                power_q_pipe[reset_sample] <= 32'd0;
                power_i_sum_input[reset_sample] <= 32'd0;
                power_q_sum_input[reset_sample] <= 32'd0;
                power_sum_pipe[reset_sample] <= 33'd0;
                detector_ptr_pipe[reset_sample] <= 5'd0;
                power_ptr_mult[reset_sample] <= 5'd0;
                power_ptr_product[reset_sample] <= 5'd0;
                power_ptr_sum_input[reset_sample] <= 5'd0;
                power_ptr_pipe[reset_sample] <= 5'd0;
                detector_toa_pipe[reset_sample] <= 64'd0;
                power_toa_mult[reset_sample] <= 64'd0;
                power_toa_product[reset_sample] <= 64'd0;
                power_toa_sum_input[reset_sample] <= 64'd0;
                power_toa_pipe[reset_sample] <= 64'd0;
            end
            for (reset_sample = 0; reset_sample < 4; reset_sample = reset_sample + 1) begin
                group_valid[reset_sample] <= 1'b0;
                group_channel[reset_sample] <= 3'd0;
                group_lane[reset_sample] <= 1'b0;
                group_power[reset_sample] <= 33'd0;
                group_ptr[reset_sample] <= 5'd0;
                group_toa[reset_sample] <= 64'd0;
            end
        end else begin
            for (reset_channel = 0; reset_channel < 8; reset_channel = reset_channel + 1) begin
                detector_i_pipe[reset_channel * 2] <= $signed(axis_data[reset_channel][15:0]);
                detector_q_pipe[reset_channel * 2] <= $signed(axis_data[reset_channel][31:16]);
                detector_i_pipe[reset_channel * 2 + 1] <= $signed(axis_data[reset_channel][47:32]);
                detector_q_pipe[reset_channel * 2 + 1] <= $signed(axis_data[reset_channel][63:48]);
                detector_valid_pipe[reset_channel * 2] <= &axis_valid;
                detector_valid_pipe[reset_channel * 2 + 1] <= &axis_valid;
                detector_ptr_pipe[reset_channel * 2] <= history_write_ptr;
                detector_ptr_pipe[reset_channel * 2 + 1] <= history_write_ptr + 1'b1;
                detector_toa_pipe[reset_channel * 2] <= sample_counter;
                detector_toa_pipe[reset_channel * 2 + 1] <= sample_counter + 1'b1;
            end
            for (reset_sample = 0; reset_sample < 16; reset_sample = reset_sample + 1) begin
                power_i_mult[reset_sample] <= detector_i_pipe[reset_sample] * detector_i_pipe[reset_sample];
                power_q_mult[reset_sample] <= detector_q_pipe[reset_sample] * detector_q_pipe[reset_sample];
                power_i_pipe[reset_sample] <= power_i_mult[reset_sample];
                power_q_pipe[reset_sample] <= power_q_mult[reset_sample];
                power_i_sum_input[reset_sample] <= power_i_pipe[reset_sample];
                power_q_sum_input[reset_sample] <= power_q_pipe[reset_sample];
                power_sum_pipe[reset_sample] <= {1'b0, power_i_sum_input[reset_sample]} +
                                                {1'b0, power_q_sum_input[reset_sample]};
                power_valid_mult[reset_sample] <= detector_valid_pipe[reset_sample];
                power_valid_product[reset_sample] <= power_valid_mult[reset_sample];
                power_valid_sum_input[reset_sample] <= power_valid_product[reset_sample];
                power_valid_pipe[reset_sample] <= power_valid_sum_input[reset_sample];
                power_ptr_mult[reset_sample] <= detector_ptr_pipe[reset_sample];
                power_ptr_product[reset_sample] <= power_ptr_mult[reset_sample];
                power_ptr_sum_input[reset_sample] <= power_ptr_product[reset_sample];
                power_ptr_pipe[reset_sample] <= power_ptr_sum_input[reset_sample];
                power_toa_mult[reset_sample] <= detector_toa_pipe[reset_sample];
                power_toa_product[reset_sample] <= power_toa_mult[reset_sample];
                power_toa_sum_input[reset_sample] <= power_toa_product[reset_sample];
                power_toa_pipe[reset_sample] <= power_toa_sum_input[reset_sample];
            end
            for (reset_sample = 0; reset_sample < 4; reset_sample = reset_sample + 1) begin
                group_valid[reset_sample] <= group_valid_next[reset_sample];
                group_channel[reset_sample] <= group_channel_next[reset_sample];
                group_lane[reset_sample] <= group_lane_next[reset_sample];
                group_power[reset_sample] <= group_power_next[reset_sample];
                group_ptr[reset_sample] <= group_ptr_next[reset_sample];
                group_toa[reset_sample] <= group_toa_next[reset_sample];
            end

            if (&axis_valid) begin
                for (reset_channel = 0; reset_channel < 8; reset_channel = reset_channel + 1) begin
                    history[reset_channel][history_write_ptr] <= axis_data[reset_channel][31:0];
                    history[reset_channel][history_write_ptr + 1'b1] <= axis_data[reset_channel][63:32];
                end
                history_write_ptr <= history_write_ptr + 2'd2;
                sample_counter <= sample_counter + 2'd2;
            end

            if (state != STATE_IDLE && hit_valid && acquisition_enable_i) begin
                drop_count_o <= drop_count_o + 1'b1;
                stream_errors_o <= stream_errors_o | ERROR_EVENT_BUSY;
            end

            case (state)
                STATE_IDLE: begin
                    stream_index <= 4'd0;
                    if (acquisition_enable_i && hit_valid && (&axis_valid)) begin
                        event_channel <= {1'b0, hit_channel};
                        event_range <= (hit_channel == 3 || hit_channel == 7) ? 2'd3 :
                                       ((hit_channel % 4) > 2 ? 2'd2 : (hit_channel % 4));
                        event_polarization <= (hit_channel < 4) ? 8'd0 : 8'd1;
                        event_flags <= 8'd0;
                        event_toa <= hit_toa;
                        event_width <= 32'd1;
                        event_peak <= hit_power[32] ? 32'hFFFFFFFF : hit_power[31:0];
                        event_mean <= hit_power[32] ? 32'hFFFFFFFF : hit_power[31:0];
                        event_frequency <= 32'd0;
                        event_channel_mask <= 32'd1 << hit_channel;
                        event_sample_ptr <= hit_sample_ptr;
                        active_config_version <= config_version_i;
                        active_event_id <= next_event_id;
                        next_event_id <= next_event_id + 1'b1;
                        state <= STATE_CAPTURE;
                    end
                end
                STATE_CAPTURE: begin
                    if (sample_counter >= event_toa + 16) begin
                        for (history_index = 0; history_index < 16; history_index = history_index + 1) begin
                            event_iq[history_index] <=
                                history[event_channel[2:0]][(event_sample_ptr + 16 + history_index) % 32];
                            event_iq[16 + history_index] <=
                                history[event_channel[2:0]][(event_sample_ptr + history_index) % 32];
                        end
                        state <= STATE_STREAM;
                        stream_index <= 4'd0;
                    end
                end
                STATE_STREAM: begin
                    if (m_event_axis_tready) begin
                        if (stream_index == 11) begin
                            event_count_o <= event_count_o + 1'b1;
                            state <= STATE_IDLE;
                            stream_index <= 4'd0;
                        end else begin
                            stream_index <= stream_index + 1'b1;
                        end
                    end
                end
                default: state <= STATE_IDLE;
            endcase
        end
    end

endmodule
