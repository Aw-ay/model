# Cycle 2SPC RFDC Ingress Contract

Status: implemented armed fail-closed Cycle checkpoint for ModelConfig `11/17`.

## Clock and throughput

```text
clock                         250 MHz
physical ADC channels         8
complex samples/channel/clock 2
complex sample rate           500 MSPS/channel
registered latency            1 clock
input backpressure            forbidden / no ready port
```

The single `clk_i` architecture is legal only when Vivado proves that
`m0_axis_aclk` through `m3_axis_aclk` are the same physical 250 MHz clock
network, use one synchronously released reset system, and the configured MTS
group is complete. Equal configured frequencies are not sufficient evidence.

`ModelConfig.rfdc_adc_clocking_mode` freezes the intended architecture as
`common_pl_clock_mts`. Its proof status remains `unverified` until RFDC property
readback, clock-net inspection and CDC reporting have all passed. Generated
metadata therefore publishes
`single_clock_ingress_integration_ready=false`. If the common-clock condition
cannot be proven, the design must select `per_tile_cdc` and use a different
four-ingress plus CDC/alignment architecture; `RxGroupIngress2Spc` rejects that
configuration.

Each channel still follows the frozen RFDC word contract:

```text
I_word[15:0]  = I lane0 (earlier sample)
I_word[31:16] = I lane1 (later sample)
Q_word[15:0]  = Q lane0
Q_word[31:16] = Q lane1
```

The Cycle module flattens channel 0 into the least-significant 32 input bits.
Its four 128-bit lane outputs similarly place channel 0 in bits `[15:0]` and
channel 7 in bits `[127:112]`.

## Time axis and valid policy

`sample_base_index_o` is the absolute `RFDC_COMPLEX_INPUT` index of lane0.
For complete valid groups it produces `0, 2, 4, ...`; lane1 is base plus one.

While `acquisition_enable_i=0`, every RFDC valid pattern is ignored. This is
the only state in which an all-idle group or startup partial-valid pattern is
legal. Control logic may assert `acquisition_enable_i` only after all RFDC
tiles, common clocks, resets and MTS status are ready. The enable must stay high
for the acquisition and a reset is required before beginning another one.

Once enabled, all eight I-valid and eight Q-valid bits must be simultaneously
one on every clock. A complete group asserts `rx_valid_o`, advances the sample
counter by two and makes `stream_active_o` sticky-high while the acquisition is
healthy.

An enabled all-idle group is a missing physical RFDC beat. It drops the group,
asserts sticky `gap_error_o`, clears `stream_active_o` and blocks every later
group until reset. An enabled partial-valid pattern follows the same fail-closed
policy but asserts sticky `format_error_o`. The sample counter does not advance
on either fault, and because later groups cannot be accepted the implementation
cannot silently compress the physical timeline.

The fault sequence is therefore:

1. drops the idle or partial group;
2. classifies it as `gap_error_o` or `format_error_o`;
3. stops publishing later groups;
4. requires reset to restart the absolute index at zero.

This is intentionally fail-closed. Fabric logic must never invent a continuous
timeline after an RFDC stream-alignment failure.

## Single structural source

`RxGroupIngress2Spc.compute()` defines only combinational next-state logic and
`clock()` defines registered updates. `VerilogEmitter` emits those exact
assignments as `always @(*)` and `always @(posedge clk_i)` blocks. The generated
file is registered as `rx_group_ingress_2spc.v`; generation rejects any
unregistered `.v` in its output directory.

The generated RTL is local build output. The committed sources are the Cycle
class, restricted DSL, emitter, tests and generator; RTL must be regenerated.

## Verification boundary

Python Cycle tests cover signed-rail lane order, one-cycle latency, absolute
indexing, pre-arm startup patterns, enabled idle-gap failure, partial-valid
failure, sticky errors and reset recovery. Vivado 2025.2 compiles, elaborates
and simulates the generated module with the committed SystemVerilog testbench.

This is model/RTL verification only. Until the clock proof status is changed by
an evidence-producing Vivado check, the generated manifest deliberately marks
the single-clock ingress as not ready for Block Design integration.

This checkpoint does not yet implement the SPC2 fractional delay, 2x2
polarization matrix, multi-target accumulator, detector decimator, DMA/event
path or DAC packer, and it does not modify the existing Block Design.
