# Open Issues

| ID | Status | Evidence | Exit gate | Forbidden claim |
|---|---|---|---|---|
| `MIGRATION-ENV-2025-2` | blocked | Fresh detached-worktree manifest in `connected_evidence_bundle.json` measured Vivado 2025.2 build 6299465 but Python 3.13.2, so Phase 0 is `ready=false` with `python_3_12_required`. | Use Python 3.12 and rerun Phase 0 on a clean current checkout. | “Fresh connected evidence is available.” |
| `BD-T5-REPORT-PROTOCOL` | superseded | Historical report-protocol findings are retained for identifier continuity; the current parser remains fail-closed and the fresh bundle is authoritative for its own attempt only. | Regenerate a successful fresh OOC attempt after the environment gate is restored. | “Historical reports prove current evidence.” |
| `BD-T5-MTS-AUTHORITY` | superseded | Historical MTS-property authority findings are retained for identifier continuity; configuration proof remains separate from runtime MTS/SYSREF. | Preserve measured bindings and add runtime evidence later. | “MTS runtime is verified.” |
| `CONNECTED-OOC-EVIDENCE` | pending | The current fresh attempt stopped before catalog/probe/connected execution; request/Tcl/report hashes and current bonded-IOB measurement are null. | Fresh catalog, probe, OOC run, four report hashes, exact CDC-15 inventory, and measured `bonded_iob_used=0`. | “OOC shell is freshly ready.” |
| `CDC-TIMING` | pending | The contract permits only the exact 60-pair CDC-15 inventory and keeps timing `ooc_boundary_only`. | Close CDC and timing after real top-level integration, without broad waivers. | “Post-route timing closed” or “250 MHz production-ready.” |
| `MTS-RUNTIME` | pending | Probe configuration is distinct from runtime MTS/SYSREF behavior. | Driver/SYSREF evidence plus repeated phase/latency and reset-cycle measurements. | “MTS runtime is verified.” |
| `PRODUCTION-2SPC` | pending | Candidate modules remain `architecture_pending`; current focused counts are 14 calibrated-H/V tests and 57 Cycle tests. | Full production Golden bit/cycle equivalence, ownership review, and synthesis evidence. | “Candidate or legacy 2SPC satisfies production.” |
| `DMA-GEM3-BOARD` | pending | No reviewed production event transport or enabled board authority is present. | Complete monitor/event chain, DMA, GEM3 authority, integration, and board acceptance. | “Network/board integration is accepted.” |

The historical `327 tests / 8 skips` result is scoped only to baseline
`c118362`; it is not evidence for the current branch.
