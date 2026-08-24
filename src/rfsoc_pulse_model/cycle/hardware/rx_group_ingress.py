from __future__ import annotations

from ...common.config import ModelConfig
from ...common.types import RfdcAdcClockingMode
from ..dsl.expr import ConstExpr, concat, mux
from ..dsl.module import RTLModule


class RxGroupIngress2Spc(RTLModule):
    """Register and unpack eight RFDC I/Q stream pairs at two samples/cycle.

    There is deliberately no ready input. Before acquisition is enabled, RFDC
    startup valid patterns are ignored. Once enabled, a complete 16-stream
    valid group is accepted atomically and any idle or partial group fails
    closed with a sticky error.
    """

    module_name = "rx_group_ingress_2spc"
    latency_cycles = 1
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        if config.rfdc_complex_samples_per_cycle != 2:
            raise ValueError("RxGroupIngress2Spc requires exactly two samples/cycle")
        if config.adc_channels != 8:
            raise ValueError("RxGroupIngress2Spc requires eight ADC channels")
        if config.rfdc_axis.adc_component_stream_width_bits != 32:
            raise ValueError("RxGroupIngress2Spc requires 32-bit I/Q component words")
        if (
            config.rfdc_adc_clocking_mode
            != RfdcAdcClockingMode.COMMON_PL_CLOCK_MTS
        ):
            raise ValueError(
                "RxGroupIngress2Spc requires the common PL clock + MTS mode; "
                "per-tile CDC requires a different ingress architecture"
            )
        self.config = config

        self.clk_i = self.input("clk_i")
        self.rst_i = self.input("rst_i")
        self.reset_signal = self.rst_i
        self.acquisition_enable_i = self.input("acquisition_enable_i")
        self.adc_i_tdata_i = self.input("adc_i_tdata_i", 8 * 32)
        self.adc_q_tdata_i = self.input("adc_q_tdata_i", 8 * 32)
        self.adc_i_tvalid_i = self.input("adc_i_tvalid_i", 8)
        self.adc_q_tvalid_i = self.input("adc_q_tvalid_i", 8)

        self.rx_valid_o = self.output_reg("rx_valid_o")
        self.rx_i_lane0_o = self.output_reg("rx_i_lane0_o", 8 * 16)
        self.rx_q_lane0_o = self.output_reg("rx_q_lane0_o", 8 * 16)
        self.rx_i_lane1_o = self.output_reg("rx_i_lane1_o", 8 * 16)
        self.rx_q_lane1_o = self.output_reg("rx_q_lane1_o", 8 * 16)
        self.sample_base_index_o = self.output_reg("sample_base_index_o", 64)
        self.stream_active_o = self.output_reg("stream_active_o")
        self.format_error_o = self.output_reg("format_error_o")
        self.gap_error_o = self.output_reg("gap_error_o")

        self.sample_counter = self.reg("sample_counter", 64)
        self.next_valid = self.wire("next_valid")
        self.next_i_lane0 = self.wire("next_i_lane0", 128)
        self.next_q_lane0 = self.wire("next_q_lane0", 128)
        self.next_i_lane1 = self.wire("next_i_lane1", 128)
        self.next_q_lane1 = self.wire("next_q_lane1", 128)
        self.next_sample_base = self.wire("next_sample_base", 64)
        self.next_sample_counter = self.wire("next_sample_counter", 64)
        self.next_stream_active = self.wire("next_stream_active")
        self.next_format_error = self.wire("next_format_error")
        self.next_gap_error = self.wire("next_gap_error")

    @staticmethod
    def _lane(data, lane: int):
        parts = []
        for channel in reversed(range(8)):
            lsb = channel * 32 + lane * 16
            parts.append(data.slice(lsb + 15, lsb))
        return concat(parts)

    def compute(self) -> None:
        all_valid = self.adc_i_tvalid_i.eq(0xFF) & self.adc_q_tvalid_i.eq(0xFF)
        all_idle = self.adc_i_tvalid_i.eq(0) & self.adc_q_tvalid_i.eq(0)
        faulted = self.format_error_o | self.gap_error_o
        armed = self.acquisition_enable_i & (~faulted)
        accepted = armed & all_valid
        gap_group = armed & all_idle
        partial_group = armed & (~all_idle) & (~all_valid)
        fault_now = gap_group | partial_group

        self.drive(self.next_valid, accepted)
        self.drive(
            self.next_i_lane0,
            mux(accepted, self._lane(self.adc_i_tdata_i, 0), self.rx_i_lane0_o),
        )
        self.drive(
            self.next_q_lane0,
            mux(accepted, self._lane(self.adc_q_tdata_i, 0), self.rx_q_lane0_o),
        )
        self.drive(
            self.next_i_lane1,
            mux(accepted, self._lane(self.adc_i_tdata_i, 1), self.rx_i_lane1_o),
        )
        self.drive(
            self.next_q_lane1,
            mux(accepted, self._lane(self.adc_q_tdata_i, 1), self.rx_q_lane1_o),
        )
        self.drive(
            self.next_sample_base,
            mux(accepted, self.sample_counter, self.sample_base_index_o),
        )
        self.drive(
            self.next_sample_counter,
            mux(
                accepted,
                self.sample_counter.add(ConstExpr(2, 64)),
                self.sample_counter,
            ),
        )
        self.drive(
            self.next_stream_active,
            mux(
                fault_now | (~self.acquisition_enable_i),
                ConstExpr(0, 1),
                self.stream_active_o | accepted,
            ),
        )
        self.drive(self.next_format_error, self.format_error_o | partial_group)
        self.drive(self.next_gap_error, self.gap_error_o | gap_group)

    def clock(self) -> None:
        self.update(self.rx_valid_o, self.next_valid)
        self.update(self.rx_i_lane0_o, self.next_i_lane0)
        self.update(self.rx_q_lane0_o, self.next_q_lane0)
        self.update(self.rx_i_lane1_o, self.next_i_lane1)
        self.update(self.rx_q_lane1_o, self.next_q_lane1)
        self.update(self.sample_base_index_o, self.next_sample_base)
        self.update(self.stream_active_o, self.next_stream_active)
        self.update(self.format_error_o, self.next_format_error)
        self.update(self.gap_error_o, self.next_gap_error)
        self.update(self.sample_counter, self.next_sample_counter)
