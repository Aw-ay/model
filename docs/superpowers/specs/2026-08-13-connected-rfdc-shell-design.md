# Connected RFDC Shell Design

**Date:** 2026-08-13
**Status:** Approved design
**Target branch:** `connected-bd-rfdc-shell-20260813`

## 1. Purpose

Replace the unconnected `rfdc_0` realization with the first production-facing
Block Design checkpoint: a fresh ZU27DR project containing a configured PS, an
RF Data Converter 2.6 instance, explicit control/reset/interrupt plumbing, and
all 8 ADC plus 8 DAC data interfaces at the frozen 250 MHz, 2SPC boundary.

This checkpoint proves RFDC parameters and structural connectivity. It does
not treat structural proof as proof of the continuous reflection algorithm,
event transport, Ethernet software, post-route timing, converter
synchronization at runtime, or board wiring.

## 2. Non-negotiable authorities

The connected shell consumes, but does not duplicate, these authorities:

- `ModelConfig` owns converter rates, PL rates, 2SPC, physical channel maps,
  ADC I/Q stream identity, DAC word format, and the device part.
- `HardwareArchitectureConfig` owns AMD IP families, concrete instances,
  lifecycle and maturity, RFDC integration intent, and topology status.
- a new packaged `PsPlatformConfig` owns the reviewed PS property allowlist,
  the 100 MHz control clock, and provenance of the one-time board-platform
  extraction.
- the existing production IP lock owns the exact required Vivado catalog
  family set. It never owns connected-realization Tcl.
- generated Tcl owns the reproducible BD structure. Generated Tcl and generated
  BD files are never edited manually.

The two source/package copies of every packaged JSON authority remain
byte-identical and are checked out with LF line endings so that SHA-256
provenance is independent of Windows `core.autocrlf`.

## 3. Configuration evolution

The architecture object structure remains schema v2. The connected checkpoint
increments `architecture_config_version` and changes the topology value from
`unconnected_skeleton` to `connected_rfdc_shell`. It materializes the platform
instances described below while leaving algorithm, detector, DMA, and
reflection owners pending.

`PsPlatformConfig` is a separate schema-v1 package resource. It contains:

- exact device part and PS VLNV;
- `control_clock_hz = 100000000`;
- a canonical, explicit PS property mapping;
- the source reference path and SHA-256 used for one-time extraction;
- the Vivado version used to verify that the property mapping remains valid.

The production build never reads `save_v2.1`. A temporary, read-only Vivado
extraction uses an upgraded disposable copy of
`save_v2.1/XCZU27_MEM_TEST_TOP/XCZU27_TOP.srcs/sources_1/bd/design_1/design_1.bd`
once to create and review the platform mapping. The GTY example BD is not a
board PS/DDR authority. After the platform mapping is committed, every normal
build starts from an empty project.

## 4. Required platform IP families

The exact required family set expands to include:

| Family ID | Required identity |
|---|---|
| `zynq_ultra_ps_e` | `xilinx.com:ip:zynq_ultra_ps_e:3.5` |
| `smartconnect` | `xilinx.com:ip:smartconnect:1.0` |
| `proc_sys_reset` | `xilinx.com:ip:proc_sys_reset:5.0` |
| `util_vector_logic` | `xilinx.com:ip:util_vector_logic:2.0` |
| `xlconcat` | `xilinx.com:ip:xlconcat:2.1` |

These families participate in the same strict discovery, evidence, candidate,
and explicit promotion flow as the existing thirteen families. Vivado BD
automation may not insert an undeclared cell or catalog family.

The connected shell materializes these stable instances:

```text
zynq_ultra_ps_e_0
ctrl_smartconnect_0
reset_inverter_0
ctrl_reset_0
rx_reset_0
tx_reset_0
irq_concat_0
rfdc_0
```

The `rfdc_frontend` remains not production-accepted until the evidence gates in
this document pass. Every continuous-reflection, monitor, event, and status
owner remains pending, so overall production readiness remains false.

## 5. Fresh-project Block Design

The connected-realization Tcl must:

1. create a disk-backed build project under the requested output root or reuse
   only an existing project whose `PART` exactly matches
   `xczu27dr-fsve1156-2-i`;
2. create one BD named `connected_rfdc_shell`;
3. create only the declared materialized cells;
4. apply the canonical PS property mapping and RFDC property mapping;
5. connect the control, reset, interrupt, clock, and data-boundary networks;
6. assign the RFDC AXI-Lite address;
7. externalize RF analogue, reference-clock, SYSREF, and all data interfaces;
8. validate and save the BD; and
9. emit no acceptance claim. Verification is a separate Tcl and parser step.

