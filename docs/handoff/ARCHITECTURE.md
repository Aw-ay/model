# System Architecture

## Mission and Data Policy

The target system transmits and receives complex-baseband signals around a 2.8 GHz RF carrier on a ZU27DR RFSoC. It models a continuous dual-polarization active reflection source while retaining pulse detection as an independent monitor branch.

The production data policy is event-only upload: retain and transfer hit IQ windows plus coarse PDW metadata. Continuous background IQ is not a host-upload product. The monitor branch may observe the stream, but detector thresholds, missed events, or PDW activity must never move, block, or alter the continuous reflection samples.

Primary authorities are [ModelConfig](../../config/default.json), the [physical channel contract](../contracts/zu27dr-v2.1-physical-channel-map.md), and the [polarimetric design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md).

## Physical 8-ADC / 8-DAC Mapping

All eight RF-ADC converters and all eight RF-DAC converters leave the device package. The project role mapping is:

| Logical ADC | RFDC tile/slice | Polarization/range | Role |
|---|---|---|---|
| ADC0 | 0/0 | H +20 dB | echo |
| ADC1 | 0/2 | H 0 dB | echo |
| ADC2 | 1/0 | H -20 dB | echo |
| ADC3 | 1/2 | H reference | calibration |
| ADC4 | 2/0 | V +20 dB | echo |
| ADC5 | 2/2 | V 0 dB | echo |
| ADC6 | 3/0 | V -20 dB | echo |
| ADC7 | 3/2 | V reference | calibration |

| Logical DAC | RFDC tile/slice | Polarization/range | Role |
|---|---|---|---|
| DAC0 | 0/0 | V +20 dB | echo |
| DAC1 | 0/1 | H +20 dB | echo |
| DAC2 | 0/2 | V 0 dB | echo |
| DAC3 | 0/3 | H 0 dB | echo |
| DAC4 | 1/0 | V -20 dB | echo |
| DAC5 | 1/1 | H -20 dB | echo |
| DAC6 | 1/2 | V reference | calibration or active cancellation |
| DAC7 | 1/3 | H reference | calibration or active cancellation |

The +20/0/-20 dB values are nominal external analogue voltage gains. Digital processing consumes the channel map and calibration response; it does not infer measured gain from the enum alone. Schematic escape does not prove mezzanine population, cable identity, H/V labelling, or measured range ratios. Those remain board-acceptance gates.

## Sampling and Clock Domains

The current [RFDC AXI word contract](../contracts/rfdc-axis-word-format.md) defines:

```text
RF-ADC converter rate       4.000 GSPS real
RFDC DDC/decimation        x8
RFDC complex output        500 MSPS
RFDC AXI clock             250 MHz
RFDC complex samples/beat  2
PL monitor decimation      2:1
detector sample rate       250 MSPS
detector sample period     4 ns
source index mapping       7 + 2 * detector_sample_index

RF-DAC converter rate      4.000 GSPS real analogue
RFDC DUC/interpolation     x8
RFDC complex input         500 MSPS
RFDC AXI clock             250 MHz
RFDC complex samples/beat  2
fine-mixer NCO             2.8 GHz, I/Q to real
```

The continuous reflection path remains in `RFDC_COMPLEX_INPUT` at 500 MSPS. The detector branch uses `DETECTOR` at 250 MSPS after PL FIR decimation. Neither domain may reuse the other's sample index without the configured mapping.

PS `pl_clk0=100 MHz` is the low-bandwidth AXI-Lite control clock. It does not clock RF sample data. Candidate RX and TX AXI domains are separate 250 MHz RFDC clocks. Common-clock legality, synchronous reset release, MTS, SYSREF, and inter-tile phase alignment require independent Vivado and runtime proof.

## Golden -> Cycle -> Generated Verilog

The project uses a one-way authority chain:

```text
Golden Model
  mathematical algorithm truth, floating point, arrays, no timing/backpressure
        |
        v
Cycle Model
  fixed width, cycle/valid/state/RAM semantics, compute()/clock() structure
        |
        v
Generated Verilog
  structural emission from Cycle only; generated RTL is never hand-edited
```

Golden-to-Cycle checks compare algorithm semantics after declared latency and quantization. Cycle-to-Verilog checks compare valid-cycle bits and state behavior. A Cycle hardware model must emit Verilog or be explicitly classified as software-only.

The current 2SPC ingress and egress RTL are legacy reference artifacts, not production owners. Production 2SPC boundaries and the full continuous reflection Cycle implementation remain pending in [the AMD IP ownership contract](../contracts/amd-ip-ownership.md).

