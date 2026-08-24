# Task 2 Report

## Outcome

Implemented the calibrated H/V 2SPC candidate as an architecture-pending Cycle module in the isolated `E:\AWAY\RFSOC-model` workspace, reusing the Task 1 fixed-point helpers instead of duplicating arithmetic.

## Changed files

- `src/rfsoc_pulse_model/cycle/hardware/production_calibrated_hv.py`
- `tests/cycle/test_production_calibrated_hv.py`

## Commit

- `5a499b8eb9476dedbc58b24d8907c3ebe42336ae` - `feat: add calibrated H/V 2spc candidate`

## What changed

- Added `HvCalibrationCoefficients` with immutable six-path scalar coefficients and an `identity()` constructor.
- Added `RxCalibratedHvFrontend2Spc` with:
  - registered H/V I/Q lane outputs in `reflection_sample` format;
  - exact sample-base preservation;
  - sticky `format_error_o`, `gap_error_o`, and `calibration_error_o`;
  - reserved range-code rejection after enable;
  - ADC ownership validation that keeps ADC3/ADC7 calibration-only;
  - fail-closed behavior for upstream faults and invalid/mutated coefficient payloads.
- Reused `signed_mul()`, `round_shift_ties_away_from_zero()`, and `saturate_signed()` from `rfsoc_pulse_model.cycle.dsl.fixed`.
- Added focused Cycle tests for:
  - HIGH/MID/LOW H/V echo selection;
  - reserved-code stickiness;
  - pre-enable ignore semantics;
  - reset re-arming;
  - upstream fault propagation;
  - mutated channel-map rejection;
  - unity gain, negative gain, positive gain, and half-way rounding behavior;
  - mutated invalid coefficient fail-closed behavior.

## TDD evidence

### RED 1: module missing

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
```

Result:

```text
test_production_calibrated_hv (unittest.loader._FailedTest.test_production_calibrated_hv) ... ERROR
ImportError: Failed to import test module: test_production_calibrated_hv
ModuleNotFoundError: No module named 'rfsoc_pulse_model.cycle.hardware.production_calibrated_hv'
```

### GREEN 1: initial candidate behavior

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
```

Result:

```text
Ran 5 tests in 0.017s
OK
```

### RED 2: invalid coefficient payload not fail-closing

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
```

Result:

```text
FAIL: test_invalid_coefficients_raise_sticky_calibration_error
AssertionError: 1 != 0
```

Root cause:

- A mutated out-of-contract coefficient object could slip past normal dataclass validation and still emit a valid beat.

### GREEN 2: invalid coefficient payload now sticky fail-closed

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
```

Result:

```text
Ran 7 tests in 0.019s
OK
```

## Verification commands and output

### Focused fixed-point + calibrated-front-end tests

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr tests.cycle.test_production_calibrated_hv -v
```

Output:

```text
Ran 15 tests in 0.021s
OK
```

### Full Cycle suite

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

Output:

```text
Ran 38 tests in 0.041s
OK
```

## Self-review

- Confirmed the change is limited to the new candidate module and its focused tests.
- Confirmed no production registry change, no Vivado attempt, and no RFDC/MTS/authority file edits were introduced.
- Removed one dead internal helper before commit and reran verification afterward.

## Concerns

- The current candidate protects against mutated invalid coefficient payloads at module construction time by falling back to identity coefficients internally and asserting `calibration_error_o`. That matches the fail-closed intent exercised by the tests, but a future registration/Verilog-emission task may still want an explicit hard rejection path for invalid coefficients before any RTL text is emitted.

## Fix Round 1

### Changed files

- `src/rfsoc_pulse_model/cycle/dsl/__init__.py`
- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `src/rfsoc_pulse_model/cycle/hardware/production_calibrated_hv.py`
- `tests/cycle/test_fixed_point_expr.py`
- `tests/cycle/test_production_calibrated_hv.py`

### Root cause

- `RxCalibratedHvFrontend2Spc` converted invalid constructor coefficients into an identity fallback instead of rejecting them before construction.
- `_calibrate_sample()` always saturated rounded results, so the front-end had no shared simulator/RTL expression for “rounded value is outside the signed 24-bit/4-frac contract” and therefore no way to fail-close on overflow before asserting valid.
- The earlier ownership test only exercised matched H/V range pairs, which left selector cross-pairs less directly proven against ADC3/ADC7 leakage.

### Fix

- Added `signed_out_of_range(value, result_width)` to the Cycle fixed-point DSL and covered it with focused tests for both rails plus emitted signed-compare RTL.
- Changed `RxCalibratedHvFrontend2Spc.__init__()` to revalidate the supplied coefficient object by reconstructing `HvCalibrationCoefficients`, so mutated invalid constructor payloads now raise `ValueError` before module construction/Verilog emission.
- Changed the calibrated H/V data path to compute rounded values, detect out-of-range results before saturation, and treat any I/Q lane overflow as a sticky `calibration_error_o` that suppresses the valid beat and zeroes the registered data outputs.
- Strengthened the ownership test to cover all nine valid H/V selector combinations and explicitly prove that neither ADC3 nor ADC7 values can surface on any H/V output lane.

### TDD evidence

#### RED 3: missing out-of-range helper and rejected semantics still absent

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr -v
```

