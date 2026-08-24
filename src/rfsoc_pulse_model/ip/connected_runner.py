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
import re
import stat
import subprocess
import tempfile

from rfsoc_pulse_model.common.config import ModelConfig

from .cdc_inventory import CDC15_ENDPOINT_PAIRS
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
_MAX_REPORT_BYTES = 1_000_000
_LAUNCH_TCL_BYTES = (
    b"source $::env(CONNECTED_REALIZATION_TCL)\n"
    b"source $::env(CONNECTED_VERIFICATION_TCL)\n"
)
_VENDOR_CDC_WAIVER_IDS = frozenset({"CDC-11", "CDC-13", "CDC-15"})
_OOC_BOUNDARY_CHECK_COUNTS = {
    "no_clock": 10,
    "no_input_delay": 515,
    "no_output_delay": 536,
}


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

    @property
    def verification_tcl_sha256(self) -> str:
        """Hash the exact attempt Tcl that the launcher is about to source."""
        return _sha256(_read_regular_file(self.verification_tcl_path))

    def vivado_environment(self, verification_tcl_sha256: str) -> dict[str, str]:
        return {
            "CONNECTED_PROJECT_DIR": str(self.project_dir),
            "CONNECTED_READBACK_TSV": str(self.readback_path),
            "CONNECTED_REPORT_DIR": str(next(iter(self.report_paths.values())).parent),
            "CONNECTED_VERIFICATION_TCL_SHA256": verification_tcl_sha256,
            # Keep source paths out of Tcl brace words.  A legal Windows path
            # component can contain `}`, which would otherwise terminate one.
            "CONNECTED_REALIZATION_TCL": str(self.realization_tcl_path),
            "CONNECTED_VERIFICATION_TCL": str(self.verification_tcl_path),
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
    """Repository-locked owner of connected-shell lifecycle state.

    The strict default makes a production Task 6 invocation impossible to
    start without a fresh Phase-0 environment manifest.  Synthetic tests or
    historical schema-1 fixtures may explicitly opt out with
    ``require_environment=False``; that compatibility switch is never used
    by the migration path.
    """

    def __init__(
        self,
        repository_root: Path,
        output_root: Path,
        *,
        require_environment: bool = True,
    ) -> None:
        self.repository_root = Path(os.path.abspath(repository_root))
        self.output_root = Path(os.path.abspath(output_root))
        if not isinstance(require_environment, bool):
            raise ValueError("require_environment must be a boolean")
        self.require_environment = require_environment
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
        self._require_current_environment(authority_bytes)
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
                _assert_attempt_bindings(
                    attempt.root,
                    artifacts.request_sha256,
                    artifacts.realization_tcl_sha256,
                    artifacts.verification_tcl_sha256,
                )
                result = launcher(attempt)
                if not isinstance(result, int) or isinstance(result, bool) or result != 0:
                    raise RuntimeError(f"launcher failed with exit status {result!r}")
                _assert_attempt_bindings(
                    attempt.root,
                    artifacts.request_sha256,
                    artifacts.realization_tcl_sha256,
                    artifacts.verification_tcl_sha256,
                )
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

        self._require_current_environment(authority_bytes)
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
            _assert_attempt_bindings(
                attempt_root,
                evidence.connected_request_sha256,
                evidence.realization_tcl_sha256,
                evidence.verification_tcl_sha256,
            )
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

    def _require_current_environment(self, authority_bytes: ConnectedAuthorityBytes) -> None:
        """Reject copied connected artifacts when a Phase-0 manifest is bound."""

        if not authority_bytes.environment_manifest_bytes:
            if self.require_environment:
                raise ValueError(
                    "Task 6 requires a Phase-0 environment manifest; "
                    "schema-1 authority is legacy fixture-only"
                )
            return
        from .environment import require_environment_ready

        _manifest, current_bytes = require_environment_ready(self.output_root)
        if current_bytes != authority_bytes.environment_manifest_bytes:
            raise ValueError("connected shell authority is not bound to current environment")

    def _next_run_id(self) -> int:
        """Return the next durable attempt id, starting at one on a fresh tree."""

        prior = 0
        try:
            if self.state_path.exists():
                prior = _parse_state(_read_regular_file(self.state_path)).run_id
        except ValueError:
            prior = 0
        attempts_root = self.output_root / "vivado" / "connected_rfdc_shell_attempts"
        highest_on_disk = 0
        if attempts_root.is_dir() and not attempts_root.is_symlink():
            for child in attempts_root.iterdir():
                if not child.is_dir() or child.is_symlink():
                    continue
                match = re.fullmatch(r"run_([1-9][0-9]*)", child.name)
                if match is not None:
                    highest_on_disk = max(highest_on_disk, int(match.group(1)))
        return max(prior, highest_on_disk) + 1

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
        _atomic_write(attempt.launch_tcl_path, _LAUNCH_TCL_BYTES)
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
        "synthesis_mode": "out_of_context",
        "axis_boundary": "bd_external_interfaces",
        "timing_scope": "ooc_boundary_only",
    }
    if meta != expected_meta: raise ValueError("readback META provenance mismatch")
    if dict(raw["CELL"]) != {cell.name: cell.vlnv for cell in request.cells}: raise ValueError("readback cell/VLNV mismatch")
    if dict(raw["CONFIG"]) != dict(artifacts.rfdc_properties): raise ValueError("readback RFDC CONFIG mismatch")
    if dict(raw["PS_CONFIG"]) != dict(artifacts.ps_properties): raise ValueError("readback PS property mismatch")
    if raw["INVERTER"] != [("C_OPERATION", "not", "C_SIZE", "1")]: raise ValueError("readback reset inverter mismatch")
    if raw["CONCAT"] != [("NUM_PORTS", "1")]: raise ValueError("readback IRQ concat mismatch")
    data_expected = {item.name: ("Master" if item.direction == "master" else "Slave", "xilinx.com:interface:axis_rtl:1.0", str(item.width_bits // 8)) for item in request.interfaces}
    if dict(raw["DATA"]) != data_expected: raise ValueError("readback AXIS interface mismatch")
    rf_expected = {item.name: (item.mode, item.vlnv) for item in artifacts.rfdc_interfaces if item.name not in {"s_axi", *data_expected}}
    rf_expected = {name: value for name, value in rf_expected.items() if name in {"adc0_clk", "adc1_clk", "adc2_clk", "adc3_clk", "dac0_clk", "dac1_clk", "sysref_in"} or name.startswith(("vin", "vout"))}
    if dict(raw["RF"]) != rf_expected: raise ValueError("readback RF external interface mismatch")
    expected_ports = {name for name in data_expected} | set(rf_expected)
    expected_port_names = {name: f"{name}_0" for name in expected_ports}
    if dict(raw["PORT"]) != expected_port_names: raise ValueError("readback external interface port inventory mismatch")
    # Vivado 2025.2 does not preserve the requested logical net label when a
    # source-driven BD net is saved.  Its deterministic realization is based
    # on the first source pin (for example ``rfdc_0/clk_adc0`` becomes
    # ``rfdc_0_clk_adc0``).  Compare the measured canonical name explicitly;
    # accepting arbitrary aliases here would make the readback non-authoritative.
    expected_clock = {
        (clock.domain, member): _vivado_source_net_name(clock.members[0])
        for clock in request.clocks for member in clock.members
    }
    if dict(raw["CLOCK"]) != expected_clock: raise ValueError("readback clock-net membership mismatch")
    expected_reset = {
        (reset.domain, member): _vivado_reset_net_name(reset.dcm_locked_members[-1])
        for reset in request.resets for member in reset.members
    }
    if dict(raw["RESET"]) != expected_reset: raise ValueError("readback reset-net membership mismatch")
    expected_lock = {
        (reset.domain, reset.dcm_locked_pin): _vivado_lock_net_name(reset.dcm_locked_pin)
        for reset in request.resets
    }
    if dict(raw["LOCK"]) != expected_lock: raise ValueError("readback dcm_locked mismatch")
    address = raw["ADDRESS"]
    if not isinstance(address, list) or len(address) != 1 or len(address[0]) != 2 or address[0][0] != "rfdc_0/s_axi/Reg" or not address[0][1] or raw["IRQ"] != [("rfdc_0/irq", "irq_concat_0/In0", "irq_concat_0/dout", "zynq_ultra_ps_e_0/pl_ps_irq0")]: raise ValueError("readback address/IRQ mismatch")
    booleans = raw["BOOL"]
    required_booleans = {"validate_bd_design_passed", "synthesis_completed", "mts_runtime_verified"}
    if set(booleans) != required_booleans: raise ValueError("readback boolean set mismatch")
    expected_mts = dict(artifacts.mts_properties)
    if dict(raw["MTS"]) != expected_mts: raise ValueError("readback MTS configuration mismatch")
    report_safety = _validate_report_safety(attempt, ooc_boundary=True)
    reports = tuple(sorted((name, _sha256(_read_regular_file(path))) for name, path in attempt.report_paths.items()))
    # An environment-bound request must publish schema 2 so the evidence
    # carries the same Phase-0 environment provenance as the request.
    return ConnectedShellEvidence(
        2 if request.environment_manifest_sha256 else 1,
        artifacts.request_sha256, request.model_config_sha256, request.architecture_config_sha256,
        request.ps_platform_config_sha256, request.production_lock_sha256,
        artifacts.realization_tcl_sha256, artifacts.verification_tcl_sha256,
        request.vivado_version, request.device_part, request.cells, request.interfaces,
        request.clocks, request.resets, request.address_path, request.irq_path,
        request.rfdc_semantics, request.mts_groups,
        # This truth is derived only after exact RFDC CONFIG readback above.
        True, booleans["mts_runtime_verified"],
        booleans["validate_bd_design_passed"], booleans["synthesis_completed"],
        report_safety["cdc_safe"], report_safety["clock_safety_verified"], reports,
        request.environment_manifest_sha256,
    )


def _vivado_source_net_name(source_pin: str) -> str:
    """Return the measured Vivado 2025.2 name for a source-driven BD net."""

    owner, separator, pin = source_pin.partition("/")
    if not separator or not owner or not pin or "/" in pin:
        raise ValueError("connected request source pin is not a canonical cell/pin path")
    return f"{owner}_{pin}"


def _vivado_reset_net_name(dcm_locked_member: str) -> str:
    """Return the measured reset-generator output net name."""

    reset_cell, separator, pin = dcm_locked_member.partition("/")
    if not separator or not reset_cell or pin != "dcm_locked":
        raise ValueError("connected request reset source is not a canonical dcm_locked path")
    return f"{reset_cell}_peripheral_aresetn"


def _vivado_lock_net_name(dcm_locked_port: str) -> str:
    """Return the measured net name created for an external lock port."""

    if not dcm_locked_port or dcm_locked_port.endswith("_1"):
        raise ValueError("connected request lock port is not canonical")
    return f"{dcm_locked_port}_1"


def _parse_readback(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw.endswith(b"\n"): raise ValueError("readback TSV must be LF-terminated bytes")
    try: lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error: raise ValueError("readback TSV must be UTF-8") from error
    values: dict[str, object] = {"META": {}, "CELL": [], "CONFIG": [], "PS_CONFIG": [], "DATA": [], "RF": [], "PORT": [], "CLOCK": [], "RESET": [], "LOCK": [], "ADDRESS": [], "IRQ": [], "BOOL": {}, "INVERTER": [], "CONCAT": [], "MTS": []}
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
        elif kind in {"CELL", "CONFIG", "PS_CONFIG", "PORT", "MTS"} and len(fields) == 4:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], fields[3]))
        elif kind == "DATA" and len(fields) == 6:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], (fields[3], fields[4], fields[5])))
        elif kind == "RF" and len(fields) == 5:
            cast = values[kind]; assert isinstance(cast, list); cast.append((fields[2], (fields[3], fields[4])))
        elif kind in {"CLOCK", "RESET", "LOCK"} and len(fields) == 5:
            cast = values[kind]; assert isinstance(cast, list); cast.append(((fields[2], fields[3]), fields[4]))
        elif kind == "INVERTER" and len(fields) == 6:
            cast = values[kind]; assert isinstance(cast, list); cast.append(tuple(fields[2:]))
        elif kind == "CONCAT" and len(fields) == 4:
            cast = values[kind]; assert isinstance(cast, list); cast.append(tuple(fields[2:]))
        elif kind in {"ADDRESS", "IRQ"} and len(fields) >= 3:
            cast = values[kind]; assert isinstance(cast, list); cast.append(tuple(fields[2:]))
        elif kind == "BOOL" and len(fields) == 4 and fields[3] in {"true", "false"}:
            booleans = values["BOOL"]; assert isinstance(booleans, dict)
            if fields[2] in booleans: raise ValueError("duplicate readback boolean")
            booleans[fields[2]] = fields[3] == "true"
        else: raise ValueError("unknown or malformed connected readback record")
    if not ended: raise ValueError("readback END is missing")
    for kind in ("CELL", "CONFIG", "PS_CONFIG", "DATA", "RF", "PORT", "CLOCK", "RESET", "LOCK", "MTS"):
        cast = values[kind]; assert isinstance(cast, list)
        if len(cast) != len(dict(cast)): raise ValueError(f"duplicate readback {kind}")
    return values


