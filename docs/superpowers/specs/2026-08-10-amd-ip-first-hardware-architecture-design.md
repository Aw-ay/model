# AMD IP-First RFSoC Hardware Architecture Design

Date: 2026-08-10

Status: design review checkpoint

Source authority: `D:/AWAY/RFSOC/docs/review/ip使用.md`

## 1. Objective

Refactor the hardware implementation boundary so that AMD-provided converter,
AXI4-Stream, DSP, memory and DMA functions are instantiated as supported
Vivado IP or XPM macros. Project-owned logic is limited to behavior specific to
the dual-polarization active-reflection source.

The project retains three distinguishable truth layers, but the third layer no
longer means that every hardware function is reimplemented by the local Python
RTL DSL:

1. Golden is the mathematical and physical-algorithm truth.
2. Cycle is the transaction, fixed-point, scheduling and observable-latency
   truth at project-owned boundaries.
3. Hardware generation emits Vivado Block Design Tcl, exact AMD IP parameters,
   XPM/custom RTL integration and a reproducible architecture manifest.

AMD IP internals are external black boxes. A standard AMD IP does not require a
local cycle-exact reimplementation of its unpublished internal pipeline. It
does require a local boundary contract, declared latency/throughput behavior,
test vectors and vendor behavioral-simulation evidence.

## 2. Mandatory RF Data Converter Baseline

The RF converter is locked to the exact VLNV:

```text
xilinx.com:ip:usp_rf_data_converter:2.6
```

Vivado 2025.2 Block Design is the configuration authority for this IP. The IP
owns all of the following functions:

- RF-ADC and RF-DAC conversion;
- DDC and DUC;
- RFDC decimation and interpolation;
- RFDC mixer and NCO;
- RFDC-internal FIFO and converter timing behavior;
- analogue-output and Nyquist-zone implementation details.

Golden, Cycle, custom RTL and HLS must not reimplement or infer those internal
functions. The model owns only the PL-side digital contract:

- interface names and physical channel mapping;
- AXI4-Stream width and signed component format;
- I/Q and lane ordering;
- samples per cycle and sample-domain rate;
- valid/ready continuity expectations;
- PL clock, reset and acquisition-epoch boundaries;
- sticky fault behavior visible to project software.

A version other than `2.6`, a missing RFDC IP, or a generated port contract
that differs from the model is an integration failure. Upgrading the IP
requires an explicit architecture-config version change and renewed Vivado
readback, simulation, CDC, timing and board-loopback evidence.

## 3. Configuration Separation

Algorithm configuration and hardware-integration metadata must not share one
semantic object.

`ModelConfig` remains the algorithm/Cycle boundary authority. It may contain
rates that affect observable PL data and algorithms, such as 500 MSPS, 2 SPC,
detector decimation, channel maps and fixed-point input/output formats.

A new package-data file, `config/ip_architecture.json`, and immutable
`HardwareArchitectureConfig` own:

- Vivado version;
- exact RFDC 2.6 VLNV;
- required AMD IP families and their assigned responsibilities;
- RFDC mixer/NCO/analogue settings as integration metadata;
- AXIS topology policy;
- production/custom/legacy implementation classification;
- IP resolution and Vivado proof status.

The following fields move out of `RfdcAxisWordFormat` and into RFDC integration
metadata:

```text
dac_analog_output_type
dac_mixer_mode
dac_mixer_scale_mode
dac_nco_frequency_hz
```

`RfdcAxisWordFormat` retains only PL-observable word and interface properties.
Golden and project-owned Cycle hardware may depend on `ModelConfig` and the
PL-side word contract, but must not branch on RFDC mixer, NCO, Nyquist-zone or
analogue-output metadata.

## 4. AMD IP Ownership Matrix

The production implementation uses the following ownership policy.

| Function | Production owner | Project responsibility |
|---|---|---|
| ADC/DAC, DDC/DUC, mixer/NCO, RFDC rate change | RF Data Converter 2.6 | PL contract and validation |
| AXIS register/pipeline | AXIS Register Slice | topology and latency budget |
| AXIS buffering | AXIS Data FIFO | depth and fault policy |
| AXIS CDC | AXIS Clock Converter or Data FIFO CDC | source/destination clock contract |
| AXIS width conversion | AXIS Data Width Converter | component/lane contract |
| AXIS combine/broadcast/switch | AXIS Infrastructure IP | routing policy |
| 15-tap monitor FIR/DEC2 | FIR Compiler | coefficient/output contract |
| Fractional-delay FIR when coefficient scheduling permits | FIR Compiler | coefficient-bank scheduler |
| Integer-delay storage | XPM_MEMORY_SDPRAM or supported memory IP | pointers, addresses and epochs |
| Doppler phasor | DDS Compiler | phase increment and resync control |
| Complex calibration/scattering/Doppler multiply | Complex Multiplier | coefficient scheduling |
| Frequency-estimator atan2 when enabled | CORDIC | estimator sequencing |
| Event-to-DDR transport | AXI DMA S2MM | event framing and buffer ownership |

IP versions other than RFDC are resolved from the Vivado 2025.2 catalog during
generation. The resolved exact VLNV and configuration properties are recorded
in the build manifest; they are never guessed or hard-coded without catalog
evidence.

## 5. Project-Owned Hardware

Only domain-specific behavior remains custom RTL or HLS:

