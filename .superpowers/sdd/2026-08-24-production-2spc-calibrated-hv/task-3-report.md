# Task 3 Report

## Outcome

Registered the calibrated H/V 2SPC frontend as one architecture-pending candidate without promoting it into production generation.

## Changed files

- `src/rfsoc_pulse_model/cycle/candidate_registry.py`
- `tests/cycle/test_candidate_registry.py`

## Registry contract

- Added exactly one candidate named `rx_2spc_calibrated_hv_frontend`.
- The candidate uses `RxCalibratedHvFrontend2Spc` and accepts `ModelConfig`.
- The candidate remains `ImplementationKind.ARCHITECTURE_PENDING`.
- The candidate has `production=False`, `accepts_config=True`, and Verilog filename `rx_2spc_calibrated_hv_frontend.v`.
- `HARDWARE_MODULES` remains exactly `rx_group_ingress_2spc.v` and `tx_iq_axis_boundary_2spc.v`.

## TDD evidence

### RED: registry assertions before registration

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_candidate_registry -v
```

Result:

```text
Ran 3 tests in 0.008s
FAILED (failures=2)
```

The failures were the expected missing-candidate filename assertion and missing-candidate registry assertion.

### GREEN: registered candidate and deterministic emitter coverage

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_candidate_registry -v
```

Result:

```text
Ran 3 tests in 0.021s
OK
```

The deterministic emitter test constructs the registered candidate with `ModelConfig.load_default()` and asserts its stable module name plus explicit `clk_i` and `rst_i` ports.

## Relevant verification

Command:

```powershell
$env:PYTHONPATH='E:\AWAY\RFSOC-model\src;E:\AWAY\RFSOC-model'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.cycle.test_candidate_registry tests.cycle.test_fixed_point_expr tests.cycle.test_production_calibrated_hv -v
```

Result:

```text
Ran 25 tests in 0.223s
OK
```

## Scope confirmation

No authority JSON, production registry, Vivado files, or handoff documents were modified.