def _validate_report_safety(
    attempt: ConnectedShellAttempt, *, ooc_boundary: bool = False,
) -> dict[str, bool]:
    """Parse only the measured Vivado 2025.2 synthesized-report grammar."""
    reports = {
        name: _read_attempt_report(attempt, path).decode("utf-8", "strict")
        for name, path in attempt.report_paths.items()
    }
    cdc_pairs = _parse_cdc_report(reports["cdc"])
    _parse_clock_interaction_report(reports["clock_interaction"], cdc_pairs)
    _parse_timing_summary_report(reports["timing_summary"], ooc_boundary=ooc_boundary)
    _parse_utilization_report(reports["utilization"])
    return {"cdc_safe": True, "clock_safety_verified": True}


_REPORT_HEADER = re.compile(
    r"^\| (?P<key>Tool Version|Command|Design|Device|Design State)\s+:\s+(?P<value>.+?)\s*$",
    re.MULTILINE,
)
_REQUIRED_VIVADO_BUILD = "6299465"
_CHECK_TIMING_CATEGORIES = (
    "no_clock", "constant_clock", "pulse_width_clock",
    "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay",
    "multiple_clock", "generated_clocks", "loops", "partial_input_delay",
    "partial_output_delay", "latch_loops",
)


def _validate_report_header(report: str, command_prefix: str) -> None:
    entries = _REPORT_HEADER.findall(report)
    if len(entries) != 5 or len({key for key, _ in entries}) != 5:
        raise ValueError("Vivado report header is incomplete or duplicated")
    header = dict(entries)
    if re.fullmatch(
        rf"Vivado v\.2025\.2 \(win64\) Build {_REQUIRED_VIVADO_BUILD} .+",
        header["Tool Version"],
    ) is None:
        raise ValueError("report is not from the required Vivado 2025.2 build 6299465 grammar")
    command_ok = header["Command"].startswith(command_prefix + " -file ")
    if command_prefix == "report_cdc -details":
        command_ok = command_ok or header["Command"].startswith(
            command_prefix + " -show_waiver -file ",
        )
    if not command_ok and command_prefix == "report_cdc -details":
        # A bounded Task-5 grammar probe may scope the same Vivado report to
        # one explicitly named clock pair.  Keep the Tcl shape exact; do not
        # accept arbitrary options or hand-written status markers.
        command_ok = re.fullmatch(
            r"report_cdc -from \[get_clocks -quiet [A-Za-z0-9_.-]+\] "
            r"-to \[get_clocks -quiet [A-Za-z0-9_.-]+\] "
            r"-details -file .+",
            header["Command"],
        ) is not None
    if not command_ok:
        raise ValueError("report command does not match the bounded invocation")
    if re.fullmatch(r"[A-Za-z0-9_.-]+", header["Design"]) is None:
        raise ValueError("report design name is malformed")
    if (
        re.fullmatch(r"xczu27dr-fsve1156(?:-2-i)?", header["Device"]) is None
        or header["Design State"] != "Synthesized"
    ):
        raise ValueError("report device or design state mismatch")