- RX acquisition-epoch and stream-integrity status;
- H/V `AUTO_HOLD` three-range selection;
- target scheduler and maximum-eight-target control;
- circular-delay address generation and lane scheduling;
- fractional-delay coefficient-set scheduling;
- multi-target output alignment and accumulation control;
- adaptive noise, threshold and N/M voting;
- TOA, contiguous-main-peak FWHM and coarse PDW state machines;
- hit-IQ/event framing, overflow/BIT/status and fault management;
- simple adders, muxes and counters when an IP would add no value.

Every project-owned production RTL/HLS block requires an executable Cycle
contract and Golden/Cycle or Cycle/RTL equivalence evidence as applicable.
AMD IP blocks instead require parameter-manifest checks and vendor behavioral
simulation against Golden/Cycle boundary vectors.

## 6. Cycle and Legacy DSL Policy

The current `cycle/dsl`, `RxGroupIngress2Spc` and `TxIqAxisBoundary2Spc` are not
deleted immediately. They become legacy/non-production once equivalent AMD IP
topology tests exist. This prevents losing the current known-good word-order,
epoch and underrun reference before the replacement is proven.

The migration sequence is:

1. add the IP architecture configuration, typed catalog and manifest;
2. add Tcl generation and structural tests for RFDC 2.6 and required AXIS IP;
3. replace production RX/TX transport with AMD AXIS IP plus thin custom
   epoch/status shims;
4. replace the monitor decimator with FIR Compiler and compare its behavioral
   simulation with the Golden FIR vectors;
5. migrate DDS, complex multiplication, memory and DMA in bounded batches;
6. remove a legacy generated-RTL module only after its replacement gate passes;
7. retire the general-purpose DSL from production after no production module
   depends on it.

The architecture manifest classifies every block as exactly one of:

```text
amd_ip
xpm_macro
custom_rtl
custom_hls
software_only
legacy_non_production
```

Unclassified or duplicate production ownership is rejected.

## 7. Generation Outputs

The hardware generator becomes an architecture generator and emits:

- `build/vivado/create_ip_architecture.tcl`;
- `build/metadata/ip_architecture.json`;
- `build/metadata/resolved_ip_vlnv.json` after Vivado catalog resolution;
- PL AXIS and custom-block interface manifests;
- fixed-point boundary formats and IP parameter snapshots;
- source/config/Tcl hashes;
- the remaining custom RTL/HLS source list.

Generated Tcl must create IP cells by VLNV, apply explicit property dictionaries
and connect named interfaces. It must not depend on GUI defaults for an
accepted build. RFDC must be requested by the exact 2.6 VLNV.

## 8. Error and Fail-Closed Policy

- An acquisition epoch starts once and cannot be paused. Deasserting enable
  terminates the epoch; restarting requires reset or an explicit new-epoch
  operation.
- After TX streaming starts, missing source continuity or loss of any required
  ready condition latches a fault and terminates that simulation epoch.
- AXIS/FIFO IP may absorb bounded timing variation but project logic never
  silently fabricates, reorders or resumes samples after an integrity fault.
- Unsupported IP, missing IP, wrong RFDC version, unresolved properties,
  unexpected port widths or unverified clock crossings fail generation or
  integration explicitly.

## 9. Verification Gates

### Python and configuration

- reject any RFDC VLNV other than `xilinx.com:ip:usp_rf_data_converter:2.6`;
- verify the packaged and source architecture-config mirrors are identical;
- verify RFDC-owned functions cannot also be registered as production custom
  blocks;
- verify changing RFDC mixer/NCO metadata does not change Golden output;
- verify all production blocks have one declared owner and test strategy.

### Generated architecture

- regenerate Tcl and metadata twice and require byte-identical output;
- parse Tcl tests for exact IP VLNV, explicit properties and required links;
- use Vivado 2025.2 `get_ipdefs` to resolve every requested IP;
- record the resolved exact versions and reject missing catalog entries.

### IP behavioral simulation

- FIR Compiler vectors must match the Golden 15-tap/DEC2 output contract;
- DDS and Complex Multiplier vectors must match fixed-point boundary vectors;
- AXIS topology tests must preserve I/Q lane order, 2SPC time order and channel
  identity under ready/valid activity;
- custom state machines retain cycle/bit equivalence with generated RTL/HLS.

### Vivado and hardware

The following remain distinct mandatory gates and are not implied by Python or
XSIM success:

- RFDC property and port-width readback;
- `validate_bd_design` and address validation;
- `report_cdc` and reset-release review;
- OOC and full implementation timing;
- RFDC MTS/SYSREF evidence;
- DAC-to-ADC loopback and external RF/channel calibration.

## 10. Scope of the First Implementation Plan

The first implementation plan covers only the safe architectural foundation:

1. typed IP architecture configuration and exact RFDC 2.6 gate;
2. separation of RFDC integration metadata from PL/algorithm contracts;
3. block ownership registry and production/legacy classification;
4. reproducible IP/Tcl manifest generation;
5. initial RFDC/AXIS/FIR Compiler Tcl skeleton and structural tests;
6. documentation of the legacy DSL migration boundary.

It does not delete the legacy DSL, replace every data-path block, edit the live
Block Design in place, claim timing closure or claim board-level validation.

## 11. Design Decisions

- RF Data Converter is locked to version 2.6, not merely an IP family.
- AMD IP/XPM is preferred for standard transport, DSP, memory and DMA.
- Project logic owns scheduling, state, target semantics and event semantics.
- Low-rate physical calculations remain in PS/host software and compile into
  fixed-point PL parameters.
- Migration is replacement-gated; no working reference is deleted first.
- The independent `model` project remains the architecture authority.

