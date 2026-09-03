# Calibrator PL Verification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the XCZU27DR PL design from bit-accurate models through post-route implementation and physical-board operation, without treating the current integration skeleton as the final signal-processing image.

**Architecture:** Verification is split into independent gates: configuration identity, Golden/Cycle behavior, RTL/AXIS simulation, Vivado sign-off, board smoke, RF functional measurements, DMA/event stress, and long-duration operation. Every gate produces machine-readable evidence bound to the exact Git commit, bitstream SHA-256, XSA SHA-256, configuration SHA-256, Vivado version, and board serial identity.

**Tech Stack:** Python `unittest`, Golden/Cycle models, SystemVerilog/XSIM, Vivado 2025.2, RFDC 2.6, ILA/JTAG, PetaLinux 2025.2, AXI DMA, Windows `calibrator-cli`, oscilloscope/spectrum analyzer and low-power RF loopback.

**Spec:** `docs/superpowers/specs/2026-08-24-production-2spc-calibrated-hv-design.md`, `docs/deployment/calibrator-v1.md`, `config/calibrator_platform.json`, `config/default.json`, and `config/calibrator_registers.json`

## Global Constraints

- Use Vivado, Vitis and PetaLinux 2025.2 only; reject mixed 2025.1/2025.2 evidence.
- Target part is `xczu27dr-fsve1156-2-i`; RFDC IP is `xilinx.com:ip:usp_rf_data_converter:2.6`.
- RFDC input and output are continuous 2-samples-per-cycle streams; verification must never repair a missing beat or reorder samples.
- H routes are ADC 0/1/2/3 to DAC 1/3/5/7; V routes are ADC 4/5/6/7 to DAC 0/2/4/6.
- The current gate-enabled bitstream is an integration image. It does not contain the final 63-tap calibration, complex correction, automatic range selection or full detector chain.
- Final PL acceptance is permitted only after those Cycle/Golden functions are present in the synthesized design and their production ownership is no longer `architecture_pending`.
- DAC output remains muted through reset, RFDC/MTS failure, illegal configuration, stream fault and software initialization failure.
- RFDC input must never be backpressured. FIFO or DMA pressure drops a whole event and increments a visible counter.
- Old explained RFDC/vendor CDC-15 warnings are recorded risks; new critical CDC, DRC errors, negative timing slack or unrouted nets fail the build.

---

## Verification gates

| Gate | Scope | Release condition |
| --- | --- | --- |
| PL-G0 | Identity and traceability | Exact source/config/tool/artifact identity is recorded |
| PL-G1 | Golden and Cycle behavior | Bit-exact functional vectors pass |
| PL-G2 | RTL and AXIS simulation | Functional, reset, backpressure and fault tests pass |
| PL-G3 | Vivado implementation | BD, synthesis, route, timing, CDC and DRC gates pass |
| PL-G4 | JTAG and board smoke | Safe programming, clocks, resets, AXI and mute behavior pass |
| PL-G5 | RFDC/MTS and channel routing | Ten repeatable MTS runs and all eight routes pass |
| PL-G6 | Calibration, range and detector | Final DSP image meets digital and RF tolerances |
| PL-G7 | PDW, IQ window and DMA | Event contents, ordering, loss accounting and no-backpressure behavior pass |
| PL-G8 | Recovery and endurance | Ten cold boots plus two hours and 100,000 events pass |

The current integration image may pass PL-G0 through PL-G5 and the skeleton portions of PL-G7. It cannot pass PL-G6 or final PL-G8 release acceptance.

### Task 1: Freeze the release candidate and evidence identity

**Consumes:** repository commit, `config/*.json`, generated ABI files, `.bit`, `.xsa`.

**Produces:** one immutable verification manifest used by every later result.

