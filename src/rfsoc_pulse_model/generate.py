from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Iterable

from .common.config import ModelConfig
from .common.types import SampleTimeReference
from .cycle.dsl.emitter import VerilogEmitter
from .cycle.registry import HARDWARE_MODULES
from .ip.evidence import canonical_json_bytes
from .ip.generate import generate_ip_architecture
from .ip.lock import GenerationMode
from .ip.registry import ArchitectureRegistry
from .ip.types import ImplementationKind


_VERILOG_FILENAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.v$")
_WINDOWS_REPARSE_POINT = 0x0400


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ports(module) -> list[dict[str, object]]:
    return [
        {
            "name": port.name,
            "direction": port.direction,
            "width": port.width,
            "registered": port.registered,
        }
        for port in module.ports
    ]


def _validate_registered_verilog_filenames() -> None:
    """Reject untrusted registry names before any output is elaborated."""

    for registration in HARDWARE_MODULES:
        filename = registration.verilog_filename
        if not isinstance(filename, str) or not _VERILOG_FILENAME_RE.fullmatch(filename):
            raise ValueError(f"unsafe registered Verilog filename: {filename!r}")


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _is_reparse_or_symlink(path: Path, information: os.stat_result) -> bool:
    if stat.S_ISLNK(information.st_mode):
        return True
    if os.name == "nt":
        attributes = getattr(information, "st_file_attributes", 0)
        return bool(attributes & _WINDOWS_REPARSE_POINT) or path.is_junction()
    return False


def _windows_directory_identity(path: Path) -> tuple[int, int]:
    """Bind a Windows directory handle before accepting its identity."""

    import ctypes
    from ctypes import wintypes

    generic_read = 0x80000000
    share_read_write_delete = 0x00000007
    open_existing = 3
    file_attribute_directory = 0x0010
    file_attribute_reparse_point = 0x0400
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    invalid_handle_value = ctypes.c_void_p(-1).value

    class _FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("creation_time", _FileTime),
            ("last_access_time", _FileTime),
            ("last_write_time", _FileTime),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateFileW(
        str(path),
        generic_read,
        share_read_write_delete,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_backup_semantics,
        None,
    )
    if handle == invalid_handle_value:
        raise OSError(ctypes.get_last_error(), f"CreateFileW directory failed: {path}")
    try:
        information = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(
            wintypes.HANDLE(handle), ctypes.byref(information)
        ):
            raise OSError(
                ctypes.get_last_error(), f"GetFileInformationByHandle failed: {path}"
            )
        if information.file_attributes & file_attribute_reparse_point:
            raise RuntimeError(f"unsafe directory reparse point: {path}")
        if not information.file_attributes & file_attribute_directory:
            raise RuntimeError(f"unsafe directory is not a directory: {path}")
        return (
            information.volume_serial_number,
            (information.file_index_high << 32) | information.file_index_low,
        )
    finally:
        if not kernel32.CloseHandle(wintypes.HANDLE(handle)):
            raise OSError(ctypes.get_last_error(), f"CloseHandle directory failed: {path}")


def _directory_identity(path: Path, scope: str) -> tuple[int, int]:
    """Return a non-link directory identity used to detect path swaps."""

    information = _lstat_or_none(path)
    if information is None:
        raise RuntimeError(f"missing generated RTL directory for {scope}: {path}")
    if _is_reparse_or_symlink(path, information):
        raise RuntimeError(f"unsafe {scope} symlink or reparse point: {path}")
    if not stat.S_ISDIR(information.st_mode):
        raise RuntimeError(f"unsafe {scope} is not a directory: {path}")
    if os.name == "nt":
        return _windows_directory_identity(path)
    return (information.st_dev, information.st_ino)


