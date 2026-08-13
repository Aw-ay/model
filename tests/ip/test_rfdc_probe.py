"""Contract tests for the isolated RFDC 2.6 Vivado probe."""

from __future__ import annotations

import unittest
import hashlib
import json

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_probe_output() -> bytes:
    """Small canonical raw fixture; real Vivado values are frozen after probing."""

    return b"\n".join((
        b"RFDC_PROBE\tVIVADO_VERSION\t2025.2",
        b"RFDC_PROBE\tDEVICE_PART\txczu27dr-fsve1156-2-i",
        b"RFDC_PROBE\tCELL\trfdc_0\txilinx.com:ip:usp_rf_data_converter:2.6",
        b"RFDC_PROBE\tCONFIG\tADC0_Enable\t1",
        b"RFDC_PROBE\tCONFIG\tDAC0_Enable\t1",
        b"RFDC_PROBE\tINTERFACE\tm00_axis\tMaster\taxis_rtl\t32\t250000000\trx_axis_clk\trx_peripheral_aresetn",
        b"RFDC_PROBE\tSCALAR_PIN\tclk_adc0\tO\t1\t250000000\trx_axis_clk",
        b"RFDC_PROBE\tSCALAR_PIN\ts_axi_aclk\tI\t1\t100000000\tctrl_axis_clk",
        b"RFDC_PROBE\tVALIDATE\t",
        b"RFDC_PROBE\tEND",
    )) + b"\n"


