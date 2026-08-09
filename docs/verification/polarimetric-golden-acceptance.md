# Polarimetric Golden Acceptance

- Date: 2026-08-09
- Branch: `codex/golden-system-reference`
- Interpreter: bundled Python 3.12.13
- NumPy: 2.3.5
- Python executable: `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Source path: `D:\AWAY\RFSOC\model\src`
- Golden test command: `python -m unittest discover -s tests\golden -v`
- Golden result: 62 tests passed
- High-value focused result: 22 tests passed
- Config mirrors: byte-identical
- Public import: `GoldenReflectionSource` available from `rfsoc_pulse_model`
- Main reflection domain: `RFDC_COMPLEX_INPUT` at 500 MSPS complex
- Monitor domain: `DETECTOR` at 250 MSPS

The verified Golden path is:

```text
8 ADC channels
  -> calibrated H/V reconstruction
  -> causal integer/fractional delay
  -> calibrated or explicit relative RCS
  -> 2x2 polarimetric scattering and Doppler
  -> TX complex predistortion
  -> configured 8 DAC complex-baseband reference frame
```

The existing FIR, pulse detector, PDW and hit-IQ logic runs as a monitor
branch. A regression test changes the detector threshold by twelve orders of
magnitude and verifies that the complete DAC frame remains unchanged.

Explicitly not verified by this acceptance:

- Cycle timing or fixed-point equivalence;
- generated Verilog bit/cycle equivalence;
- RFDC DAC AXI word representation;
- Vivado Block Design interfaces, clocks, reset or CDC;
- synthesis, implementation or timing closure;
- J4 expansion hardware population;
- board-level eight-channel RF performance;
- absolute RCS accuracy without measured calibration data.
