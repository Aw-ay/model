#!/usr/bin/env python3
"""Materialize the single FPGA bitstream embedded in an XSA archive."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile


def _archive_hash(archive: zipfile.ZipFile, member: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with archive.open(member) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def materialize_bitstream(xsa_path: Path, output_path: Path) -> tuple[str, int, str]:
    with zipfile.ZipFile(xsa_path) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".bit")]
        if len(candidates) != 1:
            raise ValueError("XSA must contain exactly one embedded .bit bitstream")
        member = candidates[0]
        archive_hash, archive_size = _archive_hash(archive, member)
        if archive_size == 0:
            raise ValueError("embedded .bit bitstream is empty")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            size = 0
            with archive.open(member) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    temporary.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        if size != archive_size or digest.hexdigest() != archive_hash:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError("materialized bitstream does not match XSA payload")
        temporary_path.replace(output_path)
    return member, archive_size, archive_hash


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: extract_xsa_bitstream.py <input.xsa> <output.bit>", file=sys.stderr)
        return 2
    try:
        member, size, digest = materialize_bitstream(Path(argv[1]), Path(argv[2]))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"bitstream extraction failed: {error}", file=sys.stderr)
        return 2
    print(f"materialized {member}: {size} bytes sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
