"""Standalone Vivado elaboration regression for the calibrated-H/V candidate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.hardware.production_calibrated_hv import (
    RxCalibratedHvFrontend2Spc,
)


def _vivado_2025_2() -> Path | None:
    configured = os.environ.get("VIVADO_2025_2")
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and "2025.2" in str(candidate):
            return candidate

    manifest = Path(__file__).resolve().parents[2] / "docs" / "handoff" / "environment_manifest.json"
    if manifest.is_file():
        manifest_executable = Path(json.loads(manifest.read_text(encoding="utf-8"))["vivado_executable"])
        if manifest_executable.is_file() and "2025.2" in str(manifest_executable):
            return manifest_executable
        raise RuntimeError(
            f"tracked environment manifest Vivado 2025.2 executable cannot run: {manifest_executable}"
        )

    legacy = Path(r"C:\Xilinx\2025.2\Vivado\bin\vivado.bat")
    if legacy.is_file():
        return legacy
    return None


class CandidateCompileTest(unittest.TestCase):
    def test_manifest_executable_is_selected_when_no_override_is_set(self) -> None:
        """The verified manifest executable must keep the real gate enabled."""
        manifest = Path(__file__).resolve().parents[2] / "docs" / "handoff" / "environment_manifest.json"
        expected = Path(json.loads(manifest.read_text(encoding="utf-8"))["vivado_executable"])
        self.assertTrue(expected.is_file(), "the tracked manifest executable must be installed for this test")

        with patch.dict(os.environ, {"VIVADO_2025_2": ""}):
            self.assertEqual(_vivado_2025_2(), expected)

    def test_candidate_invocation_uses_systemverilog_and_isolated_user_data(self) -> None:
        """A plain-Verilog reader or inherited Vivado profile must fail this regression."""
        with tempfile.TemporaryDirectory(prefix="rfsoc_candidate_compile_test_") as directory:
            root = Path(directory)
            executable = root / "Vivado" / "2025.2" / "bin" / "vivado.bat"
            executable.parent.mkdir(parents=True)
            executable.touch()
            observed: dict[str, object] = {}

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                observed["command"] = command
                observed["environment"] = kwargs.get("env")
                observed["script"] = Path(command[-1]).read_text(encoding="utf-8")
                environment = kwargs.get("env")
                if isinstance(environment, dict):
                    observed["vivado_user_directory"] = (
                        Path(environment["APPDATA"]) / "Xilinx" / "Vivado"
                    ).is_dir()
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.dict(os.environ, {"VIVADO_2025_2": str(executable)}), patch(
                "tests.verilog.test_candidate_compile.subprocess.run", side_effect=fake_run
            ):
                self.test_calibrated_hv_candidate_elaborates_in_vivado_2025_2()

        self.assertIn("read_verilog -sv", observed["script"])
        environment = observed["environment"]
        self.assertIsInstance(environment, dict)
        self.assertTrue(Path(environment["APPDATA"]).is_absolute())
        self.assertTrue(Path(environment["LOCALAPPDATA"]).is_absolute())
        self.assertTrue(observed["vivado_user_directory"])

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
                        f"read_verilog -sv {{{source.as_posix()}}}",
                        "synth_design -top rx_2spc_calibrated_hv_frontend -part xczu27dr-fsve1156-2-i",
                        "exit",
                        "",
                    )
                ),
                encoding="utf-8",
                newline="\n",
            )
            appdata = root / "appdata"
            local_appdata = root / "localappdata"
            (appdata / "Xilinx" / "Vivado").mkdir(parents=True)
            (local_appdata / "Xilinx" / "Vivado").mkdir(parents=True)
            environment = os.environ.copy()
            environment.update(
                {
                    "APPDATA": str(appdata),
                    "LOCALAPPDATA": str(local_appdata),
                }
            )
            result = subprocess.run(
                [str(vivado), "-mode", "batch", "-nojournal", "-nolog", "-source", str(script)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"Vivado elaboration failed:\n{result.stdout}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
