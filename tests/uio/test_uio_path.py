"""Clean-checkout behavioral contract for the control UIO path parser."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UioPathContractTest(unittest.TestCase):
    def test_sysfs_name_path_maps_to_its_device_node(self) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            self.skipTest("gcc is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "uio_path.c"
            executable = Path(directory) / "uio_path"
            program.write_text(
                "#include <string.h>\n"
                "#include \"calibrator_uio_path.h\"\n"
                "int main(void) { char path[32] = {0}; return "
                "cal_uio_device_from_sysfs_name(\"/sys/class/uio/uio0/name\", path) || "
                "strcmp(path, \"/dev/uio0\") != 0; }\n",
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "software/calibratord/include"), str(program),
                 "-o", str(executable)],
                check=True, capture_output=True,
            )
            self.assertEqual(subprocess.run([str(executable)], check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
