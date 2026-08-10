from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Literal

import numpy as np


class RoundingMode(str, Enum):
    TIES_AWAY_FROM_ZERO = "ties_away_from_zero"


PROJECT_ROUNDING_MODE = RoundingMode.TIES_AWAY_FROM_ZERO


def round_ties_away_from_zero(value: float) -> int:
    """Round to nearest; exact half steps move away from zero."""

    magnitude = math.floor(abs(float(value)) + 0.5)
    return magnitude if value >= 0 else -magnitude


def round_array_ties_away_from_zero(values: np.ndarray) -> np.ndarray:
    """NumPy form of the project-wide rounding rule."""

    array = np.asarray(values, dtype=np.float64)
    return np.where(array >= 0.0, np.floor(array + 0.5), np.ceil(array - 0.5))


@dataclass(frozen=True)
class FixedFormat:
    """Shared numeric-format declaration for later Cycle quantization."""

    width: int
    signed: bool = False
    fraction_bits: int = 0
    overflow: Literal["saturate", "wrap", "error"] = "saturate"

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError("width must be positive")
        if self.fraction_bits < 0:
            raise ValueError("fraction_bits cannot be negative")
        if self.fraction_bits > self.width:
            raise ValueError("fraction_bits cannot exceed width")
        if self.overflow not in ("saturate", "wrap", "error"):
            raise ValueError("overflow must be saturate, wrap, or error")

    @property
    def minimum(self) -> int:
        return -(1 << (self.width - 1)) if self.signed else 0

    @property
    def maximum(self) -> int:
        if self.signed:
            return (1 << (self.width - 1)) - 1
        return (1 << self.width) - 1

    def quantize(self, value: float) -> int:
        return self.cast_integer(
            round_ties_away_from_zero(value * (1 << self.fraction_bits))
        )

    def cast_integer(self, value: int) -> int:
        if self.overflow == "saturate":
            return max(self.minimum, min(self.maximum, int(value)))
        if self.overflow == "error":
            integer = int(value)
            if not self.minimum <= integer <= self.maximum:
                raise OverflowError(
                    f"value does not fit {self.width}-bit "
                    f"{'signed' if self.signed else 'unsigned'} format"
                )
            return integer
        raw = int(value) & ((1 << self.width) - 1)
        if self.signed and raw & (1 << (self.width - 1)):
            return raw - (1 << self.width)
        return raw

    def to_float(self, value: int) -> float:
        return self.cast_integer(value) / float(1 << self.fraction_bits)
