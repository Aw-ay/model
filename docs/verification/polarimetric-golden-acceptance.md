# Polarimetric Golden Acceptance

- Date: 2026-08-09
- Branch: local `main`
- Interpreter: bundled Python 3.12.13
- NumPy: 2.3.5
- Python executable: `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Source path: `D:\AWAY\RFSOC\model\src`
- Golden test command: `python -m unittest discover -s tests\golden -v`
- Golden result: 69 tests passed
- Config mirrors: byte-identical
- Public import: `GoldenReflectionSource` available from `rfsoc_pulse_model`
- Main reflection domain: `RFDC_COMPLEX_INPUT` at 500 MSPS complex
- Monitor domain: `DETECTOR` at 250 MSPS
- Config schema/version: `5/8`
- RFDC fabric contract: two complete complex samples per 250 MHz cycle

The verified Golden path is:

```text
8 ADC channels
  -> nominal-range and residual calibrated H/V reconstruction
  -> causal integer/fractional delay
  -> explicit carrier range phase
  -> calibrated or explicit relative RCS
  -> 2x2 polarimetric scattering and Doppler
  -> TX complex predistortion
  -> configured 8 DAC complex-baseband reference frame
```

The existing FIR, pulse detector, PDW and hit-IQ logic runs as a monitor
branch. A regression test changes the detector threshold by twelve orders of
magnitude and verifies that the complete DAC frame remains unchanged.

The pre-Cycle physical-contract checkpoint additionally verifies:

- ADC/DAC relative delay alignment does not expose the 63-tap kernel's
  31-sample center delay;
- `rfdc_complex_samples_per_cycle` is the only accepted 2SPC field;
- ideal +20/0/-20 dB ADC paths reconstruct the same H/V waveform when the
  residual calibration is identity;
- the target compiler emits and the reflection kernel applies
  `range_carrier_phase_rad` for the full device-equivalent delay.

Explicitly not verified by this acceptance:

- Cycle timing or fixed-point equivalence;
- generated Verilog bit/cycle equivalence;
- RFDC DAC AXI word representation;
- Vivado Block Design interfaces, clocks, reset or CDC;
- synthesis, implementation or timing closure;
- J4 expansion hardware population;
- board-level eight-channel RF performance;
- absolute RCS accuracy without measured calibration data.
