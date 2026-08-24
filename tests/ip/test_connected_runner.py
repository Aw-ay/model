"""Transactional lifecycle tests using an injected fake Vivado launcher."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from tests.ip.test_connected import authority_fixture, fixture, sha
from tests.ip.test_connected_tcl import probe_result


def readback_bytes(artifacts):
    """Fake Vivado protocol output, derived from generated request/artifacts."""
    from rfsoc_pulse_model.ip.connected import parse_connected_request
    request = parse_connected_request(artifacts.request_bytes)
    lines = [
        f"CONNECTED_READBACK\tMETA\trequest_sha256\t{artifacts.request_sha256}",
        f"CONNECTED_READBACK\tMETA\trealization_tcl_sha256\t{artifacts.realization_tcl_sha256}",
        f"CONNECTED_READBACK\tMETA\tverification_tcl_sha256\t{artifacts.verification_tcl_sha256}",
        f"CONNECTED_READBACK\tMETA\tvivado_version\t{request.vivado_version}",
        f"CONNECTED_READBACK\tMETA\tdevice_part\t{request.device_part}",
        "CONNECTED_READBACK\tMETA\tsynthesis_mode\tout_of_context",
        "CONNECTED_READBACK\tMETA\taxis_boundary\tbd_external_interfaces",
        "CONNECTED_READBACK\tMETA\ttiming_scope\tooc_boundary_only",
    ]
    lines += [f"CONNECTED_READBACK\tCELL\t{x.name}\t{x.vlnv}" for x in request.cells]
    lines += [f"CONNECTED_READBACK\tCONFIG\t{k}\t{v}" for k, v in artifacts.rfdc_properties]
    lines += [f"CONNECTED_READBACK\tPS_CONFIG\t{k}\t{v}" for k, v in artifacts.ps_properties]
    lines += [f"CONNECTED_READBACK\tDATA\t{x.name}\t{'Master' if x.direction == 'master' else 'Slave'}\txilinx.com:interface:axis_rtl:1.0\t{x.width_bits // 8}" for x in request.interfaces]
    names = {x.name for x in request.interfaces}
    lines += [f"CONNECTED_READBACK\tRF\t{x.name}\t{x.mode}\t{x.vlnv}" for x in artifacts.rfdc_interfaces if x.name not in names and (x.name in {'adc0_clk','adc1_clk','adc2_clk','adc3_clk','dac0_clk','dac1_clk','sysref_in'} or x.name.startswith(('vin','vout')))]
    lines += [f"CONNECTED_READBACK\tPORT\t{x.name}\t{x.name}_0" for x in request.interfaces]
    lines += [f"CONNECTED_READBACK\tPORT\t{x.name}\t{x.name}_0" for x in artifacts.external_rf_interfaces]
    lines += ["CONNECTED_READBACK\tINVERTER\tC_OPERATION\tnot\tC_SIZE\t1", "CONNECTED_READBACK\tCONCAT\tNUM_PORTS\t1"]
    # Vivado 2025.2 canonicalizes the realized net names from their source
    # pins/cells.  Keep the fake protocol aligned with the measured machine
    # readback instead of masking that normalization in the runner.
    lines += [f"CONNECTED_READBACK\tCLOCK\t{x.domain}\t{member}\t{x.members[0].replace('/', '_')}" for x in request.clocks for member in x.members]
    lines += [f"CONNECTED_READBACK\tRESET\t{x.domain}\t{member}\t{x.dcm_locked_members[-1].split('/')[0]}_peripheral_aresetn" for x in request.resets for member in x.members]
    lines += [f"CONNECTED_READBACK\tLOCK\t{x.domain}\t{x.dcm_locked_pin}\t{x.dcm_locked_pin}_1" for x in request.resets]
    lines += ["CONNECTED_READBACK\tADDRESS\trfdc_0/s_axi/Reg\tsegment", "CONNECTED_READBACK\tIRQ\trfdc_0/irq\tirq_concat_0/In0\tirq_concat_0/dout\tzynq_ultra_ps_e_0/pl_ps_irq0"]
    lines += [f"CONNECTED_READBACK\tMTS\t{k}\t{v}" for k, v in artifacts.mts_properties]
    lines += [f"CONNECTED_READBACK\tBOOL\t{name}\t{value}" for name, value in (("validate_bd_design_passed","true"),("synthesis_completed","true"),("mts_runtime_verified","false"))]
    return ("\n".join(lines) + "\nCONNECTED_READBACK\tEND\n").encode("utf-8")


def write_clean_reports(attempt) -> None:
    """Measured Vivado 2025.2 report forms accepted by the fail-closed parser."""
    contents = {
        "cdc": clean_cdc_report(),
        "clock_interaction": clean_clock_report(),
        "timing_summary": clean_timing_report(),
        "utilization": clean_utilization_report(),
    }
    for name, path in attempt.report_paths.items():
        path.write_bytes(contents[name])


def report_header(command: str) -> str:
    return "\n".join((
        "Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.",
        "----------------------------------------",
        "| Tool Version      : Vivado v.2025.2 (win64) Build 6299465 Fri Nov 14 19:35:11 GMT 2025",
        "| Date              : Thu Aug 20 23:08:34 2026",
        "| Host              : measured-host",
        f"| Command           : {command}",
        "| Design            : connected_rfdc_shell_wrapper",
        "| Device            : xczu27dr-fsve1156",
        "| Speed File        : -2 PRODUCTION",
        "| Design State      : Synthesized",
        "----------------------------------------",
        "",
    ))


def vivado_report_bytes(report: str) -> bytes:
    """Vivado 2025.2 on Windows writes reports with CRLF line endings."""
    return report.replace("\n", "\r\n").encode("utf-8")


def clean_cdc_report() -> bytes:
    return vivado_report_bytes(report_header("report_cdc -details -file ./cdc.rpt") + """CDC Report