## Polarimetric Reflection Chain

The ordered production semantic chain is:

```text
8-channel continuous 2SPC ingress
  -> ADC channel alignment and residual calibration
  -> independent H/V three-range selection
  -> continuous absolute sample-time integrity
  -> integer and fractional target delay
  -> range/RCS complex gain
  -> 2x2 polarimetric scattering
  -> Doppler phase and complex modulation
  -> multi-target alignment and accumulation
  -> TX polarization predistortion
  -> eight-channel DAC routing
  -> signed-I16 quantization
  -> continuous 2SPC egress
```

Golden uses a 63-tap fractional-delay reference, causal zero fill, global absolute-sample Doppler phase, calibrated 2x2 complex matrices, and at most eight targets. The symmetric filter centre is 31 samples, but it is an internal coordinate rather than a public extra delay. The deployed common pipeline delay must be measured and carried once as `FixedInternalDelay`.

## Monitor Pulse Event Chain

The monitor side branch consumes the six H/V echo-range channels and excludes the two reference channels from ordinary range association. Its intended processing is:

```text
500 MSPS complex echo streams
  -> Q17 15-tap PL FIR decimator by 2
  -> 250 MSPS I^2 + Q^2 power
  -> boot/adaptive noise estimate and threshold
  -> moving average and 3-of-5 vote
  -> coarse start/stop/peak
  -> contiguous-main-peak half-height refinement
  -> coarse frequency, PDW, and hit-IQ framing
  -> event queue and DMA
```

Range association occurs only within one polarization. The preferred range is the highest-gain unsaturated observation. Stream delivery emits only stable, globally ordered records; a chunk boundary cannot close a pulse artificially. Queue overflow or dropped events must be explicit and must not backpressure the continuous RFDC source.

## AMD IP and Connected Block Design

[HardwareArchitectureConfig](../../config/ip_architecture.json) separates IP family, IP instance, architecture block, production responsibility, and legacy reference responsibility. The exact production catalog is locked by [ip_lock.json](../../config/ip_lock.json). RF Data Converter is the black-box family `xilinx.com:ip:usp_rf_data_converter:2.6` and the single integration instance is `rfdc_0`.

The connected-shell checkpoint materializes PS 3.5, SmartConnect, three reset controllers, reset inversion, interrupt concatenation, and RFDC. It externalizes 16 ADC component AXIS interfaces, 8 DAC complex AXIS interfaces, reference clocks, SYSREF, and RF analogue interfaces. It intentionally excludes detector, production 2SPC, reflection processing, DMA, DDR event masters, and GEM3 data-plane cells.

[PsPlatformConfig](../../config/ps_platform.json) owns the reviewed PS property allowlist and the 100 MHz control clock. GEM3 board I/O remains fail-closed because the hashed legacy BD disables ENET3/MDIO and does not constitute an enabled-board authority.

## Software and Network Boundary

AMD RFDC, DMA, DDR, Ethernet, and asynchronous FIFO components are integrated as black boxes rather than reimplemented by the Python RTL generator. The intended transport is pulse-event S2MM DMA to DDR followed by GEM3 software upload of PDW and hit-IQ records.

No continuous waveform upload is permitted by the product data policy. Packet framing, DMA rings, Ethernet software, packet loss accounting, and host storage/display are future gates and cannot be inferred from the current connected RFDC shell work.

## Validation Layers

| Layer | What it can prove | What it cannot prove |
|---|---|---|
| Golden tests | mathematical detection/reflection semantics and physical units | widths, cycle timing, AXI, CDC, hardware |
| Cycle tests | fixed-point, state, throughput, valid and overflow semantics | emitted RTL equivalence unless compared |
| Generated RTL/XSIM | bit/cycle equivalence for emitted modules | BD inference, timing, board behavior |
| RFDC/IP probe | exact tool-visible properties, ports, widths and diagnostics | connected shell synthesis or runtime MTS |
| Connected BD validation/synthesis | topology, address, reset/clock membership and synthesized reports | post-route timing, runtime software, analogue behavior |
| Implementation and runtime | placed/routed timing, CDC review, MTS calls, DMA/Ethernet | external RF mapping unless measured |
| Board acceptance | continuity, H/V/range ratios, loopback and stability | future hardware revisions without revalidation |

`production_integration_ready` stays false until every required production owner and all downstream gates are accepted. Responsibility completeness and catalog completeness are necessary but not sufficient.
