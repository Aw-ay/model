# Frozen Engineering Decisions

## Numeric and Sampling Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| Project rounding | nearest, ties away from zero | [ModelConfig](../../config/default.json), [fixed-point contract](../contracts/fixed-point-widths.md) | Every fractional-bit reduction and Golden boundary uses one rounding rule. |
| ADC code boundary | signed 16-bit, Q0, unit `adc_code` | [ModelConfig](../../config/default.json) | No implicit fractional scaling or integer wrap is allowed. |
| Power boundary | unsigned 32-bit, Q0, unit `adc_code_squared` | [ModelConfig](../../config/default.json) | Detector thresholds and PDW powers use the same declared unit. |
| Clipping | explicit per-sample sideband; signed rails are `+32767` and `-32768` when inferred | [Golden/common tests](../../tests/golden/test_common.py), [receive tests](../../tests/golden/test_receive.py) | `-32767` is not a clipped rail and FIR propagation OR-reduces real clipping history. |
| FWHM | contiguous region around the main peak above `max(half_peak, threshold)` | [detector tests](../../tests/golden/test_detector.py) | Disconnected above-half-height lobes cannot extend pulse width. |
| Reflection domain | 500 MSPS `RFDC_COMPLEX_INPUT` | [ModelConfig](../../config/default.json) | Target delays, Doppler, reflection frames, and fixed delay share this domain. |
| Detector domain | 250 MSPS `DETECTOR`, 4 ns/sample | [ModelConfig](../../config/default.json) | Hardware fields remain in samples; host converts units with configuration. |
| Detector source mapping | `source_sample_index = 7 + 2 * detector_sample_index` | [ModelConfig](../../config/default.json) | Detector ToA maps to the FIR centre in the absolute RFDC sample axis. |
| Public fixed internal delay | measured ADC-complex-input to DAC-baseband-output latency at 500 MSPS | [fixed-delay contract](../contracts/fixed-internal-delay.md) | The Golden test value is not a measured board value and must not enter a deployment manifest. |
| Fractional FIR centre | `(63 - 1) / 2 = 31` internal samples | [fixed-delay contract](../contracts/fixed-internal-delay.md) | The 31-sample centre is cropped/absorbed internally and is never added again as public delay. |

## RFDC and AXI Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| RFDC identity | `xilinx.com:ip:usp_rf_data_converter:2.6`, instance `rfdc_0` | [architecture config](../../config/ip_architecture.json), [production lock](../../config/ip_lock.json) | No second RFDC identity or wildcard production selection is allowed. |
| Converter rates | ADC and DAC 4.000 GSPS | [ModelConfig](../../config/default.json) | RFDC DDC/DUC rate changes and fabric widths must preserve the sample equations. |
| RFDC rate changes | ADC decimation ×8; DAC interpolation ×8 | [ModelConfig](../../config/default.json) | PL sees a 500 MSPS complex envelope on both directions. |
| RF data clock | 250 MHz, two complex samples per beat | [RFDC word contract](../contracts/rfdc-axis-word-format.md) | RF data must not be moved into the 100 MHz control domain. |
| ADC AXIS format | 16 I/Q component streams, each 32-bit `{sample1,sample0}` signed-I16 | [RFDC word contract](../contracts/rfdc-axis-word-format.md) | Even stream is I and adjacent odd stream is Q for each physical dual ADC route. |
| Internal complex packing | 64-bit `{Q1,I1,Q0,I0}` from MSB to LSB | [RFDC word contract](../contracts/rfdc-axis-word-format.md) | Pair only same-cycle I/Q beats; do not repair gaps with later data. |
| DAC AXIS format | 8 streams, each 64-bit `{Q1,I1,Q0,I0}` | [RFDC word contract](../contracts/rfdc-axis-word-format.md) | Each logical DAC consumes its own complex-IQ stream before RFDC I/Q-to-real mixing. |
| RF translation | fine mixer I/Q-to-real, NCO 2.8 GHz, unity scale | [architecture config](../../config/ip_architecture.json) | PL preserves complex envelope phase; RFDC owns carrier translation. |
| Control clock | PS `pl_clk0=100 MHz` | [PS platform config](../../config/ps_platform.json) | AXI-Lite control is isolated from RX/TX 250 MHz sample domains. |

## Polarimetric and Range Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| Polarization order | index 0 = H, index 1 = V | [polarimetric design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md) | All 2x2 matrices and H/V frames use one order. |
| Scattering matrix | `[[HH, HV], [VH, VV]]`, row = receive/output, column = transmit/input | [polarimetric design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md) | H-only and V-only tests must distinguish cross-polar terms. |
| Echo ranges | independent H/V high, mid, low with nominal +20/0/-20 dB | [physical channel contract](../contracts/zu27dr-v2.1-physical-channel-map.md) | Association never mixes polarizations; select highest-gain unsaturated path. |
| Reference channels | ADC3 = H reference, ADC7 = V reference | [physical channel contract](../contracts/zu27dr-v2.1-physical-channel-map.md) | Reference inputs are excluded from ordinary echo range selection. |
| Echo DAC routing | V to DAC0/2/4; H to DAC1/3/5 | [physical channel contract](../contracts/zu27dr-v2.1-physical-channel-map.md) | Three paths receive the same logical envelope before per-channel calibration and external gain. |
| Calibration/cancellation DACs | DAC6 = V, DAC7 = H | [physical channel contract](../contracts/zu27dr-v2.1-physical-channel-map.md) | Mode must explicitly choose calibration, supplied cancellation, or zero. |
| Doppler sign | positive radial velocity means receding; monostatic Doppler is negative | [polarimetric design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md) | Chunked processing uses the same global absolute phase convention. |
| Continuous main chain | detector-independent, 500 MSPS complex | [polarimetric design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md) | Pulse detection cannot gate, schedule, or alter reflection samples. |

