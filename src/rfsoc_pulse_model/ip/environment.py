"""Portable machine/environment provenance for Vivado migrations.

The four JSON files under ``config/`` are architecture authority.  This
module deliberately keeps machine-specific facts in a separate, generated
manifest so moving the repository does not require changing those files or
their hashes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from importlib import metadata as package_metadata
from importlib import resources
from importlib.util import find_spec
import json
import os
from pathlib import Path
import platform as host_platform
import re
import shutil
import stat
import subprocess
import sys
from typing import Mapping


ENVIRONMENT_SCHEMA_VERSION = 1
AUTHORITY_FILENAMES = (
    "default.json",
    "ip_architecture.json",
    "ip_lock.json",
    "ps_platform.json",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$\Z")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}\Z")
_VIVADO_VERSION_RE = re.compile(
    r"Vivado\s+v\.?(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_VIVADO_BUILD_RE = re.compile(
    r"(?:SW\s+)?Build\s+(?P<build>[0-9]+)",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
PYTHON_PACKAGE_NAMES = ("numpy", "scipy", "pytest", "unittest")
PYTHON_REQUIRED_PACKAGE_NAMES = ("numpy", "scipy", "unittest")
_ATTEMPT_LOCAL_DIRNAMES = (".Xil", ".runs", ".gen")
_ATTEMPT_LOCAL_FILE_NAMES = {"journal.log", "vivado.jou", "dfx_runtime.txt"}
_ATTEMPT_LOCAL_FILE_SUFFIXES = (".xpr", ".jou")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8") + b"\n"


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _strict_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a nonempty trimmed string")
    return value


@dataclass(frozen=True)
class EnvironmentManifest:
    """Immutable machine facts used to bind newly generated evidence."""

    host: str
    os: str
    python: str
    vivado: str
    vivado_build: str
    repo_root: str
    git_commit: str
    timezone: str
    git_status_clean: bool
    # The installation path is environment provenance, never architecture
    # authority.  Keep a default so older in-process callers can still build
    # a manifest object before serializing it under the current schema.
    vivado_executable: str = "unavailable"

    def __post_init__(self) -> None:
        for field in (
            "host", "os", "python", "vivado", "vivado_build", "repo_root",
            "git_commit", "timezone", "vivado_executable",
        ):
            _strict_text(getattr(self, field), field)
        if not _GIT_COMMIT_RE.fullmatch(self.git_commit):
            raise ValueError("git_commit must be a full 40-character SHA-1")
        if not isinstance(self.git_status_clean, bool):
            raise ValueError("git_status_clean must be a boolean")

    def as_mapping(self) -> dict[str, object]:
        return {
            "environment_schema_version": ENVIRONMENT_SCHEMA_VERSION,
            **asdict(self),
        }

    def bytes(self) -> bytes:
        return _canonical(self.as_mapping())

    @property
    def sha256(self) -> str:
        return _sha256(self.bytes())


@dataclass(frozen=True)
class EnvironmentReady:
    """Result of the migration preflight, written even when it is blocked."""

    ready: bool
    reasons: tuple[str, ...]
    environment_manifest_sha256: str
    git_commit: str
    git_status_clean: bool
    authority_sha256: Mapping[str, str]
    python_packages: Mapping[str, str]

    def as_mapping(self) -> dict[str, object]:
        return {
            "environment_ready_schema_version": 1,
            "ready": self.ready,
            "reasons": list(self.reasons),
            "environment_manifest_sha256": self.environment_manifest_sha256,
            "git_commit": self.git_commit,
            "git_status_clean": self.git_status_clean,
            "authority_sha256": dict(sorted(self.authority_sha256.items())),
            "python_packages": dict(sorted(self.python_packages.items())),
        }

    def bytes(self) -> bytes:
        return _canonical(self.as_mapping())


def authority_bytes(repository_root: Path) -> dict[str, bytes]:
    """Read only the four repository authority files as immutable bytes."""

    root = _absolute(repository_root)
    result: dict[str, bytes] = {}
    for filename in AUTHORITY_FILENAMES:
        path = root / "config" / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"authority file is missing or unsafe: {path}")
        result[filename] = path.read_bytes()
    return result


def authority_sha256(repository_root: Path) -> dict[str, str]:
    return {
        filename: _sha256(payload)
        for filename, payload in authority_bytes(repository_root).items()
    }


def authority_package_mismatches(repository_root: Path) -> tuple[str, ...]:
    """Return authority files whose packaged resource bytes differ from root."""

    root_bytes = authority_bytes(repository_root)
    packaged_root = resources.files("rfsoc_pulse_model.config")
    mismatches: list[str] = []
    for filename, expected in root_bytes.items():
        try:
            actual = packaged_root.joinpath(filename).read_bytes()
        except OSError:
            mismatches.append(filename)
            continue
        if actual != expected:
            mismatches.append(filename)
    return tuple(mismatches)


def _contains_absolute_path(value: object) -> bool:
    if isinstance(value, str):
        return bool(_WINDOWS_ABSOLUTE_RE.match(value) or value.startswith("/"))
    if isinstance(value, Mapping):
        return any(
            _contains_absolute_path(key) or _contains_absolute_path(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False


def authority_absolute_path_violations(repository_root: Path) -> tuple[str, ...]:
    """Return authority JSON files containing absolute path strings."""

    violations: list[str] = []
    for filename, raw in authority_bytes(repository_root).items():
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"authority file is not valid JSON: {filename}") from error
        if _contains_absolute_path(value):
            violations.append(filename)
    return tuple(violations)


def _git(repository_root: Path, *arguments: str) -> str:
    root = _absolute(repository_root)
    command = [
        "git", "-c", f"safe.directory={root}", "-C", str(root), *arguments
    ]
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def git_identity(repository_root: Path) -> tuple[str, bool]:
    commit = _git(repository_root, "rev-parse", "HEAD")
    if not _GIT_COMMIT_RE.fullmatch(commit):
        raise ValueError("git rev-parse HEAD did not return a full commit SHA")
    status = _git(
        repository_root, "status", "--porcelain", "--untracked-files=all"
    )
    return commit, not bool(status)


def _vivado_executable(explicit: Path | None) -> str | None:
    if explicit is not None:
        return str(_absolute(explicit))
    configured = os.environ.get("VIVADO_EXECUTABLE")
    if configured:
        return str(_absolute(Path(configured)))
    for name in ("vivado", "vivado.bat", "vivado.cmd"):
        found = shutil.which(name)
        if found:
            return str(_absolute(Path(found)))
    return None


def vivado_identity(explicit: Path | None = None) -> tuple[str, str] | None:
    executable = _vivado_executable(explicit)
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    output = f"{completed.stdout}\n{completed.stderr}"
    version_match = _VIVADO_VERSION_RE.search(output)
    build_match = (
        _VIVADO_BUILD_RE.search(output, version_match.end())
        if version_match is not None else None
    )
    # Vivado's Windows launcher may return 1 for ``-version`` while still
    # emitting a complete, authoritative version/build record.  The parsed
    # output is the useful contract for this read-only probe.
    if version_match is None or build_match is None:
        return None
    return version_match.group("version"), build_match.group("build")


def _timezone_name() -> str:
    configured = os.environ.get("TZ")
    if configured:
        return configured
    local = datetime.now().astimezone().tzinfo
    key = getattr(local, "key", None)
    return str(key or local or "unknown")


def _python_freeze() -> tuple[str, str | None]:
    """Capture the active interpreter package set without making it authority."""

    completed = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return "", "pip_freeze_failed"
    lines = [line.rstrip() for line in completed.stdout.splitlines() if line.strip()]
    return ("\n".join(sorted(lines)) + ("\n" if lines else ""), None)


def python_package_audit() -> dict[str, str]:
    """Report the requested regression packages in the active interpreter."""

    result: dict[str, str] = {}
    for name in PYTHON_PACKAGE_NAMES:
        if name == "unittest":
            result[name] = "stdlib" if find_spec(name) is not None else "missing"
            continue
        if find_spec(name) is None:
            result[name] = "missing"
            continue
        try:
            result[name] = package_metadata.version(name)
        except package_metadata.PackageNotFoundError:
            result[name] = "importable"
    return result


def capture_environment_manifest(
    repository_root: Path,
    *,
    vivado_executable: Path | None = None,
    timezone: str | None = None,
) -> EnvironmentManifest:
    """Capture a new manifest from the current checkout and tool installs."""

    root = _absolute(repository_root)
    commit, clean = git_identity(root)
    executable = _vivado_executable(vivado_executable)
    vivado = vivado_identity(vivado_executable)
    vivado_version, vivado_build = vivado or ("unavailable", "unavailable")
    return EnvironmentManifest(
        host=host_platform.node() or "unknown-host",
        os=host_platform.platform() or host_platform.system() or "unknown-os",
        python=host_platform.python_version() or f"{sys.version_info.major}.{sys.version_info.minor}",
        vivado=vivado_version,
        vivado_build=vivado_build,
        repo_root=str(root),
        git_commit=commit,
        timezone=timezone or _timezone_name(),
        git_status_clean=clean,
        vivado_executable=executable or "unavailable",
    )


def parse_environment_manifest(raw: bytes) -> EnvironmentManifest:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid environment manifest JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("environment manifest must be a JSON object")
    expected = {"environment_schema_version", *EnvironmentManifest.__dataclass_fields__}
    if set(payload) != expected:
        raise ValueError("environment manifest has unknown or missing keys")
    if payload["environment_schema_version"] != ENVIRONMENT_SCHEMA_VERSION:
        raise ValueError("unsupported environment_schema_version")
    manifest = EnvironmentManifest(
        **{field: payload[field] for field in EnvironmentManifest.__dataclass_fields__}
    )
    if raw != manifest.bytes():
        raise ValueError("environment manifest is not canonical")
    return manifest


def parse_environment_ready(raw: bytes) -> EnvironmentReady:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid environment_ready JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("environment_ready must be a JSON object")
    expected = {
        "environment_ready_schema_version", "ready", "reasons",
        "environment_manifest_sha256", "git_commit", "git_status_clean",
        "authority_sha256", "python_packages",
    }
    if set(payload) != expected or payload["environment_ready_schema_version"] != 1:
        raise ValueError("environment_ready has unknown, missing, or unsupported keys")
    if not isinstance(payload["ready"], bool) or not isinstance(payload["git_status_clean"], bool):
        raise ValueError("environment_ready boolean fields are invalid")
    reasons = payload["reasons"]
    if not isinstance(reasons, list) or any(not isinstance(item, str) or not item for item in reasons):
        raise ValueError("environment_ready reasons are invalid")
    if payload["ready"] and reasons:
        raise ValueError("ready environment cannot contain failure reasons")
    if payload["ready"] and not payload["git_status_clean"]:
        raise ValueError("ready environment must have a clean Git status")
    if not payload["ready"] and not reasons:
        raise ValueError("blocked environment must contain at least one failure reason")
    manifest_sha = _strict_sha(payload["environment_manifest_sha256"], "environment_manifest_sha256")
    commit = payload["git_commit"]
    if not isinstance(commit, str) or not _GIT_COMMIT_RE.fullmatch(commit):
        raise ValueError("environment_ready git_commit is invalid")
    hashes = payload["authority_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(AUTHORITY_FILENAMES):
        raise ValueError("environment_ready authority_sha256 is incomplete")
    parsed_hashes = {
        key: _strict_sha(value, f"authority_sha256.{key}")
        for key, value in hashes.items()
    }
    packages = payload["python_packages"]
    if not isinstance(packages, dict) or set(packages) != set(PYTHON_PACKAGE_NAMES):
        raise ValueError("environment_ready python_packages is incomplete")
    if any(not isinstance(value, str) or not value for value in packages.values()):
        raise ValueError("environment_ready python_packages is invalid")
    ready = EnvironmentReady(
        payload["ready"], tuple(reasons), manifest_sha, commit,
        payload["git_status_clean"], parsed_hashes, dict(packages),
    )
    if raw != ready.bytes():
        raise ValueError("environment_ready is not canonical")
    return ready


def _is_reparse_point(path: Path) -> bool:
    """Return whether a path is a link/reparse point that must not be followed."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_attribute)


