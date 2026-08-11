"""Production IP-lock validation and recoverable two-target promotion.

Promotion is not a cross-file atomic filesystem instruction.  Only writers
using this module's repository advisory lock are supported; manual changes to
either lock target are prohibited.  Snapshot rechecks are fail-fast diagnostics,
not an atomic compare-and-swap defence against non-participating editors.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import errno
from enum import Enum
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Iterable

from .catalog import validate_resolved_catalog
from .evidence import build_catalog_request, canonical_json_bytes
from .tcl import emit_catalog_discovery_tcl
from .types import HardwareArchitectureConfig


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_HEX_RE = re.compile(r"^(?:[0-9a-f]{2})*$")
_LOCK_KEYS = {
    "lock_schema_version",
    "architecture_config_sha256",
    "generated_tcl_sha256",
    "catalog_request_sha256",
    "vivado_version",
    "families",
}
_JOURNAL_KEYS = {
    "journal_schema_version",
    "phase",
    "root_lock_path",
    "package_lock_path",
    "root_snapshot",
    "package_snapshot",
    "new_lock_hex",
    "new_lock_sha256",
}
_SNAPSHOT_KEYS = {"exists", "sha256", "contents_hex"}
_PROMOTION_LOCK_NAME = ".ip_lock.promotion.lock"
_PROMOTION_JOURNAL_NAME = ".ip_lock.promotion.json"
LOCK_WRITER_CONCURRENCY_CONTRACT = (
    "Only promote/recover writers holding the same repository advisory lock are "
    "supported. Manual edits to config/ip_lock.json and "
    "src/rfsoc_pulse_model/config/ip_lock.json are prohibited. Snapshot rechecks "
    "fail fast but cannot atomically protect non-participating editors."
)


class GenerationMode(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ProductionLock:
    lock_schema_version: int
    architecture_config_sha256: str
    generated_tcl_sha256: str
    catalog_request_sha256: str
    vivado_version: str
    families: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProductionLockValidation:
    valid: bool
    lock: ProductionLock


@dataclass(frozen=True)
class _TargetSnapshot:
    exists: bool
    sha256: str | None
    contents: bytes | None


def validate_production_lock(
    config: HardwareArchitectureConfig,
    request_bytes: bytes,
    discovery_tcl_bytes: bytes,
    lock_payload: Mapping[str, object],
) -> ProductionLockValidation:
    """Validate the complete, discovery-bound production-lock predicate."""

    lock = _parse_lock(lock_payload)
    resolved = dict(lock.families)
    for family_id, vlnv in resolved.items():
        if vlnv.split(":")[-1] == "*":
            raise ValueError(f"lock family {family_id} requires an exact VLNV version")
    validate_resolved_catalog(config, resolved)
    if lock.lock_schema_version != 1:
        raise ValueError("unsupported lock_schema_version")

    source_config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    expected_config_sha256 = hashlib.sha256(source_config_bytes).hexdigest()
    if lock.architecture_config_sha256 != expected_config_sha256:
        raise ValueError("architecture_config_sha256 does not match current config")

    expected_tcl_sha256 = hashlib.sha256(discovery_tcl_bytes).hexdigest()
    if lock.generated_tcl_sha256 != expected_tcl_sha256:
        raise ValueError("generated_tcl_sha256 does not match discovery Tcl")

    expected_request = canonical_json_bytes(
        build_catalog_request(config, expected_config_sha256, expected_tcl_sha256)
    )
    if request_bytes != expected_request:
        raise ValueError("catalog request does not match current discovery inputs")
    if lock.catalog_request_sha256 != hashlib.sha256(request_bytes).hexdigest():
        raise ValueError("catalog_request_sha256 does not match current request")
    if lock.vivado_version != config.vivado_version:
        raise ValueError("vivado_version does not match current config")
    return ProductionLockValidation(valid=True, lock=lock)


def decode_production_lock_json(raw_bytes: bytes, description: str) -> Mapping[str, object]:
    """Decode lock JSON while rejecting duplicate keys at every object depth."""

    try:
        decoded = raw_bytes.decode("utf-8")
        payload = json.loads(decoded, object_pairs_hook=_reject_duplicate_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"unable to decode {description}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{description} must be a JSON object")
    return payload


def promote_candidate_lock(
    candidate_path: Path,
    root_lock_path: Path,
    package_lock_path: Path,
) -> None:
    """Promote a validated candidate through a recoverable two-file transaction.

    A successful call leaves byte-identical canonical locks.  A partial I/O
    failure preserves a transaction journal and backups, then raises an error
    naming the required `recover` action instead of claiming cross-file atomicity.
    Only callers participating in the repository advisory-lock protocol are
    supported; this function cannot atomically protect a manual external edit.
    """

    candidate = Path(candidate_path)
    root_lock, package_lock = _normalise_distinct_targets(
        root_lock_path, package_lock_path
    )
    payload = _read_lock_payload(candidate)
    _validate_current_lock_payload(payload)
    lock_bytes = canonical_json_bytes(payload)
    with _repository_promotion_lock(root_lock, package_lock):
        _promote_with_journal(root_lock, package_lock, lock_bytes)


def recover_interrupted_promotion(root_lock_path: Path, package_lock_path: Path) -> int:
    """Roll forward the interrupted promotion for these exact two targets.

    Recovery only overwrites a target that still contains either its journaled
    pre-promotion bytes or the journaled new canonical lock.  Any other bytes
    are treated as an external edit and leave the journal intact for an operator.
    As with promotion, only participating repository-lock writers are supported.
    """

    root_lock, package_lock = _normalise_distinct_targets(
        root_lock_path, package_lock_path
    )
    with _repository_promotion_lock(root_lock, package_lock):
        journal_path = _promotion_journal_path(root_lock, package_lock)
        if not _lstat_exists(journal_path):
            return 0
        _recover_journal(journal_path, root_lock, package_lock)
        return 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote or recover an IP lock. Promotion is a recoverable two-file "
            "transaction, not a cross-file atomic filesystem instruction. Only "
            "writers using this repository lock are supported; manual lock edits "
            "are prohibited."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    promote = subcommands.add_parser(
        "promote",
        help="validate a candidate and commit both locks; retain recovery data on I/O failure",
    )
    promote.add_argument("--candidate", type=Path, required=True)
    promote.add_argument("--root-lock", type=Path, required=True)
    promote.add_argument("--package-lock", type=Path, required=True)
    recover = subcommands.add_parser(
        "recover",
        help="roll forward an interrupted promotion journal for one root/package lock pair",
    )
    recover.add_argument("--root-lock", type=Path, required=True)
    recover.add_argument("--package-lock", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "promote":
        promote_candidate_lock(args.candidate, args.root_lock, args.package_lock)
    else:
        recover_interrupted_promotion(args.root_lock, args.package_lock)
    return 0


def _parse_lock(payload: Mapping[str, object]) -> ProductionLock:
    if not isinstance(payload, Mapping):
        raise ValueError("production lock must be a mapping")
    keys = set(payload)
    if keys != _LOCK_KEYS:
        raise ValueError(
            "production lock keys must be exactly "
            f"{sorted(_LOCK_KEYS)}; got {sorted(keys)}"
        )
    lock_schema_version = payload["lock_schema_version"]
    if not isinstance(lock_schema_version, int) or isinstance(lock_schema_version, bool):
        raise ValueError("lock_schema_version must be an integer")
    fields: dict[str, str] = {}
    for name in (
        "architecture_config_sha256",
        "generated_tcl_sha256",
        "catalog_request_sha256",
    ):
        value = payload[name]
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError(f"malformed SHA-256 for {name}")
        fields[name] = value
    vivado_version = payload["vivado_version"]
    if not isinstance(vivado_version, str) or not vivado_version.strip():
        raise ValueError("vivado_version must be a nonempty string")
    raw_families = payload["families"]
    if not isinstance(raw_families, Mapping):
        raise ValueError("lock families must be a mapping")
    families: list[tuple[str, str]] = []
    for family_id, vlnv in raw_families.items():
        if not isinstance(family_id, str) or not family_id or family_id != family_id.strip():
            raise ValueError("lock family identifiers must be nonempty strings")
        if not isinstance(vlnv, str) or not vlnv or vlnv != vlnv.strip():
            raise ValueError("lock family VLNV values must be nonempty strings")
        families.append((family_id, vlnv))
    return ProductionLock(
        lock_schema_version=lock_schema_version,
        architecture_config_sha256=fields["architecture_config_sha256"],
        generated_tcl_sha256=fields["generated_tcl_sha256"],
        catalog_request_sha256=fields["catalog_request_sha256"],
        vivado_version=vivado_version,
        families=tuple(sorted(families)),
    )


def _read_lock_payload(path: Path) -> Mapping[str, object]:
    try:
        return decode_production_lock_json(path.read_bytes(), "production lock candidate")
    except OSError as error:
        raise ValueError(f"unable to read production lock candidate: {path}") from error


def _reject_duplicate_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    decoded: dict[str, object] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"duplicate JSON key: {key}")
        decoded[key] = value
    return decoded


def _validate_current_lock_payload(payload: Mapping[str, object]) -> None:
    config = HardwareArchitectureConfig.load_default()
    config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_bytes = canonical_json_bytes(
        build_catalog_request(
            config,
            hashlib.sha256(config_bytes).hexdigest(),
            hashlib.sha256(discovery_bytes).hexdigest(),
        )
    )
    validate_production_lock(config, request_bytes, discovery_bytes, payload)


def _normalise_distinct_targets(
    root_lock_path: Path, package_lock_path: Path
) -> tuple[Path, Path]:
    root_lock = Path(root_lock_path).resolve()
    package_lock = Path(package_lock_path).resolve()
    if root_lock.name != "ip_lock.json" or root_lock.parent.name != "config":
        raise ValueError("root lock must be exactly config/ip_lock.json")
    repository_root = root_lock.parent.parent
    expected_package = (
        repository_root / "src/rfsoc_pulse_model/config/ip_lock.json"
    ).resolve()
    if package_lock != expected_package:
        raise ValueError(
            "package lock must be exactly "
            "src/rfsoc_pulse_model/config/ip_lock.json in the same repository"
        )
    return root_lock, package_lock


@contextmanager
def _repository_promotion_lock(root_lock: Path, package_lock: Path) -> Iterator[None]:
    lock_path = _promotion_lock_path(root_lock, package_lock)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _flush_directory(lock_path.parent)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.fstat(descriptor).st_size == 0:
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        _acquire_os_advisory_lock(descriptor, lock_path)
        yield
    finally:
        try:
            _release_os_advisory_lock(descriptor)
        except OSError:
            pass
        os.close(descriptor)


def _promotion_lock_path(root_lock: Path, package_lock: Path) -> Path:
    return _transaction_scope(root_lock, package_lock) / _PROMOTION_LOCK_NAME


def _transaction_scope(root_lock: Path, package_lock: Path) -> Path:
    del package_lock
    return root_lock.parent.parent


def _promotion_journal_path(root_lock: Path, package_lock: Path) -> Path:
    del package_lock
    return root_lock.parent / _PROMOTION_JOURNAL_NAME


def _promote_with_journal(root_lock: Path, package_lock: Path, lock_bytes: bytes) -> None:
    root_lock.parent.mkdir(parents=True, exist_ok=True)
    package_lock.parent.mkdir(parents=True, exist_ok=True)
    _flush_directory(root_lock.parent)
    _flush_directory(package_lock.parent)
    root_snapshot = _snapshot_target(root_lock)
    package_snapshot = _snapshot_target(package_lock)
    journal_path = _write_promotion_journal(
        root_lock, package_lock, root_snapshot, package_snapshot, lock_bytes
    )
    temporary_paths: list[Path] = []
    replaced: list[tuple[Path, _TargetSnapshot]] = []
    try:
        temporary_paths = [
            _write_temporary(root_lock.parent, lock_bytes),
            _write_temporary(package_lock.parent, lock_bytes),
        ]
        for target, snapshot, temporary in (
            (root_lock, root_snapshot, temporary_paths[0]),
            (package_lock, package_snapshot, temporary_paths[1]),
        ):
            _assert_snapshot_current(target, snapshot)
            os.replace(temporary, target)
            replaced.append((target, snapshot))
            _flush_directory(target.parent)
        temporary_paths.clear()
        _assert_exact_bytes(root_lock, lock_bytes)
        _assert_exact_bytes(package_lock, lock_bytes)
    except Exception as error:
        for temporary in temporary_paths:
            _unlink_quietly(temporary)
        if not replaced:
            _remove_promotion_journal(journal_path)
            raise RuntimeError(f"promotion target changed since snapshot: {error}") from error
        rollback_errors = _attempt_rollback(replaced, lock_bytes)
        detail = "; ".join(rollback_errors) if rollback_errors else "rollback staged"
        raise RuntimeError(
            "promotion failed; recovery required; "
            f"journal={journal_path}; {detail}; run `ip.lock recover`"
        ) from error
    _remove_promotion_journal(journal_path)


def _write_promotion_journal(
    root_lock: Path,
    package_lock: Path,
    root_snapshot: _TargetSnapshot,
    package_snapshot: _TargetSnapshot,
    lock_bytes: bytes,
) -> Path:
    journal_path = _promotion_journal_path(root_lock, package_lock)
    journal = {
        "journal_schema_version": 1,
        "phase": "prepared",
        "root_lock_path": str(root_lock),
        "package_lock_path": str(package_lock),
        "root_snapshot": _snapshot_payload(root_snapshot),
        "package_snapshot": _snapshot_payload(package_snapshot),
        "new_lock_hex": lock_bytes.hex(),
        "new_lock_sha256": _sha256(lock_bytes),
    }
    temporary = _write_temporary(journal_path.parent, canonical_json_bytes(journal))
    try:
        # Replacing a symlink replaces the link itself, never its target.
        os.replace(temporary, journal_path)
        _flush_directory(journal_path.parent)
    finally:
        _unlink_quietly(temporary)
    return journal_path


def _snapshot_target(target: Path) -> _TargetSnapshot:
    if not target.exists():
        return _TargetSnapshot(exists=False, sha256=None, contents=None)
    if not target.is_file():
        raise ValueError(f"lock target is not a file: {target}")
    contents = target.read_bytes()
    return _TargetSnapshot(exists=True, sha256=_sha256(contents), contents=contents)


def _snapshot_payload(snapshot: _TargetSnapshot) -> dict[str, object]:
    return {
        "exists": snapshot.exists,
        "sha256": snapshot.sha256,
        "contents_hex": snapshot.contents.hex() if snapshot.exists else None,
    }


def _assert_snapshot_current(target: Path, snapshot: _TargetSnapshot) -> None:
    current = _snapshot_target(target)
    if current != snapshot:
        raise RuntimeError(f"lock target changed since snapshot: {target}")


def _attempt_rollback(
    replaced: list[tuple[Path, _TargetSnapshot]],
    lock_bytes: bytes,
) -> list[str]:
    errors: list[str] = []
    for target, snapshot in reversed(replaced):
        try:
            _assert_exact_bytes(target, lock_bytes)
            if snapshot.exists:
                assert snapshot.contents is not None
                backup_bytes = snapshot.contents
                _assert_sha256(backup_bytes, snapshot.sha256, "journal snapshot")
                temporary = _write_temporary(target.parent, backup_bytes)
                try:
                    os.replace(temporary, target)
                    _flush_directory(target.parent)
                finally:
                    _unlink_quietly(temporary)
            else:
                target.unlink()
                _flush_directory(target.parent)
            _assert_snapshot_current(target, snapshot)
        except Exception as error:
            errors.append(f"rollback {target}: {error}")
    return errors


def _recover_journal(journal_path: Path, root_lock: Path, package_lock: Path) -> None:
    journal = _read_journal(journal_path)
    if journal["root_lock_path"] != str(root_lock):
        raise RuntimeError(f"noncanonical root_lock_path in journal: {journal_path}")
    if journal["package_lock_path"] != str(package_lock):
        raise RuntimeError(f"noncanonical package_lock_path in journal: {journal_path}")
    root_snapshot = _parse_snapshot(journal["root_snapshot"], "root_snapshot")
    package_snapshot = _parse_snapshot(journal["package_snapshot"], "package_snapshot")
    lock_bytes = _decode_hex(journal["new_lock_hex"], "new_lock_hex")
    _assert_sha256(lock_bytes, journal["new_lock_sha256"], "new.lock")
    payload = decode_production_lock_json(lock_bytes, "journaled new lock")
    if lock_bytes != canonical_json_bytes(payload):
        raise RuntimeError(f"journaled new lock is not canonical: {journal_path}")
    _validate_current_lock_payload(payload)
    _assert_recovery_state(root_lock, root_snapshot, lock_bytes)
    _assert_recovery_state(package_lock, package_snapshot, lock_bytes)
    temporary_paths = [
        _write_temporary(root_lock.parent, lock_bytes),
        _write_temporary(package_lock.parent, lock_bytes),
    ]
    try:
        os.replace(temporary_paths[0], root_lock)
        _flush_directory(root_lock.parent)
        os.replace(temporary_paths[1], package_lock)
        _flush_directory(package_lock.parent)
        _assert_exact_bytes(root_lock, lock_bytes)
        _assert_exact_bytes(package_lock, lock_bytes)
    except Exception as error:
        raise RuntimeError(
            f"recovery required but roll-forward failed; journal={journal_path}"
        ) from error
    finally:
        for temporary in temporary_paths:
            _unlink_quietly(temporary)
    _remove_promotion_journal(journal_path)


def _read_journal(journal_path: Path) -> Mapping[str, object]:
    try:
        raw_bytes = _read_promotion_journal_bytes(journal_path)
        journal = decode_production_lock_json(raw_bytes, "promotion journal")
    except OSError as error:
        raise RuntimeError(f"unable to read promotion journal: {journal_path}") from error
    if raw_bytes != canonical_json_bytes(journal):
        raise RuntimeError(f"promotion journal is not canonical: {journal_path}")
    if set(journal) != _JOURNAL_KEYS:
        raise RuntimeError(f"invalid promotion journal keys: {journal_path}")
    if type(journal["journal_schema_version"]) is not int or journal[
        "journal_schema_version"
    ] != 1:
        raise RuntimeError(f"unsupported promotion journal schema: {journal_path}")
    if type(journal["phase"]) is not str or journal["phase"] != "prepared":
        raise RuntimeError(f"unsupported promotion journal phase: {journal_path}")
    for key in (
        "root_lock_path",
        "package_lock_path",
        "new_lock_sha256",
        "new_lock_hex",
    ):
        if type(journal[key]) is not str or not journal[key]:
            raise RuntimeError(f"invalid {key} in promotion journal: {journal_path}")
    if not _SHA256_RE.fullmatch(journal["new_lock_sha256"]):
        raise RuntimeError(f"invalid new_lock_sha256 in promotion journal: {journal_path}")
    _decode_hex(journal["new_lock_hex"], "new_lock_hex")
    return journal


def _parse_snapshot(value: object, name: str) -> _TargetSnapshot:
    if not isinstance(value, Mapping) or set(value) != _SNAPSHOT_KEYS:
        raise RuntimeError(f"invalid {name} in promotion journal")
    exists = value["exists"]
    sha256 = value["sha256"]
    if type(exists) is not bool:
        raise RuntimeError(f"invalid {name}.exists in promotion journal")
    if exists:
        if type(sha256) is not str or not _SHA256_RE.fullmatch(sha256):
            raise RuntimeError(f"invalid {name}.sha256 in promotion journal")
        contents = _decode_hex(value["contents_hex"], f"{name}.contents_hex")
        _assert_sha256(contents, sha256, name)
        return _TargetSnapshot(exists=True, sha256=sha256, contents=contents)
    if sha256 is not None or value["contents_hex"] is not None:
        raise RuntimeError(f"invalid absent {name} data in promotion journal")
    return _TargetSnapshot(exists=False, sha256=None, contents=None)


def _assert_recovery_state(
    target: Path, snapshot: _TargetSnapshot, lock_bytes: bytes
) -> None:
    current = _read_target_or_none(target)
    expected_before = snapshot.contents if snapshot.exists else None
    if current not in {expected_before, lock_bytes}:
        raise RuntimeError(
            f"recovery required but target has external bytes: {target}; journal retained"
        )


def _read_target_or_none(target: Path) -> bytes | None:
    if not target.exists():
        return None
    if not target.is_file():
        raise RuntimeError(f"recovery target is not a file: {target}")
    return target.read_bytes()


def _acquire_os_advisory_lock(descriptor: int, lock_path: Path) -> None:
    """Acquire a process-owned lock released by the OS when the owner dies."""

    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        elif os.name == "posix":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            raise RuntimeError(f"unsupported OS advisory lock platform: {sys.platform}")
    except (BlockingIOError, OSError) as error:
        raise RuntimeError(
            f"another participating writer holds the repository lock: {lock_path}"
        ) from error


def _release_os_advisory_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    elif os.name == "posix":
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _flush_directory(directory: Path) -> None:
    """Persist directory metadata or fail closed when the platform cannot do so."""

    try:
        if os.name == "posix":
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return
        if os.name == "nt":
            _flush_windows_directory(directory)
            return
    except OSError as error:
        raise RuntimeError(f"directory metadata flush failed: {directory}") from error
    raise RuntimeError(f"directory metadata flush unsupported on {sys.platform}")


def _flush_windows_directory(directory: Path) -> None:
    import ctypes
    from ctypes import wintypes

    generic_read_write = 0xC0000000
    share_read_write_delete = 0x00000007
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    invalid_handle_value = ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateFileW(
        str(directory),
        generic_read_write,
        share_read_write_delete,
        None,
        open_existing,
        file_flag_backup_semantics,
        None,
    )
    if handle == invalid_handle_value:
        raise OSError(ctypes.get_last_error(), "CreateFileW directory failed")
    try:
        if not kernel32.FlushFileBuffers(wintypes.HANDLE(handle)):
            raise OSError(ctypes.get_last_error(), "FlushFileBuffers directory failed")
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))


def _write_temporary(directory: Path, payload: bytes) -> Path:
    descriptor, temporary = tempfile.mkstemp(prefix=".ip_lock.", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    _flush_directory(directory)
    return Path(temporary)


def _lstat_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _read_promotion_journal_bytes(journal_path: Path) -> bytes:
    """Read the fixed journal without following a symlink or reparse point."""

    if os.name == "posix":
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(journal_path, flags)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise RuntimeError(
                    f"unsafe promotion journal symlink: {journal_path}"
                ) from error
            raise
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise RuntimeError(f"unsafe promotion journal is not a regular file: {journal_path}")
            return _read_descriptor_bytes(descriptor)
        finally:
            os.close(descriptor)
    if os.name == "nt":
        return _read_windows_regular_journal_no_reparse(journal_path)
    raise RuntimeError(f"promotion journal no-follow read unsupported on {sys.platform}")


def _read_descriptor_bytes(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_windows_regular_journal_no_reparse(journal_path: Path) -> bytes:
    """Bind a Windows handle to the journal before inspecting or reading it."""

    import ctypes
    import msvcrt
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
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(journal_path),
        generic_read,
        share_read_write_delete,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_backup_semantics,
        None,
    )
    if handle == invalid_handle_value:
        raise OSError(ctypes.get_last_error(), "CreateFileW promotion journal failed")
    try:
        information = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(
            wintypes.HANDLE(handle), ctypes.byref(information)
        ):
            raise OSError(ctypes.get_last_error(), "GetFileInformationByHandle failed")
        if information.file_attributes & file_attribute_reparse_point:
            raise RuntimeError(f"unsafe promotion journal reparse point: {journal_path}")
        if information.file_attributes & file_attribute_directory:
            raise RuntimeError(f"unsafe promotion journal is a directory: {journal_path}")
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        handle = None
        try:
            return _read_descriptor_bytes(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if handle is not None:
            kernel32.CloseHandle(wintypes.HANDLE(handle))


def _assert_exact_bytes(path: Path, expected: bytes) -> None:
    if _read_target_or_none(path) != expected:
        raise RuntimeError(f"lock target changed unexpectedly: {path}")


def _assert_sha256(payload: bytes, expected: object, description: str) -> None:
    if not isinstance(expected, str) or _sha256(payload) != expected:
        raise RuntimeError(f"SHA-256 mismatch for {description}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        _flush_directory(path.parent)
    except Exception:
        pass


def _decode_hex(value: object, description: str) -> bytes:
    if type(value) is not str or not _CANONICAL_HEX_RE.fullmatch(value):
        raise RuntimeError(f"invalid {description} in promotion journal")
    return bytes.fromhex(value)


def _remove_promotion_journal(journal_path: Path) -> None:
    """Unlink only the fixed journal pathname, never a directory tree.

    `unlink` operates on the link object itself on both supported platforms;
    it does not follow a swapped symlink.  A directory or junction fails closed
    and keeps the material for explicit operator recovery.
    """

    try:
        info = os.lstat(journal_path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"unsafe promotion journal directory retained: {journal_path}")
    try:
        os.unlink(journal_path)
    except OSError as error:
        raise RuntimeError(f"unable to remove promotion journal: {journal_path}") from error
    _flush_directory(journal_path.parent)


if __name__ == "__main__":
    raise SystemExit(main())
