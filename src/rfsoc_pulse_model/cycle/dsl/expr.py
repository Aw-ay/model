from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _mask(width: int) -> int:
    return (1 << width) - 1


def _signed_value(value: int, width: int) -> int:
    masked = int(value) & _mask(width)
    sign_bit = 1 << (width - 1)
    return masked - (1 << width) if masked & sign_bit else masked


class Expr:
    width: int
    signed: bool

    def evaluate(self) -> int:
        raise NotImplementedError

    def verilog(self) -> str:
        raise NotImplementedError

    def __and__(self, other: object) -> "Expr":
        return BinaryExpr("&", self, as_expr(other, self.width))

    def __or__(self, other: object) -> "Expr":
        return BinaryExpr("|", self, as_expr(other, self.width))

    def __invert__(self) -> "Expr":
        return UnaryExpr("~", self)

    def add(self, other: object) -> "Expr":
        return BinaryExpr("+", self, as_expr(other, self.width))

    def eq(self, other: object) -> "Expr":
        return BinaryExpr("==", self, as_expr(other, self.width), result_width=1)

    def slice(self, msb: int, lsb: int) -> "Expr":
        return SliceExpr(self, msb, lsb)


@dataclass(frozen=True)
class ConstExpr(Expr):
    value: int
    width: int
    signed: bool = False

    def evaluate(self) -> int:
        return int(self.value) & _mask(self.width)

    def verilog(self) -> str:
        if self.signed:
            value = int(self.value)
            literal = f"{self.width}'sd{abs(value)}"
            return f"-{literal}" if value < 0 else literal
        return f"{self.width}'d{int(self.value) & _mask(self.width)}"


@dataclass(frozen=True)
class BinaryExpr(Expr):
    operator: str
    left: Expr
    right: Expr
    result_width: int | None = None

    @property
    def width(self) -> int:
        return self.result_width or max(self.left.width, self.right.width)

    @property
    def signed(self) -> bool:
        return self.left.signed and self.right.signed

    def evaluate(self) -> int:
        left = self.left.evaluate()
        right = self.right.evaluate()
        if self.operator == "&":
            value = left & right
        elif self.operator == "|":
            value = left | right
        elif self.operator == "+":
            value = left + right
        elif self.operator == "==":
            value = int(left == right)
        else:
            raise ValueError(f"unsupported binary operator {self.operator}")
        return value & _mask(self.width)

    def verilog(self) -> str:
        return f"({self.left.verilog()} {self.operator} {self.right.verilog()})"


@dataclass(frozen=True)
class UnaryExpr(Expr):
    operator: str
    operand: Expr

    @property
    def width(self) -> int:
        return self.operand.width

    @property
    def signed(self) -> bool:
        return self.operand.signed

    def evaluate(self) -> int:
        if self.operator != "~":
            raise ValueError(f"unsupported unary operator {self.operator}")
        return (~self.operand.evaluate()) & _mask(self.width)

    def verilog(self) -> str:
        return f"{self.operator}({self.operand.verilog()})"


@dataclass(frozen=True)
class SliceExpr(Expr):
    source: Expr
    msb: int
    lsb: int
    signed: bool = False

    def __post_init__(self) -> None:
        if self.lsb < 0 or self.msb < self.lsb or self.msb >= self.source.width:
            raise ValueError("invalid expression slice")

    @property
    def width(self) -> int:
        return self.msb - self.lsb + 1

    def evaluate(self) -> int:
        return (self.source.evaluate() >> self.lsb) & _mask(self.width)

    def verilog(self) -> str:
        if self.msb == self.lsb:
            return f"{self.source.verilog()}[{self.lsb}]"
        return f"{self.source.verilog()}[{self.msb}:{self.lsb}]"


@dataclass(frozen=True)
class ConcatExpr(Expr):
    parts: tuple[Expr, ...]
    signed: bool = False

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("concat requires at least one expression")

    @property
    def width(self) -> int:
        return sum(part.width for part in self.parts)

    def evaluate(self) -> int:
        value = 0
        for part in self.parts:
            value = (value << part.width) | part.evaluate()
        return value & _mask(self.width)

    def verilog(self) -> str:
        return "{" + ", ".join(part.verilog() for part in self.parts) + "}"


@dataclass(frozen=True)
class MuxExpr(Expr):
    condition: Expr
    when_true: Expr
    when_false: Expr

    def __post_init__(self) -> None:
        if self.condition.width != 1:
            raise ValueError("mux condition must be one bit")
        if self.when_true.width != self.when_false.width:
            raise ValueError("mux branches must have equal width")

    @property
    def width(self) -> int:
        return self.when_true.width

    @property
    def signed(self) -> bool:
        return self.when_true.signed and self.when_false.signed

    def evaluate(self) -> int:
        selected = self.when_true if self.condition.evaluate() else self.when_false
        return selected.evaluate() & _mask(self.width)

    def verilog(self) -> str:
        return (
            f"({self.condition.verilog()} ? {self.when_true.verilog()} : "
            f"{self.when_false.verilog()})"
        )


def as_expr(value: object, width: int | None = None) -> Expr:
    if isinstance(value, Expr):
        return value
    if not isinstance(value, int) or width is None:
        raise TypeError("integer expressions require an explicit width")
    return ConstExpr(value, width)


def concat(parts: Iterable[Expr]) -> Expr:
    return ConcatExpr(tuple(parts))


def mux(condition: Expr, when_true: Expr, when_false: Expr) -> Expr:
    return MuxExpr(condition, when_true, when_false)

