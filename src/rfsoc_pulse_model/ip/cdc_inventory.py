"""Canonical measured CDC-15 RFDC vendor-waiver endpoint inventory."""

from __future__ import annotations


def _ipif(index: int) -> str:
    return f"rfdc_0/inst/IP2Bus_Data_reg[{index}]/D"


CDC15_MARKER_COUNTER_PAIRS = (
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc11/mrk_cntr_ff_reg[0]/C", _ipif(0)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_cntr_ff_reg[1]/C", _ipif(1)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc33/mrk_cntr_ff_reg[2]/C", _ipif(2)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc33/mrk_cntr_ff_reg[3]/C", _ipif(3)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc02/mrk_cntr_ff_reg[4]/C", _ipif(4)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc30/mrk_cntr_ff_reg[5]/C", _ipif(5)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc03/mrk_cntr_ff_reg[6]/C", _ipif(6)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc03/mrk_cntr_ff_reg[7]/C", _ipif(7)),
)
CDC15_MARKER_LOCATION_PAIRS = (
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc13/mrk_loc_ff_reg[0]/C", _ipif(16)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[1]/C", _ipif(17)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[2]/C", _ipif(18)),
    ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[3]/C", _ipif(19)),
)
_INTERNAL_DESTINATIONS = tuple(_ipif(index) for index in range(8, 16))
CDC15_ADC_INTERNAL_PAIRS = tuple(
    (f"rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/rx{tile}_u_adc/INTERNAL_FBRC_DIV2_MUX", destination)
    for tile in range(4) for destination in _INTERNAL_DESTINATIONS
)
CDC15_DAC_INTERNAL_PAIRS = tuple(
    (f"rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/tx{tile}_u_dac/INTERNAL_FBRC_MUX", destination)
    for tile in range(2) for destination in _INTERNAL_DESTINATIONS
)
CDC15_ENDPOINT_PAIRS = CDC15_MARKER_COUNTER_PAIRS + CDC15_MARKER_LOCATION_PAIRS + CDC15_ADC_INTERNAL_PAIRS + CDC15_DAC_INTERNAL_PAIRS
CDC15_CATEGORY_COUNTS = {
    "marker_counter": len(CDC15_MARKER_COUNTER_PAIRS),
    "marker_location": len(CDC15_MARKER_LOCATION_PAIRS),
    "adc_internal": len(CDC15_ADC_INTERNAL_PAIRS),
    "dac_internal": len(CDC15_DAC_INTERNAL_PAIRS),
}

if len(CDC15_ENDPOINT_PAIRS) != 60 or len(set(CDC15_ENDPOINT_PAIRS)) != 60:
    raise RuntimeError("CDC-15 inventory must contain exactly 60 unique endpoint pairs")
