"""Small deterministic evaluator for the Verilog emitted by the Cycle DSL tests."""

from __future__ import annotations

from dataclasses import dataclass


def _mask(width: int) -> int:
    return (1 << width) - 1


def _signed_value(value: int, width: int) -> int:
    value &= _mask(width)
    sign_bit = 1 << (width - 1)
    return value - (1 << width) if value & sign_bit else value


@dataclass(frozen=True)
class VerilogValue:
    raw: int
    width: int
    signed: bool

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError("Verilog values require a positive width")
        object.__setattr__(self, "raw", int(self.raw) & _mask(self.width))

    @property
    def integer(self) -> int:
        if self.signed:
            return _signed_value(self.raw, self.width)
        return self.raw

    def resize(self, width: int, *, signed: bool | None = None) -> "VerilogValue":
        target_signed = self.signed if signed is None else signed
        return VerilogValue(self.integer if target_signed else self.raw, width, target_signed)


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith(">>>", index):
            tokens.append(_Token("operator", ">>>"))
            index += 3
            continue
        if source.startswith("==", index):
            tokens.append(_Token("operator", "=="))
            index += 2
            continue
        if char.isdigit():
            start = index
            while index < len(source) and source[index].isdigit():
                index += 1
            if index < len(source) and source[index] == "'":
                index += 1
                signed = False
                if index < len(source) and source[index] in "sS":
                    signed = True
                    index += 1
                if index >= len(source) or source[index] not in "dD":
                    raise ValueError(f"unsupported Verilog literal near {source[start:]!r}")
                index += 1
                value_start = index
                digit_start = index
                while index < len(source) and source[index].isdigit():
                    index += 1
                if digit_start == index:
                    raise ValueError(f"missing literal digits near {source[start:]!r}")
                tokens.append(
                    _Token(
                        "literal",
                        f"{source[start:value_start]}{source[value_start:index]}",
                    )
                )
            else:
                tokens.append(_Token("number", source[start:index]))
            continue
        if char.isalpha() or char == "_" or char == "$":
            start = index
            index += 1
            while index < len(source) and (
                source[index].isalnum() or source[index] in "_$"
            ):
                index += 1
            tokens.append(_Token("identifier", source[start:index]))
            continue
        if char in "(){}[],?:+*&|~<>-":
            tokens.append(_Token("operator", char))
            index += 1
            continue
        raise ValueError(f"unsupported Verilog character {char!r} in {source!r}")
    tokens.append(_Token("eof", ""))
    return tokens


