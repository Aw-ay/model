# Task 1 Report

## Outcome

Implemented the fixed-point Cycle expression foundation required for the production 2SPC calibrated H/V slice.

## Changed files

- `src/rfsoc_pulse_model/cycle/dsl/expr.py`
- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `src/rfsoc_pulse_model/cycle/dsl/__init__.py`
- `tests/cycle/test_fixed_point_expr.py`

## Commit

- `27155166b38b66ae4e7517466579348eccffd1f6` - `feat: add signed fixed-point cycle expressions`

## What changed

- Added signed fixed-point expression helpers in `cycle/dsl/fixed.py`:
  - `signed_mul(left, right, result_width)`
  - `round_shift_ties_away_from_zero(value, shift, result_width)`
  - `saturate_signed(value, result_width)`
- Added the smallest shared signed-value helper in `cycle/dsl/expr.py` to support the new expressions without changing existing operator behavior.
- Exported the new helpers from `cycle/dsl/__init__.py`.
- Added focused tests covering:
  - signed multiplication evaluation for positive and negative operands;
  - deterministic Verilog emission with explicit signed handling;
  - rejection of unsigned operands and non-positive result widths;
  - ties-away-from-zero rounding for positive, negative, and zero-shift cases;
  - signed saturation at both rails and at exact endpoints.

## Test commands and results

### Initial red state

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
```

Result:

```text
test_fixed_point_expr (unittest.loader._FailedTest.test_fixed_point_expr) ... ERROR
ImportError: Failed to import test module: test_fixed_point_expr
ModuleNotFoundError: No module named 'rfsoc_pulse_model.cycle.dsl.fixed'
```

### Focused fixed-point test file

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
```

Result:

```text
Ran 7 tests in 0.001s
OK
```

### Existing cycle DSL regression suite

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

Result:

```text
Ran 30 tests in 0.027s
OK
```

### Verilog regression suite

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\verilog' -v
```

Result:

```text
Ran 13 tests in 0.447s
OK (skipped=6)
```

## Concerns

- `signed_mul()` currently emits a sign-extended Verilog multiply whose intermediate product is wider than the declared output width, then relies on assignment width to trim to the requested 48-bit result. That is correct for the current contract and test coverage, but if a later slice needs an exact intermediate-width proof in RTL, it may want an explicit width-limiting helper.

## Fix Round 1

### Changed files

- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `tests/cycle/test_fixed_point_expr.py`

### Root cause

The evaluator for `round_shift_ties_away_from_zero()` already rounded negative values by magnitude and then reapplied the sign. The emitted Verilog did not do that for negative non-half values. It subtracted the bias from the negative signed input directly, which made values such as `-5 >> 2` diverge between the simulator and RTL text.

### Fix

- Updated the negative Verilog branch to:
  - sign-extend the operand by one bit for safe magnitude handling;
  - negate the extended value to form the magnitude;
  - add the rounding bias to that magnitude;
  - arithmetic-shift the magnitude;
  - reapply the sign by negating the shifted result.
- Extended the focused tests to cover:
  - negative non-half inputs `-5` and `-7`;
  - positive non-half input `5`;
  - the corresponding emitted Verilog branch text.

### Covering test commands and output

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
```

Output:

