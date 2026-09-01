#!/usr/bin/env python3
"""Build and validate the PetaLinux 2025.2 SDK used by Vitis."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
import re
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

    for command in ("petalinux-build", "petalinux-package"):
        if which(command) is None:
            raise RuntimeError(f"missing {command}")

    sdk_installer = project / "images/linux/sdk.sh"
    runner(
        ["petalinux-build", "--sdk", "-p", str(project)],
        check=True,
    )
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
    compiler = _one(
        sorted(path for path in sysroots.rglob("aarch64*-gcc") if path.is_file()),
        "AArch64 cross compiler",
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
