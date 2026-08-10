from __future__ import annotations

from ...common.config import ModelConfig
from ...common.types import RfdcDacClockingMode
from ..dsl.expr import ConstExpr, concat, mux
from ..dsl.module import RTLModule


class TxIqAxisBoundary2Spc(RTLModule):
    """Pack eight I/Q lanes for RFDC I/Q-to-real fine-mixer inputs.

    The reflection source cannot be backpressured once streaming has started.
    All eight RFDC DAC streams therefore advance atomically. A ready loss or a
    missing source beat after start drives zeros and latches an underrun until
    status is cleared while disabled.
    """

    module_name = "tx_iq_axis_boundary_2spc"
    latency_cycles = 0
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        axis = config.rfdc_axis
        if config.dac_channels != 8:
            raise ValueError("TxIqAxisBoundary2Spc requires eight DAC channels")
        if axis.dac_data_type != "iq_interleaved":
            raise ValueError("TxIqAxisBoundary2Spc requires RFDC I/Q input data")
        if axis.dac_axis_width_bits != 64:
            raise ValueError("TxIqAxisBoundary2Spc requires 64-bit DAC AXI words")
        if axis.dac_complex_samples_per_cycle != 2:
            raise ValueError("TxIqAxisBoundary2Spc requires two complex samples/cycle")
        if (
            config.rfdc_dac_clocking_mode
            != RfdcDacClockingMode.COMMON_PL_CLOCK_MTS_SYSREF
        ):
            raise ValueError(
                "TxIqAxisBoundary2Spc requires the common PL clock + "
                "MTS/SYSREF mode; per-tile CDC requires a different boundary"
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
        start = (
            self.tx_enable_i
            & all_ready
            & self.source_valid_i
            & (~faulted)
        )
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
