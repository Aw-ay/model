"""Restricted structural DSL shared by Cycle simulation and Verilog emission."""

from .emitter import VerilogEmitter
from .expr import ConstExpr, Expr, concat, mux
from .fixed import round_shift_ties_away_from_zero, signed_out_of_range, saturate_signed, signed_mul
from .module import RTLModule, Signal
from .simulator import CycleSimulator

__all__ = [
    "ConstExpr",
    "CycleSimulator",
    "Expr",
    "RTLModule",
    "Signal",
    "VerilogEmitter",
    "concat",
    "round_shift_ties_away_from_zero",
    "signed_out_of_range",
    "saturate_signed",
    "signed_mul",
    "mux",
]
