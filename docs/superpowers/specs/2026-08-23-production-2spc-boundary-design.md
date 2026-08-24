# Production 2SPC Boundary Layer Design

## Status

Candidate implementation design. This document does not promote any
architecture-pending owner to production and does not modify authority JSON.

## Scope

The first implementation slice establishes three independent Cycle-to-Verilog
boundary candidates for the continuous reflection path:

```text
RFDC ADC component words
        |
        v
rx_2spc_continuous_ingress
        |
        v
continuous_stream_timebase
        |
        v
reflection processing (later slice)
        |
        v
tx_2spc_continuous_egress
        |
        v
RFDC DAC complex-I/Q words
```

The legacy `rx_group_ingress_2spc` and `tx_iq_axis_boundary_2spc` classes remain
unchanged and remain reference-only.

## Frozen interface semantics

### RX ingress

- Common `clk_i` and synchronous active-high `rst_i`.
- Eight ADC channels, each with 32-bit I and Q component words.
- Each component word contains two signed 16-bit samples.
- Both eight-bit valid masks must be all ones for an accepted beat.
- Before acquisition is enabled, valid patterns are ignored.
- After enable, an all-idle beat raises sticky `gap_error_o`; any other
  incomplete beat raises sticky `format_error_o`.
- Faulted state is fail-closed until reset.
- Accepted beats have one registered cycle of latency and advance the absolute
  sample base by two.
- Output lanes preserve the fixed channel order and sample order from the RFDC
  word contract.

### Stream timebase

- Common `clk_i` and synchronous active-high `rst_i`.
- Consumes the registered ingress `sample_valid_i`,
  `sample_base_index_i`, and upstream fault status.
- Before acquisition enable, no sample is accepted and no fault is raised.
- After enable, every missing valid beat is a sticky stream-integrity fault.
- The first accepted base must be zero; each following accepted base must equal
  the previous base plus two.
- An index discontinuity raises sticky `timebase_error_o` and fails closed.
- Valid and base outputs are registered and never repair or reorder a later
  beat.

### TX egress

- Common `clk_i` and synchronous active-high `rst_i`.
- Eight channels of two signed 16-bit I/Q samples per cycle.
- All eight DAC ready bits are required for an atomic transfer.
- `dac_tvalid_o` is asserted after reset as required by the RFDC contract.
- Before streaming starts, ready and source-valid are a start condition.
- After streaming starts, a ready loss or source-valid loss latches
  `underrun_o`, drives zero data, and stops advancement.
- Underrun can only be cleared while disabled with `clear_status_i`.
- Packed words use `{Q1,I1,Q0,I0}` per channel and never silently swap,
  truncate, or pad data.

## Promotion boundary

The candidates are intentionally not added to `HARDWARE_MODULES`, so the
existing production/reference RTL manifest remains unchanged. A separate
candidate registry exposes their class, filename, architecture owner, and
promotion blockers. Promotion requires an explicit authority review that may
later update the architecture source and its hash as a deliberate design
change; this migration task does not perform that update.

## Verification gates

1. Cycle tests cover lane packing, two-sample advancement, reset/arming,
   sticky faults, index continuity, atomic DAC transfer, and fail-closed
   underrun behavior.
2. Candidate Verilog emission is deterministic and has the expected module and
   port widths.
3. Existing legacy RTL generation tests remain unchanged.
4. The four authority SHA256 values and MTS fields remain byte-identical.
5. No connected Vivado attempt is created by this slice.

## Deferred work

ADC calibration, timebase consumers, delay, RCS gain, polarimetric scattering,
Doppler, target accumulation, predistortion, and full BD integration remain
separate slices. Post-route timing remains a full top-level gate.
