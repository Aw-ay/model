"""Build the reproducible Vitis 2025.2 Linux XPFM through XSCT.

This launcher runs under ordinary Python, invokes the supported XSCT platform
commands, and validates the actual artifact instead of trusting the XSCT exit
code alone.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence


EXPECTED_VERSION = "2025.2"
PLATFORM_NAME = "calibrator_platform"
SUCCESS_PREFIX = "CALIBRATOR_XPFM="


def find_built_xpfm(output_dir: Path) -> Path:
    component = output_dir / PLATFORM_NAME
    expected = component / "export" / PLATFORM_NAME / f"{PLATFORM_NAME}.xpfm"
    candidates = sorted(component.rglob(f"{PLATFORM_NAME}.xpfm"))
    if candidates != [expected] or not expected.is_file():
        raise RuntimeError(
            f"XSCT must produce exactly one {PLATFORM_NAME}.xpfm at {expected}"
        )
    return expected


def _validate_inputs(vitis_root: Path, xsa: Path, output_dir: Path) -> tuple[Path, Path]:
    if output_dir.exists():
        raise RuntimeError(f"refusing to reuse existing output directory: {output_dir}")
    if EXPECTED_VERSION not in vitis_root.as_posix():
        raise RuntimeError(f"Vitis {EXPECTED_VERSION} required; got {vitis_root}")
    xsct = vitis_root / "bin" / ("xsct.bat" if os.name == "nt" else "xsct")
    if not xsct.is_file():
        raise RuntimeError(f"XSCT launcher does not exist: {xsct}")
    qemu_payload = vitis_root / "data/emulation/platforms/zynqmp/sw/a53_linux/qemu"
    if not qemu_payload.is_dir():
        raise RuntimeError(
            "Vitis Embedded ZynqMP Linux payload is incomplete; "
            f"missing {qemu_payload}"
        )
    if not xsa.is_file():
        raise RuntimeError(f"XSA does not exist: {xsa}")
    tcl_script = Path(__file__).with_name("create_linux_platform.tcl")
    if not tcl_script.is_file():
        raise RuntimeError(f"XSCT platform script does not exist: {tcl_script}")
    return xsct, tcl_script


def build_xsct_platform(
    *,
    vitis_root: Path,
    xsa: Path,
    output_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    vitis_root = Path(vitis_root).resolve()
    xsa = Path(xsa).resolve()
    output_dir = Path(output_dir).resolve()
    xsct, tcl_script = _validate_inputs(vitis_root, xsa, output_dir)
    command: Sequence[str] = [
        str(xsct),
        "-quiet",
        str(tcl_script),
        str(xsa),
        str(output_dir),
    ]
    result = runner(
        command,
        capture_output=True,
        text=True,
        shell=os.name == "nt",
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"XSCT platform build failed ({result.returncode}): {details}")
    built_xpfm = find_built_xpfm(output_dir)
    expected_marker = f"{SUCCESS_PREFIX}{built_xpfm.as_posix()}"
    normalized_stdout = result.stdout.replace("\\", "/")
    if expected_marker not in normalized_stdout:
        raise RuntimeError(
            "XSCT platform build did not emit the expected success marker: "
            f"{expected_marker}"
        )
    return built_xpfm


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xsa", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--vitis-root",
        type=Path,
        default=Path(os.environ["XILINX_VITIS"]) if "XILINX_VITIS" in os.environ else None,
        required="XILINX_VITIS" not in os.environ,
    )
    args = parser.parse_args(argv)
    try:
        built_xpfm = build_xsct_platform(
            vitis_root=args.vitis_root,
            xsa=args.xsa,
            output_dir=args.output_dir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{SUCCESS_PREFIX}{built_xpfm.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