class RfdcProbeContractTests(unittest.TestCase):
    def test_public_probe_api_is_available(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (  # noqa: PLC0415
            RFDC_PROBE_VLNV,
            RfdcProbeResult,
            build_rfdc_probe_evidence,
            canonical_rfdc_probe_json_bytes,
            emit_rfdc_probe_tcl,
            parse_rfdc_probe_evidence,
        )

        self.assertEqual(RFDC_PROBE_VLNV, "xilinx.com:ip:usp_rf_data_converter:2.6")
        self.assertTrue(callable(emit_rfdc_probe_tcl))
        self.assertTrue(callable(build_rfdc_probe_evidence))
        self.assertTrue(callable(canonical_rfdc_probe_json_bytes))
        self.assertTrue(callable(parse_rfdc_probe_evidence))
        self.assertIn("provenance", RfdcProbeResult.__dataclass_fields__)

    def test_emitter_is_deterministic_exact_part_and_one_rfdc_cell(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import emit_rfdc_probe_tcl

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        first = emit_rfdc_probe_tcl(model, architecture)
        self.assertEqual(first, emit_rfdc_probe_tcl(model, architecture))
        self.assertIn("create_project rfdc_probe", first)
        self.assertIn("set probe_part {xczu27dr-fsve1156-2-i}", first)
        self.assertEqual(first.count("create_bd_cell -type ip"), 1)
        self.assertIn("xilinx.com:ip:usp_rf_data_converter:2.6 rfdc_0", first)
        self.assertIn("CONFIG.ADC0_Enable", first)
        self.assertIn("CONFIG.ADC3_Enable", first)
        self.assertIn("CONFIG.ADC0_PLL_Enable {true}", first)
        self.assertIn("CONFIG.ADC_Data_Width00 {2}", first)
        self.assertIn("CONFIG.ADC_Mixer_Type00 {2}", first)
        self.assertIn("CONFIG.DAC0_Enable", first)
        self.assertIn("CONFIG.DAC1_Enable", first)
        self.assertIn("CONFIG.DAC0_PLL_Enable {true}", first)
        self.assertIn("CONFIG.DAC_Data_Width00 {4}", first)
        self.assertIn("CONFIG.DAC_Mixer_Type00 {2}", first)
        self.assertNotIn("zynq_ultra_ps_e", first)
        self.assertNotIn("smartconnect", first)

    def test_strict_canonical_evidence_returns_task3_provenance(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            canonical_rfdc_probe_json_bytes,
            emit_rfdc_probe_tcl,
            parse_rfdc_probe_evidence,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = _raw_probe_output()
        encoded = build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=7)
        result = parse_rfdc_probe_evidence(encoded, tcl, model, architecture)
        self.assertEqual(result.provenance.vivado_version, "2025.2")
        self.assertEqual(result.provenance.probe_tcl_sha256, _sha(tcl))
        self.assertEqual(result.provenance.raw_output_sha256, _sha(raw))
        self.assertEqual(result.provenance.run_id, 7)
        self.assertEqual(result.cells, (("rfdc_0", "xilinx.com:ip:usp_rf_data_converter:2.6"),))
        self.assertFalse(result.common_rx_clock_legality_verified)
        self.assertFalse(result.mts_runtime_verified)
        self.assertEqual(encoded, canonical_rfdc_probe_json_bytes(result))

    def test_parser_fails_closed_for_noncanonical_or_wrong_probe_facts(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
            parse_rfdc_probe_evidence,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = _raw_probe_output()
        encoded = build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=7)
        for label, corrupted in (
            ("noncanonical", encoded + b"\n"),
            ("wrong_tcl", encoded),
            ("wrong_part", encoded.replace(b"xczu27dr-fsve1156-2-i", b"wrong-part")),
            ("extra_cell", encoded.replace(b'"cells":[["rfdc_0","xilinx.com:ip:usp_rf_data_converter:2.6"]]', b'"cells":[["rfdc_0","xilinx.com:ip:usp_rf_data_converter:2.6"],["other","xilinx.com:ip:axi_dma:7.1"]]')),
        ):
            with self.subTest(label=label):
                expected_tcl = b"other" if label == "wrong_tcl" else tcl
                with self.assertRaises(ValueError):
                    parse_rfdc_probe_evidence(corrupted, expected_tcl, model, architecture)

    def test_raw_parser_rejects_partial_duplicate_and_unsafe_records(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        cases = (
            b"RFDC_PROBE\tVIVADO_VERSION\t2025.2\n",
            _raw_probe_output().replace(b"RFDC_PROBE\tEND\n", b"RFDC_PROBE\tCELL\trfdc_0\txilinx.com:ip:usp_rf_data_converter:2.6\nRFDC_PROBE\tEND\n"),
            _raw_probe_output().replace(b"ADC0_Enable", b"ADC0_Enable; unsafe"),
        )
        for raw in cases:
            with self.subTest(raw=raw[:32]), self.assertRaises(ValueError):
                build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=7)

    def test_measured_vivado_2025_2_port_spellings_confirm_24_data_interfaces(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
            parse_rfdc_probe_evidence,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        data_lines = []
        for tile in range(4):
            for slice_index in range(4):
                data_lines.append(
                    f"RFDC_PROBE\tINTERFACE\tm{tile}{slice_index}_axis\tMaster\txilinx.com:interface:axis_rtl:1.0\t32\t\t\t"
                )
        for tile in range(2):
            for slice_index in range(4):
                data_lines.append(
                    f"RFDC_PROBE\tINTERFACE\ts{tile}{slice_index}_axis\tSlave\txilinx.com:interface:axis_rtl:1.0\t64\t\t\t"
                )
        raw = ("\n".join((
            "RFDC_PROBE\tVIVADO_VERSION\t2025.2",
            "RFDC_PROBE\tDEVICE_PART\txczu27dr-fsve1156-2-i",
            "RFDC_PROBE\tCELL\trfdc_0\txilinx.com:ip:usp_rf_data_converter:2.6",
            "RFDC_PROBE\tCONFIG\tADC0_Enable\t1",
            *data_lines,
            "RFDC_PROBE\tEND",
        )) + "\n").encode("utf-8")
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        result = parse_rfdc_probe_evidence(
            build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=2),
            tcl,
            model,
            architecture,
        )
        interfaces = {item.name: item for item in result.interfaces}
        adc = [item for item in interfaces.values() if item.name.startswith("m")]
        dac = [item for item in interfaces.values() if item.name.startswith("s") and item.name != "s_axi"]
        self.assertEqual(len(adc), 16)
        self.assertEqual({item.width_bits for item in adc}, {32})
        self.assertEqual(len(dac), 8)
        self.assertEqual({item.width_bits for item in dac}, {64})
        self.assertIn("m33_axis", interfaces)


if __name__ == "__main__":
    unittest.main()
