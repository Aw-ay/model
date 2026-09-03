#!/usr/bin/env python3
"""Build and validate the PetaLinux 2025.2 SDK used by Vitis."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
from typing import NamedTuple


EXPECTED_VERSION = "2025.2"


class SdkBuildResult(NamedTuple):
    install_dir: Path
    environment_setup: Path
    target_sysroot: Path
    compiler: Path


def _one(paths: Sequence[Path], description: str) -> Path:
    if len(paths) != 1:
        raise RuntimeError(f"expected exactly one {description}, found {len(paths)}")
    return paths[0]


def _sdk_compiler_name(environment_setup: Path) -> str:
    assignments = [
        line.partition("=")[2].strip()
        for line in environment_setup.read_text(encoding="utf-8").splitlines()
        if line.startswith("export CC=")
    ]
    if len(assignments) != 1:
        raise RuntimeError(
            f"expected exactly one CC export in {environment_setup}, found {len(assignments)}"
        )
    try:
        words = shlex.split(assignments[0], posix=True)
    except ValueError as exc:
        raise RuntimeError(f"invalid CC export in {environment_setup}") from exc
    if not words:
        raise RuntimeError(f"empty CC export in {environment_setup}")
    compiler_name = words[0].split()[0]
    if not re.fullmatch(r"aarch64[-A-Za-z0-9_.+]*-gcc", compiler_name):
        raise RuntimeError(f"unexpected SDK compiler command: {compiler_name}")
    return compiler_name


def build_sdk(
    project: Path,
    install_dir: Path,
    *,
    environ: Mapping[str, str] = os.environ,
    os_release_path: Path = Path("/etc/os-release"),
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> SdkBuildResult:
    project = project.resolve()
    install_dir = install_dir.resolve()
    if not project.is_dir():
        raise RuntimeError(f"PetaLinux project does not exist: {project}")
    if install_dir.exists():
        raise RuntimeError(f"refusing to reuse existing SDK directory: {install_dir}")

    petalinux_root = environ.get("PETALINUX", "")
    if EXPECTED_VERSION not in petalinux_root:
        raise RuntimeError(
            f"source the PetaLinux {EXPECTED_VERSION} settings.sh before running this script"
        )
    try:
        os_release = os_release_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read host release: {os_release_path}") from exc
    if re.search(r'^VERSION_ID="?22\.04(?:[^"\n]*)"?$', os_release, re.MULTILINE) is None:
        raise RuntimeError("Ubuntu 22.04 is required for this qualified SDK build")

    for command in ("petalinux-build", "petalinux-package", "g++"):
        if which(command) is None:
            raise RuntimeError(f"missing {command}")

    compat_value = environ.get("CALIBRATOR_XSCT_LIBTINFO_DIR", "").strip()
    if not compat_value:
        raise RuntimeError(
            "set CALIBRATOR_XSCT_LIBTINFO_DIR to the directory containing libtinfo.so.5"
        )
    compat_dir = Path(compat_value).resolve()
    if not (compat_dir / "libtinfo.so.5").is_file():
        raise RuntimeError(f"XSCT compatibility library is missing: {compat_dir / 'libtinfo.so.5'}")
    command_environment = dict(environ)
    command_environment.pop("LD_PRELOAD", None)
    passthrough = command_environment.get("BB_ENV_PASSTHROUGH_ADDITIONS", "").split()
    if "LIBRARY_PATH" not in passthrough:
        passthrough.append("LIBRARY_PATH")
    command_environment["LIBRARY_PATH"] = str(compat_dir)
    command_environment["BB_ENV_PASSTHROUGH_ADDITIONS"] = " ".join(passthrough)

    host_environment = dict(environ)
    for variable in ("COMPILER_PATH", "GCC_EXEC_PREFIX", "LD_PRELOAD", "LIBRARY_PATH"):
        host_environment.pop(variable, None)
    host_gxx = which("g++")
    assert host_gxx is not None
    host_crt_probe = runner(
        [host_gxx, "-print-file-name=crt1.o"],
        check=True,
        capture_output=True,
        text=True,
        env=host_environment,
    )
    host_crt = Path(host_crt_probe.stdout.strip()).resolve()
    if not host_crt.is_file() or not (host_crt.parent / "crti.o").is_file():
        raise RuntimeError("host g++ cannot locate crt1.o and crti.o")

    local_conf = project / "build/conf/local.conf"
    try:
        original_local_conf = local_conf.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot read PetaLinux local.conf: {local_conf}") from exc
    crt_dir = str(host_crt.parent)
    if any(character in crt_dir for character in ('"', "\n", "\r")):
        raise RuntimeError(f"host CRT directory cannot be represented in local.conf: {crt_dir}")
    sdk_override = (
        "\n# Temporary host startup-object path for the SDK cross-compiler.\n"
        f'LIBRARY_PATH:pn-gcc-crosssdk-x86_64-petalinux-linux = "{crt_dir}"\n'
    ).encode("utf-8")

    sdk_installer = project / "images/linux/sdk.sh"
    local_conf.write_bytes(original_local_conf + sdk_override)
    try:
        runner(
            ["petalinux-build", "--sdk", "-p", str(project)],
            check=True,
            env=command_environment,
        )
    finally:
        local_conf.write_bytes(original_local_conf)
    if not sdk_installer.is_file():
        raise RuntimeError(f"PetaLinux SDK installer was not generated: {sdk_installer}")

    runner(
        [
            "petalinux-package",
            "--sysroot",
            "-p",
            str(project),
            "--sdk",
            str(sdk_installer),
            "--dir",
            str(install_dir),
        ],
        check=True,
        env=command_environment,
    )

    environment_setup = _one(
        sorted(path for path in install_dir.glob("environment-setup-*") if path.is_file()),
        "environment-setup script",
    )
    sysroots = install_dir / "sysroots"
    target_candidates = [
        path
        for path in sysroots.iterdir()
        if path.is_dir()
        and (path / "usr/include/metal/device.h").is_file()
        and (path / "usr/include/metal/sys.h").is_file()
        and (path / "usr/include/xrfdc.h").is_file()
    ] if sysroots.is_dir() else []
    target_sysroot = _one(target_candidates, "target sysroot with libmetal and xrfdc headers")
    compiler_name = _sdk_compiler_name(environment_setup)
    compiler = _one(
        sorted(
            path
            for path in sysroots.rglob(compiler_name)
            if path.is_file() and path.name == compiler_name
        ),
        f"AArch64 cross compiler selected by CC ({compiler_name})",
    )
    return SdkBuildResult(install_dir, environment_setup, target_sysroot, compiler)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="existing PetaLinux project directory")
    parser.add_argument("install_dir", type=Path, help="new SDK/sysroot output directory")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = build_sdk(args.project, args.install_dir)
    print(f"CALIBRATOR_SDK={result.install_dir}")
    print(f"CALIBRATOR_ENV_SETUP={result.environment_setup}")
    print(f"CALIBRATOR_TARGET_SYSROOT={result.target_sysroot}")
    print(f"CALIBRATOR_CROSS_GCC={result.compiler}")
    print("CALIBRATOR_SDK_VERIFY_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
