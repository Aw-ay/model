# Task 1: Fixed-point RTL legal-literal and width contract evidence

## Scope

- Legal signed SystemVerilog literals now use prefix unary minus, including
  signed `ConstExpr` values that are nested inside fixed-point helper output.
- `signed_mul` explicitly resizes its final signed multiplication expression
  to its declared result width.
- The deterministic evaluator rejects the invalid inline-minus sized-literal
  spelling.
- Added evaluator regressions for literal legality, 4-bit narrowing composition,
  and zero/nonzero-shift signed rails.
- Added a standalone temporary-source Vivado 2025.2 elaboration check for
  `RxCalibratedHvFrontend2Spc`; it does not invoke connected-shell tooling or
  write `build/` evidence.

`src/rfsoc_pulse_model/cycle/dsl/expr.py` is included because fixed-point helper
expressions contain signed `ConstExpr` operands; rejecting inline-minus literals
without correcting that producer would make valid negative fixed-point inputs
unparseable.

## Red evidence

1. `python -m unittest tests.cycle.test_fixed_point_expr -v`
   without the project-required `PYTHONPATH` produced one import error
   (`ModuleNotFoundError: rfsoc_pulse_model`); this was an invocation-environment
   failure, not behavioral test evidence.

2. `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest tests.cycle.test_fixed_point_expr -v`
   before production edits ran 18 tests and failed 4 as expected:

   - saturation and out-of-range bounds emitted `24'sd-8388608`, not legal
     `-24'sd8388608`;
   - narrowing `signed_mul(5, 5, 4)` emitted a 5-bit value, not 4-bit;
   - the evaluator accepted `24'sd-8388608`.

3. Reversible mutation red check:
   `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest tests.cycle.test_fixed_point_expr.VerilogEvaluatorLiteralTest.test_signed_constant_uses_prefix_minus -v`
   with the old `ConstExpr` literal emission ran 1 test and failed 1, showing
   `24'sd-5` versus expected `-24'sd5`. The corrected emitter was restored
   immediately after this check.

## Green evidence

1. `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest tests.cycle.test_fixed_point_expr -v`
   — 19 passed, 0 failed.

2. `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest tests.cycle.test_production_calibrated_hv -v`
   — 14 passed, 0 failed.

3. `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest tests.verilog.test_candidate_compile -v`
   — 1 skipped, 0 failed. The only local executable is Vivado 2025.1;
   Vivado 2025.2 is unavailable, so the 2025.2-only elaboration test correctly
   skipped and no Vivado invocation occurred.

4. `$env:PYTHONPATH = "$PWD\src;$PWD"; python -m unittest discover -s tests\verilog -v`
   — 14 tests run, 7 skipped, 0 failed. Skips are the unavailable Vivado 2025.2
   executable and Windows symlink privileges in pre-existing tests.

## Boundary confirmation

No authority JSON, RFDC/MTS configuration, connected-shell attempt, connected
evidence, production ownership, or `build/` evidence was changed.
