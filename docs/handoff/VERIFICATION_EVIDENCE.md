# Verification Evidence

## Migration Checkout Supplement (2026-08-21)

The current portable-migration checkout is `commit:73904b8` on
`connected-bd-rfdc-shell-20260813`. Its fresh environment record is
`build/metadata/environment_manifest.json`, with manifest SHA-256
`f5cb7846ba673fbc4caaf5993dddee93c3cbe09586067584abe002f3a1753229`.
The record correctly binds this checkout to Python 3.12.13 and the absolute
repository path as environment-only data, while
`build/metadata/environment_ready.json` is `ready:false` because this machine
currently exposes only Vivado 2025.1 build `6140274`; the required Vivado
2025.2 build `6299465` is not verified here.

The four authority SHA-256 values below are unchanged. The fresh `build/`
contains only environment metadata: no copied catalog, RFDC probe, connected
request, report, or Task 6 evidence. The full Python regression for the
migration gates passed 298 tests with 8 host-dependent Windows symbolic-link
capability skips. That result does not upgrade the historical Vivado evidence
or clear the Task 5/6 gates.

This record separates mathematical, cycle/RTL, catalog, RFDC-probe, connected-shell, and board evidence. A passing result at one layer is not evidence for a later layer.

## Reproduction Environment

- Target device: `xczu27dr-fsve1156-2-i`.
- Model/test interpreter: the project-pinned Python 3.12 runtime with `PYTHONPATH` set to the repository `src` directory.
- Vivado evidence version: AMD Vivado 2025.2, SW build 6299465 and IP build 6300035 where recorded by the tracked normalization acceptance.
- Main accepted normalization checkpoint: `commit:dc31c5c` on `model-update-20260811`.
- Connected-shell implementation anchor: `commit:89a2362` on `connected-bd-rfdc-shell-20260813`.
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
- catalog completeness and lock validity do not imply connected topology or production integration.

## RFDC 2.6 Probe

Connected-shell Task 4 ended CLEAN at `commit:9a28daa`. Reviewed real attempt 6 recorded:

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

The mandatory diagnostic counters were sampled from before the first project/BD/cell/property action and emitted unconditionally. The strict parser rejects missing, duplicate, unknown, malformed, or nonzero diagnostic records and validates exact interface/scalar inventories and authority-derived RFDC properties.

This RFDC-only probe does **not** prove common-clock legality, connected-shell CDC, synthesis/implementation timing, runtime MTS/SYSREF success, DMA/Ethernet integration, or board RF behavior.

## Connected-Shell Tasks 1-5

| Task | Implementation lineage | Final bounded state | Evidence |
|---|---|---|---|
| 1: PS platform authority | `commit:cc54bf5`, `commit:dd46ba2`, `commit:a9b8d19` | CLEAN | Fresh Vivado PS 3.5 property readback; 59 focused and 231 full tests with 8 host-dependent skips. GEM3 board I/O remains pending. |
| 2: schema-v3 platform IP/lock | `commit:23d957c`, `commit:c9dd242`, `commit:b06f80e`, `commit:bb28c36`, `commit:059fb97` | CLEAN | Real 18-family discovery/lock; protected owners and exact shell cells fail closed; controller run reported 243 full tests with 8 skips. |
| 3: pure request/evidence/readiness | `commit:cd0ce18`, `commit:2403c5b`, `commit:79ca1dd` | CLEAN | Pure data boundary, explicit authority bytes and lock provenance; 54 focused with 2 skips and 251 full with 8 skips. |
| 4: RFDC-only probe | `commit:67b2106`, `commit:84166e9`, `commit:85780f7`, `commit:9a28daa` | CLEAN | Real attempt-6 readback above; 47 focused and 262 full tests with 8 skips. |
| 5: connected Tcl/runner | `commit:86af2d5`, `commit:ed8933f`, `commit:89a2362` | **BLOCKED** | Historical implementation-anchor suite: 274 passed, 8 host-dependent symlink skips. Current migration-gate suite is 298 passed with 8 skips, but neither result closes the real-report protocol or current-machine MTS-property authority. |

At the implementation anchor, Task 5 remains structurally blocked even though its focused and full Python tests pass. Task 6 real connected-shell execution was therefore not started.

## Evidence Not Yet Obtained

- A Task 5 protocol whose clean proof is emitted by generated Tcl or derived from validated real Vivado report grammar, rather than synthetic fixture-only markers.
- RFDC 2.6 MTS properties established by probe authority and exact production readback; no invented property names are acceptable.
- A successful real connected-shell runner attempt and canonical published evidence.
- `validate_bd_design`, synthesis, opened synthesized run, bounded CDC/clock/timing interpretation, implementation, and timing closure for the final connected topology.
- Runtime RFDC MTS/SYSREF alignment and measured fixed internal delay.
- Production Cycle and generated-Verilog implementations for RX/TX 2SPC, continuous reflection, and monitor events.
- DMA/DDR/GEM3 event-only transfer, packet-loss accounting, and host reception.
- Board-level 8 ADC/8 DAC continuity, H/V identity, +20/0/-20 dB range ratios, loopback, phase stability, and 24-hour operation.
