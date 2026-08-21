# Current Project State

## Snapshot Semantics

The live migration checkout is identified by the `git_commit` field in
`build/metadata/environment_manifest.json`; the latest connected-attempt
provenance hardening is `commit:47c251f` (`Bind connected attempts to on-disk
Tcl hashes`). It adds portable environment provenance and fresh-attempt
cleanup on top of the earlier connected-shell implementation anchor
`commit:89a2362`; it does not make Task 5 complete or prove additional
hardware readiness.

Always compare this snapshot with the live checkout before acting. The observed HEAD when the handoff implementation began was `commit:8cd3494`, which already followed the implementation anchor with handoff design and planning commits.

## Repository and Branches

| Role | Branch | Stable reference | Meaning |
|---|---|---|---|
| Accepted prior development line | `model-update-20260811` | `commit:dc31c5c` | Last accepted AMD IP normalization documentation state before connected-shell work |
| Connected-shell isolated line | `connected-bd-rfdc-shell-20260813` | `environment_manifest.git_commit` | Current migration-provenance checkout; hardware implementation anchor remains `commit:89a2362` |

The two branches were observed as separate linked worktrees. Their old absolute locations are intentionally not part of this portable authority.

## Completed Gates

Connected-shell Tasks 1 through 4 are complete and independently reviewed within their stated boundaries:

1. Task 1 froze the PS 3.5 control platform, DDR/MIO source provenance, 100 MHz PS control clock, HPM0, IRQ, and fail-closed GEM3 board-I/O responsibility.
2. Task 2 froze architecture revision 3, exact connected-shell AMD IP families and instances, and a production lock derived from real Vivado 2025.2 catalog discovery.
3. Task 3 implemented the pure canonical connected request/evidence/readiness layer without runner, Tcl launch, or lifecycle ownership.
4. Task 4 established the RFDC 2.6 probe authority with real Vivado readback and strict CONFIG/interface/scalar/diagnostic grammar.

These completions do not include a connected RFDC shell synthesis, CDC closure, timing closure, MTS runtime verification, DMA, Ethernet, or board validation.

## Current Blocker

Task 5 is **BLOCKED** after three evidence-driven implementation and review attempts:

1. `commit:86af2d5` lacked a complete candidate-evidence and synthesis/readback protocol.
2. `commit:ed8933f` completed much of the protocol but hard-coded CDC, clock-safety, and MTS readiness to true.
3. `commit:89a2362` added fail-closed parsing and structural readback, but required synthetic `CDC_SAFE`, `CLOCK_SAFE`, and `TIMING_CONSTRAINED` strings that neither its generated Tcl nor standard Vivado reports emit.

The same third attempt also introduced guessed `ADCn/DACn_Multi_Tile_Sync` property names that were not established by the Task 4 RFDC probe. Green Python tests therefore do not make the real runner protocol executable or authoritative.

The migration gates are now implemented, but Phase 0 is still **NOT READY** on this machine: the readiness record detects only Vivado 2025.1 build `6140274`, while the project gate requires Vivado 2025.2 build `6299465`. No catalog, RFDC probe, connected request, or Task 6 evidence has been accepted for this machine.

## Work Not Started

- Task 6 real Vivado connected-shell execution through the runner;
- production 2SPC continuous dual-polarization reflection chain integration;
- monitor pulse detection, hit-IQ capture, and coarse-PDW event integration;
- event DMA buffering and GEM3 data-plane integration;
- full CDC, implementation timing, MTS runtime, 24-hour stability, and board-loopback acceptance.

## Verification Boundary

At the current migration checkout, the full Python regression under the bundled Python 3.12.13 runtime reports 300 tests passing and 8 host-dependent Windows symbolic-link capability skips. This proves the tested Python contracts only.

It does not prove that generated connected-shell Tcl can accept a clean real Vivado report, that the exact MTS properties exist in the required Vivado 2025.2 installation, or that the shell synthesizes and closes CDC/timing. No Task 6 claim may be inferred from this test count.

## Resume Condition

Do not start Task 6 until all of these conditions are met:

1. Phase 0 says `ready: true` with Vivado 2025.2 build `6299465`, a clean Git tree, Python 3.12, and unchanged authority hashes;
2. a fresh catalog run and real Vivado 2025.2 RFDC probe establish the exact catalog, report grammar, and RFDC MTS configuration properties used by the evidence protocol;
3. Task 5 is amended so a deliberately unsafe report fails, a real clean report passes, all status records are canonical and measured, and an independent review closes both blockers.

After those gates close, continue in the strict order defined by [NEXT_STEPS.md](NEXT_STEPS.md).