ID     Severity  Count  Description
-----  --------  -----  ------------------------------------------
CDC-3  Info          1  1-bit synchronized with ASYNC_REG property

Source Clock: clk_a
Destination Clock: clk_b
CDC Type: No Common Primary Clock

Row  ID     Severity  Description                                 Depth  Exception            Source (From)        Destination (To)
---  -----  --------  ------------------------------------------  -----  -------------------  -------------------  ------------------
  1  CDC-3  Info      1-bit synchronized with ASYNC_REG property      2  Asynch Clock Groups  source_toggle_reg/C  sync_stage_1_reg/D
""")


def unsafe_cdc_report() -> bytes:
    return clean_cdc_report().replace(
        b"CDC-3  Info          1  1-bit synchronized with ASYNC_REG property",
        b"CDC-1  Critical      1  1-bit unknown CDC circuitry",
    ).replace(
        b"CDC-3  Info      1-bit synchronized with ASYNC_REG property      2",
        b"CDC-1  Critical  1-bit unknown CDC circuitry                         0",
    )


def waived_vendor_cdc_report() -> bytes:
    return vivado_report_bytes(report_header(
        "report_cdc -details -show_waiver -file ./cdc.rpt"
    ) + """CDC Report

ID     Severity  Count  Description
-----  --------  -----  ------------------------------------------
CDC-3  Info          1  1-bit synchronized with ASYNC_REG property

ID      Waived Endpoints
------  ----------------
CDC-13                 1

Source Clock: clk_pl_0
Destination Clock: RFADC0_CLK
CDC Type: No Common Primary Clock

Row  ID     Severity  Description                                 Depth  Exception    Source (From)                                                                 Destination (To)                                                                 Waived
---  -----  --------  ------------------------------------------  -----  -----------  ----------------------------------------------------------------------------  -----------------------------------------------------------------------------  ------
  1  CDC-13  Critical  1-bit CDC path on a non-FD primitive            0  False Path  connected_rfdc_shell_i/rfdc_0/inst/adc0_cmn_control_ff_reg[12]/C  connected_rfdc_shell_i/rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/rx0_u_adc/CONTROL_COMMON[12]  Y
  2  CDC-3   Info      1-bit synchronized with ASYNC_REG property      2  False Path  source_toggle_reg/C                                                     sync_stage_1_reg/D                                                                  N
""")


def waived_vendor_reset_cdc_report() -> bytes:
    return vivado_report_bytes(report_header(
        "report_cdc -details -show_waiver -file ./cdc.rpt"
    ) + """CDC Report

ID     Severity  Count  Description
-----  --------  -----  ------------------------------------------
CDC-3  Info          1  1-bit synchronized with ASYNC_REG property
CDC-11 Critical      1  Fan-out from launch flop to destination clock

ID      Waived Endpoints
------  ----------------
CDC-11                 1

Source Clock: RFADC0_CLK
Destination Clock: clk_pl_0
CDC Type: No Common Primary Clock

Row  ID     Severity  Description                                 Depth  Exception    Source (From)                                                                 Destination (To)                                                                 Waived
---  -----  --------  ------------------------------------------  -----  -----------  ----------------------------------------------------------------------------  -----------------------------------------------------------------------------  ------
  1  CDC-11 Critical  Fan-out from launch flop to destination clock   4  False Path  connected_rfdc_shell_i/rx_reset_0/U0/ACTIVE_LOW_PR_OUT_DFF[0].FDRE_PER_N/C  connected_rfdc_shell_i/rfdc_0/inst/cdc_adc0_clk_valid_i/syncstages_ff_reg[0]/D  Y
  2  CDC-3  Info      1-bit synchronized with ASYNC_REG property      2  False Path  source_toggle_reg/C                                                     sync_stage_1_reg/D                                                                  N
""")


def measured_cdc15_pairs() -> tuple[tuple[str, str], ...]:
    """The 60 CDC-15 endpoint suffix pairs measured from the RFDC OOC run."""
    ipif = lambda index: f"rfdc_0/inst/IP2Bus_Data_reg[{index}]/D"
    marker_counter = (
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc11/mrk_cntr_ff_reg[0]/C", ipif(0)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_cntr_ff_reg[1]/C", ipif(1)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc33/mrk_cntr_ff_reg[2]/C", ipif(2)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc33/mrk_cntr_ff_reg[3]/C", ipif(3)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc02/mrk_cntr_ff_reg[4]/C", ipif(4)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc30/mrk_cntr_ff_reg[5]/C", ipif(5)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc03/mrk_cntr_ff_reg[6]/C", ipif(6)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc03/mrk_cntr_ff_reg[7]/C", ipif(7)),
    )
    marker_location = (
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc13/mrk_loc_ff_reg[0]/C", ipif(16)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[1]/C", ipif(17)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[2]/C", ipif(18)),
        ("rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc12/mrk_loc_ff_reg[3]/C", ipif(19)),
    )
    internal_destinations = tuple(ipif(index) for index in range(8, 16))
    adc_internal = tuple(
        (f"rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/rx{tile}_u_adc/INTERNAL_FBRC_DIV2_MUX", destination)
        for tile in range(4) for destination in internal_destinations
    )
    dac_internal = tuple(
        (f"rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/tx{tile}_u_dac/INTERNAL_FBRC_MUX", destination)
        for tile in range(2) for destination in internal_destinations
    )
    assert tuple(map(len, (marker_counter, marker_location, adc_internal, dac_internal))) == (8, 4, 32, 16)
    return marker_counter + marker_location + adc_internal + dac_internal


def measured_cdc15_report(*, extra_pair: tuple[str, str] | None = None) -> bytes:
    """A canonical CDC-15 fixture with optional regex-legal inventory drift."""
    pairs = measured_cdc15_pairs() + (() if extra_pair is None else (extra_pair,))
    rows = "\n".join(
        "{row:3d}  CDC-15  Warning   Clock enable controlled CDC structure detected      0  False Path  "
        "connected_rfdc_shell_i/{source}  connected_rfdc_shell_i/{destination}  Y".format(
            row=index, source=source, destination=destination,
        )
        for index, (source, destination) in enumerate(pairs, 1)
    )
    return vivado_report_bytes(report_header(
        "report_cdc -details -show_waiver -file ./cdc.rpt"
    ) + f"""CDC Report

