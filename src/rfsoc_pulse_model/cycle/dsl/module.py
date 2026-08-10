from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .expr import Expr


def _mask(width: int) -> int:
    return (1 << width) - 1


@dataclass(eq=False)
class Signal(Expr):
    name: str
    width: int
    signed: bool = False
    direction: Optional[str] = None
    registered: bool = False
    value: int = 0
    pending: Optional[int] = None

    def evaluate(self) -> int:
        return self.value & _mask(self.width)

    def verilog(self) -> str:
        return self.name

    def set_value(self, value: int) -> None:
        self.value = int(value) & _mask(self.width)


class RTLModule:
    """Restricted compute/clock module with nonblocking commit semantics."""

    module_name = "rtl_module"

    def __init__(self) -> None:
        self.ports: list[Signal] = []
        self.internal_signals: list[Signal] = []
        self.comb_assignments: "OrderedDict[Signal, Expr]" = OrderedDict()
        self.clock_assignments: "OrderedDict[Signal, tuple[Expr, int]]" = OrderedDict()
        self.reset_signal: Optional[Signal] = None

    def input(self, name: str, width: int = 1) -> Signal:
        signal = Signal(name, width, direction="input")
        self.ports.append(signal)
        return signal

    def output_reg(self, name: str, width: int = 1) -> Signal:
        signal = Signal(name, width, direction="output", registered=True)
        self.ports.append(signal)
        return signal

    def wire(self, name: str, width: int = 1) -> Signal:
        signal = Signal(name, width)
        self.internal_signals.append(signal)
        return signal

    def reg(self, name: str, width: int = 1) -> Signal:
        signal = Signal(name, width, registered=True)
        self.internal_signals.append(signal)
        return signal

    def drive(self, target: Signal, expression: Expr) -> None:
        if target.registered:
            raise ValueError("compute() cannot drive a register directly")
        if target.width != expression.width:
            raise ValueError(
                f"width mismatch driving {target.name}: {target.width} != {expression.width}"
            )
        self.comb_assignments[target] = expression
        target.set_value(expression.evaluate())

    def update(self, target: Signal, expression: Expr, *, reset: int = 0) -> None:
        if not target.registered:
            raise ValueError("clock() can only update registers")
        if target.width != expression.width:
            raise ValueError(
                f"width mismatch updating {target.name}: {target.width} != {expression.width}"
            )
        self.clock_assignments[target] = (expression, reset)
        reset_active = self.reset_signal is not None and self.reset_signal.evaluate() != 0
        target.pending = reset if reset_active else expression.evaluate()

    def compute(self) -> None:
        raise NotImplementedError

    def clock(self) -> None:
        raise NotImplementedError

    def set_inputs(self, values: dict[str, int]) -> None:
        inputs = {port.name: port for port in self.ports if port.direction == "input"}
        unknown = set(values) - set(inputs)
        if unknown:
            raise KeyError(f"unknown input ports: {sorted(unknown)}")
        for signal in inputs.values():
            signal.set_value(values.get(signal.name, 0))

    def commit(self) -> None:
        for signal in self.ports + self.internal_signals:
            if signal.pending is not None:
                signal.set_value(signal.pending)
                signal.pending = None

    def outputs(self) -> dict[str, int]:
        return {
            port.name: port.evaluate()
            for port in self.ports
            if port.direction == "output"
        }

    def elaborate(self) -> None:
        self.comb_assignments.clear()
        self.clock_assignments.clear()
        self.compute()
        self.clock()
        for signal in self.ports + self.internal_signals:
            signal.pending = None

