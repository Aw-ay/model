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
        self.assertIn("CONFIG.ADC_Data_Type00 {1}", first)
        self.assertIn("CONFIG.ADC_Mixer_Type00 {2}", first)
        self.assertIn("CONFIG.DAC0_Enable", first)
        self.assertIn("CONFIG.DAC1_Enable", first)
        self.assertIn("CONFIG.DAC0_PLL_Enable {true}", first)
        self.assertIn("CONFIG.DAC_Data_Width00 {4}", first)
        self.assertIn("CONFIG.DAC_Data_Type00 {0}", first)
        self.assertIn("CONFIG.DAC_Mixer_Type00 {2}", first)
        self.assertIn("get_msg_config -severity WARNING -count", first)
        self.assertIn("CURRENT_RUN_COUNT", first)
        self.assertNotIn("report_messages", first)
        self.assertLess(first.index("set rfdc_probe_message_base(WARNING)"), first.index("set_property -dict"))
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
        raw = self._measured_raw_fixture()
        encoded = build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=7)
        result = parse_rfdc_probe_evidence(encoded, tcl, model, architecture)
        self.assertEqual(result.provenance.vivado_version, "2025.2")
        self.assertEqual(result.provenance.probe_tcl_sha256, _sha(tcl))
        self.assertEqual(result.provenance.raw_output_sha256, _sha(raw))
        self.assertEqual(result.provenance.run_id, 7)
        self.assertEqual(result.cells, (("rfdc_0", "xilinx.com:ip:usp_rf_data_converter:2.6"),))
        self.assertEqual(result.messages, (("INFO", "PROBE_START", "clean"),))
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
        raw = self._measured_raw_fixture()
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

    def test_measured_inventory_rejects_missing_extra_and_mutated_internal_objects(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = self._measured_raw_fixture()
        mutations = {
            "missing_interface": raw.replace(b"RFDC_PROBE\tINTERFACE\tm00_axis", b"RFDC_PROBE\tREMOVED\tm00_axis", 1),
            "extra_interface": raw.replace(b"RFDC_PROBE\tEND", b"RFDC_PROBE\tINTERFACE\textra_axis\tMaster\txilinx.com:interface:axis_rtl:1.0\t32\t\t\nRFDC_PROBE\tEND"),
            "swapped_axis_mode": raw.replace(b"m00_axis\tMaster", b"m00_axis\tSlave", 1),
            "missing_scalar": raw.replace(b"RFDC_PROBE\tSCALAR_PIN\tclk_adc0", b"RFDC_PROBE\tREMOVED\tclk_adc0", 1),
            "extra_scalar": raw.replace(b"RFDC_PROBE\tEND", b"RFDC_PROBE\tSCALAR_PIN\textra\tI\t1\t\t\nRFDC_PROBE\tEND"),
            "wrong_scalar_width": raw.replace(b"s_axi_araddr\tI\t18", b"s_axi_araddr\tI\t17", 1),
        }
        for name, corrupted in mutations.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_rfdc_probe_evidence(corrupted, tcl, model, architecture, run_id=2)

    def test_authority_bound_config_rejects_wrong_or_missing_semantics(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = self._measured_raw_fixture()
        mutations = {
            "adc_nco": (b"ADC_NCO_Freq00\t2.800", b"ADC_NCO_Freq00\t1.000"),
            "adc_decimation": (b"ADC_Decimation_Mode00\t8", b"ADC_Decimation_Mode00\t4"),
            "adc_data_type": (b"ADC_Data_Type00\t1", b"ADC_Data_Type00\t0"),
            "dac_mixer": (b"DAC_Mixer_Mode00\t0", b"DAC_Mixer_Mode00\t2"),
            "dac_data_type": (b"DAC_Data_Type00\t0", b"DAC_Data_Type00\t1"),
            "dac_width": (b"DAC_Data_Width00\t4", b"DAC_Data_Width00\t2"),
            "fabric": (b"ADC0_Fabric_Freq\t250.000", b"ADC0_Fabric_Freq\t125.000"),
            "pll": (b"ADC0_PLL_Enable\ttrue", b"ADC0_PLL_Enable\tfalse"),
            "missing_config": (b"RFDC_PROBE\tCONFIG\tADC_NCO_Freq00\t2.800", b"RFDC_PROBE\tREMOVED\tADC_NCO_Freq00\t2.800"),
            "duplicate_config": (b"RFDC_PROBE\tEND", b"RFDC_PROBE\tCONFIG\tADC_NCO_Freq00\t2.800\nRFDC_PROBE\tEND"),
            "validation_error": (b"RFDC_PROBE\tEND", b"RFDC_PROBE\tVALIDATE\tvalidation_failure\nRFDC_PROBE\tEND"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_rfdc_probe_evidence(raw.replace(old, new, 1), tcl, model, architecture, run_id=2)

    def test_message_records_reject_warning_critical_and_error(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = self._measured_raw_fixture()
        for severity in (b"WARNING", b"CRITICAL_WARNING", b"ERROR"):
            corrupted = raw.replace(
                b"RFDC_PROBE\tEND",
                b"RFDC_PROBE\tMESSAGE\t" + severity + b"\tIP_Flow_19_3374\tdiagnostic\nRFDC_PROBE\tEND",
            )
            with self.subTest(severity=severity), self.assertRaises(ValueError):
                build_rfdc_probe_evidence(corrupted, tcl, model, architecture, run_id=2)

    def test_message_records_reject_duplicate_unsafe_and_noncanonical_shapes(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        raw = self._measured_raw_fixture()
        cases = (
            raw.replace(b"RFDC_PROBE\tEND", b"RFDC_PROBE\tMESSAGE\tINFO\tID\tfirst\nRFDC_PROBE\tMESSAGE\tINFO\tID\tsecond\nRFDC_PROBE\tEND"),
            raw.replace(b"RFDC_PROBE\tEND", b"RFDC_PROBE\tMESSAGE\tINFO\tID\tunsafe;message\nRFDC_PROBE\tEND"),
            raw.replace(b"RFDC_PROBE\tEND", b"RFDC_PROBE\tMESSAGE\tINFO\tID\nRFDC_PROBE\tEND"),
        )
        for corrupted in cases:
            with self.subTest(corrupted=corrupted[-80:]), self.assertRaises(ValueError):
                build_rfdc_probe_evidence(corrupted, tcl, model, architecture, run_id=2)

    def test_canonical_evidence_parser_rechecks_message_and_config_contracts(self) -> None:
        from rfsoc_pulse_model.ip.rfdc_probe import (
            build_rfdc_probe_evidence,
            emit_rfdc_probe_tcl,
            parse_rfdc_probe_evidence,
        )

        model = ModelConfig.load_default()
        architecture = HardwareArchitectureConfig.load_default()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        encoded = build_rfdc_probe_evidence(self._measured_raw_fixture(), tcl, model, architecture, run_id=2)
        for name, old, new in (
            ("warning", b'[["INFO","PROBE_START","clean"]]', b'[["WARNING","PROBE_START","clean"]]'),
            ("data_type", b'"ADC_Data_Type00","1"', b'"ADC_Data_Type00","0"'),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_rfdc_probe_evidence(encoded.replace(old, new, 1), tcl, model, architecture)

    @staticmethod
    def _measured_raw_fixture() -> bytes:
        """Complete exact classification measured from Vivado 2025.2 run ID 2."""

        records = [
            "RFDC_PROBE\tVIVADO_VERSION\t2025.2",
            "RFDC_PROBE\tDEVICE_PART\txczu27dr-fsve1156-2-i",
            "RFDC_PROBE\tCELL\trfdc_0\txilinx.com:ip:usp_rf_data_converter:2.6",
            "RFDC_PROBE\tMESSAGE\tINFO\tPROBE_START\tclean",
        ]
        for tile in range(4):
            records.extend((
                f"RFDC_PROBE\tCONFIG\tADC{tile}_Enable\t1",
                f"RFDC_PROBE\tCONFIG\tADC{tile}_PLL_Enable\ttrue",
                f"RFDC_PROBE\tCONFIG\tADC{tile}_Sampling_Rate\t4.000",
                f"RFDC_PROBE\tCONFIG\tADC{tile}_Fabric_Freq\t250.000",
            ))
        for tile in range(2):
            records.extend((
                f"RFDC_PROBE\tCONFIG\tDAC{tile}_Enable\t1",
                f"RFDC_PROBE\tCONFIG\tDAC{tile}_PLL_Enable\ttrue",
                f"RFDC_PROBE\tCONFIG\tDAC{tile}_Sampling_Rate\t4.000",
                f"RFDC_PROBE\tCONFIG\tDAC{tile}_Fabric_Freq\t250.000",
            ))
        for tile in range(4):
            for slice_index in range(4):
                suffix = f"{tile}{slice_index}"
                records.extend((
                    f"RFDC_PROBE\tCONFIG\tADC_Slice{suffix}_Enable\ttrue",
                    f"RFDC_PROBE\tCONFIG\tADC_Data_Type{suffix}\t1",
                    f"RFDC_PROBE\tCONFIG\tADC_Decimation_Mode{suffix}\t8",
                    f"RFDC_PROBE\tCONFIG\tADC_Data_Width{suffix}\t2",
                    f"RFDC_PROBE\tCONFIG\tADC_Mixer_Type{suffix}\t2",
                    f"RFDC_PROBE\tCONFIG\tADC_Mixer_Mode{suffix}\t0",
                    f"RFDC_PROBE\tCONFIG\tADC_NCO_Freq{suffix}\t2.800",
                    f"RFDC_PROBE\tINTERFACE\tm{suffix}_axis\tMaster\txilinx.com:interface:axis_rtl:1.0\t32\t\t\t",
                ))
        for tile in range(2):
            for slice_index in range(4):
                suffix = f"{tile}{slice_index}"
                records.extend((
                    f"RFDC_PROBE\tCONFIG\tDAC_Slice{suffix}_Enable\ttrue",
                    f"RFDC_PROBE\tCONFIG\tDAC_Data_Type{suffix}\t0",
                    f"RFDC_PROBE\tCONFIG\tDAC_Interpolation_Mode{suffix}\t8",
                    f"RFDC_PROBE\tCONFIG\tDAC_Data_Width{suffix}\t4",
                    f"RFDC_PROBE\tCONFIG\tDAC_Mixer_Type{suffix}\t2",
                    f"RFDC_PROBE\tCONFIG\tDAC_Mixer_Mode{suffix}\t0",
                    f"RFDC_PROBE\tCONFIG\tDAC_NCO_Freq{suffix}\t2.800",
                    f"RFDC_PROBE\tINTERFACE\ts{suffix}_axis\tSlave\txilinx.com:interface:axis_rtl:1.0\t64\t\t\t",
                ))
        for name in ("adc0_clk", "adc1_clk", "adc2_clk", "adc3_clk", "dac0_clk", "dac1_clk"):
            records.append(f"RFDC_PROBE\tINTERFACE\t{name}\tSlave\txilinx.com:interface:diff_clock_rtl:1.0\t0\t\t\t")
        records.append("RFDC_PROBE\tINTERFACE\ts_axi\tSlave\txilinx.com:interface:aximm_rtl:1.0\t0\t\t\t")
        records.append("RFDC_PROBE\tINTERFACE\tsysref_in\tSlave\txilinx.com:display_usp_rf_data_converter:diff_pins_rtl:1.0\t0\t\t\t")
        for tile in range(4):
            for suffix in ("01", "23"):
                records.append(f"RFDC_PROBE\tINTERFACE\tvin{tile}_{suffix}\tSlave\txilinx.com:interface:diff_analog_io_rtl:1.0\t0\t\t\t")
        for tile in range(2):
            for slice_index in range(4):
                records.append(f"RFDC_PROBE\tINTERFACE\tvout{tile}{slice_index}\tMaster\txilinx.com:interface:diff_analog_io_rtl:1.0\t0\t\t\t")
        scalar: dict[str, tuple[str, int]] = {"irq": ("O", 1)}
        for tile in range(4):
            scalar[f"adc{tile}_clk_n"] = ("I", 1); scalar[f"adc{tile}_clk_p"] = ("I", 1); scalar[f"clk_adc{tile}"] = ("O", 1)
            for slice_index in range(4):
                suffix = f"{tile}{slice_index}"
                scalar[f"m{suffix}_axis_tdata"] = ("O", 32); scalar[f"m{suffix}_axis_tready"] = ("I", 1); scalar[f"m{suffix}_axis_tvalid"] = ("O", 1)
            scalar[f"m{tile}_axis_aclk"] = ("I", 1); scalar[f"m{tile}_axis_aresetn"] = ("I", 1)
        for tile in range(2):
            scalar[f"dac{tile}_clk_n"] = ("I", 1); scalar[f"dac{tile}_clk_p"] = ("I", 1); scalar[f"clk_dac{tile}"] = ("O", 1)
            for slice_index in range(4):
                suffix = f"{tile}{slice_index}"
                scalar[f"s{suffix}_axis_tdata"] = ("I", 64); scalar[f"s{suffix}_axis_tready"] = ("O", 1); scalar[f"s{suffix}_axis_tvalid"] = ("I", 1)
            scalar[f"s{tile}_axis_aclk"] = ("I", 1); scalar[f"s{tile}_axis_aresetn"] = ("I", 1)
        scalar.update({
            "s_axi_aclk": ("I", 1), "s_axi_aresetn": ("I", 1), "s_axi_araddr": ("I", 18), "s_axi_arready": ("O", 1), "s_axi_arvalid": ("I", 1), "s_axi_awaddr": ("I", 18), "s_axi_awready": ("O", 1), "s_axi_awvalid": ("I", 1), "s_axi_bready": ("I", 1), "s_axi_bresp": ("O", 2), "s_axi_bvalid": ("O", 1), "s_axi_rdata": ("O", 32), "s_axi_rready": ("I", 1), "s_axi_rresp": ("O", 2), "s_axi_rvalid": ("O", 1), "s_axi_wdata": ("I", 32), "s_axi_wready": ("O", 1), "s_axi_wstrb": ("I", 4), "s_axi_wvalid": ("I", 1), "sysref_in_n": ("I", 1), "sysref_in_p": ("I", 1),
        })
        for tile in range(4):
            for suffix in ("01", "23"):
                scalar[f"vin{tile}_{suffix}_n"] = ("I", 1); scalar[f"vin{tile}_{suffix}_p"] = ("I", 1)
        for tile in range(2):
            for slice_index in range(4):
                scalar[f"vout{tile}{slice_index}_n"] = ("O", 1); scalar[f"vout{tile}{slice_index}_p"] = ("O", 1)
        records.extend(f"RFDC_PROBE\tSCALAR_PIN\t{name}\t{direction}\t{width}\t\t" for name, (direction, width) in sorted(scalar.items()))
        records.append("RFDC_PROBE\tEND")
        return ("\n".join(records) + "\n").encode("utf-8")

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
        raw = self._measured_raw_fixture()
        tcl = emit_rfdc_probe_tcl(model, architecture).encode("utf-8")
        result = parse_rfdc_probe_evidence(
            build_rfdc_probe_evidence(raw, tcl, model, architecture, run_id=2),
            tcl,
            model,
            architecture,
        )
        interfaces = {item.name: item for item in result.interfaces}
        adc = [item for item in interfaces.values() if item.name.startswith("m")]
        dac = [item for item in interfaces.values() if item.name.startswith(("s0", "s1")) and item.name.endswith("_axis")]
        self.assertEqual(len(adc), 16)
        self.assertEqual({item.width_bits for item in adc}, {32})
        self.assertEqual(len(dac), 8)
        self.assertEqual({item.width_bits for item in dac}, {64})
        self.assertIn("m33_axis", interfaces)


if __name__ == "__main__":
    unittest.main()