ID      Waived Endpoints
------  ----------------
CDC-15                {len(pairs)}

Source Clock: RFADC0_CLK
Destination Clock: clk_pl_0
CDC Type: No Common Primary Clock

Row  ID      Severity  Description                                     Depth  Exception   Source (From)  Destination (To)  Waived
---  ------  --------  ----------------------------------------------  -----  ----------  -------------  ----------------  ------
{rows}
""")


def clean_clock_report() -> bytes:
    return vivado_report_bytes(report_header("report_clock_interaction -file ./clock_interaction.rpt") + """Clock Interaction Report

Clock Interaction Table
-----------------------

From Clock    To Clock      Clock Edges  WNS(ns)  TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints  WNS Path Requirement(ns)  Clock-Pair Classification  Inter-Clock Constraints
------------  ------------  -----------  -------  -------  ---------------------  -------------------  ------------------------  -------------------------  -----------------------
clk_a         clk_a         rise - rise     9.54     0.00                      0                    1                     10.00  Clean                Timed
clk_a         clk_b                                                  0            1                   Ignored              Asynchronous Groups
clk_b         clk_b         rise - rise     7.57     0.00                      0                    1                      8.00  Clean                Timed

""")


_CHECKS = (
    "no_clock", "constant_clock", "pulse_width_clock",
    "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay",
    "multiple_clock", "generated_clocks", "loops", "partial_input_delay",
    "partial_output_delay", "latch_loops",
)


def clean_timing_report() -> bytes:
    toc = "\n".join(f"{index}. checking {name} (0)" for index, name in enumerate(_CHECKS, 1))
    details = "\n\n".join(
        f"{index}. checking {name} (0)\n------------------------\n There are 0 affected objects."
        for index, name in enumerate(_CHECKS, 1)
    )
    return vivado_report_bytes(report_header(
        "report_timing_summary -report_unconstrained -no_detailed_paths -file ./timing_summary.rpt"
    ) + f"""Timing Summary Report

check_timing report

Table of Contents
-----------------
{toc}

{details}

Timing constraints are not met.

| Unconstrained Path Table
| ------------------------
----------------------------------------

Path Group    From Clock    To Clock
----------    ----------    --------

""")


def clean_utilization_report() -> bytes:
    return vivado_report_bytes(report_header("report_utilization -file ./utilization.rpt") + """Utilization Estimates

+----------------------------+------+-------+-----------+-------+
| Site Type                  | Used | Fixed | Available | Util% |
+----------------------------+------+-------+-----------+-------+
| CLB LUTs                   | 10   | 0     | 100       | 10.00%|
| CLB Registers              | 20   | 0     | 200       | 10.00%|
| Bonded IOB                 | 0    | 0     | 728       | 0.00% |
+----------------------------+------+-------+-----------+-------+

""")


class ConnectedRunnerTest(unittest.TestCase):
    def test_accepts_measured_vivado_report_table_variants(self) -> None:
        """The parser accepts the real 2025.2 table columns and path class."""
        from rfsoc_pulse_model.ip.connected_runner import (
            _parse_cdc_report,
            _parse_clock_interaction_report,
            _parse_utilization_report,
        )

        clean_scope = vivado_report_bytes(report_header(
            "report_cdc -from [get_clocks -quiet clk_a] -to "
            "[get_clocks -quiet clk_a] -details -file ./cdc.rpt"
        ) + """CDC Report

All paths are Safely Timed.
""")
        self.assertEqual(_parse_cdc_report(clean_scope.decode("utf-8")), set())

        utilization_header = report_header(
            "report_utilization -file ./utilization.rpt"
        ).replace(
            "| Device            : xczu27dr-fsve1156",
            "| Device            : xczu27dr-fsve1156-2-i",
        )
        utilization = vivado_report_bytes(utilization_header + """Utilization Design Information

|          Site Type         |  Used | Fixed | Prohibited | Available | Util% |
| CLB LUTs                   |    10 |     0 |          0 |       100 | 10.00 |
| CLB Registers              |    20 |     0 |          0 |       200 | 10.00 |
| Bonded IOB                 |     0 |     0 |          0 |       728 | 0.00  |

""")
        self.assertEqual(_parse_utilization_report(utilization.decode("utf-8")), 0)

        clock = vivado_report_bytes(report_header(
            "report_clock_interaction -file ./clock_interaction.rpt"
        ) + """Clock Interaction Report

Clock Interaction Table
-----------------------

From Clock    To Clock      Clock-Pair Classification  Inter-Clock Constraints
------------  ------------  -------------------------  ----------------------
clk_a         clk_a         Clean                      Timed
clk_a         clk_b         Ignored                    False Path

