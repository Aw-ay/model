# Cycle 2SPC RFDC Ingress Contract

Status: implemented initial Cycle checkpoint for ModelConfig `9/16`.

## Clock and throughput

```text
clock                         250 MHz
physical ADC channels         8
complex samples/channel/clock 2
complex sample rate           500 MSPS/channel
registered latency            1 clock
input backpressure            forbidden / no ready port
```

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
Idle groups publish `rx_valid_o=0` and do not move the base.

All eight I-valid and eight Q-valid bits must be simultaneously zero (idle) or
simultaneously one (complete group). Any other pattern means cross-channel time
alignment can no longer be proven. The module then:

1. drops the partial group;
2. asserts sticky `format_error_o`;
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
indexing, idle holes, sticky error and reset recovery. Vivado 2025.2 compiles,
elaborates and simulates the generated module with the committed SystemVerilog
testbench.

This checkpoint does not yet implement the SPC2 fractional delay, 2x2
polarization matrix, multi-target accumulator, detector decimator, DMA/event
path or DAC packer, and it does not modify the existing Block Design.