def _normalize_report_newlines(report: str) -> str:
    """Normalize the measured Windows CRLF grammar without accepting bare CR."""
    normalized = report.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ValueError("Vivado report contains noncanonical line endings")
    return normalized


def _is_exact_vendor_cdc_waiver(
    identifier: str, source: str, destination: str,
) -> bool:
    if identifier == "CDC-11":
        source_match = re.fullmatch(
            r".*/(rx|tx)_reset_0/U0/ACTIVE_LOW_PR_OUT_DFF\[0\]\.FDRE_PER_N/C",
            source,
        )
        destination_match = re.fullmatch(
            r".*/rfdc_0/inst/cdc_(adc|dac)([0-9]+)_clk_valid_i/syncstages_ff_reg\[0\]/D",
            destination,
        )
        if not source_match or not destination_match:
            return False
        source_domain, destination_domain = source_match.group(1), destination_match.group(1)
        tile = int(destination_match.group(2))
        return (
            (source_domain == "rx" and destination_domain == "adc" and tile in range(4))
            or (source_domain == "tx" and destination_domain == "dac" and tile in range(2))
        )
    if identifier == "CDC-13":
        source_match = re.fullmatch(
            r".*/rfdc_0/inst/adc([0-3])_cmn_control_ff_reg\[12\]/C", source,
        )
        destination_match = re.fullmatch(
            r".*/rfdc_0/inst/connected_.*_rf_wrapper_i/rx([0-3])_u_adc/CONTROL_COMMON\[12\]",
            destination,
        )
        return bool(
            source_match and destination_match
            and source_match.group(1) == destination_match.group(1)
        )
    return identifier == "CDC-15" and _canonical_cdc15_pair(source, destination) is not None


