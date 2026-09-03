"""Materialize deterministic Vivado and cross-language ABI build inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from ..common.control_abi import ControlAbi
from .calibrator_platform import CalibratorPlatformConfig
from .calibrator_vivado import emit_calibrator_vivado_tcl


def finalize_xsa_with_bitstream(
    source_xsa: Path,
    bitstream: Path,
    output_xsa: Path,
) -> dict[str, object]:
    """Create a fixed XSA containing the foreground-build bitstream.

    Vivado's ``write_hw_platform -include_bit`` only accepts a managed
    implementation run.  The production Tcl intentionally uses foreground
    implementation for sandbox-safe reproducibility, so this finalizer adds
    the exact emitted bitstream and both standard XSA metadata records, then
    reopens the archive and verifies its bytes.
    """

    for label, path in (("source_xsa", source_xsa), ("bitstream", bitstream)):
        if not isinstance(path, Path) or not path.is_file() or path.is_symlink():
            raise ValueError(f"{label} must be a regular file")
    if not isinstance(output_xsa, Path) or output_xsa.is_symlink():
        raise ValueError("output_xsa must be a non-symlink pathlib.Path")
    if output_xsa.resolve() in {source_xsa.resolve(), bitstream.resolve()}:
        raise ValueError("output_xsa must differ from both inputs")

    bitstream_bytes = bitstream.read_bytes()
    bitstream_name = bitstream.name
    temporary = output_xsa.with_suffix(output_xsa.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    output_xsa.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_xsa, "r") as source:
        names = set(source.namelist())
        if not {"xsa.json", "xsa.xml"}.issubset(names):
            raise ValueError("source XSA lacks xsa.json or xsa.xml")
        json_metadata = json.loads(source.read("xsa.json"))
        files = json_metadata.setdefault("files", [])
        files[:] = [entry for entry in files if entry.get("type") != "BITSTREAM"]
        files.append({"name": bitstream_name, "type": "BITSTREAM"})

        xml_root = ET.fromstring(source.read("xsa.xml"))
        xml_files = xml_root.find(".//Files")
        if xml_files is None:
            raise ValueError("source XSA xsa.xml lacks Files element")
        for entry in list(xml_files):
            if entry.tag == "File" and entry.get("Type") == "BITSTREAM":
                xml_files.remove(entry)
        ET.SubElement(xml_files, "File", {"Type": "BITSTREAM", "Name": bitstream_name})

        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                if info.filename in {"xsa.json", "xsa.xml", bitstream_name}:
                    continue
                target.writestr(info, source.read(info.filename))
            target.writestr(
                "xsa.json",
                (json.dumps(json_metadata, indent=4) + "\n").encode("utf-8"),
            )
            target.writestr(
                "xsa.xml",
                ET.tostring(xml_root, encoding="utf-8", xml_declaration=True),
            )
            target.writestr(bitstream_name, bitstream_bytes)

    temporary.replace(output_xsa)
    with zipfile.ZipFile(output_xsa, "r") as archive:
        embedded = archive.read(bitstream_name)
        embedded_json = json.loads(archive.read("xsa.json"))
        if embedded != bitstream_bytes:
            raise RuntimeError("embedded XSA bitstream verification failed")
        if {"name": bitstream_name, "type": "BITSTREAM"} not in embedded_json["files"]:
            raise RuntimeError("embedded XSA bitstream metadata verification failed")
    return {
        "output_xsa": str(output_xsa),
        "bitstream_name": bitstream_name,
        "bitstream_size": len(bitstream_bytes),
        "bitstream_sha256": hashlib.sha256(bitstream_bytes).hexdigest(),
    }


def generate_calibrator_sources(output_directory: Path) -> dict[str, object]:
    if not isinstance(output_directory, Path):
        raise ValueError("output_directory must be a pathlib.Path")
    if output_directory.exists() and output_directory.is_symlink():
        raise ValueError("output_directory cannot be a symbolic link")
    output_directory.mkdir(parents=True, exist_ok=True)
    abi = ControlAbi.load_default()
    platform = CalibratorPlatformConfig.load_default()
    platform.require_deployable()
    artifacts = {
        "build_calibrator.tcl": emit_calibrator_vivado_tcl(),
        "calibrator_registers.h": abi.emit_c_header(),
        "calibrator_registers.vh": abi.emit_verilog_header(),
        "calibrator_registers.py": abi.emit_python_constants(),
        "calibrator.dtsi": abi.emit_device_tree_binding(),
    }
    hashes: dict[str, str] = {}
    for filename, content in artifacts.items():
        path = output_directory / filename
        if path.exists() and path.is_symlink():
            raise ValueError(f"generated artifact cannot be a symbolic link: {filename}")
        encoded = content.encode("utf-8")
        path.write_bytes(encoded)
        hashes[filename] = hashlib.sha256(encoded).hexdigest()
    manifest: dict[str, object] = {
        "generation_schema_version": 1,
        "device_part": platform.device_part,
        "vivado_version": platform.vivado_version,
        "vitis_version": platform.vitis_version,
        "petalinux_version": platform.petalinux_version,
        "artifacts": hashes,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (output_directory / "generation_manifest.json").write_bytes(manifest_bytes)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path, nargs="?")
    parser.add_argument(
        "--finalize-xsa",
        nargs=3,
        metavar=("SOURCE_XSA", "BITSTREAM", "OUTPUT_XSA"),
        type=Path,
    )
    args = parser.parse_args(argv)
    if args.finalize_xsa:
        finalize_xsa_with_bitstream(*args.finalize_xsa)
    elif args.output_directory is not None:
        generate_calibrator_sources(args.output_directory)
    else:
        parser.error("output_directory or --finalize-xsa is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
