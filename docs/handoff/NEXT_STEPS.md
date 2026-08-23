# Strictly Ordered Next Steps

The order below is a gate chain. Do not skip a step because a later implementation looks independent; downstream evidence consumes upstream authority.

## Completed migration gates: Tasks 1-6

Tasks 1-4 remain CLEAN under their original authority boundaries. Task 5 is
now CLEAN for the bounded connected-shell protocol: real Vivado reports are
parsed, Tcl/report hashes are bound, and unsafe or stale attempts fail closed.
Task 6 is CLEAN for the OOC connected shell: the latest fresh Vivado 2025.2
attempt validated the BD, synthesized `synth_1`, preserved all 24 AXIS
interfaces at the BD boundary, used 0 bonded IOBs, and accepted only exact
AMD RFDC CDC waiver endpoints.

The evidence deliberately leaves `production_integration_ready=false`.
Post-route timing, runtime MTS/SYSREF, and the complete production data path
remain later gates.

## 1. Add the Production 2SPC Reflection Chain — boundary candidate slice complete

- **Prerequisites:** OOC connected shell structurally ready; RF clocks/resets and MTS configuration contract frozen; Cycle numeric formats unchanged or explicitly versioned.
- **Current candidate evidence:** New `rx_2spc_continuous_ingress`, `continuous_stream_timebase`, and `tx_2spc_continuous_egress` Cycle candidates pass 13 focused tests and deterministic Verilog emission. They remain outside the production registry and do not alter authority configuration.
- **Likely files:** `src/rfsoc_pulse_model/cycle/hardware`, Cycle registry/emitter/generator, equivalence and Verilog tests, architecture ownership config.
- **Required tests/evidence:** Cycle implementations for 2SPC ingress, calibrated H/V selection, delay, polarimetric scattering, Doppler, accumulation, predistortion and egress; generated RTL only; bit/cycle equivalence; continuous throughput and fault tests; synthesis resource/timing evidence.
- **Independent review checkpoint:** prove legacy reference RTL is not in production sources and every production responsibility has one current owner.
- **Stop condition:** stop before BD integration if a hardware Cycle leaf lacks emission/equivalence or cannot sustain every 250 MHz two-sample beat.

## 2. Add the Monitor Pulse IQ/PDW Event Chain

- **Prerequisites:** production ingress/time axis stable; Golden detector behavior and numeric formats still pass; main reflection path remains detector-independent.
- **Likely files:** Golden boundary tests if clarified, Cycle FIR/detector/refinement/buffer/association/packetizer modules, generated RTL and event-interface tests.
- **Required tests/evidence:** 2:1 FIR decimation, power/noise/vote, contiguous FWHM refinement, frequency/PDW fields, pre/post IQ windows, H/V-local three-range association, ordering, queue overflow/drop status, no RFDC backpressure, bit/cycle equivalence.
- **Independent review checkpoint:** change detector thresholds over a wide range and prove the continuous DAC stream is identical while event output changes appropriately.
- **Stop condition:** stop if an event queue, refiner, or packetizer can stall the continuous source or silently lose an event.

## 3. Add Event DMA and GEM3

- **Prerequisites:** `MONITOR-EVENT-CHAIN` complete; `GEM3-BOARD-IO` closed; event format/version frozen.
- **Likely files:** architecture config/ownership, connected Tcl and runner evidence schema, DMA/GEM software, packet protocol and integration tests.
- **Required tests/evidence:** AXI DMA S2MM to DDR ring; exact addresses/interrupts; descriptor ownership; packet CRC/sequence/config version; event-only payload; overflow, reset, loss and reconnect tests; sustained worst-case event throughput.
- **Independent review checkpoint:** trace one pulse from ADC sample indices through IQ/PDW bytes, DDR, network packet and host decode; verify continuous background IQ is absent.
- **Stop condition:** stop on unbounded buffering, silent DMA/network loss, unresolved board PHY settings, or any continuous-waveform upload path.

## 4. Close Implementation, Runtime, and Board Acceptance

- **Prerequisites:** all prior steps complete and independently reviewed; final source/config/lock hashes frozen.
- **Likely files:** timing/CDC constraints, tracked acceptance records, calibration manifests, host test tooling and deployment configuration.
- **Required tests/evidence:** implemented timing closure for all clocks; CDC/reset review; runtime MTS/SYSREF success; measured fixed internal delay; 8-channel H/V/range loopback; event transport; recovery cycles; temperature/level sweeps; 24-hour stability.
- **Independent review checkpoint:** audit source-to-bitstream provenance and reproduce the final acceptance from a clean checkout.
- **Stop condition:** any broad timing waiver, unexplained phase/delay change, channel-map mismatch, packet loss without explicit accounting, or stability failure blocks production acceptance.
