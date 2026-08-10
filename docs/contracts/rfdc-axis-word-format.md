# RFDC ADC/DAC AXI Word Format Contract

Status: frozen at ModelConfig schema/config `8/11`, carried unchanged by the
current `9/16` authority, and tied to RF Data Converter IP
`xilinx.com:ip:usp_rf_data_converter:2.6`.

This is the only word-level authority allowed at the Golden/Cycle/Block Design
boundary. A different generated port width, data type, interface name or lane
order is an integration failure. RTL must not silently pad, truncate, swap or
pair data from a later clock.

## Target RFDC rates

| Path | Converter rate | RFDC rate change | PL AXI clock | Samples/clock |
|---|---:|---:|---:|---:|
| ADC | 4.000 GSPS real | DDC/decimation x8 | 250 MHz | 2 complex |
| DAC | 4.000 GSPS real | DUC/interpolation x8 | 250 MHz | 2 real |

The RFDC ADC output is 500 MSPS complex before the PL 2:1 decimator. The DAC
input is 500 MSPS real before RFDC interpolation.

## Dual RF-ADC stream identity

The XCZU27DR uses dual 4 GSPS RF-ADC tiles. In I/Q output mode, one physical
even converter route consumes two AXI streams: the even stream carries I and
the adjacent odd stream carries Q. Odd stream numbers are therefore **not**
additional physical ADC inputs.

| Logical ADC | Physical tile/slice | I stream | Q stream |
|---|---|---|---|
| ADC0 | 0/0 | `m00_axis` | `m01_axis` |
| ADC1 | 0/2 | `m02_axis` | `m03_axis` |
| ADC2 | 1/0 | `m10_axis` | `m11_axis` |
| ADC3 | 1/2 | `m12_axis` | `m13_axis` |
| ADC4 | 2/0 | `m20_axis` | `m21_axis` |
| ADC5 | 2/2 | `m22_axis` | `m23_axis` |
| ADC6 | 3/0 | `m30_axis` | `m31_axis` |
| ADC7 | 3/2 | `m32_axis` | `m33_axis` |

Every I or Q stream is 32 bits and contains two signed 16-bit components:

```text
component_tdata[15:0]  = component sample 0 (earlier)
component_tdata[31:16] = component sample 1 (later)
```

The ingress adapter combines matching I and Q beats from the same clock into:

```text
complex_tdata[15:0]  = I0
complex_tdata[31:16] = Q0
complex_tdata[47:32] = I1
complex_tdata[63:48] = Q1

MSB -> LSB spelling: {Q1, I1, Q0, I0}
```

Both component `TVALID` values must be asserted for the combined beat to be
valid. A mismatch drops that clock's beat and sets a sticky pairing error; it
must never re-align one component with the following clock.

## RF-DAC stream identity

All eight RF-DAC paths use real data:

```text
DAC0..DAC7 = s00_axis, s01_axis, s02_axis, s03_axis,
             s10_axis, s11_axis, s12_axis, s13_axis
```

Each stream is 32 bits:

```text
dac_tdata[15:0]  = signed real sample 0 (earlier)
dac_tdata[31:16] = signed real sample 1 (later)

MSB -> LSB spelling: {sample1, sample0}
```

The Golden reflection engine's complex-baseband DAC frame remains a
mathematical reference. Conversion to the real RFDC input word is a separate
TX waveform/DUC contract; no Cycle module may feed a Python complex value
directly to an RFDC AXI port.

## Evidence and current-design mismatch

- AMD PG269 defines configurable 16-bit AXI words, dual-ADC I/Q stream
  separation and the even-I/odd-Q convention.
- Vivado 2025.2 readback of the current `/rfdc` cell proves that the existing
  design is still ADC 125 MHz with 64-bit component streams and only ADC tiles
  0/1 enabled. Its DAC ports are 32-bit but only tile 1 is enabled.
- The generated RFDC wrapper independently labels `mXY_axis` as the stream for
  converter XY and shows the same current port widths.

Consequently the current Block Design is not accepted as the target 8 ADC / 8
DAC design. The later BD checkpoint must enable ADC tiles 0..3, DAC tiles 0..1,
set the target rates, and read back all 24 data interfaces before connection.

## Machine-readable authority and tests

`ModelConfig.rfdc_axis` owns interface names, widths, lane order and pack/unpack
helpers. Known-rail vectors include `-32768`, `-1`, `12345` and `32767` to
catch signedness, half-word swaps and sample-order reversals. The packaged and
source-tree `default.json` files must remain byte-identical.