- [ ] Record `git rev-parse HEAD`, `git status --porcelain`, Vivado version, part and RFDC VLNV.
- [ ] Compute SHA-256 for `config/calibrator_platform.json`, `config/default.json`, `config/calibrator_registers.json`, the release `.bit`, release `.xsa`, generated register header and device-tree overlay.
- [ ] Reject dirty tracked source, missing hashes, an XSA without the exact embedded bitstream, or a tool version other than 2025.2.
- [ ] Record whether the candidate is `integration_skeleton` or `final_dsp`; do not allow the former to produce a final acceptance result.

### Task 2: Run model and fixed-point regression

**Consumes:** `tests/golden`, `tests/cycle`, default configuration and calibration vectors.

**Produces:** bit-accurate expected files for RTL and board comparison.

- [ ] Run from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m unittest discover -s tests\golden -v
python -m unittest discover -s tests\cycle -v
```

- [ ] Exercise integer delays `0`, `1`, `2046`, `2047`; reject `2048` without changing the active configuration.
- [ ] Exercise normalized fractional delays at `0`, `0.25`, `0.5`, `0.75` samples using the exact 63-tap coefficient sets. A requested negative relative delay must first be converted to a causal common integer baseline plus a nonnegative fractional value; reject a negative register value.
- [ ] Exercise unity, zero, negative, quadrature and maximum legal s24.Q20 complex gains; include positive and negative half-way rounding and both saturation rails.
- [ ] Exercise automatic H/V range thresholds at 0.25 and 0.9 with one-LSB-below/equal/one-LSB-above values and verify the 64-sample hold interval.
- [ ] Verify reference channels never participate in ordinary H/V range decisions.
- [ ] Verify detector vectors for bootstrap, isolated noise, threshold edge, adjacent pulses, cross-frame pulses, clipping and signed positive/negative frequency.
- [ ] Export expected selected range, corrected IQ, saturation, ToA, pulse width, peak, frequency, PDW bytes and 16-before/16-after IQ samples.

**Pass:** every test passes and every expected vector is bound to the configuration SHA-256.

### Task 3: Verify RTL datapath and AXIS behavior

**Consumes:** Task 2 vectors and generated production RTL.

**Produces:** XSIM logs and waveforms for each block and the integrated top.

- [ ] Run the focused boundary and datapath tests:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m unittest tests.cycle.test_production_2spc_boundary -v
python -m unittest tests.cycle.test_production_calibrated_hv -v
python -m unittest tests.cycle.test_calibrator_datapath -v
python -m unittest tests.cycle.test_event_dma_queue -v
python -m unittest tests.verilog.test_candidate_compile -v
```

- [ ] Verify `{Q1,I1,Q0,I0}` lane order on known asymmetric samples and all eight channel identities.
- [ ] Verify continuous input with no `TREADY`-driven pause and no sample-index discontinuity.
- [ ] Randomize downstream AXIS readiness for event/DMA outputs; verify no data mutation, beat duplication or partial-event acceptance.
- [ ] Inject reset at idle, during calibration, during a pulse, between event beats and while the event FIFO is full.
- [ ] Verify acquisition enable and the complete calibration snapshot cross clock domains atomically with `config_version`.
- [ ] Verify illegal range values, delay overflow, arithmetic saturation, input gaps and TX ready loss fail closed and set sticky status.
- [ ] Fill the event FIFO and pause DMA; verify whole-event drops, exact drop counters and uninterrupted RFDC input.

**Pass:** all expected IQ and metadata are bit-exact; every event is either complete or wholly dropped; no RFDC input backpressure occurs.

### Task 4: Prove full-top Vivado implementation

**Consumes:** generated Tcl, constraints and Task 3 production RTL.

**Produces:** post-synthesis/post-route checkpoints, reports, bitstream and embedded-bit XSA.

- [ ] Rebuild in a new output directory using Vivado 2025.2:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:XILINX_LOCAL_USER_DATA = 'no'
$env:CALIBRATOR_SOURCE_DIR = (Get-Location).Path
$env:CALIBRATOR_BUILD_DIR = (Join-Path (Get-Location) 'build\calibrator_pl_verify')
python -m rfsoc_pulse_model.ip.calibrator_build build\calibrator_pl_verify_generated
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch `
  -source build\calibrator_pl_verify_generated\build_calibrator.tcl
```