class _Parser:
    def __init__(self, source: str, environment: dict[str, VerilogValue]) -> None:
        self.tokens = _tokenize(source)
        self.environment = environment
        self.index = 0

    def _peek(self, offset: int = 0) -> _Token:
        return self.tokens[self.index + offset]

    def _take(self) -> _Token:
        token = self._peek()
        self.index += 1
        return token

    def _accept(self, text: str) -> bool:
        if self._peek().text == text:
            self.index += 1
            return True
        return False

    def _expect(self, text: str) -> None:
        if not self._accept(text):
            raise ValueError(f"expected {text!r}, got {self._peek().text!r}")

    def parse(self) -> VerilogValue:
        result = self._parse_conditional()
        if self._peek().kind != "eof":
            raise ValueError(f"unexpected token {self._peek().text!r}")
        return result

    def _parse_conditional(self) -> VerilogValue:
        condition = self._parse_bit_or()
        if not self._accept("?"):
            return condition
        when_true = self._parse_conditional()
        self._expect(":")
        when_false = self._parse_conditional()
        width = max(when_true.width, when_false.width)
        signed = when_true.signed and when_false.signed
        selected = when_true if condition.raw else when_false
        return selected.resize(width, signed=signed)

    def _parse_bit_or(self) -> VerilogValue:
        value = self._parse_bit_and()
        while self._accept("|"):
            value = self._binary_bitwise("|", value, self._parse_bit_and())
        return value

    def _parse_bit_and(self) -> VerilogValue:
        value = self._parse_equality()
        while self._accept("&"):
            value = self._binary_bitwise("&", value, self._parse_equality())
        return value

    def _parse_equality(self) -> VerilogValue:
        value = self._parse_relation()
        while self._accept("=="):
            right = self._parse_relation()
            value = VerilogValue(int(value.raw == right.raw), 1, False)
        return value

    def _parse_relation(self) -> VerilogValue:
        value = self._parse_shift()
        while self._peek().text in (">", "<"):
            operator = self._take().text
            right = self._parse_shift()
            signed = value.signed and right.signed
            left_integer = value.integer if signed else value.raw
            right_integer = right.integer if signed else right.raw
            result = left_integer > right_integer if operator == ">" else left_integer < right_integer
            value = VerilogValue(int(result), 1, False)
        return value

    def _parse_shift(self) -> VerilogValue:
        value = self._parse_add()
        while self._accept(">>>"):
            shift = self._parse_add()
            shifted = value.integer >> shift.raw if value.signed else value.raw >> shift.raw
            value = VerilogValue(shifted, value.width, value.signed)
        return value

    def _parse_add(self) -> VerilogValue:
        value = self._parse_multiply()
        while self._accept("+"):
            right = self._parse_multiply()
            value = self._binary_arithmetic("+", value, right)
        return value

    def _parse_multiply(self) -> VerilogValue:
        value = self._parse_unary()
        while self._accept("*"):
            right = self._parse_unary()
            value = self._binary_arithmetic("*", value, right)
        return value

    def _parse_unary(self) -> VerilogValue:
        if self._accept("~"):
            operand = self._parse_unary()
            return VerilogValue(~operand.raw, operand.width, operand.signed)
        if self._accept("-"):
            operand = self._parse_unary()
            return VerilogValue(-operand.integer, operand.width, operand.signed)
        return self._parse_primary()

    def _parse_primary(self) -> VerilogValue:
        token = self._peek()
        if token.kind == "literal":
            self._take()
            text = token.text
            width_text, value_text = text.split("'", 1)
            signed = value_text[0].lower() == "s"
            base_text = value_text[1:] if signed else value_text
            if base_text[0].lower() != "d":
                raise ValueError(f"unsupported literal {text!r}")
            value = int(base_text[1:])
            return VerilogValue(value, int(width_text), signed)
        if token.kind == "number":
            self._take()
            return VerilogValue(int(token.text), 32, True)
        if token.kind == "identifier":
            self._take()
            if token.text == "$signed":
                self._expect("(")
                value = self._parse_conditional()
                self._expect(")")
                value = VerilogValue(value.raw, value.width, True)
            else:
                try:
                    value = self.environment[token.text]
                except KeyError as exc:
                    raise ValueError(f"unknown Verilog signal {token.text!r}") from exc
            return self._parse_slices(value)
        if self._accept("("):
            value = self._parse_conditional()
            self._expect(")")
            return self._parse_slices(value)
        if self._peek().text == "{":
            return self._parse_braces()
        context = " ".join(item.text for item in self.tokens[max(0, self.index - 4) : self.index + 4])
        raise ValueError(f"expected Verilog primary, got {token.text!r} near {context!r}")

    def _parse_slices(self, value: VerilogValue) -> VerilogValue:
        while self._accept("["):
            msb = int(self._take().text)
            if self._accept(":"):
                lsb = int(self._take().text)
            else:
                lsb = msb
            self._expect("]")
            if lsb < 0 or msb < lsb or msb >= value.width:
                raise ValueError("invalid Verilog slice")
            value = VerilogValue(value.raw >> lsb, msb - lsb + 1, False)
        return value

    def _parse_braces(self) -> VerilogValue:
        self._expect("{")
        if self._peek().kind == "number" and self._peek(1).text == "{":
            count = int(self._take().text)
            self._expect("{")
            part = self._parse_conditional()
            self._expect("}")
            self._expect("}")
            value = 0
            for _ in range(count):
                value = (value << part.width) | part.raw
            return VerilogValue(value, count * part.width, False)

        parts = [self._parse_conditional()]
        while self._accept(","):
            parts.append(self._parse_conditional())
        self._expect("}")
        value = 0
        width = 0
        for part in parts:
            value = (value << part.width) | part.raw
            width += part.width
        return VerilogValue(value, width, False)

    @staticmethod
    def _binary_arithmetic(
        operator: str,
        left: VerilogValue,
        right: VerilogValue,
    ) -> VerilogValue:
        width = max(left.width, right.width)
        signed = left.signed and right.signed
        left_value = left.integer if signed else left.raw
        right_value = right.integer if signed else right.raw
        result = left_value + right_value if operator == "+" else left_value * right_value
        return VerilogValue(result, width, signed)

    @staticmethod
    def _binary_bitwise(
        operator: str,
        left: VerilogValue,
        right: VerilogValue,
    ) -> VerilogValue:
        width = max(left.width, right.width)
        signed = left.signed and right.signed
        left_value = left.resize(width, signed=signed).raw
        right_value = right.resize(width, signed=signed).raw
        result = left_value & right_value if operator == "&" else left_value | right_value
        return VerilogValue(result, width, signed)


def evaluate_verilog_expression(
    expression: str,
    environment: dict[str, tuple[int, int, bool] | VerilogValue],
) -> VerilogValue:
    values = {
        name: value
        if isinstance(value, VerilogValue)
        else VerilogValue(value[0], value[1], value[2])
        for name, value in environment.items()
    }
    return _Parser(expression, values).parse()