def _remove_attempt_local_path(path: Path, *, directory: bool) -> None:
    """Remove one validated generated artifact without following links."""

    if not os.path.lexists(path):
        return
    if _is_reparse_point(path):
        raise ValueError(f"attempt-local artifact is an unsafe link: {path}")
    if directory:
        if not path.is_dir():
            raise ValueError(f"attempt-local directory is not a directory: {path}")
        shutil.rmtree(path)
        return
    if not path.is_file():
        raise ValueError(f"attempt-local file is not a regular file: {path}")
    path.unlink()


def _remove_root_attempt_local_artifacts(repository_root: Path) -> None:
    """Delete only known Vivado attempt-local artifacts at repository root.

    Generated state under ``build/`` is removed separately.  This deliberately
    does not recurse through the checkout: source-controlled files and nested
    workspaces are outside the migration cleanup boundary.
    """

    root = _absolute(repository_root)
    for dirname in _ATTEMPT_LOCAL_DIRNAMES:
        _remove_attempt_local_path(root / dirname, directory=True)

    for child in root.iterdir():
        if not os.path.lexists(child):
            continue
        lowered = child.name.lower()
        if (
            lowered in _ATTEMPT_LOCAL_FILE_NAMES
            or lowered.endswith(_ATTEMPT_LOCAL_FILE_SUFFIXES)
        ):
            _remove_attempt_local_path(child, directory=False)