def _canonical_cdc15_pair(source: str, destination: str) -> tuple[str, str] | None:
    return next(
        (pair for pair in CDC15_ENDPOINT_PAIRS
         if source.endswith(pair[0]) and destination.endswith(pair[1])),
        None,
    )


def _parse_cdc_report(report: str) -> set[tuple[str, str]]:
    report = _normalize_report_newlines(report)
    _validate_report_header(report, "report_cdc -details")
    requires_cdc15_inventory = "report_cdc -details -show_waiver" in report
    if "\nCDC Report\n" not in report:
        raise ValueError("CDC report title is missing")
    cdc_body = report.split("\nCDC Report\n", 1)[1].strip()
    if cdc_body == "All paths are Safely Timed.":
        if requires_cdc15_inventory:
            raise ValueError("CDC-15 endpoint inventory does not match the measured set")
        return set()
    summary_area = report.split("Source Clock:", 1)[0]
    summary_rows = re.findall(
        r"^(CDC-[0-9]+)\s+(Info|Warning|Critical)\s+([0-9]+)\s+(.+?)\s*$",
        summary_area,
        re.MULTILINE,
    )
    summary: dict[str, int] = {}
    summary_severity: dict[str, str] = {}
    for identifier, severity, count, _description in summary_rows:
        if identifier in summary or int(count) <= 0:
            raise ValueError("CDC summary contains duplicate or unsafe circuitry")
        summary[identifier] = int(count)
        summary_severity[identifier] = severity
    waived_summary: dict[str, int] = {}
    if re.search(r"^ID\s+Waived Endpoints\s*$", report, re.MULTILINE):
        waived_area = report.split("Source Clock:", 1)[0].split(
            "ID      Waived Endpoints", 1
        )[1]
        for identifier, count in re.findall(
            r"^(CDC-[0-9]+)\s+([0-9]+)\s*$", waived_area, re.MULTILINE,
        ):
            if identifier in waived_summary or int(count) <= 0:
                raise ValueError("CDC waived summary is duplicated or invalid")
            waived_summary[identifier] = int(count)
    blocks = list(re.finditer(
        r"^Source Clock:\s*(\S+)\s*$\n^Destination Clock:\s*(\S+)\s*$\n"
        r"^CDC Type:\s*.+?$\n(?P<body>.*?)(?=^Source Clock:|\Z)",
        report,
        re.MULTILINE | re.DOTALL,
    ))
    pairs: set[tuple[str, str]] = set()
    observed: dict[str, int] = {}
    observed_waived: dict[str, int] = {}
    observed_cdc15_pairs: set[tuple[str, str]] = set()
    for block in blocks:
        pair = (block.group(1), block.group(2))
        if pair in pairs: raise ValueError("duplicate CDC clock-pair block")
        pairs.add(pair)
        details = re.findall(
            r"^\s*[0-9]+\s+(CDC-[0-9]+)\s+(Info|Warning|Critical)\s+.*?"
            r"\s+[0-9]+\s+(?:False Path|Asynch Clock Groups|Asynchronous Groups|Partial False Path)\s+"
            r"(?P<source>\S+)\s+(?P<destination>\S+)"
            r"(?:\s+(?P<waived>[YN]))?\s*$",
            block.group("body"),
            re.MULTILINE,
        )
        if not details: raise ValueError("CDC clock-pair block lacks detail rows")
        for identifier, severity, source, destination, waived in details:
            if waived == "Y":
                if identifier == "CDC-15" and _canonical_cdc15_pair(source, destination) is None:
                    raise ValueError("CDC-15 endpoint inventory contains an unapproved vendor waiver")
                if identifier not in _VENDOR_CDC_WAIVER_IDS or not _is_exact_vendor_cdc_waiver(identifier, source, destination):
                    raise ValueError("CDC detail contains an unapproved vendor waiver")
                observed_waived[identifier] = observed_waived.get(identifier, 0) + 1
                if identifier == "CDC-15":
                    canonical = _canonical_cdc15_pair(source, destination)
                    if canonical is None or canonical in observed_cdc15_pairs:
                        raise ValueError("CDC-15 endpoint inventory is invalid")
                    observed_cdc15_pairs.add(canonical)
            else:
                if severity != "Info": raise ValueError("CDC detail contains unsafe circuitry")
                observed[identifier] = observed.get(identifier, 0) + 1
    expected_unwaived: dict[str, int] = {}
    for identifier, count in summary.items():
        severity = summary_severity[identifier]
        if severity == "Info":
            expected_unwaived[identifier] = count
            if observed_waived.get(identifier, 0) != 0:
                raise ValueError("CDC Info circuitry cannot be vendor-waived")
        elif (
            identifier not in _VENDOR_CDC_WAIVER_IDS
            or observed.get(identifier, 0) != 0
            or observed_waived.get(identifier, 0) != count
        ):
            raise ValueError("CDC summary contains duplicate or unsafe circuitry")
    if (
        observed != expected_unwaived
        or observed_waived != waived_summary
        or bool(blocks) != bool(summary or waived_summary)
    ):
        raise ValueError("CDC summary/detail counts do not match")
    if requires_cdc15_inventory and observed_cdc15_pairs != set(CDC15_ENDPOINT_PAIRS):
        raise ValueError("CDC-15 endpoint inventory does not match the measured set")
    return pairs


