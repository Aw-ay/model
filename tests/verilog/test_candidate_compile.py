"""Standalone Vivado elaboration regression for the calibrated-H/V candidate."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.hardware.production_calibrated_hv import (
    RxCalibratedHvFrontend2Spc,
)


def _vivado_2025_2() -> Path | None:
    configured = os.environ.get("VIVADO_2025_2")
    candidates = (
        Path(configured) if configured else None,
        Path(r"C:\Xilinx\2025.2\Vivado\bin\vivado.bat"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file() and "2025.2" in str(candidate):
            return candidate
    return None


class CandidateCompileTest(unittest.TestCase):
    def test_calibrated_hv_candidate_elaborates_in_vivado_2025_2(self) -> None:
        vivado = _vivado_2025_2()
        if vivado is None:
            self.skipTest("Vivado 2025.2 executable is unavailable")

        rtl = VerilogEmitter().emit(
            RxCalibratedHvFrontend2Spc(ModelConfig.load_default())
        )
        with tempfile.TemporaryDirectory(prefix="rfsoc_candidate_compile_") as directory:
            root = Path(directory)
            source = root / "rx_2spc_calibrated_hv_frontend.v"
            script = root / "elaborate.tcl"
            source.write_text(rtl, encoding="utf-8", newline="\n")
            script.write_text(
                "\n".join(
                    (
                        f"read_verilog {{{source.as_posix()}}}",
                        "synth_design -top rx_2spc_calibrated_hv_frontend -part xczu27dr-fsve1156-2-i",
                        "exit",
                        "",
                    )
                ),
                encoding="utf-8",
                newline="\n",
            )
            result = subprocess.run(
                [str(vivado), "-mode", "batch", "-nojournal", "-nolog", "-source", str(script)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"Vivado elaboration failed:\n{result.stdout}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