def _assert_fresh_build_root(repository_root: Path, output_root: Path) -> Path:
    repository = _absolute(repository_root)
    output = _absolute(output_root)
    if not repository.is_dir() or _is_reparse_point(repository):
        raise ValueError("migration repository root is not a real directory")
    if output != repository / "build":
        raise ValueError("migration output_root must be the repository build directory")
    if os.path.lexists(output):
        if _is_reparse_point(output) or not output.is_dir():
            raise ValueError("migration build directory is not a real directory")
        shutil.rmtree(output)
    _remove_root_attempt_local_artifacts(repository)
    output.mkdir(parents=True, exist_ok=False)
    return output


def prepare_environment(
    repository_root: Path,
    output_root: Path,
    *,
    vivado_executable: Path | None = None,
    timezone: str | None = None,
) -> EnvironmentReady:
    """Start a migration with a fresh build tree and write Phase-0 files.

    The function intentionally writes ``environment_ready.json`` even when
    the checkout is dirty or Vivado is unavailable.  A false result is a
    durable stop signal for Task 6, not permission to continue.
    """

    output = _assert_fresh_build_root(repository_root, output_root)
    manifest = capture_environment_manifest(
        repository_root, vivado_executable=vivado_executable, timezone=timezone
    )
    hashes = authority_sha256(repository_root)
    violations = authority_absolute_path_violations(repository_root)
    package_mismatches = authority_package_mismatches(repository_root)
    package_snapshot, package_error = _python_freeze()
    package_audit = python_package_audit()
    reasons: list[str] = []
    if not manifest.git_status_clean:
        reasons.append("git_working_tree_not_clean")
    if not re.fullmatch(r"3\.12(?:\.[0-9]+)?", manifest.python):
        reasons.append("python_3_12_required")
    if manifest.vivado != "2025.2" or manifest.vivado_build == "unavailable":
        reasons.append("vivado_2025_2_build_not_verified")
    if violations:
        reasons.append("authority_contains_absolute_path:" + ",".join(violations))
    if package_mismatches:
        reasons.append("packaged_authority_mismatch:" + ",".join(package_mismatches))
    if package_error is not None:
        reasons.append(package_error)
    for package in PYTHON_REQUIRED_PACKAGE_NAMES:
        if package_audit[package] == "missing":
            reasons.append("python_package_missing:" + package)
    ready = EnvironmentReady(
        ready=not reasons,
        reasons=tuple(reasons),
        environment_manifest_sha256=manifest.sha256,
        git_commit=manifest.git_commit,
        git_status_clean=manifest.git_status_clean,
        authority_sha256=hashes,
        python_packages=package_audit,
    )
    metadata = output / "metadata"
    metadata.mkdir()
    (metadata / "environment_manifest.json").write_bytes(manifest.bytes())
    (metadata / "environment_ready.json").write_bytes(ready.bytes())
    (metadata / "environment.txt").write_text(package_snapshot, encoding="utf-8")
    return ready


