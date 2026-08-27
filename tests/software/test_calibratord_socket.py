"""Linux socket-level contracts for the calibratord one-request connection."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CalibratordSocketContractTest(unittest.TestCase):
    def test_reader_uses_a_monotonic_total_deadline(self) -> None:
        source = (ROOT / "software/calibratord/src/control.c").read_text(encoding="utf-8")
        self.assertIn("CLOCK_MONOTONIC", source)
        self.assertIn("remaining_timeout_ms", source)

    def test_socket_segmentation_timeout_and_boundaries(self) -> None:
        if not sys.platform.startswith("linux"):
            self.skipTest("AF_UNIX C socket contract is executed in the PetaLinux Ubuntu VM")
        compiler = shutil.which("gcc")
        if compiler is None:
            self.skipTest("gcc is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "calibratord_socket_contract"
            subprocess.run(
                [
                    compiler,
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "software/calibratord/include"),
                    str(ROOT / "tests/software/calibratord_socket_contract.c"),
                    str(ROOT / "software/calibratord/src/control.c"),
                    "-o",
                    str(executable),
                ],
                check=True,
                capture_output=True,
            )
            self.assertEqual(subprocess.run([str(executable)], check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