def _parse_clock_interaction_report(
    report: str, cdc_pairs: set[tuple[str, str]],
) -> None:
    report = _normalize_report_newlines(report)
    _validate_report_header(report, "report_clock_interaction")
    if "\nClock Interaction Report\n" not in report or "\nClock Interaction Table\n" not in report:
        raise ValueError("clock-interaction report title is missing")
    lines = report.splitlines()
    try:
        separator = next(
            index for index, line in enumerate(lines)
            if line.lstrip().startswith("------------") and "  ------------" in line
        )
    except StopIteration as error:
        raise ValueError("clock-interaction table separator is missing") from error
    data_lines: list[str] = []
    for line in lines[separator + 1:]:
        if not line.strip():
            if data_lines: break
            continue
        data_lines.append(line)
    if not data_lines: raise ValueError("clock-interaction table has no rows")
    pairs: set[tuple[str, str]] = set()
    for line in data_lines:
        match = re.fullmatch(
            r"\s*(\S+)\s+(\S+)\s+.*?(Clean|Ignored)\s+"
            r"(Timed|Asynchronous Groups|False Path|Partial False Path)\s*",
            line,
        )
        if match is None: raise ValueError("unknown clock-interaction row grammar")
        source, destination, classification, constraint = match.groups()
        pair = (source, destination)
        if pair in pairs: raise ValueError("duplicate clock-interaction pair")
        pairs.add(pair)
        if classification == "Clean" and constraint in {"Timed", "Partial False Path"}:
            continue
        # Vivado 2025.2 emits both ``Asynchronous Groups`` and ``False Path``
        # for ignored cross-domain pairs.  Either is acceptable only when the
        # same pair has a measured, Info-only CDC block; no uncorrelated path
        # exception is allowed to hide an unsafe crossing.
        if (
            classification != "Ignored"
            or constraint not in {"Asynchronous Groups", "False Path"}
            or pair not in cdc_pairs
        ):
            raise ValueError("ignored clock pair lacks correlated safe CDC detail")
    if not cdc_pairs.issubset(pairs):
        raise ValueError("CDC clock pair is absent from clock-interaction table")