""")
        _parse_clock_interaction_report(clock.decode("utf-8"), {("clk_a", "clk_b")})

    def test_utilization_requires_exactly_one_zero_bonded_iob_row(self) -> None:
        """Omitting or using a package IOB must block structural evidence."""
        from rfsoc_pulse_model.ip.connected_runner import _parse_utilization_report

        clean = clean_utilization_report().decode("utf-8").replace("\r\n", "\n")
        missing = clean.replace(
            "| Bonded IOB                 | 0    | 0     | 728       | 0.00% |\n",
            "",
        )
        used_one = clean.replace(
            "| Bonded IOB                 | 0    | 0     | 728       | 0.00% |",
            "| Bonded IOB                 | 1    | 0     | 728       | 0.14% |",
        )
        duplicate = clean.replace(
            "+----------------------------+------+-------+-----------+-------+\n\n",
            "| Bonded IOB                 | 0    | 0     | 728       | 0.00% |\n"
            "+----------------------------+------+-------+-----------+-------+\n\n",
        )

        with self.assertRaisesRegex(ValueError, "Bonded IOB"):
            _parse_utilization_report(missing)
        with self.assertRaisesRegex(ValueError, "Bonded IOB"):
            _parse_utilization_report(used_one)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _parse_utilization_report(duplicate)

    def test_clock_interaction_accepts_clean_partial_false_path(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import _parse_clock_interaction_report

        clock = vivado_report_bytes(report_header(
            "report_clock_interaction -file ./clock_interaction.rpt"
        ) + """Clock Interaction Report

Clock Interaction Table
-----------------------

From Clock    To Clock      Clock-Pair Classification  Inter-Clock Constraints
------------  ------------  -------------------------  ----------------------
clk_a         clk_a         Clean                      Partial False Path

""")
        _parse_clock_interaction_report(clock.decode("utf-8"), set())

    def test_cdc_accepts_only_exact_vendor_waived_internal_paths(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import _parse_cdc_report

        self.assertEqual(
            _parse_cdc_report(waived_vendor_cdc_report().decode("utf-8").replace(" -show_waiver", "")),
            {("clk_pl_0", "RFADC0_CLK")},
        )

        unsafe = waived_vendor_cdc_report().decode("utf-8").replace(
            "CDC-13  Critical  1-bit CDC path on a non-FD primitive            0  False Path  "
            "connected_rfdc_shell_i/rfdc_0/inst/adc0_cmn_control_ff_reg[12]/C  "
            "connected_rfdc_shell_i/rfdc_0/inst/connected_rfdc_shell_rfdc_0_0_rf_wrapper_i/rx0_u_adc/CONTROL_COMMON[12]  Y",
            "CDC-11  Critical  Fan-out from launch flop to destination clock       0  False Path  "
            "connected_rfdc_shell_i/rx_reset_0/U0/ACTIVE_LOW_PR_OUT_DFF[0].FDRE_PER_N/C  "
            "connected_rfdc_shell_i/rfdc_0/inst/cdc_adc4_clk_valid_i/syncstages_ff_reg[0]/D  Y",
        ).replace("CDC-13                 1", "CDC-11                 1")
        with self.assertRaisesRegex(ValueError, "vendor waiver"):
            _parse_cdc_report(unsafe)

    def test_cdc15_requires_the_measured_exact_endpoint_inventory(self) -> None:
        """A legal-looking extra CDC-15 row must not broaden the vendor waiver."""
        from rfsoc_pulse_model.ip.cdc_inventory import CDC15_ENDPOINT_PAIRS
        from rfsoc_pulse_model.ip.connected_runner import _parse_cdc_report

        canonical = measured_cdc15_pairs()
        self.assertEqual(len(canonical), 60)
        self.assertEqual(CDC15_ENDPOINT_PAIRS, canonical)
        self.assertEqual(_parse_cdc_report(measured_cdc15_report().decode("utf-8")), {
            ("RFADC0_CLK", "clk_pl_0"),
        })
        with self.assertRaisesRegex(ValueError, "CDC-15.*inventory"):
            _parse_cdc_report(measured_cdc15_report(extra_pair=(
                "rfdc_0/inst/i_rf_conv_mt_mrk_counter_adc99/mrk_cntr_ff_reg[8]/C",
                "rfdc_0/inst/IP2Bus_Data_reg[20]/D",
            )).decode("utf-8"))

    def test_cdc15_waiver_report_requires_all_measured_rows(self) -> None:
        """A post-waiver report cannot omit the complete CDC-15 inventory."""
        from rfsoc_pulse_model.ip.connected_runner import _parse_cdc_report

        with self.assertRaisesRegex(ValueError, "CDC-15.*inventory"):
            _parse_cdc_report(waived_vendor_cdc_report().decode("utf-8"))

    def test_cdc15_waiver_report_rejects_empty_safely_timed_report(self) -> None:
        """The early safely-timed branch must not bypass the CDC-15 gate."""
        from rfsoc_pulse_model.ip.connected_runner import _parse_cdc_report

        empty_show_waiver = vivado_report_bytes(report_header(
            "report_cdc -details -show_waiver -file ./cdc.rpt"
        ) + """CDC Report

