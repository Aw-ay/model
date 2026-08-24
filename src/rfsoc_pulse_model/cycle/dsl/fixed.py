from __future__ import annotations

from dataclasses import dataclass

from .expr import Expr, _mask, _signed_value


def _require_signed_operand(name: str, operand: Expr) -> None:
    if not operand.signed:
        raise ValueError(f"{name} operand must be signed")


def _require_positive_width(result_width: int) -> None:
    if result_width < 1:
        raise ValueError("result_width must be positive")


def _signed_literal(width: int, value: int) -> str:
    return f"{width}'sd{int(value)}"


def _signed_expr(expr: Expr) -> str:
    return f"$signed({expr.verilog()})"


def _sign_extend_verilog(expr: Expr, target_width: int) -> str:
    if target_width <= expr.width:
        return _signed_expr(expr)
    extra = target_width - expr.width
    sign_bit = f"({_signed_expr(expr)} < 0)"
    return f"{{{{{extra}{{{sign_bit}}}}}, {expr.verilog()}}}"


def _truncate_signed_verilog(expr: Expr, target_width: int) -> str:
    if target_width >= expr.width:
        return _signed_expr(expr)
    return f"$signed(({expr.verilog()})[{target_width - 1}:0])"


@dataclass(frozen=True)
class SignedMulExpr(Expr):
    left: Expr
    right: Expr
    result_width: int

    def __post_init__(self) -> None:
        _require_positive_width(self.result_width)
        _require_signed_operand("left", self.left)
        _require_signed_operand("right", self.right)

    @property
    def width(self) -> int:
        return self.result_width

    @property
    def signed(self) -> bool:
        return True

    def evaluate(self) -> int:
        left = _signed_value(self.left.evaluate(), self.left.width)
        right = _signed_value(self.right.evaluate(), self.right.width)
        return (left * right) & _mask(self.result_width)

    def verilog(self) -> str:
        left = _sign_extend_verilog(self.left, self.result_width)
        right = _sign_extend_verilog(self.right, self.result_width)
        return f"({left} * {right})"


@dataclass(frozen=True)
class RoundShiftTiesAwayFromZeroExpr(Expr):
    value: Expr
    shift: int
    result_width: int

    def __post_init__(self) -> None:
        _require_positive_width(self.result_width)
        if self.shift < 0:
            raise ValueError("shift must be non-negative")
        _require_signed_operand("value", self.value)

    @property
    def width(self) -> int:
        return self.result_width

    @property
    def signed(self) -> bool:
        return True

    def evaluate(self) -> int:
        signed = _signed_value(self.value.evaluate(), self.value.width)
        if self.shift == 0:
            rounded = signed
        else:
            magnitude = abs(signed)
            rounded = (magnitude + (1 << (self.shift - 1))) >> self.shift
            if signed < 0:
                rounded = -rounded
        return rounded & _mask(self.result_width)

    def verilog(self) -> str:
        signed_value = _signed_expr(self.value)
        if self.shift == 0:
            return signed_value
        extended = _sign_extend_verilog(self.value, self.value.width + 1)
        bias = _signed_literal(self.result_width, 1 << (self.shift - 1))
        positive = f"(({signed_value} + {bias}) >>> {self.shift})"
        negative = f"(-(((-{extended}) + {bias}) >>> {self.shift}))"
        return f"(({signed_value} < 0) ? {negative} : {positive})"


@dataclass(frozen=True)
class SaturateSignedExpr(Expr):
    value: Expr
    result_width: int

    def __post_init__(self) -> None:
        _require_positive_width(self.result_width)
        _require_signed_operand("value", self.value)

    @property
    def width(self) -> int:
        return self.result_width

    @property
    def signed(self) -> bool:
        return True

    def evaluate(self) -> int:
        signed = _signed_value(self.value.evaluate(), self.value.width)
        minimum = -(1 << (self.result_width - 1))
        maximum = (1 << (self.result_width - 1)) - 1
        clamped = max(minimum, min(maximum, signed))
        return clamped & _mask(self.result_width)

    def verilog(self) -> str:
        signed_value = _signed_expr(self.value)
        minimum = -(1 << (self.result_width - 1))
        maximum = (1 << (self.result_width - 1)) - 1
        max_literal = _signed_literal(self.result_width, maximum)
        min_literal = _signed_literal(self.result_width, minimum)
        in_range = _truncate_signed_verilog(self.value, self.result_width)
        return (
            f"(({signed_value} > {max_literal}) ? {max_literal} : "
            f"(({signed_value} < {min_literal}) ? {min_literal} : {in_range}))"
        )


@dataclass(frozen=True)
class SignedOutOfRangeExpr(Expr):
    value: Expr
    result_width: int

    def __post_init__(self) -> None:
        _require_positive_width(self.result_width)
        _require_signed_operand("value", self.value)

    @property
    def width(self) -> int:
        return 1

    @property
    def signed(self) -> bool:
        return False

    def evaluate(self) -> int:
        signed = _signed_value(self.value.evaluate(), self.value.width)
        minimum = -(1 << (self.result_width - 1))
        maximum = (1 << (self.result_width - 1)) - 1
        return int(signed < minimum or signed > maximum)

    def verilog(self) -> str:
        signed_value = _signed_expr(self.value)
        minimum = -(1 << (self.result_width - 1))
        maximum = (1 << (self.result_width - 1)) - 1
        max_literal = _signed_literal(self.result_width, maximum)
        min_literal = _signed_literal(self.result_width, minimum)
        return f"(({signed_value} > {max_literal}) | ({signed_value} < {min_literal}))"


def signed_mul(left: Expr, right: Expr, result_width: int) -> Expr:
    return SignedMulExpr(left, right, result_width)


def round_shift_ties_away_from_zero(value: Expr, shift: int, result_width: int) -> Expr:
    return RoundShiftTiesAwayFromZeroExpr(value, shift, result_width)


def saturate_signed(value: Expr, result_width: int) -> Expr:
    return SaturateSignedExpr(value, result_width)


def signed_out_of_range(value: Expr, result_width: int) -> Expr:
    return SignedOutOfRangeExpr(value, result_width)