Before the connected-realization Tcl is frozen, a separate RFDC-only probe Tcl
creates a temporary exact-part project, configures only `rfdc_0`, and records
the actual writable RFDC property names, enabled port set, widths, directions,
clock/reset pins, RF analogue/reference/SYSREF interfaces, and common-clock
legality. Probe output is diagnostic input to the source implementation, not
production acceptance evidence.

The generated build directory, `.Xil`, `.srcs`, `.runs`, `.gen`, journals,
logs, and reports are local artifacts under `build/` and are never committed.

## 6. RFDC parameter contract

Vivado property names are treated as tool-owned spelling and must be confirmed
by the RFDC-only 2025.2 probe before they are frozen in the connected emitter.
The requested semantic values are fixed:

- ADC tiles 0 through 3 enabled;
- physical ADC slices `00`, `02`, `10`, `12`, `20`, `22`, `30`, `32` enabled;
- ADC sampling rate 4.000 GSPS, DDC/decimation x8, complex I/Q output;
- each ADC component stream is 32 bits and carries two signed-16 samples;
- DAC tiles 0 and 1 enabled;
- DAC slices `00`, `01`, `02`, `03`, `10`, `11`, `12`, `13` enabled;
- DAC sampling rate 4.000 GSPS, DUC/interpolation x8;
- DAC PL input is complex I/Q, 64 bits and two samples per clock;
- fine mixer performs I/Q-to-real conversion at 2.8 GHz with unity scaling;
- RX and TX fabric rates are 250 MHz;
- the declared MTS/SYSREF grouping covers every enabled tile.

Any missing property, unsupported value, unexpected generated width, or
different port identity is an integration failure. The emitter must not try
alternate property spellings silently. Internal RFDC interface pin names are
the comparison authority; Vivado-generated names for externalized ports are
recorded as evidence but are not treated as a stable API.

## 7. Clock and reset architecture

There are three explicit domains:

### 7.1 Control domain

`zynq_ultra_ps_e_0/pl_clk0` is configured to 100 MHz and drives PS HPM0,
SmartConnect, RFDC `s_axi_aclk`, and `ctrl_reset_0`. The 100 MHz value is an
explicit new platform decision, not an inherited legacy value. It isolates the
low-bandwidth AXI-Lite control path from the 250 MHz converter data paths.

### 7.2 RX data domain

`rfdc_0/clk_adc0` is the candidate 250 MHz `rx_axis_clk`. One physical BD net
drives `m0_axis_aclk` through `m3_axis_aclk`, all sixteen exported ADC component
interfaces, and `rx_reset_0`.

The design fails closed if RFDC 2.6 or Vivado will not permit this common-net
architecture. It must not replace the failed design with implicit per-tile CDC.
A per-tile-clock architecture requires a new design checkpoint.

### 7.3 TX data domain

`rfdc_0/clk_dac0` is the candidate 250 MHz `tx_axis_clk`. One physical BD net
drives `s0_axis_aclk` and `s1_axis_aclk`, all eight exported DAC interfaces,
and `tx_reset_0`.

PS `pl_resetn0` is explicitly inverted by `reset_inverter_0`. Each
`proc_sys_reset` receives that asynchronous assertion and synchronously
releases its own outputs in its local clock domain. A reset synchronized in
one domain is never reused in another domain.

RX and TX are separate clock domains in this checkpoint. No reflection data
path crosses between them yet.

## 8. Data and control interfaces

The control connection is:

```text
PS M_AXI_HPM0_FPD -> ctrl_smartconnect_0 -> rfdc_0/s_axi
```

`rfdc_0/irq` connects through `irq_concat_0` to `pl_ps_irq0`. Unused interrupt
inputs are not synthesized through undeclared constants; the concat width and
PS interrupt width must be configured consistently and verified by readback.

All RFDC data interfaces are external boundaries in this checkpoint:

- ADC I: `m00`, `m02`, `m10`, `m12`, `m20`, `m22`, `m30`, `m32`;
- ADC Q: `m01`, `m03`, `m11`, `m13`, `m21`, `m23`, `m31`, `m33`;
- DAC: `s00`, `s01`, `s02`, `s03`, `s10`, `s11`, `s12`, `s13`.