def load_environment_manifest(output_root: Path) -> tuple[EnvironmentManifest, bytes]:
    path = _absolute(output_root) / "metadata" / "environment_manifest.json"
    raw = path.read_bytes()
    return parse_environment_manifest(raw), raw


def require_environment_ready(output_root: Path) -> tuple[EnvironmentManifest, bytes]:
    output = _absolute(output_root)
    manifest, raw = load_environment_manifest(output)
    ready_path = output / "metadata" / "environment_ready.json"
    readiness = parse_environment_ready(ready_path.read_bytes())
    if not readiness.ready:
        raise ValueError("environment is not ready: " + ",".join(readiness.reasons))
    if readiness.environment_manifest_sha256 != manifest.sha256:
        raise ValueError("environment_ready does not bind environment_manifest")
    if readiness.git_commit != manifest.git_commit or readiness.git_status_clean != manifest.git_status_clean:
        raise ValueError("environment_ready git identity does not bind environment_manifest")
    repository_root = output.parent
    manifest_vivado = (
        None
        if manifest.vivado_executable == "unavailable"
        else Path(manifest.vivado_executable)
    )
    current = capture_environment_manifest(
        repository_root,
        vivado_executable=manifest_vivado,
        timezone=manifest.timezone,
    )
    for field in (
        "host", "os", "python", "vivado", "vivado_build", "repo_root",
        "git_commit", "git_status_clean", "vivado_executable",
    ):
        if getattr(current, field) != getattr(manifest, field):
            raise ValueError(f"environment manifest is stale for current {field}")
    current_hashes = authority_sha256(repository_root)
    if dict(current_hashes) != dict(readiness.authority_sha256):
        raise ValueError("authority bytes changed after environment freeze")
    package_mismatches = authority_package_mismatches(repository_root)
    if package_mismatches:
        raise ValueError(
            "packaged authority bytes differ from repository authority: "
            + ",".join(package_mismatches)
        )
    if python_package_audit() != dict(readiness.python_packages):
        raise ValueError("Python package environment changed after environment freeze")
    return manifest, raw


__all__ = [
    "AUTHORITY_FILENAMES",
    "ENVIRONMENT_SCHEMA_VERSION",
    "EnvironmentManifest",
    "EnvironmentReady",
    "authority_absolute_path_violations",
    "authority_package_mismatches",
    "authority_bytes",
    "authority_sha256",
    "capture_environment_manifest",
    "git_identity",
    "load_environment_manifest",
    "parse_environment_manifest",
    "parse_environment_ready",
    "prepare_environment",
    "python_package_audit",
    "require_environment_ready",
    "vivado_identity",
]


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Freeze the current RFSOC migration environment"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--vivado-executable", type=Path)
    parser.add_argument("--timezone")
    args = parser.parse_args(argv)
    repository_root = _absolute(args.repo_root)
    output_root = args.output_root or repository_root / "build"
    ready = prepare_environment(
        repository_root,
        output_root,
        vivado_executable=args.vivado_executable,
        timezone=args.timezone,
    )
    print(json.dumps(ready.as_mapping(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if ready.ready else 2


if __name__ == "__main__":
    raise SystemExit(_main())