- [ ] Require `validate_bd_design`, synthesis, placement, routing, bitstream and XSA export to return success.
- [ ] Require 0 failed/unrouted/partially-routed/overlap nets.
- [ ] Require setup WNS and hold WHS to be nonnegative, TNS and THS to be zero, and 0 failing endpoints.
- [ ] Require 0 critical CDC findings and 0 DRC critical warnings/errors. Compare all remaining warnings against an exact reviewed allowlist.
- [ ] Require `check_timing` to report no unconstrained internal endpoints, missing generated clocks or constant-clock timing paths.
- [ ] Record clock interaction, bus-skew, utilization and power-estimation reports. Require at least 15% free capacity in LUT, FF, BRAM and DSP resources; otherwise require an explicit architecture review before board testing.
- [ ] Reopen the XSA and prove that its embedded bitstream bytes equal the standalone `.bit`.

**Pass:** all sign-off gates pass in a clean build; copying old reports into a new evidence directory is prohibited.

### Task 5: Build a debug image and perform safe JTAG smoke testing

**Consumes:** the same routed design as Task 4, with ILA probes added only to a separately identified debug image.

**Produces:** debug `.bit/.ltx`, UART log and ILA captures.

- [ ] Probe ADC ingress valid/data, calibrated IQ, H/V range selection, sample index, config commit/version, detector hit, event FIFO level/drop, DMA AXIS valid/ready/last and sticky faults.
- [ ] Program by JTAG while DAC mute is asserted; confirm configuration success before enabling clocks or acquisition.
- [ ] Verify AXI-Lite project ID, ABI version and reset values from software.
- [ ] Reset PS, PL, RFDC and acquisition independently; DAC data must stay zero until RFDC/MTS success and explicit unmute.
- [ ] Toggle start/stop, loopback and mute 100 times; verify no stale configuration, stuck valid, unexpected DAC output or sticky error.
- [ ] Capture at least 4096 consecutive PL cycles and prove 2SPC sample-index increments and channel identity.

**Pass:** safe-state behavior is deterministic and the debug capture agrees with the Task 2/Cycle expectations.

### Task 6: Verify RFDC clocks, MTS and eight-channel routing

**Consumes:** low-power signal source, RF loopback cables, scope/spectrum analyzer and board service.

**Produces:** per-tile MTS records and an 8-by-8 route matrix.

- [ ] Verify required reference clocks and SYSREF are present and stable before unmute.
- [ ] Run ADC tiles 0-3 and DAC tiles 0-1 MTS ten times after independent cold starts; record tile/block state, latency and offset each time.
- [ ] Inject one low-power tone into each ADC input separately and measure every DAC output.
- [ ] Require the intended H/V route to contain the tone and all seven unintended outputs to remain at least 50 dB below the intended output or at the instrument noise floor, whichever is higher.
- [ ] Verify H mapping ADC 0/1/2/3 to DAC 1/3/5/7 and V mapping ADC 4/5/6/7 to DAC 0/2/4/6.
- [ ] Repeat after stop/start, PL reset and one complete power cycle.

**Pass:** ten MTS runs succeed and the complete channel matrix matches the frozen configuration without intermittent swaps.

### Task 7: Verify final calibration and automatic range selection

**Consumes:** only a `final_dsp` image that contains the production integer delay, 63-tap fractional delay, s24.Q20 complex correction and automatic H/V selector.

**Produces:** digital equivalence logs and calibrated RF measurements.

- [ ] Reject execution if the synthesized hierarchy or production manifest still marks any required calibration block `architecture_pending`.
- [ ] Apply Task 2 vectors through RTL/ILA and require bit-exact corrected IQ, selected range, saturation and `config_version`.
- [ ] Write all eight shadow calibration sets while acquisition is stopped, commit once and prove all channels change on the same accepted epoch.
- [ ] Attempt a commit while acquisition is enabled; require rejection with no active-word or version change.
- [ ] Sweep input level across 0.25 and 0.9 thresholds in both directions; require the exact range transition and 64-sample hold behavior independently for H and V.
- [ ] With a common tone, require residual inter-channel amplitude error no greater than 0.5 dB, phase error no greater than 3 degrees and relative delay error no greater than 0.25 of a 500 MSPS complex sample.
- [ ] Repeat the measurements at low, middle and high range for both polarizations.

