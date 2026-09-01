#!/usr/bin/env python3
"""Cross-build calibratord with a sourced PetaLinux SDK environment."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import sys
from typing import NamedTuple


class ApplicationBuildResult(NamedTuple):
    binary: Path
    machine: str
    needed: tuple[str, ...]


def _tool_command(environ: Mapping[str, str], variable: str) -> list[str]:
    value = environ.get(variable, "").strip()
    if not value:
        raise RuntimeError(
            f"{variable} is not set; source the PetaLinux SDK environment-setup file"
        )
    command = shlex.split(value)
    if not command:
        raise RuntimeError(f"{variable} contains no command")
    return command


def build_calibratord(
    repository_root: Path,
    output_dir: Path,
    *,
    environ: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> ApplicationBuildResult:
    repository_root = repository_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise RuntimeError(f"refusing to reuse existing application output: {output_dir}")

    compiler = _tool_command(environ, "CC")
    readelf = _tool_command(environ, "READELF")
    for name, command in (("CC", compiler), ("READELF", readelf)):
        if which(command[0]) is None:
            raise RuntimeError(f"{name} executable is unavailable: {command[0]}")

    source_dir = repository_root / "software/calibratord/src"
    include_dir = repository_root / "software/calibratord/include"
    sources = [source_dir / name for name in ("calibratord.c", "control.c", "protocol.c")]
    required_inputs = sources + [
        include_dir / "calibrator_control.h",
        include_dir / "calibrator_protocol.h",
        include_dir / "calibrator_regs.h",
        include_dir / "calibrator_uio_path.h",
    ]
    missing = [path for path in required_inputs if not path.is_file()]
    if missing:
        raise RuntimeError(f"calibratord source input is missing: {missing[0]}")

    output_dir.mkdir(parents=True)
    binary = output_dir / "calibratord"
    command = [
        *compiler,
        *shlex.split(environ.get("CFLAGS", "")),
        *shlex.split(environ.get("LDFLAGS", "")),
        f"-I{include_dir}",
        "-o",
        str(binary),
        *(str(path) for path in sources),
        "-pthread",
        "-lmetal",
        "-lrfdc",
    ]
    runner(command, check=True)
    if not binary.is_file():
        raise RuntimeError(f"cross compiler did not create calibratord: {binary}")

    header = runner(
        [*readelf, "-h", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    machine_match = re.search(r"^\s*Machine:\s*(.+?)\s*$", header, re.MULTILINE)
    if machine_match is None or machine_match.group(1) != "AArch64":
        machine = machine_match.group(1) if machine_match else "unknown"
        raise RuntimeError(f"calibratord is not AArch64: {machine}")

    dynamic = runner(
        [*readelf, "-d", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    needed = tuple(
        match.group(1)
        for line in dynamic.splitlines()
        if "NEEDED" in line
        for match in [re.search(r"(lib[^\]\s]+\.so(?:\.[^\]\s]+)*)", line)]
        if match is not None
    )
    for library in ("libmetal.so", "librfdc.so", "libc.so"):
        if not any(item == library or item.startswith(f"{library}.") for item in needed):
            raise RuntimeError(f"calibratord is missing dynamic dependency: {library}")

    return ApplicationBuildResult(binary, "AArch64", needed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="new application output directory")
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    try:
        result = build_calibratord(repository_root, args.output_dir)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"CALIBRATORD_ELF={result.binary}")
    print(f"CALIBRATORD_MACHINE={result.machine}")
    print(f"CALIBRATORD_NEEDED={','.join(result.needed)}")
    print("CALIBRATORD_SDK_BUILD_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
