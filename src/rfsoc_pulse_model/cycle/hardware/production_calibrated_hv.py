from __future__ import annotations

from dataclasses import dataclass

from ...common.config import ModelConfig
from ...common.fixed import FixedFormat
from ...common.reflection_types import PhysicalChannelMapEntry
from ...common.types import ChannelRole, GainRange, Polarization
from ..dsl import ConstExpr, RTLModule, concat, mux
from ..dsl.expr import Expr, _signed_value
from ..dsl.fixed import round_shift_ties_away_from_zero, saturate_signed, signed_mul


CALIBRATION_COEFFICIENT_FORMAT = FixedFormat(
    width=24,
    signed=True,
    fraction_bits=20,
    overflow="saturate",
)
REFLECTION_SAMPLE_FORMAT = FixedFormat(
    width=24,
    signed=True,
    fraction_bits=4,
    overflow="saturate",
)
CALIBRATION_TO_REFLECTION_SHIFT = (
    CALIBRATION_COEFFICIENT_FORMAT.fraction_bits
    - REFLECTION_SAMPLE_FORMAT.fraction_bits
)
ECHO_RANGE_CODES = (
    (GainRange.HIGH, 0),
    (GainRange.MID, 1),
    (GainRange.LOW, 2),
)


@dataclass(frozen=True)
class _SignedExpr(Expr):
    source: Expr

    @property
    def width(self) -> int:
        return self.source.width

    @property
    def signed(self) -> bool:
        return True

    def evaluate(self) -> int:
        return _signed_value(self.source.evaluate(), self.source.width) & ((1 << self.width) - 1)

    def verilog(self) -> str:
        return f"$signed({self.source.verilog()})"


def _signed(expr: Expr) -> Expr:
    return _SignedExpr(expr)


@dataclass(frozen=True)
class HvCalibrationCoefficients:
    h_high: int
    h_mid: int
    h_low: int
    v_high: int
    v_mid: int
    v_low: int

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer calibration coefficient")
            if not (
                CALIBRATION_COEFFICIENT_FORMAT.minimum
                <= value
                <= CALIBRATION_COEFFICIENT_FORMAT.maximum
            ):
                raise ValueError(
                    f"{name} must fit the 24-bit signed calibration coefficient contract"
                )

    @classmethod
    def identity(cls) -> "HvCalibrationCoefficients":
        unity = 1 << CALIBRATION_COEFFICIENT_FORMAT.fraction_bits
        return cls(
            h_high=unity,
            h_mid=unity,
            h_low=unity,
            v_high=unity,
            v_mid=unity,
            v_low=unity,
        )

    def for_range(self, polarization: Polarization, gain_range: GainRange) -> int:
        key = f"{polarization.value.lower()}_{gain_range.value.lower()}"
        return getattr(self, key)