def _ensure_real_directory(path: Path, scope: str) -> tuple[int, int]:
    """Create one directory only beneath a verified real parent directory."""

    information = _lstat_or_none(path)
    if information is not None:
        return _directory_identity(path, scope)
    parent = path.parent
    if parent == path:
        raise RuntimeError(f"unable to establish generated RTL directory: {path}")
    _ensure_real_directory(parent, f"{scope} parent")
    try:
        path.mkdir()
    except FileExistsError:
        pass
    return _directory_identity(path, scope)


def _assert_directory_identity(
    path: Path, expected: tuple[int, int], scope: str
) -> None:
    if _directory_identity(path, scope) != expected:
        raise RuntimeError(f"unsafe {scope} directory identity changed: {path}")


def _inspect_regular_target(
    directory: Path,
    directory_identity: tuple[int, int],
    filename: str,
    scope: str,
) -> Path | None:
    """Check one known basename without following a link or special file."""

    _assert_directory_identity(directory, directory_identity, scope)
    path = directory / filename
    information = _lstat_or_none(path)
    if information is None:
        return None
    if _is_reparse_or_symlink(path, information):
        raise RuntimeError(f"unsafe {scope} target symlink or reparse point: {path}")
    if not stat.S_ISREG(information.st_mode):
        raise RuntimeError(f"unsafe {scope} target is not a regular file: {path}")
    return path


def _reject_unregistered_rtl(
    directory: Path,
    directory_identity: tuple[int, int],
    expected_filenames: set[str],
    scope: str,
) -> None:
    _assert_directory_identity(directory, directory_identity, scope)
    stale = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.name.endswith(".v"):
                continue
            information = entry.stat(follow_symlinks=False)
            path = directory / entry.name
            if _is_reparse_or_symlink(path, information) or not stat.S_ISREG(
                information.st_mode
            ):
                raise RuntimeError(f"unsafe generated RTL entry in {scope}: {entry.name}")
            if entry.name not in expected_filenames:
                stale.append(entry.name)
    _assert_directory_identity(directory, directory_identity, scope)
    if stale:
        raise RuntimeError(
            f"unregistered generated RTL exists in {scope}: " + ", ".join(sorted(stale))
        )


def _read_regular_target(
    directory: Path,
    directory_identity: tuple[int, int],
    filename: str,
    scope: str,
) -> bytes | None:
    path = _inspect_regular_target(directory, directory_identity, filename, scope)
    if path is None:
        return None
    data = path.read_bytes()
    _assert_directory_identity(directory, directory_identity, scope)
    _inspect_regular_target(directory, directory_identity, filename, scope)
    return data


def _unlink_regular_target(
    directory: Path,
    directory_identity: tuple[int, int],
    filename: str,
    scope: str,
) -> None:
    path = _inspect_regular_target(directory, directory_identity, filename, scope)
    if path is None:
        return
    path.unlink()
    _assert_directory_identity(directory, directory_identity, scope)


def _write_regular_target(
    directory: Path,
    directory_identity: tuple[int, int],
    filename: str,
    data: bytes,
    scope: str,
) -> None:
    """Replace a verified regular target using a temporary in the same directory.

    Directory identities are rechecked around each pathname operation. This is
    fail-closed for pre-existing links and detects swaps, but it is not a claim
    of global protection against an uncooperative concurrent directory renamer.
    """

    _inspect_regular_target(directory, directory_identity, filename, scope)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".rtl-generate-", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        _assert_directory_identity(directory, directory_identity, scope)
        temporary_info = _lstat_or_none(temporary)
        if temporary_info is None or not stat.S_ISREG(temporary_info.st_mode):
            raise RuntimeError(f"unsafe temporary RTL target: {temporary}")
        _inspect_regular_target(directory, directory_identity, filename, scope)
        os.replace(temporary, directory / filename)
        _assert_directory_identity(directory, directory_identity, scope)
        _inspect_regular_target(directory, directory_identity, filename, scope)
    finally:
        _assert_directory_identity(directory, directory_identity, scope)
        temporary_info = _lstat_or_none(temporary)
        if temporary_info is not None:
            if _is_reparse_or_symlink(temporary, temporary_info) or not stat.S_ISREG(
                temporary_info.st_mode
            ):
                raise RuntimeError(f"unsafe temporary RTL target retained: {temporary}")
            temporary.unlink()
            _assert_directory_identity(directory, directory_identity, scope)