Result:

```text
ImportError: cannot import name 'signed_out_of_range' from 'rfsoc_pulse_model.cycle.dsl.fixed'
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv -v
```

Result:

```text
FAIL: test_invalid_coefficients_raise_value_error_before_module_construction
AssertionError: ValueError not raised

FAIL: test_runtime_overflow_is_sticky_and_fail_closed
AssertionError: 1 != 0
```

#### GREEN 3: constructor rejection, overflow fail-closed, and helper coverage

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr -v
```

Result:

```text
Ran 10 tests in 0.001s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv -v
```

Result:

```text
Ran 8 tests in 0.041s
OK
```

### Verification commands and output

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr tests.cycle.test_production_calibrated_hv -v
```

Output:

```text
Ran 18 tests in 0.043s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

Output:

```text
Ran 41 tests in 0.059s
OK
```

### Self-review

- Confirmed the constructor no longer contains any identity fallback path for invalid supplied coefficients.
- Confirmed overflow detection happens on the rounded 48-bit intermediate before saturation and is what drives the sticky fail-closed calibration fault.
- Kept the change scoped to the Task 2 module/tests plus the allowed fixed-point helper extension; the modified plan file already present in the workspace was left untouched.

### Concerns

- The runtime overflow regression test uses a tiny test-only subclass to inject an out-of-range rounded value into the candidate’s real overflow gate. That was necessary because the legal scalar path with valid 16-bit ADC samples and valid 24-bit/20-frac coefficients does not naturally exceed the 24-bit/4-frac reflection range.

## Fix Round 2

### Changed files

- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `tests/cycle/test_fixed_point_expr.py`
- `tests/cycle/test_production_calibrated_hv.py`

### Root cause

- `saturate_signed()` evaluated as a 24-bit expression in the simulator but emitted a conditional whose in-range branch retained the source width, so concatenating two saturated samples into one 48-bit H/V lane let Verilog truncate the upper sample in the emitted RTL.
- The prior overflow regression covered the fail-closed plumbing but did not directly prove that the repository’s emitted candidate RTL preserved both 24-bit H and V sample results.

### Fix

- Added an explicit signed-width truncation path inside `saturate_signed()` so the emitted in-range branch is sized to the requested result width before any downstream concatenation.
- Added helper regressions that require explicit `[23:0]` sizing in emitted saturated expressions and in a concatenated two-lane packed RTL example.
- Added candidate RTL regressions that emit `RxCalibratedHvFrontend2Spc` through the repository’s deterministic `VerilogEmitter` and assert that each packed H/V lane assignment contains two explicit 24-bit preserved sample results.

### TDD evidence

#### RED 4: emitted saturation path still unsized in RTL

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr -v
```

Result:

```text
FAIL: test_saturate_signed_emits_an_explicit_24_bit_result
Regex didn't match: '\[23:0\]' not found in "(($signed(48'sd1073741827) > 24'sd8388607) ? 24'sd8388607 : (($signed(48'sd1073741827) < 24'sd-8388608) ? 24'sd-8388608 : $signed(48'sd1073741827)))"

FAIL: test_concat_of_saturated_samples_preserves_both_24_bit_lanes_in_emitted_rtl
AssertionError: 0 not greater than or equal to 2
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv -v
```

Result:

```text
FAIL: test_emitted_rtl_preserves_both_h_and_v_24_bit_lane_results
AssertionError: 0 not greater than or equal to 2
```

#### GREEN 4: emitted saturation path now explicitly 24-bit before lane packing

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr -v
```

Result:

```text
Ran 12 tests in 0.001s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv -v
```

Result:

```text
Ran 9 tests in 0.060s
OK
```

### Verification commands and output

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr tests.cycle.test_production_calibrated_hv -v
```

Output:

```text
Ran 21 tests in 0.062s
OK
```

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
```

Output:

```text
Ran 44 tests in 0.074s
OK
```

### RTL verification note

- The repository-local verification path available in scope for Task 2 is the deterministic `VerilogEmitter`; no separate external Verilog compiler is wired into this Task 2 flow, so the added RTL regression asserts emitted width preservation and helper/emitter agreement directly on the generated RTL text.

### Self-review

- Confirmed the fix stays at the helper/emitter boundary and does not alter the accepted constructor-rejection or runtime fail-closed semantics from fix round 1.
- Confirmed the emitted candidate RTL now shows explicit 24-bit preserved H and V sample results before each packed lane concatenation.

## Fix Round 3

### Changed files

- `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- `tests/cycle/test_fixed_point_expr.py`
- `tests/cycle/test_production_calibrated_hv.py`
- `tests/cycle/verilog_eval.py`
- This report