External interface metadata binds each interface to its correct clock and
reset. The generator verifies the complete 16-plus-8 set and rejects missing,
duplicate, swapped, or extra data interfaces. No legacy detector, legacy 2SPC
RTL, TX MM2S DMA, event DMA, DDR data master, or GEM data plane is connected.

## 9. MTS and SYSREF proof boundary

This checkpoint verifies that:

- every required SYSREF/reference-clock/analogue interface is present;
- the configured ADC and DAC MTS groups cover the enabled tiles;
- the expected common fabric clock nets and synchronous reset trees exist; and
- Vivado reports no unsafe structural clock-domain crossing.

It does not verify that RFDC driver MTS calls succeed at runtime, that tile
latencies match on the board, or that SYSREF meets board-level electrical and
phase requirements. Machine evidence therefore contains separate
`mts_configuration_verified` and `mts_runtime_verified` values; the latter is
false for this checkpoint.

## 10. Provenance and evidence

Catalog provenance remains acyclic:

```text
architecture config -> discovery Tcl -> catalog request
                    -> Vivado catalog evidence -> candidate lock
                    -> explicit production promotion
```

In the production lock, `generated_tcl_sha256` continues to mean only the
discovery Tcl SHA-256. Adding or changing connected realization Tcl never makes
the catalog lock self-referential.

Connected-BD provenance is separate:

```text
architecture config SHA
model config SHA
PS platform config SHA
production lock SHA
connected request SHA
realization Tcl SHA
verification Tcl SHA
Vivado version and part
                  -> connected_rfdc_shell_evidence.json
```

The canonical evidence includes exact cell/VLNV sets, RFDC properties, the
24-interface inventory, clock and reset net memberships, address segments,
MTS configuration/runtime flags, validation result, generated report hashes,
and stable failure reasons. Duplicate JSON keys, unknown fields, noncanonical
encoding, stale hashes, partial evidence, and non-exact sets are rejected.

## 11. Readiness semantics

The connected checkpoint introduces an independent result:

```text
rfdc_shell_structural_ready
```

It is true only when the current production lock is valid, the connected
request and evidence hashes match, the exact topology and RFDC contract match,
`validate_bd_design` passes, synthesis completes, and CDC/clock checks contain
no unhandled unsafe result.

The existing results retain their meaning:

```text
responsibility_complete       = true
catalog_resolution_complete   = true
production_lock_valid         = true
production_integration_ready  = false
```

Structural shell readiness never implies overall production readiness. The
remaining pending algorithm, 2SPC, detector, DMA, status, and event owners keep
the latter false.

## 12. Verification gates

The checkpoint requires all of the following:

1. Python unit tests for types, strict parsing, generation, provenance,
   readiness, exact family and cell sets, and negative mismatches;
2. byte-identical root/package configuration and lock mirrors;
3. deterministic repeated generation;
4. real Vivado 2025.2 catalog discovery and explicit production promotion;
5. connected Tcl execution in a clean project;
6. exact RFDC, port, clock, reset, address, and MTS configuration readback;
7. `validate_bd_design` success;
8. wrapper/OOC synthesis success;
9. `report_cdc` with no unhandled critical or unsafe crossing;
10. clock-interaction and unconstrained-clock review;
11. a new acceptance artifact that states every unverified boundary.

Post-route timing closure, bitstream generation, MTS software execution,
analogue measurements, external range ratios, DMA, Ethernet, and board loopback
are subsequent gates and may not be inferred from this checkpoint.

## 13. Failure and recovery policy

- A failed or interrupted Vivado run produces no valid connected evidence.
- Invalid catalog evidence produces no candidate; invalid candidates are never
  promoted.
- Generated project artifacts are disposable and regenerated from authority.
- A failed common-clock design stops the checkpoint and preserves diagnostic
  reports. It does not silently insert CDC.
- No generated Tcl, metadata, lock, BD, or RTL is hand-edited.
- Each implementation batch has an isolated commit and focused regression.
- The previously accepted `model-update-20260811` branch remains unchanged.

## 14. Subsequent connected-BD sequence

After this shell is accepted, the project proceeds without redefining the
original end goal:

1. production 2SPC RX/TX Cycle models and generated RTL;
2. continuous dual-polar reflection chain;
3. monitor decimation, pulse detection, coarse PDW, and hit-IQ packetization;
4. AXI DMA S2MM and a single-HP0 event-to-DDR path;
5. GEM3 software event upload without continuous waveform upload;
6. post-route timing, MTS runtime, DAC-to-ADC loopback, and external range
   validation.
