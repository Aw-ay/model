# Migration Environment Provenance

This repository separates two kinds of identity:

- Architecture authority is the byte content of `config/default.json`,
  `config/ip_architecture.json`, `config/ip_lock.json`, and
  `config/ps_platform.json`. A machine migration must not edit these files or
  recalculate them from a new path.
- Environment provenance is generated under `build/metadata/`. It records the
host, OS, Python, Vivado version/build, absolute checkout path, Git commit,
timezone, the exact Vivado executable path, and package snapshot for one fresh
attempt. The executable path is intentionally environment-only; it is never
written into an authority JSON file or an authority hash.

`ps_platform.json` keeps `source_bd_sha256` as source proof while using the
portable `source_bd_base: external_workspace_root` and relative
`source_bd_path`. No absolute checkout path belongs in authority JSON or in an
authority hash.

## Phase 0: freeze the new machine

From a clean checkout, run:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m rfsoc_pulse_model.ip.environment `
  --repo-root (Get-Location) `
  --timezone Asia/Hong_Kong `
  --vivado-executable '<VIVADO_2025_2_EXECUTABLE>'
```

The explicit Vivado option is optional when `vivado` is already on `PATH`.
When supplied, its absolute path is persisted in the environment manifest so a
later evidence validation probes the same installation rather than depending
on a transient shell `PATH` or environment variable.
The command first removes only the repository `build/` directory and creates a
new one. It then writes:

- `build/metadata/environment_manifest.json`
- `build/metadata/environment_ready.json`
- `build/metadata/environment.txt`

The readiness record audits `numpy`, `scipy`, `pytest`, and standard-library
`unittest`. The project gate requires the packages used by the regression
contract (`numpy`, `scipy`, and `unittest`); `pytest` is recorded when present
but is not silently assumed as the test runner.

`environment_ready.json` is written even when the result is blocked. Do not
continue to Task 6 unless it says `ready: true`. In particular, the required
identity checks are:

```powershell
git rev-parse HEAD
git status --short
python --version
```

The second command must print no lines. A dirty tree, Python other than 3.12,
unverified Vivado 2025.2/build, changed authority bytes, or an absolute path
inside authority JSON is a stop condition.

## Fresh attempt-local state

Never copy these items from another machine or checkout:

```text
build/ .Xil/ .runs/ .gen/ *.xpr *.jou journal.log
```

The fresh build is the only source of generated Tcl, catalog evidence, probe
evidence, connected requests, reports, and lifecycle state. A previous success
file is not valid merely because its JSON parses; the current manifest hash is
bound through catalog evidence, RFDC probe evidence, connected request, and
connected-shell evidence. The first migration attempt therefore starts with
no valid evidence and `attempt_id=1` (`vivado/connected_rfdc_shell_attempts/run_1`).
Subsequent attempts increment from the durable state/directories, so deleting a
copied success file cannot make an old attempt look current.

## Phase 1: re-prove the RFDC

After Phase 0, generate and run the RFDC-only probe in the fresh build. Call
`build_rfdc_probe_evidence` with the bytes of
`build/metadata/environment_manifest.json`; this produces schema 3 evidence
with `environment_manifest_sha256`. The strict parser requires the current
manifest hash before connected generation can consume the result. The accepted
probe must come from real Vivado output and establish the expected 868 CONFIG,
48 interface, 156 scalar-pin, MTS, and zero warning/critical-warning/error
facts.

Catalog discovery is also new-machine evidence. The generated discovery Tcl
uses `update_ip_catalog` and takes the environment hash as its fourth Tcl
argument. It writes schema 2 `catalog_evidence.tsv`; do not copy the old TSV.

## Phase 2 and Phase 3

Only after the new catalog and RFDC evidence are accepted, repair the six Task
5 blockers: exact CONFIG whitelist, immutable report bytes, Tcl hash binding,
utilization parsing, real Vivado reports, and atomic publication. Then run the
real connected BD flow through Task 6. `docs/handoff/CURRENT_STATE.md` and
`docs/handoff/NEXT_STEPS.md` remain authoritative about the existing Task 5
blocker; this migration layer does not claim hardware readiness.
