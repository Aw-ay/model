# Strictly Ordered Next Steps

The order below is a gate chain. Do not skip a step because a later implementation looks independent; downstream evidence consumes upstream authority.

## 1. Probe Real Report Grammar and MTS Properties

- **Prerequisites:** Task 4 CLEAN evidence at `commit:9a28daa`; exact Vivado 2025.2 and `xczu27dr-fsve1156-2-i`; current RFDC 2.6 lock.
- **Likely files:** `src/rfsoc_pulse_model/ip/rfdc_probe.py`, `tests/ip/test_rfdc_probe.py`, and the connected-shell design/plan if the evidence schema changes.
- **Required tests/evidence:** RFDC-only temporary-project probe records real clean and deliberately unsafe report forms; enumerates actual RFDC MTS property names, types, legal values, and readback; rejects missing/extra/duplicate/noncanonical records.
- **Independent review checkpoint:** confirm all accepted fields come from probe output and no property or clean marker is guessed.
- **Stop condition:** stop before Task 5 changes if real grammar or MTS authority is still ambiguous, incomplete, or tool-version dependent without an explicit version gate.

## 2. Repair the Task 5 Request/Evidence Protocol

- **Prerequisites:** Step 1 CLEAN and both blocked issue records updated with exact measured authority.
- **Likely files:** `src/rfsoc_pulse_model/ip/connected.py`, `src/rfsoc_pulse_model/ip/connected_tcl.py`, `src/rfsoc_pulse_model/ip/connected_runner.py`, and the matching connected tests.
- **Required tests/evidence:** generated Tcl emits canonical measured status records; consumer validates bounded report grammar; request and evidence bind exact MTS names/values; malformed, stripped, duplicated, unsafe, stale, and mismatched results fail closed.
- **Independent review checkpoint:** trace every readiness boolean to one tool-emitted or parser-derived fact and verify lifecycle publication cannot bypass validation.
- **Stop condition:** stop if any success fact originates only in a Python fixture, hard-coded `true`, or unprobed property.

## 3. Prove Opposite Outcomes for Clean and Unsafe Reports

- **Prerequisites:** Step 2 implementation and focused tests green.
- **Likely files:** Task 5 test modules plus tracked verification evidence; production code changes only if the differential test exposes a defect.
- **Required tests/evidence:** one fake unsafe report must produce fail-closed/not-ready; one real clean Vivado report must produce the opposite accepted structural result under the same parser and schema; all hashes and attempt lifecycle fields must bind.
- **Independent review checkpoint:** reviewer reproduces both outcomes and confirms the real report is not edited or translated by hand.
- **Stop condition:** stop and mark Task 5 blocked if either input cannot reach its expected opposite result after bounded repair/review attempts.

## 4. Run Task 6 Through the Real Runner

- **Prerequisites:** Steps 1-3 independently CLEAN; both `BD-T5` issues closed; production lock valid; clean working tree.
- **Likely files:** generated attempt-local Tcl/evidence under the build directory, tracked acceptance documentation, and only defect-driven source/test changes.
- **Required tests/evidence:** create a disk-backed exact-part project; realize declared cells/connections; run `validate_bd_design`; synthesize; open `synth_1`; collect and validate CDC, clock interaction, timing summary, utilization, topology, address, reset, IRQ, RF interface, and MTS configuration evidence.
- **Independent review checkpoint:** compare generated request, Tcl, readback, reports, canonical evidence, lifecycle state, and source hashes; reject stale prior success.
- **Stop condition:** no success publication on any Vivado error, unsafe/unconstrained report, missing report, topology drift, hash drift, or failed cleanup/recovery.

## 5. Add the Production 2SPC Reflection Chain

- **Prerequisites:** Task 6 connected shell structurally ready; RF clocks/resets and MTS contract frozen; Cycle numeric formats unchanged or explicitly versioned.
- **Likely files:** `src/rfsoc_pulse_model/cycle/hardware`, Cycle registry/emitter/generator, equivalence and Verilog tests, architecture ownership config.
- **Required tests/evidence:** Cycle implementations for 2SPC ingress, calibrated H/V selection, delay, polarimetric scattering, Doppler, accumulation, predistortion and egress; generated RTL only; bit/cycle equivalence; continuous throughput and fault tests; synthesis resource/timing evidence.
- **Independent review checkpoint:** prove legacy reference RTL is not in production sources and every production responsibility has one current owner.
- **Stop condition:** stop before BD integration if a hardware Cycle leaf lacks emission/equivalence or cannot sustain every 250 MHz two-sample beat.

## 6. Add the Monitor Pulse IQ/PDW Event Chain

- **Prerequisites:** production ingress/time axis stable; Golden detector behavior and numeric formats still pass; main reflection path remains detector-independent.
- **Likely files:** Golden boundary tests if clarified, Cycle FIR/detector/refinement/buffer/association/packetizer modules, generated RTL and event-interface tests.
- **Required tests/evidence:** 2:1 FIR decimation, power/noise/vote, contiguous FWHM refinement, frequency/PDW fields, pre/post IQ windows, H/V-local three-range association, ordering, queue overflow/drop status, no RFDC backpressure, bit/cycle equivalence.
- **Independent review checkpoint:** change detector thresholds over a wide range and prove the continuous DAC stream is identical while event output changes appropriately.
- **Stop condition:** stop if an event queue, refiner, or packetizer can stall the continuous source or silently lose an event.

## 7. Add Event DMA and GEM3

- **Prerequisites:** `MONITOR-EVENT-CHAIN` complete; `GEM3-BOARD-IO` closed; event format/version frozen.
- **Likely files:** architecture config/ownership, connected Tcl and runner evidence schema, DMA/GEM software, packet protocol and integration tests.
- **Required tests/evidence:** AXI DMA S2MM to DDR ring; exact addresses/interrupts; descriptor ownership; packet CRC/sequence/config version; event-only payload; overflow, reset, loss and reconnect tests; sustained worst-case event throughput.
- **Independent review checkpoint:** trace one pulse from ADC sample indices through IQ/PDW bytes, DDR, network packet and host decode; verify continuous background IQ is absent.
- **Stop condition:** stop on unbounded buffering, silent DMA/network loss, unresolved board PHY settings, or any continuous-waveform upload path.

## 8. Close Implementation, Runtime, and Board Acceptance

- **Prerequisites:** all prior steps complete and independently reviewed; final source/config/lock hashes frozen.
- **Likely files:** timing/CDC constraints, tracked acceptance records, calibration manifests, host test tooling and deployment configuration.
- **Required tests/evidence:** implemented timing closure for all clocks; CDC/reset review; runtime MTS/SYSREF success; measured fixed internal delay; 8-channel H/V/range loopback; event transport; recovery cycles; temperature/level sweeps; 24-hour stability.
- **Independent review checkpoint:** audit source-to-bitstream provenance and reproduce the final acceptance from a clean checkout.
- **Stop condition:** any broad timing waiver, unexplained phase/delay change, channel-map mismatch, packet loss without explicit accounting, or stability failure blocks production acceptance.
