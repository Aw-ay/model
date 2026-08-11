"""Production IP-lock validation and explicit candidate promotion."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable

from .catalog import validate_resolved_catalog
from .evidence import build_catalog_request, canonical_json_bytes
from .tcl import emit_catalog_discovery_tcl
from .types import HardwareArchitectureConfig


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCK_KEYS = {
    "lock_schema_version",
    "architecture_config_sha256",
    "generated_tcl_sha256",
    "catalog_request_sha256",
    "vivado_version",
    "families",
}


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


def promote_candidate_lock(
    candidate_path: Path,
    root_lock_path: Path,
    package_lock_path: Path,
) -> None:
    """Promote one validated candidate to byte-identical source/package locks."""

    candidate = Path(candidate_path)
    root_lock = Path(root_lock_path)
    package_lock = Path(package_lock_path)
    if root_lock.resolve() == package_lock.resolve():
        raise ValueError("root and package lock targets must be distinct")

    payload = _read_lock_payload(candidate)
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
    lock_bytes = canonical_json_bytes(payload)
    _replace_both_or_restore(root_lock, package_lock, lock_bytes)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote a validated IP lock")
    subcommands = parser.add_subparsers(dest="command", required=True)
    promote = subcommands.add_parser("promote", help="promote a candidate lock")
    promote.add_argument("--candidate", type=Path, required=True)
    promote.add_argument("--root-lock", type=Path, required=True)
    promote.add_argument("--package-lock", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    promote_candidate_lock(args.candidate, args.root_lock, args.package_lock)
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
        decoded = path.read_text(encoding="utf-8")
        payload = json.loads(decoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to read production lock candidate: {path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("production lock candidate must be a JSON object")
    return payload


def _replace_both_or_restore(root_lock: Path, package_lock: Path, lock_bytes: bytes) -> None:
    root_lock.parent.mkdir(parents=True, exist_ok=True)
    package_lock.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    backup_paths: dict[Path, Path | None] = {}
    targets = (root_lock, package_lock)
    replaced: list[Path] = []
    try:
        for target in targets:
            temporary_paths.append(_write_temporary(target.parent, lock_bytes))
            backup_paths[target] = _backup_existing(target)
        for target, temporary in zip(targets, temporary_paths, strict=True):
            os.replace(temporary, target)
            replaced.append(target)
        temporary_paths.clear()
    except Exception:
        for target in reversed(replaced):
            backup = backup_paths.get(target)
            try:
                if backup is None:
                    if target.exists():
                        target.unlink()
                elif backup.exists():
                    os.replace(backup, target)
            except OSError:
                pass
        raise
    finally:
        for path in temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for backup in backup_paths.values():
            if backup is not None:
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass


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
    return Path(temporary)


def _backup_existing(target: Path) -> Path | None:
    if not target.exists():
        return None
    if not target.is_file():
        raise ValueError(f"lock target is not a file: {target}")
    descriptor, backup = tempfile.mkstemp(prefix=".ip_lock.backup.", dir=target.parent)
    os.close(descriptor)
    backup_path = Path(backup)
    try:
        shutil.copyfile(target, backup_path)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


if __name__ == "__main__":
    raise SystemExit(main())
