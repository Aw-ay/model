"""Candidate Cycle hardware registry kept outside production generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from ..ip.types import ImplementationKind
from .dsl.module import RTLModule
from .hardware.production_2spc import (
    ContinuousStreamTimebase,
    RxContinuousIngress2Spc,
    TxContinuousEgress2Spc,
)


@dataclass(frozen=True)
class CandidateHardwareModuleRegistration:
    cycle_class: Type[RTLModule]
    module_name: str
    verilog_filename: str
    implementation_kind: ImplementationKind
    production: bool
    accepts_config: bool
    architecture_owner: str

    def __post_init__(self) -> None:
        if self.implementation_kind is not ImplementationKind.ARCHITECTURE_PENDING:
            raise ValueError("candidate modules must remain architecture_pending")
        if self.production:
            raise ValueError("candidate modules cannot be production")


CANDIDATE_HARDWARE_MODULES = (
    CandidateHardwareModuleRegistration(
        cycle_class=RxContinuousIngress2Spc,
        module_name="rx_2spc_continuous_ingress",
        verilog_filename="rx_2spc_continuous_ingress.v",
        implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
        production=False,
        accepts_config=True,
        architecture_owner="rx_2spc_continuous_ingress",
    ),
    CandidateHardwareModuleRegistration(
        cycle_class=ContinuousStreamTimebase,
        module_name="continuous_stream_timebase",
        verilog_filename="continuous_stream_timebase.v",
        implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
        production=False,
        accepts_config=False,
        architecture_owner="continuous_stream_timebase",
    ),
    CandidateHardwareModuleRegistration(
        cycle_class=TxContinuousEgress2Spc,
        module_name="tx_2spc_continuous_egress",
        verilog_filename="tx_2spc_continuous_egress.v",
        implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
        production=False,
        accepts_config=True,
        architecture_owner="tx_2spc_continuous_egress",
    ),
)
