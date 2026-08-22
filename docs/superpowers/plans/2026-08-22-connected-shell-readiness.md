# Connected Shell Readiness Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the top-level generated metadata consume the current connected-shell success only through the validated runner API, while keeping the OOC shell structurally separate from production integration readiness.

**Architecture:** Add a pure evidence-to-status summary beside the connected evidence model, then add one environment-bound orchestration function in the IP generator that reconstructs the current authority/probe context and calls `ConnectedShellRunner.load_validated_success`. The top-level generator records this status under `connected_shell` and never promotes it to `production_integration_ready`.

**Tech Stack:** Python 3.12, `unittest`, canonical JSON, existing `ConnectedShellRunner`, Vivado-generated ignored evidence.

**Spec:** `docs/superpowers/plans/2026-08-13-connected-rfdc-shell.md`, Task 7; migration constraints from `docs/migration/environment-provenance.md`.

## Global Constraints

- Preserve Vivado 2025.2, RFDC 2.6 configuration, MTS authority, and all four authority SHA-256 values.
- Keep all 24 AXIS interfaces in the connected BD and keep the connected shell OOC/module-boundary only.
- Do not interpret OOC boundary timing as post-route timing closure.
- Do not call `json.loads` on connected lifecycle/evidence files from top-level orchestration or create a second lifecycle parser.
- `production_integration_ready` remains false until the independent production-owner gates are satisfied.
- Any source commit changes the environment provenance; after commit, regenerate Phase 0, catalog, probe, connected request, and connected evidence.

### Task 1: Define pure connected-shell metadata summary

**Files:**
- Modify: `src/rfsoc_pulse_model/ip/connected.py`
- Modify: `tests/ip/test_connected.py`

**Interfaces:**
- Consumes: `ConnectedShellEvidence`
- Produces: `summarize_connected_shell_evidence(evidence: ConnectedShellEvidence) -> dict[str, object]`

- [ ] **Step 1: Write the failing test**

Add a test using the existing ready fixture. Assert the summary reports `status="success"`, structural readiness true, production integration false, 24 interfaces, synthesis/BD/CDC/clock/MTS configuration true, MTS runtime false, and no structural blockers.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
python -m unittest tests.ip.test_connected.ConnectedShellContractTest.test_evidence_summary_keeps_ooc_shell_separate -v
```

Expected: import failure because the summary function does not exist.

- [ ] **Step 3: Implement the minimal pure summary**

Return only canonical JSON-compatible values derived from the evidence object. Include the four report hashes as a name-to-hash mapping and use the fixed structural-only reason `production_integration_pending` for the separate production gate; never set that gate true.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same command and require one passing test.

- [ ] **Step 5: Commit the pure contract**

```powershell
git add src/rfsoc_pulse_model/ip/connected.py tests/ip/test_connected.py
git commit -m "feat: summarize connected shell readiness"
```

### Task 2: Add environment-bound validated-success consumption

**Files:**
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Modify: `tests/ip/test_generate_architecture.py`

**Interfaces:**
- Consumes: current `build/metadata/environment_manifest.json`, current probe evidence/Tcl, packaged authority bytes, and `ConnectedShellRunner.load_validated_success`.
- Produces: `consume_connected_shell_readiness(output_root: Path) -> dict[str, object]`.

- [ ] **Step 1: Write failing tests**

Add tests for a temporary output without Phase-0 evidence (returns `status="not_bound"` and structural false) and for a current-success fixture routed through the runner API (returns the pure summary). Add a stale/failed lifecycle case that returns structural false and a stable non-success reason without parsing lifecycle JSON in the test target.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
python -m unittest tests.ip.test_generate_architecture -v
```

Expected: import failure for `consume_connected_shell_readiness`.

- [ ] **Step 3: Implement the minimal orchestration**

When no environment manifest exists, return a not-bound status. Otherwise reconstruct `ModelConfig`, `HardwareArchitectureConfig`, `PsPlatformConfig`, packaged production lock, discovery bytes, catalog request bytes, and parsed probe provenance; build `ConnectedAuthorityBytes`; call only `ConnectedShellRunner.load_validated_success`. Map missing or invalid/stale lifecycle failures to false status without reading lifecycle/evidence JSON directly.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the focused generation and connected tests; require all pass.

- [ ] **Step 5: Commit the consumer**

```powershell
git add src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_generate_architecture.py
git commit -m "feat: consume validated connected shell readiness"
```

### Task 3: Publish shell readiness in top-level metadata

**Files:**
- Modify: `src/rfsoc_pulse_model/generate.py`
- Modify: `tests/ip/test_generate_architecture.py`
- Modify: `tests/verilog/test_generate.py`

**Interfaces:**
- Consumes: `consume_connected_shell_readiness(root)`.
- Produces: top-level `manifest.json["connected_shell"]` and matching `metadata/ip_architecture.json["connected_shell"]` status, with overall `production_integration_ready` unchanged.

- [ ] **Step 1: Write failing tests**

Cover generation without current evidence, current success, stale/failed state, deterministic double generation, and explicit false overall production readiness even when connected-shell structural readiness is true.

- [ ] **Step 2: Run tests and verify RED**

Run the new test names individually and confirm the new metadata key is absent or incorrect before implementation.

- [ ] **Step 3: Implement minimal top-level integration**

Call the consumer after IP architecture generation and before writing the final architecture/manifest bytes. Store the same summary in both metadata locations, preserve existing architecture readiness calculation, and keep generated RTL ownership unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the IP generation and Verilog generation test modules with the bundled Python runtime.

- [ ] **Step 5: Commit Task 7 source/tests**

```powershell
git add src/rfsoc_pulse_model/generate.py tests/ip/test_generate_architecture.py tests/verilog/test_generate.py
git commit -m "feat: publish connected shell readiness"
```

### Task 4: Re-freeze provenance and regenerate current-machine evidence

**Files:**
- Generated only under ignored `build/`.
- Update tracked handoff records only after fresh evidence is accepted.

- [ ] **Step 1: Run full Python regression from writable workspace root**

Use `E:\AWAY` as the process directory and include both `E:\AWAY\RFSOC-model\src` and `E:\AWAY\RFSOC-model` in `PYTHONPATH`; require 0 failures.

- [ ] **Step 2: Commit source and confirm clean checkout**

Require `git status --short` empty and all four authority hashes unchanged.

- [ ] **Step 3: Prepare a fresh Phase-0 environment**

Delete only the ignored build tree through the environment preparation entry point; record the new manifest and readiness hashes for the new commit.

- [ ] **Step 4: Re-run catalog, RFDC probe, connected generation, and real OOC Vivado runner**

Require RFDC 2.6, 868/48/156 probe inventory, 24 AXIS interfaces, 0 IOB, exact vendor CDC waivers, OOC timing boundary handling, and successful atomic publication.

- [ ] **Step 5: Run top-level production generation against the new success**

Require `connected_shell.status="success"`, structural readiness true, MTS runtime false, and overall production integration false.

- [ ] **Step 6: Update tracked handoff/acceptance docs from measured output**

Update `docs/handoff/CURRENT_STATE.md`, `docs/handoff/NEXT_STEPS.md`, `docs/handoff/OPEN_ISSUES.md`, and `docs/handoff/VERIFICATION_EVIDENCE.md` so they no longer claim the real connected-shell run is unstarted, while retaining post-route, runtime MTS, production DSP, DMA/GEM3, and board gates as pending.