All paths are Safely Timed.
""")
        with self.assertRaisesRegex(ValueError, "CDC-15.*inventory"):
            _parse_cdc_report(empty_show_waiver.decode("utf-8"))

    def test_cdc_accepts_exact_rfdc_clk_valid_reset_waiver(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import _parse_cdc_report

        self.assertEqual(
            _parse_cdc_report(waived_vendor_reset_cdc_report().decode("utf-8").replace(" -show_waiver", "")),
            {("RFADC0_CLK", "clk_pl_0")},
        )

    def test_ooc_timing_defers_boundary_only_checks(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import _parse_timing_summary_report

        report = clean_timing_report().decode("utf-8")
        for name, count in (
            ("no_clock", 10), ("no_input_delay", 515), ("no_output_delay", 536),
        ):
            report = report.replace(
                f"checking {name} (0)", f"checking {name} ({count})",
            )
        _parse_timing_summary_report(report, ooc_boundary=True)
        with self.assertRaisesRegex(ValueError, "OOC boundary"):
            _parse_timing_summary_report(
                report.replace("checking no_clock (10)", "checking no_clock (11)"),
                ooc_boundary=True,
            )

    def test_ooc_timing_accepts_boundary_unconstrained_clock_rows(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import _parse_timing_summary_report

        report = clean_timing_report().decode("utf-8").replace("\r\n", "\n")
        for name, count in (
            ("no_clock", 10), ("no_input_delay", 515), ("no_output_delay", 536),
        ):
            report = report.replace(
                f"checking {name} (0)", f"checking {name} ({count})",
            )
        report = report.replace(
            "Path Group    From Clock    To Clock\n----------    ----------    --------\n\n",
            "Path Group    From Clock    To Clock\n----------    ----------    --------\n"
            "(none)        RFADC0_CLK                  \n"
            "(none)        RFDAC0_CLK                  \n"
            "(none)                      RFADC0_CLK    \n"
            "(none)                      RFDAC0_CLK    \n"
            "(none)                      clk_pl_0      \n\n",
        )
        _parse_timing_summary_report(report, ooc_boundary=True)

    def _artifacts_context(self):
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl

        request, _, context = fixture()
        model, architecture, platform, _, _, _ = context
        probe = probe_result(model, architecture)
        return emit_connected_tcl(request, platform, probe), context

    def test_fresh_tree_starts_attempt_ids_at_one_and_never_reuses_disk_ids(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            self.assertEqual(runner._next_run_id(), 1)

            attempts = root / "build" / "vivado" / "connected_rfdc_shell_attempts"
            attempts.mkdir(parents=True)
            (attempts / "run_1").mkdir()
            (attempts / "run_7").mkdir()
            (attempts / "run_notes").mkdir()
            self.assertEqual(runner._next_run_id(), 8)

    def test_vivado_launcher_binds_attempt_verification_tcl_hash(self) -> None:
        """The real launcher must pass the attempt's verified Tcl hash to Vivado."""
        from types import SimpleNamespace

        from rfsoc_pulse_model.ip.connected_runner import (
            ConnectedShellRunner,
            make_vivado_launcher,
        )

        artifacts, _ = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            attempt = runner._prepare_attempt(1, artifacts)
            with patch(
                "rfsoc_pulse_model.ip.connected_runner.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ) as launch:
                result = make_vivado_launcher(Path("C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat"))(attempt)

            self.assertEqual(result, 0)
            launch.assert_called_once()
            environment = launch.call_args.kwargs["env"]
            self.assertEqual(
                environment["CONNECTED_VERIFICATION_TCL_SHA256"],
                artifacts.verification_tcl_sha256,
            )

    def test_task6_default_rejects_legacy_authority_without_phase0(self) -> None:
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        _, _, context = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build")
            with self.assertRaisesRegex(ValueError, "Phase-0 environment manifest"):
                runner._require_current_environment(context[-1])

    def test_environment_bound_candidate_evidence_uses_schema2(self) -> None:
        """Phase-0-bound requests must publish evidence with the same binding."""
        import dataclasses

        from rfsoc_pulse_model.ip.connected import build_connected_request
        from rfsoc_pulse_model.ip.connected_runner import (
            ConnectedShellRunner,
            build_candidate_evidence,
        )
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.environment import EnvironmentManifest

        (model, architecture, platform, lock), bundle, probe = authority_fixture()
        manifest = EnvironmentManifest(
            host="new_machine",
            os="Windows 11",
            python="3.12.9",
            vivado="2025.2",
            vivado_build="6299465",
            repo_root="E:/new/absolute/path",
            git_commit="0" * 40,
            timezone="Asia/Shanghai",
            git_status_clean=True,
            vivado_executable="C:/Xilinx/2025.2/Vivado/bin/vivado.bat",
        )
        measured_probe = probe_result(model, architecture)
        bound_probe = dataclasses.replace(
            measured_probe,
            provenance=dataclasses.replace(
                measured_probe.provenance,
                environment_manifest_sha256=manifest.sha256,
            ),
        )
        bound_bundle = dataclasses.replace(
            bundle, environment_manifest_bytes=manifest.bytes()
        )
        request = build_connected_request(
            model, architecture, platform, lock, bound_probe.provenance, bound_bundle
        )
        artifacts = emit_connected_tcl(request, platform, bound_probe)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            attempt = runner._prepare_attempt(1, artifacts)
            write_clean_reports(attempt)
            raw = readback_bytes(artifacts)
            attempt.readback_path.write_bytes(raw)
            evidence = build_candidate_evidence(artifacts, raw, attempt)

        self.assertEqual(evidence.evidence_schema_version, 2)
        self.assertEqual(evidence.environment_manifest_sha256, manifest.sha256)

    def test_tcl_hash_binding_is_checked_after_launcher_and_on_resume(self) -> None:
        """A replaced attempt Tcl cannot be authorized by copied readback text."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)

            def tampered(attempt):
                write_clean_reports(attempt)
                attempt.verification_tcl_path.write_bytes(
                    attempt.verification_tcl_path.read_bytes() + b"\n# tampered\n"
                )
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0

            with self.assertRaisesRegex(RuntimeError, "file hash mismatch"):
                runner.run(artifacts, *context, launcher=tampered)

            observed = []

            def clean(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0

            runner.run(artifacts, *context, launcher=clean)
            observed[0].realization_tcl_path.write_bytes(
                observed[0].realization_tcl_path.read_bytes() + b"\n# tampered\n"
            )
            with self.assertRaisesRegex(ValueError, "file hash mismatch"):
                runner.load_validated_success(*context)

    def test_report_bytes_are_immutable_after_success_publication(self) -> None:
        """Changing a report after publication invalidates the success state."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            observed = []

            def clean(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0

            runner.run(artifacts, *context, launcher=clean)
            observed[0].report_paths["cdc"].write_bytes(
                observed[0].report_paths["cdc"].read_bytes() + b"\npost-publication mutation\n"
            )
            with self.assertRaisesRegex(ValueError, "report hashes"):
                runner.load_validated_success(*context)

    @staticmethod
    def _successful_fake(artifacts, *, mutate_readback=None, mutate_reports=None):
        def fake(attempt):
            write_clean_reports(attempt)
            if mutate_reports is not None:
                mutate_reports(attempt)
            raw = readback_bytes(artifacts)
            if mutate_readback is not None:
                raw = mutate_readback(raw)
            attempt.readback_path.write_bytes(raw)
            return 0
        return fake

    def test_runner_rejects_partial_machine_readback_and_exposes_disk_command_contract(self) -> None:
        """Accepting partial readback would let a fake hide missing Vivado facts."""
        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner, build_vivado_command

        request, _, context = fixture()
        model, architecture, platform, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            observed = []
            def fake(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(b"CONNECTED_READBACK\tEND\n")
                return 0
            with self.assertRaisesRegex(RuntimeError, "readback"):
                runner.run(artifacts, *context, launcher=fake)
            command = build_vivado_command(observed[0], Path("D:/app/AMD/2025.2/Vivado/bin/vivado.bat"))
            self.assertEqual(command[1:4], ("-mode", "batch", "-source"))
            self.assertEqual(observed[0].project_dir.parent, observed[0].root)
            self.assertEqual(observed[0].vivado_environment(artifacts.verification_tcl_sha256)["CONNECTED_READBACK_TSV"], str(observed[0].readback_path))

    def test_success_replaces_old_success_before_launcher_and_validates_candidate(self) -> None:
        """Publishing after launch, or reusing stale evidence, must fail this."""

        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        request, evidence, context = fixture()
        _, _, platform, _, _, _ = context
        model, architecture, _, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            old_state = root / "build" / "metadata" / "connected_rfdc_shell_state.json"
            old_state.parent.mkdir(parents=True)
            old_state.write_text('{"stale":true}\n', encoding="utf-8")

            def fake(attempt):
                state = old_state.read_bytes()
                self.assertIn(b'"state":"in_progress"', state)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0

            accepted = runner.run(artifacts, *context, launcher=fake)
            self.assertTrue(accepted.rfdc_shell_structural_ready)
            self.assertFalse(accepted.production_integration_ready)
            loaded = runner.load_validated_success(*context)
            self.assertEqual(loaded.connected_request_sha256, evidence.connected_request_sha256)
            self.assertEqual(loaded.bonded_iob_used, 0)
            with self.assertRaisesRegex(RuntimeError, "launcher failed"):
                runner.run(artifacts, *context, launcher=lambda _attempt: 9)
            with self.assertRaisesRegex(ValueError, "success"):
                runner.load_validated_success(*context)

    def test_failed_launcher_leaves_old_success_unauthorized(self) -> None:
        """Leaving old success consumable after a failed run must fail this."""

        from rfsoc_pulse_model.ip.connected_tcl import emit_connected_tcl
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        request, _, context = fixture()
        _, _, platform, _, _, _ = context
        model, architecture, _, _, _, _ = context
        probe = probe_result(model, architecture)
        artifacts = emit_connected_tcl(request, platform, probe)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            with self.assertRaisesRegex(RuntimeError, "launcher failed"):
                runner.run(artifacts, *context, launcher=lambda _attempt: 7)
            with self.assertRaisesRegex(ValueError, "success"):
                runner.load_validated_success(*context)

    def test_report_and_mts_evidence_fail_closed(self) -> None:
        """Unsafe reports or absent/wrong per-tile RFDC MTS readback never ready."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        mutations = {
            "synthetic_protocol": lambda attempt: attempt.report_paths["cdc"].write_bytes(
                b"CDC_SAFE\nCLOCK_SAFE\nTIMING_CONSTRAINED\n"
            ),
            "critical_cdc": lambda attempt: attempt.report_paths["cdc"].write_bytes(unsafe_cdc_report()),
            "unsafe_clock": lambda attempt: attempt.report_paths["clock_interaction"].write_bytes(clean_clock_report().replace(b"clk_a         clk_b", b"clk_a         clk_c")),
            "unconstrained_timing": lambda attempt: attempt.report_paths["timing_summary"].write_bytes(clean_timing_report().rstrip() + b"\nclk_a         clk_a         clk_b\n"),
            "synthetic_utilization": lambda attempt: attempt.report_paths["utilization"].write_bytes(b"UTILIZATION_OK\n"),
            "missing_bonded_iob": lambda attempt: attempt.report_paths["utilization"].write_bytes(clean_utilization_report().replace(b"| Bonded IOB                 | 0    | 0     | 728       | 0.00% |", b"")),
            "used_bonded_iob": lambda attempt: attempt.report_paths["utilization"].write_bytes(clean_utilization_report().replace(b"| Bonded IOB                 | 0    | 0     | 728       | 0.00% |", b"| Bonded IOB                 | 1    | 0     | 728       | 0.14% |")),
            "wrong_version": lambda attempt: attempt.report_paths["cdc"].write_bytes(clean_cdc_report().replace(b"Vivado v.2025.2", b"Vivado v.2025.1")),
            "wrong_build": lambda attempt: attempt.report_paths["cdc"].write_bytes(clean_cdc_report().replace(b"Build 6299465", b"Build 6299464")),
            "oversized_report": lambda attempt: attempt.report_paths["cdc"].write_bytes(clean_cdc_report() + b"x" * 1_000_000),
            "missing_mts": lambda raw: raw.replace(b"CONNECTED_READBACK\tMTS\tADC0_Multi_Tile_Sync\ttrue\n", b""),
            "wrong_mts": lambda raw: raw.replace(b"CONNECTED_READBACK\tMTS\tDAC0_Multi_Tile_Sync\ttrue", b"CONNECTED_READBACK\tMTS\tDAC0_Multi_Tile_Sync\tfalse"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutation in mutations.items():
                with self.subTest(name=name):
                    runner = ConnectedShellRunner(root, root / "build", require_environment=False)
                    if name in {"missing_mts", "wrong_mts"}:
                        fake = self._successful_fake(artifacts, mutate_readback=mutation)
                    else:
                        fake = self._successful_fake(artifacts, mutate_reports=mutation)
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        runner.run(artifacts, *context, launcher=fake)

    def test_readback_proves_reset_ps_concat_and_external_port_inventory(self) -> None:
        """A realised shell may not silently ignore reviewed wiring/configuration."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        ps_name, ps_value = artifacts.ps_properties[0]
        wrong_ps_value = "0" if ps_value != "0" else "1"
        mutations = {
            "ps": lambda raw: raw.replace(
                f"CONNECTED_READBACK\tPS_CONFIG\t{ps_name}\t{ps_value}".encode(),
                f"CONNECTED_READBACK\tPS_CONFIG\t{ps_name}\t{wrong_ps_value}".encode(),
            ),
            "inverter": lambda raw: raw.replace(b"C_OPERATION\tnot", b"C_OPERATION\tor"),
            "concat": lambda raw: raw.replace(b"CONCAT\tNUM_PORTS\t1", b"CONCAT\tNUM_PORTS\t2"),
            "port": lambda raw: raw.replace(b"PORT\tvin0_01\tvin0_01_0", b"PORT\tvin0_01\twrong_port"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutation in mutations.items():
                with self.subTest(name=name):
                    runner = ConnectedShellRunner(root, root / "build", require_environment=False)
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        runner.run(artifacts, *context, launcher=self._successful_fake(artifacts, mutate_readback=mutation))

    def test_runner_lock_rejects_concurrent_and_recovers_stale_advisory_file(self) -> None:
        """Only an acquired advisory lock blocks; a stale file itself does not."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner, _repository_lock

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            lock = root / ".connected_rfdc_shell.runner.lock"
            lock.write_bytes(b"stale advisory content")
            accepted = runner.run(artifacts, *context, launcher=self._successful_fake(artifacts))
            self.assertTrue(accepted.rfdc_shell_structural_ready)
            with _repository_lock(lock):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    ConnectedShellRunner(root, root / "build", require_environment=False).run(artifacts, *context, launcher=self._successful_fake(artifacts))

    def test_interrupted_evidence_or_success_publication_leaves_failed_authority(self) -> None:
        """Both publish boundaries fail closed instead of leaving a usable success."""
        import rfsoc_pulse_model.ip.connected_runner as runner_module

        artifacts, context = self._artifacts_context()
        original = runner_module._atomic_write
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for boundary in ("evidence", "success"):
                with self.subTest(boundary=boundary):
                    runner = runner_module.ConnectedShellRunner(root, root / "build", require_environment=False)
                    def interrupted(path, payload, *, target=boundary):
                        if target == "evidence" and path == runner.evidence_path:
                            raise OSError("simulated evidence publish interruption")
                        if target == "success" and path == runner.state_path and b'"state":"success"' in payload:
                            raise OSError("simulated state publish interruption")
                        return original(path, payload)
                    with patch.object(runner_module, "_atomic_write", side_effect=interrupted):
                        with self.assertRaisesRegex(RuntimeError, "interruption"):
                            runner.run(artifacts, *context, launcher=self._successful_fake(artifacts))
                    self.assertIn(b'"state":"failed"', runner.state_path.read_bytes())
                    with self.assertRaisesRegex(ValueError, "success"):
                        runner.load_validated_success(*context)

    def test_attempt_report_reparse_and_launch_path_attacks_fail_closed(self) -> None:
        """Junction/symlink report substitution and `}` paths cannot alter Tcl execution."""
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary) / "legal}component"
            root.mkdir()
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            observed = []
            def brace_fake(attempt):
                observed.append(attempt)
                write_clean_reports(attempt)
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            runner.run(artifacts, *context, launcher=brace_fake)
            launch = observed[0].launch_tcl_path.read_text(encoding="utf-8")
            self.assertEqual(launch, "source $::env(CONNECTED_REALIZATION_TCL)\nsource $::env(CONNECTED_VERIFICATION_TCL)\n")
            self.assertEqual(observed[0].vivado_environment(artifacts.verification_tcl_sha256)["CONNECTED_REALIZATION_TCL"], str(observed[0].realization_tcl_path))

            attack_runner = ConnectedShellRunner(root, root / "build_attack", require_environment=False)
            outside_report = Path(outside) / "cdc.rpt"
            outside_report.write_bytes(clean_cdc_report())
            def symlink_fake(attempt):
                write_clean_reports(attempt)
                attempt.report_paths["cdc"].unlink()
                try:
                    os.symlink(outside_report, attempt.report_paths["cdc"])
                except OSError as error:
                    self.skipTest(f"symlink capability unavailable: {error}")
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            with self.assertRaisesRegex(RuntimeError, "failed"):
                attack_runner.run(artifacts, *context, launcher=symlink_fake)

    def test_report_directory_junction_is_rejected_before_readback(self) -> None:
        """A Windows junction in an attempt cannot redirect trusted report reads."""
        if os.name != "nt":
            self.skipTest("junction semantics are Windows-specific")
        from rfsoc_pulse_model.ip.connected_runner import ConnectedShellRunner

        artifacts, context = self._artifacts_context()
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            external_reports = Path(outside) / "reports"
            external_reports.mkdir()
            runner = ConnectedShellRunner(root, root / "build", require_environment=False)
            def junction_fake(attempt):
                reports = next(iter(attempt.report_paths.values())).parent
                reports.rmdir()
                result = subprocess.run(
                    ["cmd.exe", "/c", "mklink", "/J", str(reports), str(external_reports)],
                    capture_output=True, text=True, check=False,
                )
                if result.returncode != 0:
                    self.skipTest(f"junction capability unavailable: {result.stderr or result.stdout}")
                contents = {
                    "cdc": clean_cdc_report(),
                    "clock_interaction": clean_clock_report(),
                    "timing_summary": clean_timing_report(),
                    "utilization": clean_utilization_report(),
                }
                for name, path in attempt.report_paths.items():
                    path.write_bytes(contents[name])
                attempt.readback_path.write_bytes(readback_bytes(artifacts))
                return 0
            with self.assertRaisesRegex(RuntimeError, "reparse"):
                runner.run(artifacts, *context, launcher=junction_fake)

    def test_tracked_connected_evidence_bundle_is_honest_and_boundary_scoped(self) -> None:
        """Handoff evidence must not turn a blocked attempt into an OOC success claim."""
        repository = Path(__file__).resolve().parents[2]
        bundle = json.loads(
            (repository / "docs" / "handoff" / "connected_evidence_bundle.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(bundle["bundle_schema_version"], 2)
        checkout = bundle["evidence_checkout"]
        source_head = checkout["source_head"]
        self.assertRegex(source_head, r"^[0-9a-f]{40}$")
        environment = bundle["environment"]
        self.assertRegex(environment["manifest_sha256"], r"^[0-9a-f]{64}$")
        manifest_path = repository / environment["manifest_path"]
        self.assertTrue(manifest_path.is_file())
        manifest_bytes = manifest_path.read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(), environment["manifest_sha256"]
        )
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["evidence_source_head"], source_head)
        self.assertEqual(manifest["python"], environment["python"])
        self.assertEqual(manifest["vivado"], environment["vivado"])
        self.assertEqual(manifest["vivado_build"], environment["vivado_build"])
        self.assertEqual(manifest["ready"], environment["ready"])
        self.assertEqual(manifest["blocking_reasons"], environment["blocking_reasons"])
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True,
            text=True, check=True,
        ).stdout.strip()
        self.assertEqual(
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", source_head, current_head],
                cwd=repository, capture_output=True, text=True, check=False,
            ).returncode,
            0,
            "evidence source HEAD must be an ancestor of the current checkout",
        )
        handoff = bundle["handoff_commit"]
        parent_head = handoff["parent_head"]
        parent_of_current = subprocess.run(
            ["git", "rev-parse", f"{current_head}^"], cwd=repository,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertIn(parent_head, {current_head, parent_of_current})
        self.assertIn("cannot self-reference", handoff["bundle_commit_relation"])
        self.assertEqual(bundle["focused_test_counts"], {"calibrated_hv": 14, "cycle": 57})
        connected = bundle["connected"]
        self.assertEqual(connected["timing_scope"], "ooc_boundary_only")
        self.assertFalse(connected["production_integration_ready"])
        self.assertEqual(connected["cdc15_endpoint_count"], 60)
        from rfsoc_pulse_model.ip.cdc_inventory import CDC15_ENDPOINT_PAIRS

        expected_inventory_hash = hashlib.sha256(
            json.dumps(
                [list(pair) for pair in CDC15_ENDPOINT_PAIRS],
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
        ).hexdigest()
        self.assertEqual(connected["cdc15_endpoint_set_sha256"], expected_inventory_hash)
        hash_fields = (
            "request_sha256",
            "realization_tcl_sha256",
            "verification_tcl_sha256",
        )
        report_hashes = connected["report_hashes"]
        self.assertEqual(set(report_hashes), {"cdc", "clock_interaction", "timing_summary", "utilization"})
        unavailable = connected["fresh_attempt_status"] != "success"
        for value in (*(connected[name] for name in hash_fields), *report_hashes.values()):
            if unavailable:
                self.assertIsNone(value)
            else:
                self.assertRegex(value, r"^[0-9a-f]{64}$")
        if unavailable:
            self.assertIsNone(connected["bonded_iob_used"])
        else:
            self.assertEqual(connected["bonded_iob_used"], 0)

        handoff_text = "\n".join(
            (repository / "docs" / "handoff" / name).read_text(encoding="utf-8")
            for name in (
                "CURRENT_STATE.md",
                "VERIFICATION_EVIDENCE.md",
                "IMPLEMENTATION_HISTORY.md",
                "NEXT_STEPS.md",
                "OPEN_ISSUES.md",
                "DECISIONS.md",
                "NEW_CHAT_PROMPT.md",
            )
        )
        self.assertIn("connected_evidence_bundle.json", handoff_text)
        self.assertIn("ooc_boundary_only", handoff_text)
        self.assertIn("production_integration_ready=false", handoff_text)
        self.assertIn("baseline `c118362`", handoff_text)
        self.assertIn("14 calibrated-H/V tests and 57 Cycle", handoff_text)
        self.assertNotIn("51 Cycle", handoff_text)
        self.assertNotIn("full Python regression reports 327", handoff_text)
        self.assertNotIn("Task 5/6 OOC structural CLEAN", handoff_text)
        self.assertNotIn("Do not start Task 6 again", handoff_text)


if __name__ == "__main__":
    unittest.main()