def generate(
    output_root: Path,
    ip_mode: GenerationMode | str = GenerationMode.DEVELOPMENT,
) -> dict[str, object]:
    """Regenerate all registered hardware RTL and its machine manifest."""

    root = Path(output_root)
    _validate_registered_verilog_filenames()
    root_identity = _ensure_real_directory(root, "output root")
    rtl_root = root / "rtl"
    reference_rtl_root = root / "reference_rtl"
    metadata_root = root / "metadata"
    vivado_root = root / "vivado"
    rtl_identity = _ensure_real_directory(rtl_root, "rtl")
    reference_rtl_identity = _ensure_real_directory(
        reference_rtl_root, "reference_rtl"
    )
    metadata_identity = _ensure_real_directory(metadata_root, "metadata")
    vivado_identity = _ensure_real_directory(vivado_root, "vivado")
    _inspect_regular_target(root, root_identity, "manifest.json", "output root")
    config = ModelConfig.load_default()
    ip_architecture = generate_ip_architecture(root, ip_mode)
    _assert_directory_identity(root, root_identity, "output root")
    _assert_directory_identity(rtl_root, rtl_identity, "rtl")
    _assert_directory_identity(reference_rtl_root, reference_rtl_identity, "reference_rtl")
    _assert_directory_identity(metadata_root, metadata_identity, "metadata")
    _assert_directory_identity(vivado_root, vivado_identity, "vivado")
    emitter = VerilogEmitter()
    production_rtl = []
    reference_rtl = []
    expected_production_files = set()
    expected_reference_files = set()
    emitted = []
    for registration in HARDWARE_MODULES:
        module = registration.cycle_class(config)
        rtl = emitter.emit(module).encode("utf-8")
        output_directory = rtl_root if registration.production else reference_rtl_root
        output_scope = "rtl" if registration.production else "reference_rtl"
        entry = (
            {
                "module_name": module.module_name,
                "cycle_class": (
                    f"{registration.cycle_class.__module__}."
                    f"{registration.cycle_class.__qualname__}"
                ),
                "verilog_file": f"{output_scope}/{registration.verilog_filename}",
                "rtl_sha256": _sha256(rtl),
                "latency_cycles": module.latency_cycles,
                "samples_per_cycle": module.samples_per_cycle,
                "accepts_backpressure": module.accepts_backpressure,
                "implementation_kind": registration.implementation_kind.value,
                "production": registration.production,
                "ports": _ports(module),
            }
        )
        emitted.append((registration, output_directory / registration.verilog_filename, rtl, entry))
        if registration.production:
            production_rtl.append(entry)
            expected_production_files.add(registration.verilog_filename)
        else:
            reference_rtl.append(entry)
            expected_reference_files.add(registration.verilog_filename)

    for registration, _reference_path, reference_bytes, _entry in emitted:
        if registration.production:
            continue
        old_production_bytes = _read_regular_target(
            rtl_root,
            rtl_identity,
            registration.verilog_filename,
            "rtl migration source",
        )
        if old_production_bytes is None:
            continue
        if old_production_bytes != reference_bytes:
            raise RuntimeError(
                "possible hand edit in old production RTL: "
                f"{registration.verilog_filename} differs from fresh reference bytes"
            )
        _unlink_regular_target(
            rtl_root,
            rtl_identity,
            registration.verilog_filename,
            "rtl migration source",
        )

    _reject_unregistered_rtl(
        rtl_root, rtl_identity, expected_production_files, "rtl"
    )
    _reject_unregistered_rtl(
        reference_rtl_root,
        reference_rtl_identity,
        expected_reference_files,
        "reference_rtl",
    )
    for registration, _path, rtl, _entry in emitted:
        if registration.production:
            _write_regular_target(
                rtl_root,
                rtl_identity,
                registration.verilog_filename,
                rtl,
                "rtl",
            )
        else:
            _write_regular_target(
                reference_rtl_root,
                reference_rtl_identity,
                registration.verilog_filename,
                rtl,
                "reference_rtl",
            )

    modules = production_rtl + reference_rtl
    production_sources_contain_reference = any(
        entry["verilog_file"].startswith("reference_rtl/")
        or entry["implementation_kind"]
        == ImplementationKind.LEGACY_NON_PRODUCTION.value
        for entry in production_rtl
    )
    readiness = ArchitectureRegistry.default().evaluate_readiness(
        catalog_resolution_complete=ip_architecture["catalog_resolution_complete"],
        production_lock_valid=ip_architecture["production_lock_valid"],
        production_sources_contain_reference=production_sources_contain_reference,
    )
    ip_architecture.update(
        {
            "responsibility_complete": readiness.responsibility_complete,
            "production_integration_ready": readiness.production_integration_ready,
            "production_integration_blocking_reasons": list(
                readiness.blocking_reasons
            ),
        }
    )
    ip_architecture_bytes = canonical_json_bytes(ip_architecture)
    _write_regular_target(
        metadata_root,
        metadata_identity,
        "ip_architecture.json",
        ip_architecture_bytes,
        "metadata",
    )

    numeric_formats = config.numeric_formats.as_tuples()
    numeric_bytes = json.dumps(
        numeric_formats,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    _write_regular_target(
        metadata_root,
        metadata_identity,
        "numeric_formats.json",
        numeric_bytes,
        "metadata",
    )

    manifest = {
        "model_schema_version": config.model_schema_version,
        "config_version": config.config_version,
        "device_part": config.device_part,
        "rx_fabric_clock_hz": config.rx_fabric_clock_hz,
        "rfdc_complex_samples_per_cycle": config.rfdc_complex_samples_per_cycle,
        "rfdc_dac_pl_data_type": config.rfdc_axis.dac_data_type,
        "rfdc_dac_axis_width_bits": config.rfdc_axis.dac_axis_width_bits,
        "rfdc_dac_complex_samples_per_cycle": (
            config.rfdc_axis.dac_complex_samples_per_cycle
        ),
        "rfdc_adc_clocking_mode": config.rfdc_adc_clocking_mode.value,
        "rfdc_adc_clocking_proof_status": (
            config.rfdc_adc_clocking_proof_status.value
        ),
        "rfdc_dac_clocking_mode": config.rfdc_dac_clocking_mode.value,
        "rfdc_dac_clocking_proof_status": (
            config.rfdc_dac_clocking_proof_status.value
        ),
        "single_clock_ingress_integration_ready": (
            config.single_clock_ingress_integration_ready
        ),
        "single_clock_tx_integration_ready": (
            config.single_clock_tx_integration_ready
        ),
        "golden_dac_time_reference": (
            SampleTimeReference.LATENCY_NORMALIZED.value
        ),
        "fractional_delay_kernel_center_samples": (
            config.fractional_delay_taps - 1
        ) // 2,
        "fixed_internal_delay_source": "calibration_profile_measurement",
        "numeric_formats_sha256": _sha256(numeric_bytes),
        "ip_architecture": ip_architecture,
        "ip_architecture_sha256": _sha256(ip_architecture_bytes),
        "production_rtl": production_rtl,
        "reference_rtl": reference_rtl,
        "modules": modules,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _write_regular_target(
        root, root_identity, "manifest.json", manifest_bytes, "output root"
    )
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Cycle-derived Verilog")
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument(
        "--ip-mode",
        choices=tuple(mode.value for mode in GenerationMode),
        default=GenerationMode.DEVELOPMENT.value,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    generate(args.output, GenerationMode(args.ip_mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
