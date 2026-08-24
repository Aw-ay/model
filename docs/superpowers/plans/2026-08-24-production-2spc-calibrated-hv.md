# Production 2SPC Calibrated H/V Front-End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an architecture-pending, deterministic Cycle/Verilog front-end that selects the six configured H/V echo paths, applies the frozen scalar calibration fixed-point contract, and emits two calibrated H/V samples per 250 MHz cycle.

**Architecture:** Keep the proven `rx_2spc_continuous_ingress` as the only RFDC-facing source. Add a small fixed-point expression layer for signed multiplication, ties-away-from-zero rescaling, and signed saturation; then use those primitives in a one-cycle registered H/V selector/calibrator. Register the new module only in `CANDIDATE_HARDWARE_MODULES`; leave `HARDWARE_MODULES`, production RTL, connected BD Tcl, authority JSON, and readiness evidence unchanged.

**Tech Stack:** Python 3.12, `unittest`, the repository Cycle DSL and simulator, deterministic Verilog emitter, existing Golden ADC frontend, and existing fixed-point numeric-format declarations.

**Spec:** `docs/superpowers/specs/2026-08-24-production-2spc-calibrated-hv-design.md`

## Global Constraints

- Keep Vivado 2025.2, RFDC configuration, MTS fields, and the four authority SHA256 values byte-identical.
- ADC3 and ADC7 are calibration-only and must never be selectable by the continuous echo path.
- Use `adc_component` signed 16-bit, `calibration_coefficient` signed 24-bit/20 fractional bits, `calibration_product` signed 48-bit/24 fractional bits, `matrix_accumulator` signed 50-bit/24 fractional bits, and `reflection_sample` signed 24-bit/4 fractional bits.
- Use the project-wide ties-away-from-zero rounding rule and saturate, never wrap, the reflection-sample output.
- Preserve one-cycle latency, exact ingress sample-base indices, atomic two-sample beats, no backpressure, and sticky fail-closed faults.
- Keep the new module architecture-pending and do not create a Vivado attempt in this plan.

---

### Task 1: Add fixed-point Cycle expression primitives

**Files:**
- Modify: `src/rfsoc_pulse_model/cycle/dsl/expr.py`
- Create: `src/rfsoc_pulse_model/cycle/dsl/fixed.py`
- Create: `tests/cycle/test_fixed_point_expr.py`

**Interfaces:**
- Consumes: existing `Expr`, `ConstExpr`, `SliceExpr`, and `Signal` width/signed metadata.
- Produces: `signed_mul(left, right, result_width)`, `round_shift_ties_away_from_zero(value, shift, result_width)`, and `saturate_signed(value, result_width)` expressions usable by `RTLModule.drive()` and `RTLModule.update()`.

- [ ] **Step 1: Write the failing tests for signed multiplication.**

  Add tests that construct signed 16-bit and signed 24-bit constants, evaluate a 48-bit product for positive and negative operands, and assert deterministic Verilog contains explicit signed operands and the declared product width. Assert construction rejects unsigned operands and non-positive result widths.

- [ ] **Step 2: Run the focused test and verify the expected failure.**

  Run:

  ```powershell
  $env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
  & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_fixed_point_expr.py' -v
  ```

  Expected: import or attribute failure because the fixed-point expression API does not exist yet.

- [ ] **Step 3: Implement only signed multiplication.**

  Add a dedicated expression class that sign-extends both operands to the requested result width before Verilog multiplication, evaluates operands as two's-complement values in the simulator, and masks the result to the declared width. Expose it through `signed_mul()` and preserve existing expression behavior for all unrelated operators.

- [ ] **Step 4: Run the multiplication tests and verify they pass.**

  Re-run the focused command. Expected: all signed multiplication tests pass with no changes to existing DSL tests.

- [ ] **Step 5: Add failing tests for ties-away-from-zero rescaling and saturation.**

  Cover positive and negative half-way values, zero shift, positive shift, values above and below the signed output range, and exact endpoint values. Assert the expression evaluator and emitted Verilog agree on the chosen width and rounding behavior.

- [ ] **Step 6: Implement rescaling and saturation.**

  Implement the two helpers in `cycle/dsl/fixed.py` using explicit sign handling: round the discarded magnitude away from zero at the half-way point, restore the sign, then clamp to `[-2^(width-1), 2^(width-1)-1]`. Emit arithmetic-right-shift and compare/select Verilog with explicit signed casts so the generated RTL cannot wrap a saturated output.

