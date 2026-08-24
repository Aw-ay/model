# Strictly Ordered Next Steps

`production_integration_ready=false` remains the governing boundary. The
current bundle is a blocked fresh-attempt record, not a waiver to use prior
artifacts.

## 1. Restore a compliant evidence environment

Install or select Python 3.12, then create another new clean worktree at the
then-current HEAD. Run Phase 0 with Vivado 2025.2 build 6299465 and require a
clean Git tree plus unchanged authority hashes. Do not copy `build/`, `.Xil/`,
`.runs/`, `.gen/`, `project.xpr`, reports, or metadata from any prior attempt.

## 2. Regenerate connected OOC evidence

In that fresh environment, rerun catalog discovery, RFDC probe, connected
request/Tcl generation, and the connected OOC shell. Publish evidence only
if request/realization/verification Tcl hashes and all four fresh report hashes
validate, the exact CDC-15 endpoint set is 60 pairs, and the measured
`bonded_iob_used=0`. Keep timing scope `ooc_boundary_only`.

## 3. Complete verification provenance

Run the focused fixed-point, calibrated-H/V, Cycle, Verilog, Tcl/parser, and
bundle checks. Attempt the full Python regression and report its actual final
summary or its actual interrupted/failed status. The historical `327 tests /
8 skips` result remains scoped only to baseline `c118362`.

## 4. Production work stays downstream

Only after fresh OOC evidence is valid may work continue toward full 2SPC
production ownership, monitor/event hardware, DMA/GEM3, post-route timing,
runtime MTS/SYSREF, and board acceptance. OOC evidence never proves those
later gates.