```text
Ran 8 tests in 0.001s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

Output:

```text
Ran 31 tests in 0.027s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\verilog' -v
```

Output:

```text
Ran 13 tests in 0.399s
OK (skipped=6)
```

### Self-review

- The change is narrowly scoped to the negative rounding branch in the fixed-point expression emitter.
- The simulator logic was already correct, and it was left unchanged.
- The updated tests now cover the exact mismatch called out by review, including negative non-half values that previously slipped through.
- Existing cycle and Verilog regression suites remained green after the fix.

## Final Review Fix

### Changed files

- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `tests/cycle/test_fixed_point_expr.py`
- `docs/handoff/VERIFICATION_EVIDENCE.md`
- `docs/handoff/CURRENT_STATE.md`
- `docs/superpowers/plans/2026-08-24-production-2spc-calibrated-hv.md`
- This report file, appended in the follow-up documentation commit.

### Implementation commit

- `2a7335f76b121e4078f10f8dbe07c3a958f8499a` - `fix: size fixed-point round-shift RTL results`

### Root cause and fix

The round-shift evaluator returned a masked `result_width` value, but its
emitted RTL retained the source or intermediate arithmetic width. The
positive/negative conditional could also become unsigned because the negative
magnitude path contains a concatenation. Consequently, a 48-bit rounded value
requested as 32 bits evaluated as a 49-bit raw result in the repository
Verilog evaluator, and a zero-shift 32-to-24 expression remained 32 bits when
composed with saturation.

The emitter now uses the existing signed resize/truncate contract on every
round-shift path: zero shift uses `_truncate_signed_verilog()`, and positive
and negative rounded branches are each explicitly signed-resized to
`result_width` before forming the conditional. The simulator semantics are
unchanged. Both narrowing and widening signed cases are covered.

### TDD regression evidence

The new evaluator-backed assertions were added to the existing round-shift
test method so the focused calibrated-H/V and full Cycle counts remain 14 and
51 respectively. Before the implementation change, the covering focused test
failed on the intended width mismatch:

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
```

Output summary:

```text
FAIL: test_round_shift_emits_explicit_result_width_for_all_paths
AssertionError: 49 != 32
Ran 13 tests in 0.003s
FAILED (failures=1)
exit_code=1
```

The regression uses `tests.cycle.verilog_eval.evaluate_verilog_expression`
for positive and negative rounded branches, zero-shift widening and
narrowing, and composed saturation at both signed rails.

### Final covering test commands and output

Focused fixed-point expressions:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
```

```text
Ran 13 tests in 0.003s
OK
exit_code=0
```

Calibrated H/V candidate:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
```

```text
Ran 14 tests in 0.255s
OK
exit_code=0
```

Full Cycle suite:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

```text
Ran 51 tests in 0.282s
OK
exit_code=0
```

Full Verilog suite:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\verilog' -v
```

```text
Ran 13 tests in 0.402s
OK (skipped=6)
exit_code=0
```

### Authority hash verification

Command:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'config\default.json'
Get-FileHash -Algorithm SHA256 -LiteralPath 'config\ip_architecture.json'
Get-FileHash -Algorithm SHA256 -LiteralPath 'config\ip_lock.json'
Get-FileHash -Algorithm SHA256 -LiteralPath 'config\ps_platform.json'
```

Verified values:

```text
config/default.json       D92C4A334728AF441B22FA907E55CF4D6D236D899F46CBE3CD3ED7F26F9D5EB3
config/ip_architecture.json 36034E9C7B64061CDD449FB43030AEA96368C95D6E88C8C6A0A9154DA9E0BD96
config/ip_lock.json       0B1C92166B605A0A56C867FB144896D23599ADE95538A29B72C9C274437FBE97
config/ps_platform.json   A1243D78A90CCB8E00F34749A8C3F18BF55870130C8F8372402407CF5591D11F
exit_code=0
```

### Provenance and scope review

- Historical `327 passed / 8 skipped` is explicitly scoped to baseline
  `commit:c118362` in both handoff documents.
- The current branch's full Python regression is recorded as interrupted,
  exit 1 with no unittest summary, and unclaimed; no branch-wide pass count
  is asserted.
- Current focused counts are calibrated H/V 14 tests and Cycle 51 tests.
- `production_integration_ready=false` remains unchanged.
- Task 5/6, OOC, Vivado/build/evidence, authority JSON, RFDC/MTS, and
  production registration content were not changed. No Vivado attempt was
  created.
- The corrected plan-file wording was included in the implementation commit.

### Self-review

- Direct evaluator output now has `result_width` and signed metadata on the
  shift-0, positive, and negative paths.
- The max-positive 48-bit/16-bit-shift case, negative branch, signed widening
  and narrowing, and composed positive/negative saturation rails all agree
  between `Expr.evaluate()` and emitted-expression evaluation.
- The existing 24-bit lane packing/saturation fix remains intact; the
  calibrated H/V candidate and full Cycle suites pass.
- No new concerns were found. The earlier report's unchanged note about the
  signed multiplication intermediate relying on assignment-width truncation
  remains outside this fix's scope.