- [ ] **Step 7: Run the focused fixed-point tests and commit the task.**

  Run the focused test file and the existing DSL tests. Commit:

  ```powershell
  git add src/rfsoc_pulse_model/cycle/dsl/expr.py src/rfsoc_pulse_model/cycle/dsl/fixed.py tests/cycle/test_fixed_point_expr.py
  git commit -m "feat: add signed fixed-point cycle expressions"
  ```

### Task 2: Implement the calibrated H/V 2SPC candidate

**Files:**
- Create: `src/rfsoc_pulse_model/cycle/hardware/production_calibrated_hv.py`
- Create: `tests/cycle/test_production_calibrated_hv.py`

**Interfaces:**
- Consumes: `ModelConfig`, `RxContinuousIngress2Spc` lane packing, `signed_mul()`, `round_shift_ties_away_from_zero()`, and `saturate_signed()`.
- Produces: `HvCalibrationCoefficients` and `RxCalibratedHvFrontend2Spc(config, coefficients=None)` with registered outputs `incident_valid_o`, four H/V I/Q lane buses, `sample_base_index_o`, `stream_active_o`, sticky `format_error_o`, `gap_error_o`, `calibration_error_o`, and selected range outputs.

- [ ] **Step 1: Write the failing tests for channel ownership and range selection.**

  Build a `CycleSimulator` fixture with six distinct echo values and two distinct calibration-only values. For `selected_range_h_i` and `selected_range_v_i` equal to 0, 1, and 2, assert the output uses ADC indices `(0,4)`, `(1,5)`, and `(2,6)` respectively for both samples. Assert that no control value can select ADC3 or ADC7.

- [ ] **Step 2: Run the focused front-end tests and verify they fail.**

  Run:

  ```powershell
  $env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
  & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -p 'test_production_calibrated_hv.py' -v
  ```

  Expected: import failure because `production_calibrated_hv.py` does not exist.

- [ ] **Step 3: Implement the candidate boundary and ownership validation.**

  Define the six echo channel indices from `ModelConfig.adc_channel_map`, reject any map that does not contain exactly one H/V echo path for HIGH/MID/LOW, and reject reserved range code 3 while enabled. Keep ADC3 and ADC7 out of the selector table. Register all data/status outputs and preserve `sample_base_index_i` exactly on accepted beats.

- [ ] **Step 4: Implement the minimal lane selection and one-cycle pipeline.**

  Select one H and one V path for each of lane0 and lane1, propagate `rx_valid_i` only when enabled and all upstream faults are clear, and hold zero data after a fault. Do not add an AXI-Lite interface or backpressure.

- [ ] **Step 5: Run selection, latency, and fault tests to verify the minimal implementation passes.**

  Re-run the focused front-end test file and confirm the tests cover one-cycle output latency, exact sample-base preservation, reset re-arming, upstream fault propagation, and reserved-code sticky fault behavior.

- [ ] **Step 6: Add failing tests for calibration arithmetic, overflow fail-closed behavior, and construction-time coefficient rejection.**

  Use coefficients representing unity, positive gain, negative gain, half-way rounding, and values that exceed the 24-bit/4-fraction output range. Assert expected signed H/V outputs, `calibration_error_o` plus no valid beat for runtime arithmetic overflow, and `ValueError` for invalid coefficient construction before Verilog emission.

- [ ] **Step 7: Implement coefficient validation, fixed-point correction, and fail-closed overflow handling.**

  Add an immutable `HvCalibrationCoefficients` value with six signed quantized coefficients and reject invalid construction-time values before module construction/emission. Multiply each selected signed 16-bit sample by its coefficient, rescale from 20 fractional bits to the `reflection_sample` format using ties-away-from-zero rounding, detect values outside signed 24-bit before saturation, and set `calibration_error_o` while suppressing the valid beat and zeroing data for runtime arithmetic contract violations.

- [ ] **Step 8: Run all focused front-end tests and commit the task.**

  Run the fixed-point and calibrated-front-end test files together. Commit:

  ```powershell
  git add src/rfsoc_pulse_model/cycle/hardware/production_calibrated_hv.py tests/cycle/test_production_calibrated_hv.py
  git commit -m "feat: add calibrated H/V 2spc candidate"
  ```

### Task 3: Register the candidate without promoting it

**Files:**
- Modify: `src/rfsoc_pulse_model/cycle/candidate_registry.py`
- Modify: `tests/cycle/test_candidate_registry.py`

