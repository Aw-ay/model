from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from ..ip.types import ImplementationKind
from .dsl.module import RTLModule
from .hardware.rx_group_ingress import RxGroupIngress2Spc
from .hardware.tx_iq_axis_boundary import TxIqAxisBoundary2Spc


@dataclass(frozen=True)
class HardwareModuleRegistration:
    cycle_class: Type[RTLModule]
    verilog_filename: str
    implementation_kind: ImplementationKind
    production: bool

    def __post_init__(self) -> None:
        if not isinstance(self.implementation_kind, ImplementationKind):
            raise ValueError("implementation_kind must be an ImplementationKind")
        if (
            self.production
            and self.implementation_kind
            is ImplementationKind.LEGACY_NON_PRODUCTION
        ):
            raise ValueError("legacy_non_production module cannot be production")


HARDWARE_MODULES = (
    HardwareModuleRegistration(
        cycle_class=RxGroupIngress2Spc,
        verilog_filename="rx_group_ingress_2spc.v",
        implementation_kind=ImplementationKind.LEGACY_NON_PRODUCTION,
        production=False,
    ),
    HardwareModuleRegistration(
        cycle_class=TxIqAxisBoundary2Spc,
        verilog_filename="tx_iq_axis_boundary_2spc.v",
        implementation_kind=ImplementationKind.LEGACY_NON_PRODUCTION,
        production=False,
    ),
)
