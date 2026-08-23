# Current Project State

## Snapshot Semantics

The live migration checkout is identified by the `git_commit` field in
`build/metadata/environment_manifest.json`. The manifest is regenerated after
any tracked change and is the only machine-specific identity for the current
evidence. The current source line preserves the connected-attempt provenance
hardening and the OOC-boundary timing interpretation; it does not claim
post-route timing, runtime MTS, or production data-path readiness.

Always compare this snapshot with the live checkout before acting. The observed HEAD when the handoff implementation began was `commit:8cd3494`, which already followed the implementation anchor with handoff design and planning commits.

## Repository and Branches

| Role | Branch | Stable reference | Meaning |
|---|---|---|---|
| Accepted prior development line | `model-update-20260811` | `commit:dc31c5c` | Last accepted AMD IP normalization documentation state before connected-shell work |
| Connected-shell isolated line | `connected-bd-rfdc-shell-20260813` | `environment_manifest.git_commit` | Current migration-provenance checkout; hardware implementation anchor remains `commit:89a2362` |

The two branches were observed as separate linked worktrees. Their old absolute locations are intentionally not part of this portable authority.

## Completed Gates

Connected-shell Tasks 1 through 6 are complete within their stated bounded
scope:

1. Task 1 froze the PS 3.5 control platform, DDR/MIO source provenance, 100 MHz PS control clock, HPM0, IRQ, and fail-closed GEM3 board-I/O responsibility.
2. Task 2 froze architecture revision 3, exact connected-shell AMD IP families and instances, and a production lock derived from real Vivado 2025.2 catalog discovery.
3. Task 3 implemented the pure canonical connected request/evidence/readiness layer without runner, Tcl launch, or lifecycle ownership.
4. Task 4 established the RFDC 2.6 probe authority with real Vivado readback and strict CONFIG/interface/scalar/diagnostic grammar.

5. Task 5 now consumes bounded real Vivado reports, binds report/Tcl hashes,
   proves exact AMD RFDC CDC waiver endpoints, and publishes success only
   after atomic validation.
6. Task 6 has a fresh real Vivado 2025.2 OOC run: BD validation and synthesis
   pass, all 24 AXIS interfaces remain BD boundary interfaces, utilization
   reports zero bonded IOBs, and the exact vendor CDC waivers are present.

These completions do not include post-route timing closure, runtime MTS/SYSREF
verification, DMA, Ethernet, board validation, or production reflection/event
data-path integration.

## Current Boundary

The current OOC connected shell is structurally ready, not production-ready.
Its top-level readiness record deliberately reports:

- `rfdc_shell_structural_ready=true`;
- `production_integration_ready=false` with blocker
  `production_integration_pending`;
- `mts_runtime_verified=false`;
- timing scope `ooc_boundary_only`.

The migration gates are **READY** on this machine: the current environment
manifest records Vivado 2025.2 build `6299465`, Python 3.12.13, a clean Git
tree, and unchanged authority hashes. Fresh catalog, RFDC probe, and real
connected-shell evidence are all bound to that manifest.

## Production 2SPC Candidate Slice

The first production-boundary candidate slice is now implemented outside the
production manifest:

- `rx_2spc_continuous_ingress` is a new Cycle/RTL candidate for the eight ADC
  component streams, atomic valid acceptance, lane unpacking, sticky format/gap
  faults, and two-sample absolute-index advancement;
- `continuous_stream_timebase` is a new Cycle/RTL candidate for zero-based,
  contiguous two-sample index checking and upstream fault propagation;
- `tx_2spc_continuous_egress` is a new Cycle/RTL candidate for eight-way atomic
  DAC `{Q1,I1,Q0,I0}` packing and fail-closed underrun handling.

The candidates are registered separately as `architecture_pending` and are not
included in `HARDWARE_MODULES`, production RTL, or `production_integration_ready`.
The legacy 2SPC classes remain reference-only and unchanged. Candidate design
and execution records are in
[production-2spc-boundary-design.md](../superpowers/specs/2026-08-23-production-2spc-boundary-design.md)
and [production-2spc-boundary.md](../superpowers/plans/2026-08-23-production-2spc-boundary.md).

## Work Not Started

- promotion of the 2SPC candidates to reviewed production owners;
- ADC calibration, delay, RCS gain, scattering, Doppler, accumulation,
  predistortion, and full continuous reflection chain integration;
- monitor pulse detection, hit-IQ capture, and coarse-PDW event integration;
- event DMA buffering and GEM3 data-plane integration;
- post-route/full-top-level timing, MTS runtime, 24-hour stability, and
  board-loopback acceptance.

## Verification Boundary

At the current migration checkout, the full Python regression under the bundled
Python 3.12.13 runtime reports 327 tests passing and 8 host-dependent Windows
symbolic-link capability skips. Fresh catalog, RFDC probe, and connected-shell
evidence are bound to the current environment manifest. The real OOC run
reported 0 synthesis errors, 0 critical warnings, 0 synthesis warnings, and
0 bonded IOBs.

These results prove the bounded OOC shell contract. They do not prove
post-route timing, runtime MTS/SYSREF behavior, or production data-path and
board acceptance.

## Resume Condition

Before starting production integration, all of these conditions must remain
true:

1. Keep Phase 0 `ready: true` with Vivado 2025.2 build `6299465`, a clean Git tree, Python 3.12, and unchanged authority hashes;
2. retain the fresh catalog run and real Vivado 2025.2 RFDC probe as the current-machine authority for the exact catalog and RFDC MTS bindings;
3. Preserve the OOC boundary: AXIS remains in the BD interface contract and
   is not turned into package IOBs until a real top-level wrapper is supplied.
4. Keep post-route timing and runtime MTS as later gates; do not upgrade this
   OOC success record into a production claim.

Continue in the strict order defined by [NEXT_STEPS.md](NEXT_STEPS.md).