def _parse_timing_summary_report(
    report: str, *, ooc_boundary: bool = False,
) -> None:
    report = _normalize_report_newlines(report)
    _validate_report_header(
        report, "report_timing_summary -report_unconstrained -no_detailed_paths",
    )
    if "\nTiming Summary Report\n" not in report or "\ncheck_timing report\n" not in report:
        raise ValueError("timing-summary structural sections are missing")
    checks = tuple(
        (name, int(count)) for name, count in re.findall(
            r"^[0-9]+\. checking ([a-z_]+) \(([0-9]+)\)\s*$", report, re.MULTILINE,
        )
    )
    zero_expected = tuple((name, 0) for name in _CHECK_TIMING_CATEGORIES)
    if ooc_boundary:
        expected = tuple(
            (name, _OOC_BOUNDARY_CHECK_COUNTS.get(name, 0))
            for name in _CHECK_TIMING_CATEGORIES
        )
        if checks not in {zero_expected + zero_expected, expected + expected}:
            raise ValueError(
                "check_timing categories are missing, reordered, or nonzero for OOC boundary"
            )
        expected = None
    else:
        expected = zero_expected
    if expected is not None and checks != expected + expected:
        scope = "OOC boundary" if ooc_boundary else "top-level"
        raise ValueError(f"check_timing categories are missing, reordered, or nonzero for {scope}")
    marker = "| Unconstrained Path Table"
    if report.count(marker) != 1: raise ValueError("unconstrained-path table is missing or duplicated")
    tail = report.split(marker, 1)[1].splitlines()
    try:
        header_index = next(index for index, line in enumerate(tail) if line.strip().startswith("Path Group"))
        underline_index = next(
            index for index in range(header_index + 1, len(tail))
            if tail[index].strip().startswith("----------")
        )
    except StopIteration as error:
        raise ValueError("unconstrained-path table grammar is incomplete") from error
    data_lines: list[str] = []
    saw_blank = False
    for line in tail[underline_index + 1:]:
        if not line.strip():
            if data_lines:
                saw_blank = True
            continue
        if saw_blank:
            raise ValueError("timing report contains trailing unconstrained data")
        data_lines.append(line)
    if not data_lines:
        return
    if not ooc_boundary:
        raise ValueError("timing report contains unconstrained paths")
    for line in data_lines:
        fields = line.split()
        if (
            len(fields) not in {2, 3}
            or fields[0] != "(none)"
            or any(re.fullmatch(r"[A-Za-z0-9_.-]+", field) is None for field in fields[1:])
        ):
            raise ValueError("OOC timing report contains non-boundary unconstrained paths")