**Interfaces:**
- Consumes: `RxCalibratedHvFrontend2Spc` and `HvCalibrationCoefficients` default construction.
- Produces: one additional `CandidateHardwareModuleRegistration` named `rx_2spc_calibrated_hv_frontend` with `architecture_pending`, `production=False`, and Verilog filename `rx_2spc_calibrated_hv_frontend.v`.

- [ ] **Step 1: Add the failing registry assertions.**

  Extend the registry test to require the new filename, require that the new item remains `ImplementationKind.ARCHITECTURE_PENDING`, and require that `HARDWARE_MODULES` remains exactly the two legacy reference modules.

- [ ] **Step 2: Run the registry test and verify it fails.**

  Run:

  ```powershell
  $env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
  & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_candidate_registry -v
  ```

  Expected: failure because the new candidate is not registered.

- [ ] **Step 3: Add the architecture-pending registration.**

  Import the candidate class, append one registry entry with `accepts_config=True`, and leave `HARDWARE_MODULES` untouched. Update the deterministic Verilog test to emit the candidate using `ModelConfig.load_default()` and assert the explicit clock/reset ports and stable module name.

- [ ] **Step 4: Run registry and emitter tests and commit the task.**

  Run the candidate registry, fixed-point, and calibrated-front-end tests. Commit:

  ```powershell
  git add src/rfsoc_pulse_model/cycle/candidate_registry.py tests/cycle/test_candidate_registry.py
  git commit -m "feat: register calibrated H/V candidate"
  ```

### Task 4: Add Golden equivalence and handoff evidence

**Files:**
- Modify: `tests/cycle/test_production_calibrated_hv.py`
- Modify: `docs/handoff/CURRENT_STATE.md`
- Modify: `docs/handoff/NEXT_STEPS.md`
- Modify: `docs/handoff/OPEN_ISSUES.md`
- Modify: `docs/handoff/VERIFICATION_EVIDENCE.md`

**Interfaces:**
- Consumes: the candidate module, existing `GoldenEightChannelAdcFrontend`, `CalibrationProfile.identity()`, and deterministic Verilog output.
- Produces: focused equivalence tests and handoff text that records the candidate as architecture-pending, without changing Task 5/6 evidence or production readiness.

- [ ] **Step 1: Add a Golden identity-profile equivalence test.**

  Feed the same two-sample H/V HIGH/MID/LOW vectors into the Cycle candidate and the existing Golden ADC frontend configured with an identity calibration profile. Quantize the Golden corrected values with the authority rounding/saturation contract and assert equality for both lanes, including negative values and saturation cases.

- [ ] **Step 2: Add deterministic throughput and Verilog tests.**

  Drive consecutive valid beats with consecutive bases `0, 2, 4, ...`, assert one output every cycle after the registered latency, assert no backpressure port exists, and emit Verilog twice to assert byte equality and complete port widths.

- [ ] **Step 3: Run the full focused Cycle suite.**

  Run:

  ```powershell
  $env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
  & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'E:\AWAY\RFSOC-model\tests\cycle' -v
  ```

  Expected: all Cycle tests pass, with no Vivado attempt created and no authority hash changes.

- [ ] **Step 4: Update handoff status without claiming production readiness.**

  Record the candidate owner, focused test count, deterministic emission, and equivalence result. Keep `production_integration_ready=false`, keep Task 5/6 OOC evidence unchanged, and state that receive matrix inversion, delay, reflection, monitor, DMA, timing, runtime MTS, and board acceptance remain open.

- [ ] **Step 5: Run authority and regression checks, then commit the documentation.**

  Verify the four authority SHA256 values against the frozen values, run the full `327-test` regression, confirm `git status` is clean, and commit:

  ```powershell
  git add tests/cycle/test_production_calibrated_hv.py docs/handoff/CURRENT_STATE.md docs/handoff/NEXT_STEPS.md docs/handoff/OPEN_ISSUES.md docs/handoff/VERIFICATION_EVIDENCE.md
  git commit -m "docs: record calibrated H/V candidate evidence"
  ```

## Final verification

After all tasks, the branch must show:

- the new candidate present only in `CANDIDATE_HARDWARE_MODULES`;
- `HARDWARE_MODULES` unchanged;
- all focused Cycle and full Python tests passing;
- deterministic Verilog and Golden equivalence evidence;
- all four authority hashes unchanged;
- no new Vivado attempt or build evidence;
- `production_integration_ready=false`.