## Model-to-RTL Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| Layer direction | Golden → Cycle → generated Verilog | [handoff design](../superpowers/specs/2026-08-17-project-handoff-design.md) | Golden does not directly emit RTL and generated RTL is not hand-edited. |
| Cycle structure | explicit fixed-width `compute()` and `clock()` semantics | [project README](../../README.md) | Registers, valid timing, RAM behavior, overflow and latency are hardware truth. |
| Hardware leaf rule | every Cycle hardware model emits Verilog; exceptions are explicitly software-only | [project README](../../README.md) | Missing emitter coverage is a build/registry failure, not documentation debt. |
| Production source isolation | `build/rtl` production-only; legacy reference under `build/reference_rtl` | [AMD IP ownership contract](../contracts/amd-ip-ownership.md) | Legacy 2SPC RTL cannot fulfil production responsibilities or readiness. |
| Numeric overflow | `error`, `saturate`, or `wrap` only at named formats | [fixed-point contract](../contracts/fixed-point-widths.md) | Silent truncation of lossless intermediates is forbidden. |

## Block Design and IP Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| Architecture identities | family, instance, block, responsibility, and legacy reference are distinct | [architecture design](../superpowers/specs/2026-08-11-ip-architecture-normalization-design.md) | Catalog availability does not create a BD cell or production owner. |
| Ownership completeness | every production responsibility has exactly one non-legacy owner | [AMD IP ownership contract](../contracts/amd-ip-ownership.md) | Completeness may be true while production integration remains false. |
| Production lock | exact required family set and strongly bound discovery provenance | [production lock](../../config/ip_lock.json) | Missing, extra, wildcard, stale, or identity-mismatched families fail closed. |
| Discovery provenance | `generated_tcl_sha256` always means discovery Tcl | [architecture design](../superpowers/specs/2026-08-11-ip-architecture-normalization-design.md) | Realization Tcl changes do not make the catalog lock self-referential. |
| Connected shell | exact-part disk project, declared cells only, generated Tcl only | [connected-shell design](../superpowers/specs/2026-08-13-connected-rfdc-shell-design.md) | Manual BD/Tcl edits and BD automation-inserted undeclared cells are invalid. |
| Reset release | separate control/RX/TX reset controllers and explicit active-high clock-stable qualifications | [connected-shell design](../superpowers/specs/2026-08-13-connected-rfdc-shell-design.md) | A reset synchronized in one domain cannot be reused in another. |

## Event and Software Contracts

| Decision | Frozen value | Authority | Consequence |
|---|---|---|---|
| Upload policy | coarse PDW plus hit-IQ windows only | [stream/PDW contract](../contracts/stream-status-online-pdw.md) | Continuous background waveform upload is outside the product contract. |
| Online delivery | stable global order, exactly once, never closed by a chunk boundary | [stream/PDW contract](../contracts/stream-status-online-pdw.md) | Cycle needs bounded state, queues, and explicit overflow reporting. |
| RFDC input behavior | continuous source, no detector backpressure | [connected-shell design](../superpowers/specs/2026-08-13-connected-rfdc-shell-design.md) | Congestion sets drop/overflow status instead of stalling the converter. |
| Hardware fields | sample counts and configuration words, not fixed ns/Hz constants | [ModelConfig](../../config/default.json) | Host converts physical units using sample-rate and NCO configuration. |

## Pending Responsibilities

| Responsibility | Current status | Required evidence before acceptance |
|---|---|---|
| Production RX/TX 2SPC boundaries | architecture pending | Cycle structure, generated RTL, bit/cycle equivalence, continuous-stream fault semantics |
| Continuous reflection Cycle path | architecture pending | fixed widths, bounded delay memory, scheduling, throughput and equivalence |
| Monitor event hardware | planned/pending | FIR/detector/refinement/event queues, no-backpressure proof and overflow tests |
| Connected RFDC shell | Task 5 blocked | real report grammar, authoritative MTS properties, clean/unsafe differential evidence and independent review |
| GEM3 board I/O | pending fail-closed | board-authoritative PHY address, reset ownership/timing, RGMII delay/link mode and enabled PS binding |
| DMA and Ethernet event transport | pending | S2MM/DDR ring, packet protocol, loss accounting and software validation |
| CDC and timing | pending | synthesized and implemented reports without broad waivers |
| MTS runtime and board RF behavior | pending | driver/runtime success, measured latency, loopback, H/V mapping, range ratios and stability |