def _parse_utilization_report(report: str) -> None:
    """Require the measured Vivado utilization table, not a placeholder token."""
    report = _normalize_report_newlines(report)
    _validate_report_header(report, "report_utilization")
    if (
        "\nUtilization Estimates\n" not in report
        and "\nUtilization Design Information\n" not in report
    ):
        raise ValueError("utilization report title is missing")
    if re.search(
        r"^\|\s*Site Type\s*\|\s*Used\s*\|\s*Fixed\s*\|\s*"
        r"(?:Prohibited\s*\|\s*)?Available\s*\|\s*Util%\s*\|\s*$",
        report,
        re.MULTILINE,
    ) is None:
        raise ValueError("utilization table header is missing")
    rows = re.findall(
        r"^\|\s*(?P<site>[^|]+?)\s*\|\s*"
        r"(?P<used>[0-9][0-9,]*)\s*\|\s*"
        r"(?P<fixed>[0-9][0-9,]*)\s*\|\s*"
        r"(?:(?P<prohibited>[0-9][0-9,]*)\s*\|\s*)?"
        r"(?P<available>[0-9][0-9,]*)\s*\|\s*"
        r"(?P<util>[0-9]+(?:\.[0-9]+)?%?)\s*\|\s*$",
        report,
        re.MULTILINE,
    )
    if not rows:
        raise ValueError("utilization table has no measured rows")
    seen: set[str] = set()
    for site, used_text, fixed_text, prohibited_text, available_text, util_text in rows:
        site = site.strip()
        if not site or site in seen:
            raise ValueError("utilization table contains duplicate or empty site rows")
        seen.add(site)
        used = int(used_text.replace(",", ""))
        fixed = int(fixed_text.replace(",", ""))
        prohibited = int(prohibited_text.replace(",", "")) if prohibited_text else 0
        available = int(available_text.replace(",", ""))
        utilization = float(util_text.rstrip("%"))
        if (
            fixed > used
            or prohibited < 0
            or used > available
            or utilization < 0.0
            or utilization > 100.0
        ):
            raise ValueError("utilization table contains impossible measured values")


