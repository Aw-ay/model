# Task 4 Report

## Outcome

Added Task 4 evidence for the calibrated H/V 2SPC candidate without changing
production ownership, authority JSON, Vivado/build files, or Task 5/6 evidence.
The candidate remains `architecture_pending` and
`production_integration_ready=false`.

## Changed files

- `tests/cycle/test_production_calibrated_hv.py`
- `docs/handoff/CURRENT_STATE.md`
- `docs/handoff/NEXT_STEPS.md`
- `docs/handoff/OPEN_ISSUES.md`
- `docs/handoff/VERIFICATION_EVIDENCE.md`
- `.superpowers/sdd/2026-08-24-production-2spc-calibrated-hv/task-4-report.md`

The pre-existing user modification to
`docs/superpowers/plans/2026-08-24-production-2spc-calibrated-hv.md` was left
untouched.

## Evidence added

- Golden identity-profile comparison across all nine H/V HIGH/MID/LOW range
  pairs, two samples per beat, signed I/Q values, authority ties-away-from-
  zero rounding, and packed H/V equality.
- Deliberate Golden positive/negative authority saturation-rail assertions;
  the candidate's existing runtime-overflow test remains sticky and
  fail-closed rather than silently accepting a saturated beat.
- Consecutive valid beats with bases `0, 2, 4, 6`, one registered output per
  cycle, one-cycle module latency, and no backpressure port.
- Verilog byte equality from two fresh candidate instances and complete
  assertions for all 26 port widths.

The Golden equivalence fixture uses an in-memory nominal-gain-normalized copy
of the channel map to isolate this candidate's scalar fixed-point boundary.
It does not claim nominal-gain normalization, receive matrix inversion,
delay, reflection, monitor, DMA, timing, runtime MTS, or board acceptance.

## TDD and test results

The new tests were written before any production implementation change in this
task. The existing candidate already satisfied the requested behavior, so no
production source file required modification.

Focused candidate file:

```text
Ran 13 tests in 0.238s
OK
```

Full Cycle suite:

```text
Ran 50 tests in 0.273s
OK
```

Full Python regression command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests'
```

Result: interrupted by the user-directed stop after several minutes of
CPU-bound execution, exit code `1`, with no failure output or final unittest
summary emitted. The full regression is therefore not claimed as passed.

## Frozen authority hashes

All four actual SHA-256 values matched their frozen values:

| File | SHA-256 | Result |
|---|---|---|
| `config/default.json` | `d92c4a334728af441b22fa907e55cf4d6d236d899f46cbe3cd3ed7f26f9d5eb3` | match |
| `config/ip_architecture.json` | `36034e9c7b64061cdd449fb43030aea96368c95d6e88c8c6a0a9154da9e0bd96` | match |
| `config/ip_lock.json` | `0b1c92166b605a0a56c867fb144896d23599ade95538a29b72c9c274437fbe97` | match |
| `config/ps_platform.json` | `a1243d78a90ccb8e00f34749a8c3f18bf55870130c8f8372402407cf5591d11f` | match |

No Vivado attempt was created.

## Fix Round 1 — paired saturation boundary evidence

Review identified an evidence-only P2 gap: the prior Golden rail assertion and
candidate subclass-injected overflow assertion were separate fixtures. The
new test
`test_golden_saturation_boundary_pairs_with_intentional_candidate_fail_closed_injection`
uses one deliberate out-of-contract response, `reflection_sample` positive
rail plus `0.25` (`524288.1875` in the normalized Golden boundary).

- Golden authority rounding/saturation maps that shared response to the
  signed maximum code `8388607` for both samples.
- The test-only candidate subclass derives the same fixed-point rounded
  boundary code `8388611`, injects it through the real overflow gate, and
  asserts `calibration_error_o=1`, `incident_valid_o=0`, and all four packed
  I/Q data outputs equal zero.
- The test name and assertions make the intentional non-equality explicit:
  Golden saturates numerically, while the candidate rejects the out-of-contract
  response and fails closed. No production behavior is being claimed for that
  deliberate overflow vector.

Fix-round focused test result:

```text
Ran 1 test in 0.010s
OK
```

The updated candidate file has 14 passing tests; the updated full Cycle suite
has 51 passing tests. No authority/config/handoff files, plan files, Vivado
files, or production readiness fields were modified in this fix round.
