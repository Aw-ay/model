from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from .dsl.module import RTLModule
from .hardware.rx_group_ingress import RxGroupIngress2Spc
from .hardware.tx_iq_axis_boundary import TxIqAxisBoundary2Spc


@dataclass(frozen=True)
class HardwareModuleRegistration:
    cycle_class: Type[RTLModule]
    verilog_filename: str


HARDWARE_MODULES = (
    HardwareModuleRegistration(
        cycle_class=RxGroupIngress2Spc,
        verilog_filename="rx_group_ingress_2spc.v",
    ),
    HardwareModuleRegistration(
        cycle_class=TxIqAxisBoundary2Spc,
        verilog_filename="tx_iq_axis_boundary_2spc.v",
    ),
)
