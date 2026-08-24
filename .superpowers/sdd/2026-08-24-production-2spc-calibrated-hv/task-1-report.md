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
