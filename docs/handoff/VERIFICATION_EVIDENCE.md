# Verification Evidence

## Migration Checkout Supplement (2026-08-22)

The current portable-migration checkout is the `git_commit` recorded in
`build/metadata/environment_manifest.json` on
`connected-bd-rfdc-shell-20260813`. Its fresh environment record is
`build/metadata/environment_manifest.json`; its current canonical SHA-256 is
the `environment_manifest_sha256` value in the matching readiness record.
The record correctly binds this checkout to Python 3.12.13 and the absolute
repository path as environment-only data. `build/metadata/environment_ready.json`
is `ready:true` for Vivado 2025.2 build `6299465`, a clean Git tree, and
unchanged authority hashes.

The current environment manifest SHA-256 is recorded canonically in
`build/metadata/environment_manifest.json` and echoed by
`build/metadata/environment_ready.json`; it is intentionally not duplicated
in this handoff text.

The four authority SHA-256 values below are unchanged. The current `build/`
contains fresh current-machine catalog, RFDC probe, connected request, and
real connected-shell attempt artifacts; no old attempt-local Vivado project
or report outputs were copied. The full Python regression passed 314 tests
with 8 host-dependent Windows symbolic-link capability skips. The latest real
OOC attempt passed the bounded connected-shell gate; production integration
remains explicitly false.

This record separates mathematical, cycle/RTL, catalog, RFDC-probe, connected-shell, and board evidence. A passing result at one layer is not evidence for a later layer.

## Reproduction Environment

- Target device: `xczu27dr-fsve1156-2-i`.
- Model/test interpreter: the project-pinned Python 3.12 runtime with `PYTHONPATH` set to the repository `src` directory.
- Vivado evidence version: AMD Vivado 2025.2, SW build 6299465 and IP build 6300035 where recorded by the tracked normalization acceptance.
- Main accepted normalization checkpoint: `commit:dc31c5c` on `model-update-20260811`.
- Connected-shell source identity: the live checkout is the manifest's
  `git_commit`; any tracked change requires a new Phase-0 freeze.
- Current authority hashes:

| Authority | SHA-256 |
|---|---|
| `config/default.json` | `d92c4a334728af441b22fa907e55cf4d6d236d899f46cbe3cd3ed7f26f9d5eb3` |
| `config/ip_architecture.json` | `36034e9c7b64061cdd449fb43030aea96368c95d6e88c8c6a0a9154da9e0bd96` |
| `config/ip_lock.json` | `0b1c92166b605a0a56c867fb144896d23599ade95538a29b72c9c274437fbe97` |
| `config/ps_platform.json` | `a1243d78a90ccb8e00f34749a8c3f18bf55870130c8f8372402407cf5591d11f` |

These are source-authority identifiers, not a claim that generated or hardware results remain valid after any authority changes.

## Golden and Cycle Tests

The tracked [polarimetric Golden acceptance](../verification/polarimetric-golden-acceptance.md) records the mathematical checkpoint before the IP normalization work:

- 114 Golden tests passed and 128 total Python tests passed at that checkpoint.
- Eight-channel calibrated H/V reconstruction, delay, carrier phase, RCS, 2x2 scattering, Doppler, predistortion, and eight-DAC routing were exercised.
- One-shot and chunked 1024-sample continuous runs matched, including nonzero Doppler and absolute detector-domain ToA.
- A twelve-order detector-threshold change left the complete DAC reflection frame unchanged, proving monitor/main-chain separation in the Golden model.
- Physical mapping, RFDC word packing, clipping, contiguous-main-peak FWHM, online PDW semantics, fixed-delay semantics, and fixed-point manifest validation were covered.

The initial Cycle checkpoint verified restricted simultaneous `compute()`/`clock()` commit semantics and the legacy eight-channel RFDC ingress at two samples per clock. It also verified fail-closed startup/gap/format handling and generated metadata. This is a legacy-reference checkpoint only; it is not production coverage of the complete reflection or monitor chains.

## Generated RTL and Equivalence

The tracked Golden acceptance records Vivado 2025.2 `xvlog`, `xelab`, and XSim success for the generated legacy 2SPC ingress testbench. Registered generated modules carry port, latency, throughput, and SHA metadata.

The following boundaries remain explicit:

- no complete Cycle implementation exists for the continuous polarimetric reflection chain;
- no complete Cycle implementation exists for the monitor detector/event chain;
- bit/cycle equivalence beyond the legacy RFDC ingress has not been established;
- legacy `rx_group_ingress_2spc` and `tx_iq_axis_boundary_2spc` artifacts cannot satisfy production responsibilities;
- zero current production RTL files is an honest state, not an equivalence success.

## AMD IP Catalog and Production Lock

The tracked [AMD IP normalization acceptance](../verification/amd-ip-normalization-acceptance.md) records a real Vivado 2025.2 catalog discovery and an exact production lock at `commit:dc31c5c`. The connected-shell Task 2 later expanded the catalog authority to 18 exact families and tool-promoted the current lock at `commit:23d957c`.

Current source verification establishes:

- exact RFDC identity `xilinx.com:ip:usp_rf_data_converter:2.6`;
- exact lock hash `0b1c92166b605a0a56c867fb144896d23599ade95538a29b72c9c274437fbe97`;
- root and installed-package architecture/lock mirrors are byte-identical under tests;
- discovery provenance is bound separately from realization Tcl;
- the fresh catalog run is bound to the current environment manifest and has
  `catalog_status=all_required_ip_resolved` with a valid production lock;
- current catalog evidence and environment-only provenance hashes are recorded
  canonically in `build/metadata/catalog_evidence.tsv` and
  `build/metadata/catalog_provenance.json`;
- catalog completeness and lock validity do not imply connected topology or production integration.

## RFDC 2.6 Probe

Connected-shell Task 4 ended CLEAN at `commit:9a28daa`. The current migration
checkout also recorded a fresh real Vivado 2025.2 RFDC-only run `run_id=1`.
Its measured result is:

| Item | Measured result |
|---|---|
| Vivado | 2025.2 |
| Device part | `xczu27dr-fsve1156-2-i` |
| RFDC | `xilinx.com:ip:usp_rf_data_converter:2.6` |
| CONFIG records | 868 |
| Interface records | 48 |
| Scalar pin records | 156 |
| ADC AXIS | 16 component masters, 32 bits each |
| DAC AXIS | 8 complex slaves, 64 bits each |
| ADC/DAC fabric | 250 MHz |
| Fine-mixer NCO | 2.8 GHz |
| `WARNING` count | 0 |
| `CRITICAL_WARNING` count | 0 |
| `ERROR` count | 0 |

The current evidence records 13 MTS properties, 12 readback records, and 6
tile-to-property bindings. Its canonical evidence hash is recorded in
`build/metadata/rfdc_probe_evidence.json`, bound to the current environment
manifest and probe Tcl/raw-output hashes.

The fresh connected request hash is recorded canonically in
`build/metadata/connected_request.json`; it consumes probe `run_id=1` and
remains `production_integration_ready=false`.

The mandatory diagnostic counters were sampled from before the first project/BD/cell/property action and emitted unconditionally. The strict parser rejects missing, duplicate, unknown, malformed, or nonzero diagnostic records and validates exact interface/scalar inventories and authority-derived RFDC properties.

This RFDC-only probe does **not** prove common-clock legality, connected-shell CDC, synthesis/implementation timing, runtime MTS/SYSREF success, DMA/Ethernet integration, or board RF behavior.

## Connected-Shell Tasks 1-6

| Task | Implementation lineage | Final bounded state | Evidence |
|---|---|---|---|
| 1: PS platform authority | `commit:cc54bf5`, `commit:dd46ba2`, `commit:a9b8d19` | CLEAN | Fresh Vivado PS 3.5 property readback; 59 focused and 231 full tests with 8 host-dependent skips. GEM3 board I/O remains pending. |
| 2: schema-v3 platform IP/lock | `commit:23d957c`, `commit:c9dd242`, `commit:b06f80e`, `commit:bb28c36`, `commit:059fb97` | CLEAN | Real 18-family discovery/lock; protected owners and exact shell cells fail closed; controller run reported 243 full tests with 8 skips. |
| 3: pure request/evidence/readiness | `commit:cd0ce18`, `commit:2403c5b`, `commit:79ca1dd` | CLEAN | Pure data boundary, explicit authority bytes and lock provenance; 54 focused with 2 skips and 251 full with 8 skips. |
| 4: RFDC-only probe | `commit:67b2106`, `commit:84166e9`, `commit:85780f7`, `commit:9a28daa` | CLEAN | Real attempt-6 readback above; 47 focused and 262 full tests with 8 skips. |
| 5: connected Tcl/runner | Current live checkout, identified by the environment manifest | CLEAN | Real Vivado report grammar is accepted only through bounded parsers; request/Tcl/readback/report hashes are bound; unsafe, stale, and mismatched attempts fail closed. |
| 6: connected shell OOC | Latest fresh environment-bound attempt | CLEAN, OOC scope only | Vivado 2025.2 validates the BD and synthesizes `synth_1` with 0 errors, 0 critical warnings, and 0 synthesis warnings. All 24 AXIS interfaces remain BD boundary interfaces; utilization reports 0 bonded IOBs. CDC-11/13/15 waiver endpoint sets are exact and present. |

The connected-shell readiness record intentionally keeps
`production_integration_ready=false`. Its timing scope is
`ooc_boundary_only`; the 515 missing input delays and 536 missing output
delays belong to the external BD boundary and are deferred to the real
top-level data-path integration.

The latest report contains exact vendor waiver counts of CDC-11: 6,
CDC-13: 4, and CDC-15: 60. These are endpoint-specific AMD RFDC waivers,
not a broad CDC waiver.

## Evidence Not Yet Obtained

## Evidence Not Yet Obtained

- Post-route/full-top-level timing closure and final data-path CDC; the OOC boundary result is not an implementation result.
- Runtime RFDC MTS/SYSREF alignment and measured fixed internal delay.
- Production Cycle and generated-Verilog implementations for RX/TX 2SPC, continuous reflection, and monitor events.
- DMA/DDR/GEM3 event-only transfer, packet-loss accounting, and host reception.
- Board-level 8 ADC/8 DAC continuity, H/V identity, +20/0/-20 dB range ratios, loopback, phase stability, and 24-hour operation.
