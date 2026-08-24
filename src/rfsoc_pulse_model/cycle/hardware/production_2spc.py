from __future__ import annotations

from ...common.config import ModelConfig
from ...common.types import RfdcAdcClockingMode, RfdcDacClockingMode
from ..dsl.expr import ConstExpr, concat, mux
from ..dsl.module import RTLModule


class RxContinuousIngress2Spc(RTLModule):
    """Production candidate for the eight-channel RFDC ADC 2SPC boundary.

    This class is intentionally independent from the legacy reference ingress.
    It owns only RFDC word unpacking, atomic valid acceptance, and the public
    absolute sample base. Processing and detector behavior are downstream.
    """

    module_name = "rx_2spc_continuous_ingress"
    latency_cycles = 1
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        if config.rfdc_complex_samples_per_cycle != 2:
            raise ValueError("RxContinuousIngress2Spc requires exactly two samples/cycle")
        if config.adc_channels != 8:
            raise ValueError("RxContinuousIngress2Spc requires eight ADC channels")
        if config.rfdc_axis.adc_component_stream_width_bits != 32:
            raise ValueError("RxContinuousIngress2Spc requires 32-bit I/Q component words")
        if config.rfdc_adc_clocking_mode is not RfdcAdcClockingMode.COMMON_PL_CLOCK_MTS:
            raise ValueError(
                "RxContinuousIngress2Spc requires the common PL clock + MTS mode; "
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
        self.next_i_lane0 = self.wire("next_i_lane0", 8 * 16)
        self.next_q_lane0 = self.wire("next_q_lane0", 8 * 16)
        self.next_i_lane1 = self.wire("next_i_lane1", 8 * 16)
        self.next_q_lane1 = self.wire("next_q_lane1", 8 * 16)
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


class ContinuousStreamTimebase(RTLModule):
    """Production candidate that proves continuous two-sample time order."""

    module_name = "continuous_stream_timebase"
    latency_cycles = 1
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(self) -> None:
        super().__init__()

        self.clk_i = self.input("clk_i")
        self.rst_i = self.input("rst_i")
        self.reset_signal = self.rst_i
        self.acquisition_enable_i = self.input("acquisition_enable_i")
        self.sample_valid_i = self.input("sample_valid_i")
        self.sample_base_index_i = self.input("sample_base_index_i", 64)
        self.upstream_fault_i = self.input("upstream_fault_i")

        self.time_valid_o = self.output_reg("time_valid_o")
        self.sample_base_index_o = self.output_reg("sample_base_index_o", 64)
        self.stream_active_o = self.output_reg("stream_active_o")
        self.timebase_error_o = self.output_reg("timebase_error_o")
        self.stream_integrity_error_o = self.output_reg("stream_integrity_error_o")

        self.expected_base = self.reg("expected_base", 64)
        self.next_time_valid = self.wire("next_time_valid")
        self.next_sample_base = self.wire("next_sample_base", 64)
        self.next_stream_active = self.wire("next_stream_active")
        self.next_timebase_error = self.wire("next_timebase_error")
        self.next_stream_integrity_error = self.wire("next_stream_integrity_error")
        self.next_expected_base = self.wire("next_expected_base", 64)

    def compute(self) -> None:
        armed = (
            self.acquisition_enable_i
            & (~self.timebase_error_o)
            & (~self.stream_integrity_error_o)
        )
        index_matches = self.sample_base_index_i.eq(self.expected_base)
        missing = armed & (~self.sample_valid_i)
        discontinuity = armed & self.sample_valid_i & (~index_matches)
        fault_now = self.upstream_fault_i | missing | discontinuity
        accepted = armed & self.sample_valid_i & index_matches & (~self.upstream_fault_i)

        self.drive(self.next_time_valid, accepted)
        self.drive(
            self.next_sample_base,
            mux(accepted, self.sample_base_index_i, self.sample_base_index_o),
        )
        self.drive(
            self.next_stream_active,
            mux(
                fault_now | (~self.acquisition_enable_i),
                ConstExpr(0, 1),
                self.stream_active_o | accepted,
            ),
        )
        self.drive(
            self.next_timebase_error,
            self.timebase_error_o | missing | discontinuity,
        )
        self.drive(
            self.next_stream_integrity_error,
            self.stream_integrity_error_o | fault_now,
        )
        self.drive(
            self.next_expected_base,
            mux(
                accepted,
                self.sample_base_index_i.add(ConstExpr(2, 64)),
                self.expected_base,
            ),
        )

    def clock(self) -> None:
        self.update(self.time_valid_o, self.next_time_valid)
        self.update(self.sample_base_index_o, self.next_sample_base)
        self.update(self.stream_active_o, self.next_stream_active)
        self.update(self.timebase_error_o, self.next_timebase_error)
        self.update(self.stream_integrity_error_o, self.next_stream_integrity_error)
        self.update(self.expected_base, self.next_expected_base)


class TxContinuousEgress2Spc(RTLModule):
    """Production candidate for the eight-channel RFDC DAC 2SPC boundary."""

    module_name = "tx_2spc_continuous_egress"
    latency_cycles = 0
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        axis = config.rfdc_axis
        if config.dac_channels != 8:
            raise ValueError("TxContinuousEgress2Spc requires eight DAC channels")
        if axis.dac_data_type != "iq_interleaved":
            raise ValueError("TxContinuousEgress2Spc requires RFDC I/Q input data")
        if axis.dac_axis_width_bits != 64:
            raise ValueError("TxContinuousEgress2Spc requires 64-bit DAC AXI words")
        if axis.dac_complex_samples_per_cycle != 2:
            raise ValueError("TxContinuousEgress2Spc requires two complex samples/cycle")
        if config.rfdc_dac_clocking_mode is not RfdcDacClockingMode.COMMON_PL_CLOCK_MTS_SYSREF:
            raise ValueError(
                "TxContinuousEgress2Spc requires the common PL clock + MTS/SYSREF mode; "
                "per-tile CDC requires a different egress architecture"
            )
        self.config = config

        self.clk_i = self.input("clk_i")
        self.rst_i = self.input("rst_i")
        self.reset_signal = self.rst_i
        self.tx_enable_i = self.input("tx_enable_i")
        self.clear_status_i = self.input("clear_status_i")
        self.source_valid_i = self.input("source_valid_i")
        self.dac_i_lane0_i = self.input("dac_i_lane0_i", 8 * 16)
        self.dac_q_lane0_i = self.input("dac_q_lane0_i", 8 * 16)
        self.dac_i_lane1_i = self.input("dac_i_lane1_i", 8 * 16)
        self.dac_q_lane1_i = self.input("dac_q_lane1_i", 8 * 16)
        self.dac_tready_i = self.input("dac_tready_i", 8)

        self.dac_tdata_o = self.output("dac_tdata_o", 8 * 64)
        self.dac_tvalid_o = self.output("dac_tvalid_o", 8)
        self.source_advance_o = self.output("source_advance_o")
        self.stream_active_o = self.output_reg("stream_active_o")
        self.underrun_o = self.output_reg("underrun_o")

        self.next_stream_active = self.wire("next_stream_active")
        self.next_underrun = self.wire("next_underrun")

    def _packed_channels(self):
        channels = []
        for channel in reversed(range(8)):
            lsb = channel * 16
            channels.append(
                concat(
                    (
                        self.dac_q_lane1_i.slice(lsb + 15, lsb),
                        self.dac_i_lane1_i.slice(lsb + 15, lsb),
                        self.dac_q_lane0_i.slice(lsb + 15, lsb),
                        self.dac_i_lane0_i.slice(lsb + 15, lsb),
                    )
                )
            )
        return concat(channels)

    def compute(self) -> None:
        all_ready = self.dac_tready_i.eq(0xFF)
        faulted = self.underrun_o
        start = self.tx_enable_i & all_ready & self.source_valid_i & (~faulted)
        running = self.stream_active_o & self.tx_enable_i & (~faulted)
        transfer = (running | start) & all_ready & self.source_valid_i
        fault_now = (
            self.stream_active_o
            & self.tx_enable_i
            & ((~all_ready) | (~self.source_valid_i))
        )
        clear = self.clear_status_i & (~self.tx_enable_i)

        self.drive(
            self.dac_tdata_o,
            mux(transfer, self._packed_channels(), ConstExpr(0, 512)),
        )
        self.drive(
            self.dac_tvalid_o,
            mux(self.rst_i, ConstExpr(0, 8), ConstExpr(0xFF, 8)),
        )
        self.drive(self.source_advance_o, transfer)
        self.drive(
            self.next_stream_active,
            mux(
                ~self.tx_enable_i,
                ConstExpr(0, 1),
                mux(fault_now, ConstExpr(0, 1), self.stream_active_o | start),
            ),
        )
        self.drive(
            self.next_underrun,
            mux(clear, ConstExpr(0, 1), self.underrun_o | fault_now),
        )

    def clock(self) -> None:
        self.update(self.stream_active_o, self.next_stream_active)
        self.update(self.underrun_o, self.next_underrun)
