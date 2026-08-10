# Polarimetric Golden Acceptance

- Date: 2026-08-10
- Branch: local `main`
- Interpreter: bundled Python 3.12.13
- NumPy: 2.3.5
- Python executable: `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Source path: `D:\AWAY\RFSOC\model\src`
- Golden test command: `python -m unittest discover -s tests\golden -v`
- Golden result: 106 tests passed
- Config mirrors: byte-identical
- Public imports: `GoldenReflectionSource` and `GoldenReflectionStream`
- Main reflection domain: `RFDC_COMPLEX_INPUT` at 500 MSPS complex
- Monitor domain: `DETECTOR` at 250 MSPS
- Config schema/version: `9/16`
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

The continuous-stream checkpoint additionally verifies:

- one 1024-sample run equals four 256-sample chunks after concatenation,
  including target delay, fractional ADC/DAC alignment and nonzero Doppler;
- monitor FIR/detector records from the finalized stream equal the one-shot
  reference and use absolute detector-domain ToA;
- AUTO_HOLD retains independent H/V range and last-switch state on the
  absolute RFDC sample timeline across contiguous frames;
- AUTO_HOLD rejects an input gap until explicitly reset and makes its decision
  from delay-aligned raw codes/clipping corresponding to the calibrated sample;
- H and V records cannot be combined into one three-range event;
- `dataclasses.replace()` cannot bypass `ModelConfig` validation;
- DAC0..5 cover H/V x HIGH/MID/LOW exactly once;
- system fixtures use physical 10:1:0.1 ADC range ratios and an end-to-end
  impulse test checks hand-derived amplitude, delay and complex phase.

The physical-channel checkpoint additionally verifies:

- all eight ADC routes uniquely cover RFDC `00/02/10/12/20/22/30/32`;
- all eight DAC routes uniquely cover RFDC `00..03/10..13`;
- logical indices cannot be detached from their canonical RFDC tile/slice;
- every default route carries its package bank, board net and carrier endpoint;
- the two installed default-config copies remain byte-identical.

The RFDC AXI word-format checkpoint additionally verifies:

- ADC0..7 map to the exact even-I/adjacent-odd-Q stream pairs from
  `m00/m01` through `m32/m33`;
- every component stream is two signed-16 samples in a 32-bit word with the
  earlier sample in bits `[15:0]`;
- the paired complex beat is exactly `{Q1,I1,Q0,I0}`;
- DAC0..7 map to `s00..s13`, use real data and pack
  `{sample1,sample0}` into 32 bits;
- known signed-rail words catch byte, half-word, I/Q and time-order swaps;
- the current partial 125 MHz/64-bit ADC BD is rejected as the target format.

The RCS fail-closed checkpoint additionally verifies:

- anchors carry an ID, explicit validity and bounded frequency, temperature
  and physical-range conditions;
- absolute mode rejects missing, invalid and out-of-condition anchors;
- absolute mode also rejects an out-of-condition calibration profile even if
  the anchor tolerance itself is wider;
- explicit relative mode ignores an invalid anchor and reports uncalibrated
  relative gain rather than applying stale absolute scaling.

The stream-status/online-PDW checkpoint additionally verifies:

- a fully closed pulse emits PDWs and associated events before `final=True`;
- a pulse that merely reaches a software chunk boundary is withheld;
- online PDWs/events are emitted once as a global stable prefix and concatenate
  to the exact one-shot ordering;
- per-call and cumulative PDW counts are distinct;
- accepted-input, stable-output and final-state sample fronts are explicit.

The fixed-internal-delay checkpoint additionally verifies:

- the delay is a typed 500 MSPS `RFDC_COMPLEX_INPUT` quantity measured from
  the ADC complex-input mathematical boundary to the DAC baseband-output
  mathematical boundary;
- a profile from another sample rate is rejected before target compilation;
- the 63-tap kernel center is exactly 31 samples and remains internal to the
  Golden implementation rather than appearing on the public time axis;
- the fixed value includes measured common hardware latency exactly once and
  excludes the target-programmed delay.

The fixed-point-width checkpoint additionally verifies:

- all Cycle data-path and metadata formats are present in one immutable
  `ModelConfig.numeric_formats` manifest;
- a one-bit width drift fails configuration loading;
- FIR, moving-sum, noise-boot, vote, channel, target-count and delay-address
  widths are checked against their configured capacities;
- lossless intermediates use `error`, requantization boundaries use
  `saturate`, and only declared modulo fields use `wrap`;
- threshold scale `13.815510557...` quantizes to unsigned Q16 code `905413`
  using ties-away-from-zero.

The stream implementation is deliberately a buffer-backed Golden oracle. It
defines chunk-invariant observable mathematics, but does not claim bounded
memory or Cycle architecture equivalence.

Explicitly not verified by this acceptance:

- Cycle timing or fixed-point equivalence;
- generated Verilog bit/cycle equivalence;
- Vivado Block Design interfaces, clocks, reset or CDC;
- synthesis, implementation or timing closure;
- J4 expansion hardware population;
- board-level eight-channel RF performance;
- absolute RCS accuracy without measured calibration data.