**Pass:** digital results are bit-exact and all RF residual errors remain inside the stated limits.

### Task 8: Verify detector, PDW, IQ window and DMA transport

**Consumes:** final detector image and known pulsed RF/digital stimulus.

**Produces:** correlated stimulus, ILA, DDR and host event records.

- [ ] Verify the implemented hierarchy contains 15-tap FIR/2, adaptive noise/threshold, 8-point moving average and 3/5 voting before starting acceptance.
- [ ] For single and overlapping channel events, compare ToA, pulse width, peak, frequency and flags with the Cycle model. Digital simulation must be exact; board ToA may differ by at most one decimated detector sample.
- [ ] Require each event to contain one 32-byte PDW header and exactly 32 complex IQ16 samples, with 16 preceding and 16 following the hit.
- [ ] Require global output ordering by `(ToA, channel)` and no duplicate `event_id`.
- [ ] Verify the 128-bit AXIS event is exactly 12 beats/192 bytes with correct `TKEEP` and final `TLAST`.
- [ ] Pause DMA and fill the event FIFO. Require whole-event drops, matching PL/Linux/host counters, a sticky overflow flag and uninterrupted RFDC input.
- [ ] Resume DMA without resetting RFDC; require later complete events to continue with detectable sequence gaps.

**Pass:** payloads, ordering and counters agree at PL, DDR and host boundaries; no partial event reaches software.

### Task 9: Run recovery, cold-boot and endurance acceptance

**Consumes:** release bitstream/XSA, final PetaLinux image, eMMC and isolated control network.

**Produces:** final PL acceptance report and archived event capture.

- [ ] Perform ten complete power-off/cold-start cycles. Each cycle must initialize RFDC, complete MTS, keep DAC muted until ready, start acquisition and deliver a valid event.
- [ ] Exercise invalid calibration, threshold, CRC, command and unsupported-version inputs; require explicit rejection and continued safe operation.
- [ ] Start the two-hour capture:

```powershell
calibrator-cli control 192.168.1.10 start --token-file .\control.token
calibrator-cli capture 192.168.1.10 `
  --output acceptance-capture --duration 7200 --require-events 100000
calibrator-cli control 192.168.1.10 stop --token-file .\control.token
```

- [ ] During the run, poll PL stream faults, event count, whole-event drops, DMA health, RFDC tile state, MTS state and configuration version.
- [ ] Require no deadlock, DMA hang, uncounted loss, MTS loss, spontaneous reset, sample-index discontinuity or unexpected DAC unmute.
- [ ] Require host CRC errors to be zero. Any sequence gap must be explained exactly by board whole-event drop counters.
- [ ] Archive logs, ILA captures, event JSONL/IQ files, report summaries and all identity hashes read in Task 1.

**Pass:** ten cold boots pass and the two-hour run uploads at least 100,000 valid events with zero unexplained loss.

## Failure policy

- A PL-G0 identity failure invalidates all later evidence.
- A model/RTL mismatch blocks Vivado and board work; do not compensate in software.
- A timing, CDC, DRC, routing or safe-mute failure blocks bitstream programming.
- An MTS or channel-map failure blocks RF calibration measurements.
- A partial event, RFDC backpressure or uncounted loss is a release-critical failure.
- Retest only the failed gate while diagnosing; after repair, rerun that gate and every downstream gate with a new artifact hash.

## Final release statement

PL is accepted only when PL-G0 through PL-G8 pass for one exact `final_dsp` artifact set. A successful current skeleton run is reported as an integration result and must not be described as completed calibration-instrument PL functionality.