### Root cause and ruling

- The fix-round-2 regression counted `[23:0]` substrings but did not evaluate the emitted candidate expressions. It therefore could not prove emitted syntax, lane order, signed behavior, destination width, or Cycle/emitter agreement.
- `_truncate_signed_verilog()` also returned an unextended source expression when `target_width > expr.width`, despite the expression contract declaring the requested result width.

### Fix

- Replaced the candidate substring-count assertion with a deterministic two-state Verilog parser/evaluator for the actual grammar emitted by this candidate: sized literals, unsized decimal literals, `$signed`, slices, concatenation/repetition, ternaries, signed arithmetic, comparisons, bitwise operators, and arithmetic shifts.
- The regression now emits the real `RxCalibratedHvFrontend2Spc`, evaluates all four `next_incident_*` packed-lane assignments under the same reset state and input beat used by `CycleSimulator`, requires each parsed expression to be 48 bits, and compares the raw result with the Cycle output. It also explicitly checks the I lane’s lower H sample (`301 << 4`) and upper V sample (`501 << 4`).
- Updated `_truncate_signed_verilog()` to sign-extend to the declared target width when the target is wider than the source, while retaining explicit truncation when the target is narrower.

### TDD evidence

#### RED 5: semantic regression missing its evaluator

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv.RxCalibratedHvFrontend2SpcTest.test_emitted_candidate_expressions_match_cycle_outputs_for_both_packed_lanes -v
```

Output:

```text
ImportError: No module named 'tests.cycle.verilog_eval'
FAILED (errors=1)
```

#### RED 6: the regression catches the previously vulnerable helper emitter

The pre-fix round-2 `_truncate_signed_verilog()` implementation was temporarily restored only for this TDD check.

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_production_calibrated_hv.RxCalibratedHvFrontend2SpcTest.test_emitted_candidate_expressions_match_cycle_outputs_for_both_packed_lanes -v
```

Output:

```text
FAIL: test_emitted_candidate_expressions_match_cycle_outputs_for_both_packed_lanes
AssertionError: 98 != 48
FAILED (failures=1)
```

#### RED 7: narrow-source declared-width case

Before the width-extension change, the focused helper test failed because the emitted in-range branch had no sign extension:

```text
FAIL: test_saturate_signed_sign_extends_when_result_is_wider_than_source
AssertionError: '$signed({{8{' not found
FAILED (failures=1)
```

#### GREEN 5: semantic evaluator and width fix

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_fixed_point_expr.SaturateSignedTest.test_saturate_signed_sign_extends_when_result_is_wider_than_source tests.cycle.test_production_calibrated_hv.RxCalibratedHvFrontend2SpcTest.test_emitted_candidate_expressions_match_cycle_outputs_for_both_packed_lanes -v
```

Output:

```text
Ran 2 tests in 0.168s
OK
```

### Verification commands and output

Focused fixed-point and calibrated-front-end suites:

```text
Ran 22 tests in 0.216s
OK
```

Full Cycle suite:

```text
Ran 45 tests in 0.235s
OK
```

Existing generated-Verilog test suite:

```text
Ran 13 tests in 0.395s
OK (skipped=6)
```

### RTL verification limitation

- `iverilog`, `vvp`, `verilator`, `yosys`, `nvc`, and `ghdl` were all absent from `PATH` in this environment.
- The repository’s `tests/verilog` path contains deterministic emitter/generation assertions but no external compile or simulation invocation for this candidate. No Vivado attempt was created.
- The new regression is therefore semantic evaluation of the exact emitted expressions, not full vendor/compiler RTL proof. It is two-state and intentionally does not model X/Z propagation or simulator-specific diagnostics.

### Self-review

- The candidate test no longer relies on substring counts for its semantic claim; it parses every emitted I/Q packed-lane assignment and checks result width, raw value, and H/V lane order against `CycleSimulator`.
- The parser rejects unsupported or malformed emitted syntax, so syntax drift fails the regression rather than being silently ignored.
- The helper change is limited to the allowed fixed-point emitter extension. RFDC/MTS/authority inputs, ADC3/ADC7 ownership, registry state, and Vivado scope were not changed.
- The pre-existing unrelated modification to `docs/superpowers/plans/2026-08-24-production-2spc-calibrated-hv.md` remains untouched.

### Concerns

- A real Verilog compiler/simulator remains the next verification step when one is available; the deterministic evaluator is evidence of expression semantics within the emitted DSL grammar, not a replacement for that external toolchain.
