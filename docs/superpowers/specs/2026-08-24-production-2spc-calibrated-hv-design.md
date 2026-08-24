# Production 2SPC Calibrated H/V Front-End Design

## Status

Candidate implementation design for the `snapshot-c118362-20260824` branch.
This slice remains `architecture_pending`. It does not change RFDC
configuration, MTS fields, authority JSON, authority hashes, connected-shell
evidence, or the production hardware registry.

## Goal

Add the first processing leaf after the proven RFDC 2SPC ingress: select the
configured H/V echo gain paths, apply the frozen fixed-point calibration
contract, and emit two complex H/V samples per 250 MHz cycle with the original
absolute sample index and fail-closed status.

The leaf is deliberately independent of pulse detection, target reflection,
delay, Doppler, accumulation, predistortion, DMA, and board I/O.

## Existing boundary

The new leaf consumes the registered outputs of
`rx_2spc_continuous_ingress` and must preserve its stream contract:

- one common clock and synchronous active-high reset;
- `rx_valid` represents an atomic two-sample beat;
- sample base indices advance by exactly two;
- upstream format and gap faults are sticky and fail closed;
- no backpressure is introduced on the continuous RFDC stream.

The current authority map is authoritative for channel ownership:

| Logical path | ADC index | Role |
|---|---:|---|
| H high | 0 | echo |
| H mid | 1 | echo |
| H low | 2 | echo |
| H reference | 3 | calibration-only |
| V high | 4 | echo |
| V mid | 5 | echo |
| V low | 6 | echo |
| V reference | 7 | calibration-only |

ADC indices 3 and 7 must not be selectable by the continuous echo path.

## Proposed module boundary

The candidate Cycle module is named
`rx_2spc_calibrated_hv_frontend`.

### Inputs

- `clk_i`, `rst_i`;
- `frontend_enable_i`;
- `rx_valid_i`, `sample_base_index_i`;
- `rx_i_lane0_i`, `rx_q_lane0_i`, `rx_i_lane1_i`, `rx_q_lane1_i`, each carrying
  eight signed 16-bit ADC components;
- `format_error_i` and `gap_error_i`;
- `selected_range_h_i` and `selected_range_v_i`, two-bit values with the
  explicit encoding `0=HIGH`, `1=MID`, `2=LOW`, `3=reserved`;
- per-path calibration coefficients supplied as construction-time constants
  for this candidate slice, using the authority numeric format named
  `calibration_coefficient`.

The first implementation does not create an AXI-Lite register bank. Runtime
coefficient programming is a later control-plane slice and must not be
silently implied by this module.

### Outputs

- `incident_valid_o`;
- `incident_i_lane0_o`, `incident_q_lane0_o`,
  `incident_i_lane1_o`, `incident_q_lane1_o`, each carrying two signed H/V
  complex lanes in the authority `reflection_sample` format;
- `sample_base_index_o`;
- `stream_active_o`;
- `format_error_o`, `gap_error_o`, and `calibration_error_o`;
- `selected_range_h_o` and `selected_range_v_o` for evidence and downstream
  event correlation.

All data and status outputs are registered. The module has one cycle of
latency from an accepted ingress beat to `incident_valid_o`.

## Fixed-point arithmetic contract

The implementation must use the existing authority numeric formats without
changing their JSON values:

- ADC component: signed 16-bit integer;
- calibration coefficient: signed 24-bit with 20 fractional bits;
- calibration product: signed 48-bit with 24 fractional bits;
- matrix accumulator: signed 50-bit with 24 fractional bits;
- reflection sample: signed 24-bit with 4 fractional bits and saturation;
- project rounding: ties away from zero.

For this slice, each selected H/V path is independently corrected by its
scalar coefficient. The 2x2 receive polarization inverse matrix is not folded
into this module; it is a separate matrix leaf so its complex multiply and
accumulator proof cannot be hidden inside channel selection.

The candidate must expose overflow or invalid coefficient conditions as
`calibration_error_o` and drive data/valid to the fail-closed state. It must
never wrap a saturated reflection sample or silently reinterpret a reserved
range code.

## Control and fault semantics

- Before `frontend_enable_i`, input valid patterns are ignored and no fault is
  raised.
- A reserved range code raises sticky `calibration_error_o` once enabled.
- Any upstream fault propagates to the corresponding sticky output and blocks
  subsequent valid output until reset.
- A non-finite or out-of-contract construction-time coefficient is rejected
  before Verilog emission.
- An accepted beat requires `rx_valid_i=1` and all three sticky fault inputs
  clear; otherwise no output beat is emitted.
- The output sample base equals the accepted ingress sample base and is never
  repaired or renumbered.

## Promotion boundary

The module is registered in `CANDIDATE_HARDWARE_MODULES` only. It is not added
to `HARDWARE_MODULES`, production RTL generation, connected BD Tcl, or
`production_integration_ready`.

Promotion requires a later review proving:

1. the fixed-point implementation is bit-equivalent to the Golden calibration
   reference for the selected coefficient set;
2. H/V and range ownership matches `config/default.json` exactly;
3. all calibration-only channels remain unavailable to the echo selector;
4. the generated Verilog is deterministic and synthesizable;
5. two-sample throughput has no backpressure or hidden bubble;
6. resource and timing evidence is collected in the full production top level.

## Verification plan

The implementation plan must add tests before production code for:

1. canonical H/V range selection for HIGH, MID, and LOW;
2. rejection of reserved range code 3;
3. exclusion of ADC3 and ADC7 from the echo path;
4. signed coefficient multiplication, ties-away-from-zero rounding, and
   reflection-sample saturation;
5. one-cycle latency and exact sample-base preservation;
6. propagation and stickiness of upstream and calibration faults;
7. deterministic Verilog emission, including stable coefficient constants and
   complete port widths;
8. Golden bit/cycle equivalence over nominal, negative, near-zero, and
   saturation vectors;
9. continuous two-sample operation without backpressure.

The focused tests must pass before the full Python regression is rerun. No
Vivado connected-shell attempt is created by this slice.

## Explicitly deferred

- receive 2x2 polarization matrix inversion;
- relative/fixed fractional delay;
- RCS gain and target compilation in hardware;
- scattering, Doppler, multi-target accumulation, and predistortion;
- monitor/event chain, DMA, GEM3, post-route timing, runtime MTS/SYSREF, and
  board acceptance.
