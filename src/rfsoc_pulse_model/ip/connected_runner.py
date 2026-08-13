"""Transactional runner and lifecycle authority for connected-shell attempts.

Real Vivado execution is intentionally injected.  This module owns the
filesystem transaction, while Task 3 remains the sole owner of pure evidence
semantics.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

from rfsoc_pulse_model.common.config import ModelConfig

from .connected import (
    ConnectedAuthorityBytes,
    ConnectedShellEvidence,
    ConnectedShellReadiness,
    RfdcProbeProvenance,
    canonical_connected_json_bytes,
    parse_connected_evidence,
    parse_connected_request,
    validate_connected_evidence,
)
from .connected_tcl import ConnectedTclArtifacts
from .platform import PsPlatformConfig
from .types import HardwareArchitectureConfig


_STATE_NAME = "connected_rfdc_shell_state.json"
_EVIDENCE_NAME = "connected_rfdc_shell_evidence.json"
_LOCK_NAME = ".connected_rfdc_shell.runner.lock"
_STATE_KEYS = frozenset({
    "lifecycle_schema_version", "state", "run_id", "attempt_relpath",
    "request_sha256", "evidence_sha256", "report_hashes",
})
_REPORT_NAMES = ("cdc", "clock_interaction", "timing_summary", "utilization")
_SHA256_LENGTH = 64


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate lifecycle JSON key")
        result[key] = value
    return result


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


@dataclass(frozen=True)
class ConnectedShellAttempt:
    run_id: int
    root: Path
    project_dir: Path
    request_path: Path
    realization_tcl_path: Path
    verification_tcl_path: Path
    candidate_evidence_path: Path
    readback_path: Path
    report_paths: Mapping[str, Path]
    log_path: Path

    @property
    def launch_tcl_path(self) -> Path:
        return self.root / "run_connected_rfdc_shell.tcl"

    def vivado_environment(self, verification_tcl_sha256: str) -> dict[str, str]:
        return {
            "CONNECTED_PROJECT_DIR": str(self.project_dir),
            "CONNECTED_READBACK_TSV": str(self.readback_path),
            "CONNECTED_REPORT_DIR": str(next(iter(self.report_paths.values())).parent),
            "CONNECTED_VERIFICATION_TCL_SHA256": verification_tcl_sha256,
        }


@dataclass(frozen=True)
class _LifecycleState:
    state: str
    run_id: int
    attempt_relpath: str
    request_sha256: str
    evidence_sha256: str | None
    report_hashes: tuple[tuple[str, str], ...]

    def bytes(self) -> bytes:
        return _canonical({
            "lifecycle_schema_version": 1,
            "state": self.state,
            "run_id": self.run_id,
            "attempt_relpath": self.attempt_relpath,
            "request_sha256": self.request_sha256,
            "evidence_sha256": self.evidence_sha256,
            "report_hashes": [list(item) for item in self.report_hashes],
        })


class ConnectedShellRunner:
    """Repository-locked owner of connected-shell lifecycle state."""

    def __init__(self, repository_root: Path, output_root: Path) -> None:
        self.repository_root = Path(os.path.abspath(repository_root))
        self.output_root = Path(os.path.abspath(output_root))
        if self.output_root != self.repository_root and self.repository_root not in self.output_root.parents:
            raise ValueError("output_root must be inside repository_root")
        _assert_safe_directory_chain(self.repository_root, self.output_root)

    @property
    def metadata_root(self) -> Path:
        return self.output_root / "metadata"

    @property
    def state_path(self) -> Path:
        return self.metadata_root / _STATE_NAME

    @property
    def evidence_path(self) -> Path:
        return self.metadata_root / _EVIDENCE_NAME

    def run(
        self,
        artifacts: ConnectedTclArtifacts,
        model: ModelConfig,
        architecture: HardwareArchitectureConfig,
        platform: PsPlatformConfig,
        production_lock: Mapping[str, object],
        probe_provenance: RfdcProbeProvenance,
        authority_bytes: ConnectedAuthorityBytes,
        *,
        launcher: Callable[[ConnectedShellAttempt], int],
    ) -> ConnectedShellReadiness:
        """Run one injected attempt and atomically publish only validated success."""

        if not isinstance(artifacts, ConnectedTclArtifacts):
            raise ValueError("artifacts must be ConnectedTclArtifacts")
        if not callable(launcher):
            raise ValueError("launcher must be callable")
        request = parse_connected_request(artifacts.request_bytes)
        if request.probe_provenance != probe_provenance:
            raise ValueError("artifact request probe provenance mismatch")
        with _repository_lock(self.repository_root / _LOCK_NAME):
            self.metadata_root.mkdir(parents=True, exist_ok=True)
            _assert_safe_directory_chain(self.repository_root, self.metadata_root)
            run_id = self._next_run_id()
            attempt = self._prepare_attempt(run_id, artifacts)
            in_progress = _LifecycleState(
                "in_progress", run_id, attempt.root.relative_to(self.output_root).as_posix(),
                artifacts.request_sha256, None, (),
            )
            _atomic_write(self.state_path, in_progress.bytes())
            try:
                result = launcher(attempt)
                if not isinstance(result, int) or isinstance(result, bool) or result != 0:
                    raise RuntimeError(f"launcher failed with exit status {result!r}")
                readback_bytes = _read_regular_file(attempt.readback_path)
                evidence = build_candidate_evidence(artifacts, readback_bytes, attempt)
                evidence_bytes = canonical_connected_json_bytes(evidence)
                report_hashes = _validated_report_hashes(attempt, evidence)
                readiness = validate_connected_evidence(
                    request, evidence, model, architecture, platform,
                    production_lock, probe_provenance, authority_bytes,
                )
                if not readiness.rfdc_shell_structural_ready:
                    raise ValueError("candidate evidence is not structurally ready: " + ",".join(readiness.blocking_reasons))
                _atomic_write(self.evidence_path, evidence_bytes)
                success = _LifecycleState(
                    "success", run_id, attempt.root.relative_to(self.output_root).as_posix(),
                    artifacts.request_sha256, _sha256(evidence_bytes), report_hashes,
                )
                _atomic_write(self.state_path, success.bytes())
                return readiness
            except Exception as error:
                failed = _LifecycleState(
                    "failed", run_id, attempt.root.relative_to(self.output_root).as_posix(),
                    artifacts.request_sha256, None, (),
                )
                _atomic_write(self.state_path, failed.bytes())
                if isinstance(error, RuntimeError):
                    raise
                raise RuntimeError(f"connected shell attempt {run_id} failed: {error}") from error

    def load_validated_success(
        self,
        model: ModelConfig,
        architecture: HardwareArchitectureConfig,
        platform: PsPlatformConfig,
        production_lock: Mapping[str, object],
        probe_provenance: RfdcProbeProvenance,
        authority_bytes: ConnectedAuthorityBytes,
    ) -> ConnectedShellEvidence:
        """Consume success only when lifecycle, files and pure evidence agree."""

        with _repository_lock(self.repository_root / _LOCK_NAME):
            state = _parse_state(_read_regular_file(self.state_path))
            if state.state != "success":
                raise ValueError("connected shell lifecycle is not success")
            attempt_root = _safe_attempt_root(self.output_root, state.attempt_relpath, state.run_id)
            evidence_bytes = _read_regular_file(self.evidence_path)
            if _sha256(evidence_bytes) != state.evidence_sha256:
                raise ValueError("connected shell evidence hash does not match success state")
            evidence = parse_connected_evidence(evidence_bytes)
            request_bytes = _read_regular_file(attempt_root / "connected_request.json")
            request = parse_connected_request(request_bytes)
            if _sha256(request_bytes) != state.request_sha256:
                raise ValueError("connected shell request hash does not match success state")
            if request.probe_provenance != probe_provenance:
                raise ValueError("connected shell probe provenance is stale")
            expected_reports = _validated_report_hashes_from_root(attempt_root, evidence)
            if expected_reports != state.report_hashes:
                raise ValueError("connected shell report hashes do not match success state")
            readiness = validate_connected_evidence(
                request, evidence, model, architecture, platform,
                production_lock, probe_provenance, authority_bytes,
            )
            if not readiness.rfdc_shell_structural_ready:
                raise ValueError("connected shell success evidence is no longer structurally ready")
            return evidence

    def _next_run_id(self) -> int:
        if not self.state_path.exists():
            return time.time_ns()
        try:
            prior = _parse_state(_read_regular_file(self.state_path)).run_id
        except ValueError:
            prior = 0
        return max(time.time_ns(), prior + 1)

    def _prepare_attempt(self, run_id: int, artifacts: ConnectedTclArtifacts) -> ConnectedShellAttempt:
        runs = self.output_root / "vivado" / "connected_rfdc_shell_attempts"
        runs.mkdir(parents=True, exist_ok=True)
        _assert_safe_directory_chain(self.repository_root, runs)
        root = runs / f"run_{run_id}"
        try:
            root.mkdir()
        except FileExistsError as error:
            raise RuntimeError("fresh connected shell attempt directory already exists") from error
        _assert_safe_directory_chain(self.repository_root, root)
        reports = root / "reports"
        reports.mkdir()
        paths = {name: reports / f"{name}.rpt" for name in _REPORT_NAMES}
        attempt = ConnectedShellAttempt(
            run_id=run_id, root=root, project_dir=root / "project",
            request_path=root / "connected_request.json",
            realization_tcl_path=root / "realize_connected_rfdc_shell.tcl",
            verification_tcl_path=root / "verify_connected_rfdc_shell.tcl",
            candidate_evidence_path=root / "connected_candidate_evidence.json",
            readback_path=root / "connected_readback.tsv",
            report_paths=paths, log_path=root / "vivado.log",
        )
        _atomic_write(attempt.request_path, artifacts.request_bytes)
        _atomic_write(attempt.realization_tcl_path, artifacts.realization_tcl)
        _atomic_write(attempt.verification_tcl_path, artifacts.verification_tcl)
        _atomic_write(
            attempt.launch_tcl_path,
            ("source {" + str(attempt.realization_tcl_path).replace("\\", "/") + "}\n"
             "source {" + str(attempt.verification_tcl_path).replace("\\", "/") + "}\n").encode("utf-8"),
        )
        return attempt


def build_vivado_command(attempt: ConnectedShellAttempt, vivado_executable: Path) -> tuple[str, ...]:
    """Concrete non-shell batch command used by Task 6."""
    executable = Path(vivado_executable)
    if not executable.name.lower().startswith("vivado"):
        raise ValueError("vivado_executable must name Vivado")
    return (str(executable), "-mode", "batch", "-source", str(attempt.launch_tcl_path), "-log", str(attempt.log_path))


def make_vivado_launcher(vivado_executable: Path) -> Callable[[ConnectedShellAttempt], int]:
    """Build, but do not invoke, the Task-6 real-Vivado launcher."""
    def launch(attempt: ConnectedShellAttempt) -> int:
        environment = os.environ.copy()
        environment.update(attempt.vivado_environment(attempt.verification_tcl_sha256))
        return subprocess.run(build_vivado_command(attempt, vivado_executable), cwd=attempt.root, env=environment, check=False).returncode
    return launch


def build_candidate_evidence(
    artifacts: ConnectedTclArtifacts, readback_bytes: bytes, attempt: ConnectedShellAttempt,
) -> ConnectedShellEvidence:
    """Turn exact Tcl readback + attempt reports into Task-3 canonical evidence.

    This function does not infer hardware facts: every cell, RFDC CONFIG,
    AXIS/RF interface, clock/reset/lock, address, IRQ and boolean originates in
    the machine TSV.  It only reuses the already canonical request as the
    schema carrier after proving every measured item matches it.
    """
    request = parse_connected_request(artifacts.request_bytes)
    raw = _parse_readback(readback_bytes)
    meta = raw["META"]
    expected_meta = {
        "request_sha256": artifacts.request_sha256,
        "realization_tcl_sha256": artifacts.realization_tcl_sha256,
        "verification_tcl_sha256": artifacts.verification_tcl_sha256,
        "vivado_version": request.vivado_version,
        "device_part": request.device_part,
    }
    if meta != expected_meta: raise ValueError("readback META provenance mismatch")
    if dict(raw["CELL"]) != {cell.name: cell.vlnv for cell in request.cells}: raise ValueError("readback cell/VLNV mismatch")
    if dict(raw["CONFIG"]) != dict(artifacts.rfdc_properties): raise ValueError("readback RFDC CONFIG mismatch")
    data_expected = {item.name: ("Master" if item.direction == "master" else "Slave", "xilinx.com:interface:axis_rtl:1.0", str(item.width_bits // 8)) for item in request.interfaces}
    if dict(raw["DATA"]) != data_expected: raise ValueError("readback AXIS interface mismatch")
    rf_expected = {item.name: (item.mode, item.vlnv) for item in artifacts.rfdc_interfaces if item.name not in {"s_axi", *data_expected}}
    rf_expected = {name: value for name, value in rf_expected.items() if name in {"adc0_clk", "adc1_clk", "adc2_clk", "adc3_clk", "dac0_clk", "dac1_clk", "sysref_in"} or name.startswith(("vin", "vout"))}
    if dict(raw["RF"]) != rf_expected: raise ValueError("readback RF external interface mismatch")
    expected_clock = {(clock.domain, member): clock.net for clock in request.clocks for member in clock.members}
    if dict(raw["CLOCK"]) != expected_clock: raise ValueError("readback clock-net membership mismatch")
    expected_reset = {(reset.domain, member): reset.reset_net for reset in request.resets for member in reset.members}
    if dict(raw["RESET"]) != expected_reset: raise ValueError("readback reset-net membership mismatch")
    expected_lock = {(reset.domain, reset.dcm_locked_pin): reset.dcm_locked_pin for reset in request.resets}
    if dict(raw["LOCK"]) != expected_lock: raise ValueError("readback dcm_locked mismatch")
    address = raw["ADDRESS"]
    if not isinstance(address, list) or len(address) != 1 or len(address[0]) != 2 or address[0][0] != "rfdc_0/s_axi/Reg" or not address[0][1] or raw["IRQ"] != [("rfdc_0/irq", "irq_concat_0/In0", "irq_concat_0/dout", "zynq_ultra_ps_e_0/pl_ps_irq0")]: raise ValueError("readback address/IRQ mismatch")
    booleans = raw["BOOL"]
    required_booleans = {"validate_bd_design_passed", "synthesis_completed", "cdc_safe", "clock_safety_verified", "mts_configuration_verified", "mts_runtime_verified"}
    if set(booleans) != required_booleans: raise ValueError("readback boolean set mismatch")
    reports = tuple(sorted((name, _sha256(_read_regular_file(path))) for name, path in attempt.report_paths.items()))
    return ConnectedShellEvidence(
        1, artifacts.request_sha256, request.model_config_sha256, request.architecture_config_sha256,
        request.ps_platform_config_sha256, request.production_lock_sha256,
        artifacts.realization_tcl_sha256, artifacts.verification_tcl_sha256,
        request.vivado_version, request.device_part, request.cells, request.interfaces,
        request.clocks, request.resets, request.address_path, request.irq_path,
        request.rfdc_semantics, request.mts_groups,
        booleans["mts_configuration_verified"], booleans["mts_runtime_verified"],
        booleans["validate_bd_design_passed"], booleans["synthesis_completed"],
        booleans["cdc_safe"], booleans["clock_safety_verified"], reports,
    )


def _parse_readback(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw.endswith(b"\n"): raise ValueError("readback TSV must be LF-terminated bytes")
    try: lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error: raise ValueError("readback TSV must be UTF-8") from error
    values: dict[str, object] = {"META": {}, "CELL": [], "CONFIG": [], "DATA": [], "RF": [], "CLOCK": [], "RESET": [], "LOCK": [], "ADDRESS": [], "IRQ": [], "BOOL": {}}
    ended = False
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 2 or fields[0] != "CONNECTED_READBACK" or any(not field or any(c in field for c in ";`$[]\\") for field in fields): raise ValueError("unsafe or malformed connected readback")
        kind = fields[1]
        if kind == "END":
            if fields != ["CONNECTED_READBACK", "END"] or ended: raise ValueError("invalid readback END")
            ended = True; continue
        if ended: raise ValueError("readback data after END")
        if kind == "META" and len(fields) == 4:
            meta = values["META"]; assert isinstance(meta, dict)
            if fields[2] in meta: raise ValueError("duplicate readback META")
            meta[fields[2]] = fields[3]
        elif kind in {"CELL", "CONFIG"} and len(fields) == 4:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], fields[3]))
        elif kind == "DATA" and len(fields) == 6:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], (fields[3], fields[4], fields[5])))
        elif kind == "RF" and len(fields) == 5:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], (fields[3], fields[4])))
        elif kind in {"CLOCK", "RESET", "LOCK"} and len(fields) == 5:
            cast = values[kind]; assert isinstance(cast, list); cast.append(((fields[2], fields[3]), fields[4]))
        elif kind in {"ADDRESS", "IRQ"} and len(fields) >= 3:
            cast = values[kind]; assert isinstance(cast, list); cast.append(tuple(fields[2:]))
        elif kind == "BOOL" and len(fields) == 4 and fields[3] in {"true", "false"}:
            booleans = values["BOOL"]; assert isinstance(booleans, dict)
            if fields[2] in booleans: raise ValueError("duplicate readback boolean")
            booleans[fields[2]] = fields[3] == "true"
        else: raise ValueError("unknown or malformed connected readback record")
    if not ended: raise ValueError("readback END is missing")
    for kind in ("CELL", "CONFIG", "DATA", "RF", "CLOCK", "RESET", "LOCK"):
        cast = values[kind]; assert isinstance(cast, list)
        if len(cast) != len(dict(cast)): raise ValueError(f"duplicate readback {kind}")
    return values


def _validated_report_hashes(attempt: ConnectedShellAttempt, evidence: ConnectedShellEvidence) -> tuple[tuple[str, str], ...]:
    expected = _validated_report_hashes_from_root(attempt.root, evidence)
    if tuple(sorted(evidence.report_hashes)) != expected:
        raise ValueError("candidate evidence report hashes do not match attempt reports")
    return expected


def _validated_report_hashes_from_root(root: Path, evidence: ConnectedShellEvidence) -> tuple[tuple[str, str], ...]:
    _assert_safe_directory_chain(root, root)
    reports_root = root / "reports"
    _assert_safe_directory_chain(root, reports_root)
    hashes = tuple(sorted(
        (name, _sha256(_read_regular_file(reports_root / f"{name}.rpt")))
        for name in _REPORT_NAMES
    ))
    if tuple(sorted(evidence.report_hashes)) != hashes:
        raise ValueError("candidate evidence report hashes do not match attempt reports")
    return hashes


def _parse_state(raw: bytes) -> _LifecycleState:
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid connected shell lifecycle state: {error}") from error
    if not isinstance(payload, dict) or set(payload) != _STATE_KEYS:
        raise ValueError("connected shell lifecycle state has unknown or missing keys")
    if payload["lifecycle_schema_version"] != 1:
        raise ValueError("unsupported connected shell lifecycle schema")
    state = payload["state"]
    if state not in {"in_progress", "failed", "success"}:
        raise ValueError("invalid connected shell lifecycle state")
    run_id = payload["run_id"]
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValueError("connected shell run_id must be positive integer")
    relative = payload["attempt_relpath"]
    if not isinstance(relative, str) or not relative or "\\" in relative or relative.startswith("/") or ".." in relative.split("/"):
        raise ValueError("connected shell attempt_relpath is unsafe")
    request_sha = _sha(payload["request_sha256"], "request_sha256")
    evidence_sha = payload["evidence_sha256"]
    if state == "success":
        evidence_sha = _sha(evidence_sha, "evidence_sha256")
    elif evidence_sha is not None:
        raise ValueError("non-success lifecycle must not authorize evidence")
    pairs = payload["report_hashes"]
    if not isinstance(pairs, list):
        raise ValueError("report_hashes must be an array")
    result: list[tuple[str, str]] = []
    for item in pairs:
        if not isinstance(item, list) or len(item) != 2 or item[0] not in _REPORT_NAMES:
            raise ValueError("invalid lifecycle report hash entry")
        result.append((item[0], _sha(item[1], "report hash")))
    if len(result) != len(set(result)):
        raise ValueError("duplicate lifecycle report hash")
    if state == "success" and {name for name, _ in result} != set(_REPORT_NAMES):
        raise ValueError("success lifecycle requires exact report hash set")
    if state != "success" and result:
        raise ValueError("non-success lifecycle must not authorize reports")
    parsed = _LifecycleState(state, run_id, relative, request_sha, evidence_sha, tuple(sorted(result)))
    if raw != parsed.bytes():
        raise ValueError("connected shell lifecycle state is not canonical")
    return parsed


def _safe_attempt_root(output_root: Path, relpath: str, run_id: int) -> Path:
    result = output_root.joinpath(*relpath.split("/"))
    if result.name != f"run_{run_id}":
        raise ValueError("connected shell attempt run ID/path mismatch")
    _assert_safe_directory_chain(output_root, result)
    if not result.is_dir():
        raise ValueError("connected shell attempt directory is missing")
    return result


def _read_regular_file(path: Path) -> bytes:
    """Read through a no-follow handle, rejecting symlinks and junctions."""

    if os.name == "posix":
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ValueError(f"unable to open regular non-reparse file: {path}") from error
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"path is not a regular file: {path}")
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 65536):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    if os.name == "nt":
        # Reuse the reviewed handle-first Win32 reader from lock promotion;
        # it opens with FILE_FLAG_OPEN_REPARSE_POINT and rejects directories or
        # any reparse-tagged handle before reading bytes.
        from .lock import _read_windows_regular_journal_no_reparse
        try:
            return _read_windows_regular_journal_no_reparse(path)
        except OSError as error:
            raise ValueError(f"unable to read regular non-reparse file: {path}") from error
    raise ValueError(f"unsupported no-follow filesystem platform: {os.name}")


def _assert_regular_no_reparse(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError(f"required file is missing: {path}") from error
    if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
        raise ValueError(f"path is not a regular non-reparse file: {path}")


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _assert_safe_directory_chain(root: Path, target: Path) -> None:
    # Do not resolve first: ``resolve`` follows a Windows junction/symlink and
    # would hide the unsafe component we are required to reject.
    root = Path(os.path.abspath(root))
    target = Path(os.path.abspath(target))
    if target != root and root not in target.parents:
        raise ValueError("path escapes repository root")
    current = root
    if current.exists():
        info = current.lstat()
        if _is_reparse(info):
            raise ValueError("repository root is a reparse point")
    for part in target.relative_to(root).parts:
        current = current / part
        if current.exists():
            info = current.lstat()
            if _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"path contains a reparse/non-directory component: {current}")


@contextmanager
def _repository_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_directory_chain(path.parent, path.parent)
    if path.exists():
        _assert_regular_no_reparse(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        _acquire_lock(descriptor, path)
        yield
    finally:
        try:
            _release_lock(descriptor)
        except OSError:
            pass
        os.close(descriptor)


def _acquire_lock(descriptor: int, path: Path) -> None:
    if os.name == "nt":
        import msvcrt
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError(f"connected shell runner is already active: {path}") from error
    else:
        import fcntl
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError(f"connected shell runner is already active: {path}") from error


def _release_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_directory_chain(path.parent, path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".connected-tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
