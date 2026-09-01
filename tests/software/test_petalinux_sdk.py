from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PetaLinuxSdkBuilderTest(unittest.TestCase):
    def test_builder_produces_a_validated_calibratord_sysroot(self) -> None:
        module_path = ROOT / "software/petalinux/build_sdk.py"
        self.assertTrue(module_path.is_file(), "PetaLinux SDK builder is missing")
        spec = importlib.util.spec_from_file_location("calibrator_petalinux_sdk", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            project = root / "petalinux-project"
            (project / "images/linux").mkdir(parents=True)
            install_dir = root / "sdk"
            os_release = root / "os-release"
            os_release.write_text('VERSION_ID="22.04.5 LTS"\n', encoding="utf-8")

            def fake_which(command: str) -> str | None:
                if command in {"petalinux-build", "petalinux-package"}:
                    return f"/fake/bin/{command}"
                return None

            def fake_runner(command, **kwargs):
                build_command = ["petalinux-build", "--sdk", "-p", str(project)]
                package_command = [
                    "petalinux-package",
                    "--sysroot",
                    "-p",
                    str(project),
                    "--sdk",
                    str(project / "images/linux/sdk.sh"),
                    "--dir",
                    str(install_dir),
                ]
                if command == build_command:
                    (project / "images/linux/sdk.sh").write_text("sdk installer\n", encoding="utf-8")
                elif command == package_command:
                    (install_dir / "environment-setup-aarch64-xilinx-linux").parent.mkdir(parents=True)
                    (install_dir / "environment-setup-aarch64-xilinx-linux").write_text(
                        "export CC=aarch64-xilinx-linux-gcc\n",
                        encoding="utf-8",
                    )
                    target_include = install_dir / "sysroots/aarch64-xilinx-linux/usr/include"
                    (target_include / "metal").mkdir(parents=True)
                    (target_include / "metal/device.h").write_text("device\n", encoding="utf-8")
                    (target_include / "metal/sys.h").write_text("sys\n", encoding="utf-8")
                    (target_include / "xrfdc.h").write_text("rfdc\n", encoding="utf-8")
                    compiler = (
                        install_dir
                        / "sysroots/x86_64-petalinux-linux/usr/bin/aarch64-xilinx-linux"
                        / "aarch64-xilinx-linux-gcc"
                    )
                    compiler.parent.mkdir(parents=True)
                    compiler.write_text("compiler\n", encoding="utf-8")
                else:
                    raise AssertionError(f"unexpected command: {command}")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = module.build_sdk(
                project=project,
                install_dir=install_dir,
                environ={"PETALINUX": "/home/petalinux/petalinux/2025.2"},
                os_release_path=os_release,
                which=fake_which,
                runner=fake_runner,
            )

            self.assertEqual(result.install_dir, install_dir)
            self.assertEqual(
                result.environment_setup,
                install_dir / "environment-setup-aarch64-xilinx-linux",
            )
            self.assertEqual(result.target_sysroot.name, "aarch64-xilinx-linux")
            self.assertEqual(result.compiler.name, "aarch64-xilinx-linux-gcc")

    def test_sdk_application_builder_emits_a_validated_aarch64_daemon(self) -> None:
        module_path = ROOT / "software/petalinux/build_calibratord.py"
        self.assertTrue(module_path.is_file(), "SDK application builder is missing")
        spec = importlib.util.spec_from_file_location("calibrator_sdk_application", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output_dir = root / "output"
            expected_binary = output_dir / "calibratord"

            def fake_which(command: str) -> str | None:
                if command in {"aarch64-xilinx-linux-gcc", "aarch64-xilinx-linux-readelf"}:
                    return f"/fake/bin/{command}"
                return None

            def fake_runner(command, **kwargs):
                if command[0] == "aarch64-xilinx-linux-gcc":
                    required = {
                        "--sysroot=/fake/target",
                        "-O2",
                        "-pipe",
                        "-Wl,--as-needed",
                        f"-I{ROOT / 'software/calibratord/include'}",
                        "-pthread",
                        "-lmetal",
                        "-lrfdc",
                        str(ROOT / "software/calibratord/src/calibratord.c"),
                        str(ROOT / "software/calibratord/src/control.c"),
                        str(ROOT / "software/calibratord/src/protocol.c"),
                    }
                    if not required.issubset(command):
                        raise AssertionError(f"incomplete compile command: {command}")
                    expected_binary.parent.mkdir(parents=True, exist_ok=True)
                    expected_binary.write_bytes(b"aarch64 daemon")
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["aarch64-xilinx-linux-readelf", "-h", str(expected_binary)]:
                    return subprocess.CompletedProcess(command, 0, "Machine: AArch64\n", "")
                if command == ["aarch64-xilinx-linux-readelf", "-d", str(expected_binary)]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        "NEEDED libmetal.so.1\nNEEDED librfdc.so.13\nNEEDED libc.so.6\n",
                        "",
                    )
                raise AssertionError(f"unexpected command: {command}")

            result = module.build_calibratord(
                repository_root=ROOT,
                output_dir=output_dir,
                environ={
                    "CC": "aarch64-xilinx-linux-gcc --sysroot=/fake/target",
                    "CFLAGS": "-O2 -pipe",
                    "LDFLAGS": "-Wl,--as-needed",
                    "READELF": "aarch64-xilinx-linux-readelf",
                },
                which=fake_which,
                runner=fake_runner,
            )

            self.assertEqual(result.binary, expected_binary)
            self.assertEqual(result.machine, "AArch64")
            self.assertEqual(
                result.needed,
                ("libmetal.so.1", "librfdc.so.13", "libc.so.6"),
            )


if __name__ == "__main__":
    unittest.main()