def _read_attempt_report(attempt: ConnectedShellAttempt, path: Path) -> bytes:
    _assert_safe_directory_chain(attempt.root, path.parent)
    payload = _read_regular_file(path)
    if not payload or len(payload) > _MAX_REPORT_BYTES:
        raise ValueError("report is empty or exceeds bounded parser limit")
    return payload


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


def _assert_attempt_bindings(
    root: Path,
    request_sha256: str,
    realization_tcl_sha256: str,
    verification_tcl_sha256: str,
) -> None:
    """Prove that the files actually present in an attempt are the bound inputs.

    Readback Tcl contains declared hashes, but those declarations are not
    self-authenticating.  Check the attempt files before and after the launcher
    and again when consuming success, so replacing a Tcl or request file cannot
    preserve an otherwise valid-looking evidence record.
    """

    root = Path(os.path.abspath(root))
    _assert_safe_directory_chain(root, root)
    bindings = (
        ("connected_request.json", _sha(request_sha256, "request_sha256")),
        ("realize_connected_rfdc_shell.tcl", _sha(realization_tcl_sha256, "realization_tcl_sha256")),
        ("verify_connected_rfdc_shell.tcl", _sha(verification_tcl_sha256, "verification_tcl_sha256")),
    )
    for name, expected in bindings:
        path = root / name
        _assert_safe_directory_chain(root, path.parent)
        if _sha256(_read_regular_file(path)) != expected:
            raise ValueError(f"connected attempt file hash mismatch: {name}")
    launch_path = root / "run_connected_rfdc_shell.tcl"
    _assert_safe_directory_chain(root, launch_path.parent)
    if _read_regular_file(launch_path) != _LAUNCH_TCL_BYTES:
        raise ValueError("connected launch Tcl binding mismatch")


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