class RxCalibratedHvFrontend2Spc(RTLModule):
    """Calibrated H/V 2SPC candidate using the fixed-point Cycle helpers."""

    module_name = "rx_2spc_calibrated_hv_frontend"
    latency_cycles = 1
    samples_per_cycle = 2
    accepts_backpressure = False

    def __init__(
        self,
        config: ModelConfig,
        coefficients: HvCalibrationCoefficients | None = None,
    ) -> None:
        super().__init__()
        if config.rfdc_complex_samples_per_cycle != 2:
            raise ValueError("RxCalibratedHvFrontend2Spc requires exactly two samples/cycle")
        if config.adc_channels != 8:
            raise ValueError("RxCalibratedHvFrontend2Spc requires eight ADC channels")

        self.config = config
        requested_coefficients = coefficients or HvCalibrationCoefficients.identity()
        self.coefficients_valid = self._coefficients_are_valid(requested_coefficients)
        self.coefficients = (
            requested_coefficients
            if self.coefficients_valid
            else HvCalibrationCoefficients.identity()
        )
        self.range_indices = self._resolve_echo_indices(config.adc_channel_map)

        self.clk_i = self.input("clk_i")
        self.rst_i = self.input("rst_i")
        self.reset_signal = self.rst_i
        self.frontend_enable_i = self.input("frontend_enable_i")
        self.rx_valid_i = self.input("rx_valid_i")
        self.rx_i_lane0_i = self.input("rx_i_lane0_i", 8 * 16)
        self.rx_q_lane0_i = self.input("rx_q_lane0_i", 8 * 16)
        self.rx_i_lane1_i = self.input("rx_i_lane1_i", 8 * 16)
        self.rx_q_lane1_i = self.input("rx_q_lane1_i", 8 * 16)
        self.sample_base_index_i = self.input("sample_base_index_i", 64)
        self.stream_active_i = self.input("stream_active_i")
        self.format_error_i = self.input("format_error_i")
        self.gap_error_i = self.input("gap_error_i")
        self.selected_range_h_i = self.input("selected_range_h_i", 2)
        self.selected_range_v_i = self.input("selected_range_v_i", 2)

        self.incident_valid_o = self.output_reg("incident_valid_o")
        self.incident_i_lane0_o = self.output_reg("incident_i_lane0_o", 2 * 24)
        self.incident_q_lane0_o = self.output_reg("incident_q_lane0_o", 2 * 24)
        self.incident_i_lane1_o = self.output_reg("incident_i_lane1_o", 2 * 24)
        self.incident_q_lane1_o = self.output_reg("incident_q_lane1_o", 2 * 24)
        self.sample_base_index_o = self.output_reg("sample_base_index_o", 64)
        self.stream_active_o = self.output_reg("stream_active_o")
        self.format_error_o = self.output_reg("format_error_o")
        self.gap_error_o = self.output_reg("gap_error_o")
        self.calibration_error_o = self.output_reg("calibration_error_o")
        self.selected_range_h_o = self.output_reg("selected_range_h_o", 2)
        self.selected_range_v_o = self.output_reg("selected_range_v_o", 2)

        self.next_incident_valid = self.wire("next_incident_valid")
        self.next_incident_i_lane0 = self.wire("next_incident_i_lane0", 2 * 24)
        self.next_incident_q_lane0 = self.wire("next_incident_q_lane0", 2 * 24)
        self.next_incident_i_lane1 = self.wire("next_incident_i_lane1", 2 * 24)
        self.next_incident_q_lane1 = self.wire("next_incident_q_lane1", 2 * 24)
        self.next_sample_base = self.wire("next_sample_base", 64)
        self.next_stream_active = self.wire("next_stream_active")
        self.next_format_error = self.wire("next_format_error")
        self.next_gap_error = self.wire("next_gap_error")
        self.next_calibration_error = self.wire("next_calibration_error")
        self.next_selected_range_h = self.wire("next_selected_range_h", 2)
        self.next_selected_range_v = self.wire("next_selected_range_v", 2)

    @staticmethod
    def _resolve_echo_indices(
        entries: tuple[PhysicalChannelMapEntry, ...],
    ) -> dict[tuple[Polarization, GainRange], int]:
        indices: dict[tuple[Polarization, GainRange], int] = {}
        for gain_range, _code in ECHO_RANGE_CODES:
            for polarization in (Polarization.H, Polarization.V):
                matches = [
                    entry.index
                    for entry in entries
                    if entry.enabled
                    and entry.polarization == polarization
                    and entry.gain_range == gain_range
                    and ChannelRole.ECHO in entry.allowed_roles
                ]
                if len(matches) != 1:
                    raise ValueError(
                        "adc_channel_map must contain one echo path per polarization and range"
                    )
                if matches[0] in (3, 7):
                    raise ValueError("ADC3 and ADC7 are calibration-only and cannot be selected")
                indices[(polarization, gain_range)] = matches[0]
        return indices

    @staticmethod
    def _coefficients_are_valid(coefficients: HvCalibrationCoefficients) -> bool:
        try:
            HvCalibrationCoefficients(**coefficients.__dict__)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _slice_channel(data: Expr, channel_index: int) -> Expr:
        lsb = channel_index * 16
        return _signed(data.slice(lsb + 15, lsb))

    def _select_sample(self, lane_bus: Expr, polarization: Polarization, selected_range: Expr) -> Expr:
        return mux(
            selected_range.eq(0),
            self._slice_channel(
                lane_bus,
                self.range_indices[(polarization, GainRange.HIGH)],
            ),
            mux(
                selected_range.eq(1),
                self._slice_channel(
                    lane_bus,
                    self.range_indices[(polarization, GainRange.MID)],
                ),
                self._slice_channel(
                    lane_bus,
                    self.range_indices[(polarization, GainRange.LOW)],
                ),
            ),
        )

    def _coefficient_expr(self, polarization: Polarization, selected_range: Expr) -> Expr:
        return mux(
            selected_range.eq(0),
            ConstExpr(
                self.coefficients.for_range(polarization, GainRange.HIGH),
                24,
                signed=True,
            ),
            mux(
                selected_range.eq(1),
                ConstExpr(
                    self.coefficients.for_range(polarization, GainRange.MID),
                    24,
                    signed=True,
                ),
                ConstExpr(
                    self.coefficients.for_range(polarization, GainRange.LOW),
                    24,
                    signed=True,
                ),
            ),
        )

    def _calibrate_sample(self, lane_bus: Expr, polarization: Polarization, selected_range: Expr) -> Expr:
        sample = self._select_sample(lane_bus, polarization, selected_range)
        coefficient = self._coefficient_expr(polarization, selected_range)
        product = signed_mul(sample, coefficient, 48)
        rounded = round_shift_ties_away_from_zero(
            product,
            CALIBRATION_TO_REFLECTION_SHIFT,
            48,
        )
        return saturate_signed(rounded, 24)

    def _pack_lane_pair(self, lane_bus: Expr, selected_range_h: Expr, selected_range_v: Expr) -> Expr:
        return concat(
            (
                self._calibrate_sample(lane_bus, Polarization.V, selected_range_v),
                self._calibrate_sample(lane_bus, Polarization.H, selected_range_h),
            )
        )

    def compute(self) -> None:
        prior_fault = self.format_error_o | self.gap_error_o | self.calibration_error_o
        reserved_range = self.selected_range_h_i.eq(3) | self.selected_range_v_i.eq(3)
        invalid_coefficients = ConstExpr(int(not self.coefficients_valid), 1)
        fault_now = self.frontend_enable_i & (
            self.format_error_i | self.gap_error_i | reserved_range | invalid_coefficients
        )
        accepted = self.frontend_enable_i & self.rx_valid_i & (~prior_fault) & (~fault_now)
        zero_lane = ConstExpr(0, 2 * 24)

        self.drive(self.next_incident_valid, accepted)
        self.drive(
            self.next_incident_i_lane0,
            mux(
                accepted,
                self._pack_lane_pair(
                    self.rx_i_lane0_i,
                    self.selected_range_h_i,
                    self.selected_range_v_i,
                ),
                zero_lane,
            ),
        )
        self.drive(
            self.next_incident_q_lane0,
            mux(
                accepted,
                self._pack_lane_pair(
                    self.rx_q_lane0_i,
                    self.selected_range_h_i,
                    self.selected_range_v_i,
                ),
                zero_lane,
            ),
        )
        self.drive(
            self.next_incident_i_lane1,
            mux(
                accepted,
                self._pack_lane_pair(
                    self.rx_i_lane1_i,
                    self.selected_range_h_i,
                    self.selected_range_v_i,
                ),
                zero_lane,
            ),
        )
        self.drive(
            self.next_incident_q_lane1,
            mux(
                accepted,
                self._pack_lane_pair(
                    self.rx_q_lane1_i,
                    self.selected_range_h_i,
                    self.selected_range_v_i,
                ),
                zero_lane,
            ),
        )
        self.drive(
            self.next_sample_base,
            mux(accepted, self.sample_base_index_i, self.sample_base_index_o),
        )
        self.drive(
            self.next_stream_active,
            mux(
                prior_fault | fault_now | (~self.frontend_enable_i),
                ConstExpr(0, 1),
                self.stream_active_i | accepted,
            ),
        )
        self.drive(
            self.next_format_error,
            self.format_error_o | (self.frontend_enable_i & self.format_error_i),
        )
        self.drive(
            self.next_gap_error,
            self.gap_error_o | (self.frontend_enable_i & self.gap_error_i),
        )
        self.drive(
            self.next_calibration_error,
            self.calibration_error_o
            | (self.frontend_enable_i & (reserved_range | invalid_coefficients)),
        )
        self.drive(
            self.next_selected_range_h,
            mux(accepted, self.selected_range_h_i, self.selected_range_h_o),
        )
        self.drive(
            self.next_selected_range_v,
            mux(accepted, self.selected_range_v_i, self.selected_range_v_o),
        )

    def clock(self) -> None:
        self.update(self.incident_valid_o, self.next_incident_valid)
        self.update(self.incident_i_lane0_o, self.next_incident_i_lane0)
        self.update(self.incident_q_lane0_o, self.next_incident_q_lane0)
        self.update(self.incident_i_lane1_o, self.next_incident_i_lane1)
        self.update(self.incident_q_lane1_o, self.next_incident_q_lane1)
        self.update(self.sample_base_index_o, self.next_sample_base)
        self.update(self.stream_active_o, self.next_stream_active)
        self.update(self.format_error_o, self.next_format_error)
        self.update(self.gap_error_o, self.next_gap_error)
        self.update(self.calibration_error_o, self.next_calibration_error)
        self.update(self.selected_range_h_o, self.next_selected_range_h)
        self.update(self.selected_range_v_o, self.next_selected_range_v)
