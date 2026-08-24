# Implementation History

## Long-lived foundations

The Golden model, Cycle reference work, AMD IP normalization, production-lock
validation, and RFDC-only probe were implemented in earlier commits. Their
bounded results establish model/configuration contracts; they do not by
themselves establish current connected-shell or production readiness.

## Connected-shell lineage

- Connected-shell Tasks 1–4 froze PS/platform authority, catalog/lock
  authority, pure request/evidence validation, and the RFDC 2.6 probe.
- The earlier connected runner review exposed report-protocol and MTS
  authority defects. Subsequent closure work added immutable attempt files,
  report parsing, exact CDC endpoint validation, OOC timing semantics, and a
  zero-Bonded-IOB machine gate.
- `commit:89a2362` remains a historical review anchor for those repaired
  report-protocol findings; it is not current evidence or a current task
  status.
- PR-hardening Tasks 1–3 at base `e70e774` made signed fixed-point emission
  legal and width-exact, froze the exact 60-pair CDC-15 inventory, and made a
  measured zero Bonded IOB mandatory for connected evidence.
- PR-hardening Task 4 records the new fresh-attempt outcome in
  [connected_evidence_bundle.json](connected_evidence_bundle.json). The
  environment stopped at the Python 3.12 gate, so it does not replace prior
  artifacts with a claim of fresh OOC success.

## Test provenance

The historical `327 tests / 8 skips` result belongs only to baseline
`c118362`. Current focused counts are 14 calibrated-H/V tests and 57 Cycle
tests. The current branch-wide Python regression is unclaimed until a fresh
complete run produces a final summary.

## Durable boundaries

`production_integration_ready=false` remains invariant. OOC timing is
`ooc_boundary_only`; post-route timing, runtime MTS/SYSREF, full production
data-path ownership, DMA/Ethernet, and board-loopback acceptance remain later
work.
