# RFDC ADC/DAC AXI Word Format Contract

Status: ADC layout frozen at ModelConfig schema/config `8/11`, armed ingress
semantics added at `11/17`, DAC I/Q-to-real layout frozen at `12/18`, and tied to RF Data Converter IP
`xilinx.com:ip:usp_rf_data_converter:2.6`.

This is the only word-level authority allowed at the Golden/Cycle/Block Design
boundary. A different generated port width, data type, interface name or lane
order is an integration failure. RTL must not silently pad, truncate, swap or
pair data from a later clock.

## Target RFDC rates

| Path | Converter rate | RFDC rate change | PL AXI clock | Samples/clock |
|---|---:|---:|---:|---:|
| ADC | 4.000 GSPS real | DDC/decimation x8 | 250 MHz | 2 complex |
| DAC | 4.000 GSPS real analogue | DUC/interpolation x8 plus fine mixer | 250 MHz | 2 complex I/Q |

The RFDC ADC output is 500 MSPS complex before the PL 2:1 decimator. The DAC
PL input is 500 MSPS complex before RFDC interpolation and I/Q-to-real mixing.

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

Before acquisition is enabled, startup `TVALID` patterns are ignored. After
enable, every I/Q stream for all eight ADC channels must be valid on every
clock. An all-idle clock is a sticky stream-gap error and a partial pattern is a
sticky format error; either condition fails closed and must never be repaired
by pairing data from a later clock.

The eight-channel single-clock adapter additionally requires a proven common
`m0_axis_aclk` through `m3_axis_aclk` network and synchronous reset/MTS release.
That clock proof is separate from this word-layout contract.

## RF-DAC stream identity

All eight RF-DAC paths use complex I/Q PL input data and independent real
analogue output:

```text
DAC0..DAC7 = s00_axis, s01_axis, s02_axis, s03_axis,
             s10_axis, s11_axis, s12_axis, s13_axis
```

Each stream is 64 bits and contains two signed-I16/Q16 samples:

```text
dac_tdata[15:0]  = I0 (earlier)
dac_tdata[31:16] = Q0 (earlier)
dac_tdata[47:32] = I1 (later)
dac_tdata[63:48] = Q1 (later)

MSB -> LSB spelling: {Q1, I1, Q0, I0}
```

The Golden reflection engine keeps the mathematical complex envelope and
rounds I and Q independently to signed 16-bit codes using project-wide
ties-away-from-zero rounding and saturation. Cycle receives only those fixed
I/Q codes; it packs them into the word above and never feeds a Python complex
value to an RFDC port.

The RFDC fine mixer contract is `I/Q -> real`, NCO frequency 2.8 GHz and
manual unity (`0 dB`) mixer scaling. RFDC is therefore responsible for RF
carrier translation; PL preserves the complex envelope, including scattering
phase and Doppler. This does not configure two physical DACs as an analogue
I/Q pair: `s00_axis` through `s13_axis` still map one-to-one onto DAC0..DAC7.

The single-clock Cycle boundary assumes both DAC tiles use one common 250 MHz
PL clock plus MTS/SYSREF phase synchronization. The configuration records this
architecture but its proof status remains `unverified`; only RFDC property
readback, clock/reset inspection and Vivado CDC/timing reports may change that
status to `vivado_verified`. A per-tile-clock design requires explicit CDC and
must not instantiate this boundary.

RF-DAC `TVALID` is not used by the converter core to suppress invalid data.
The generated boundary drives `TVALID=1` after reset, waits for all eight
`TREADY` signals before starting, advances all channels atomically and drives
zero with sticky `underrun` if ready or source data disappears after start.
It cannot silently resume until disabled and explicitly cleared.

## Evidence and current-design mismatch

- AMD PG269 defines configurable 16-bit AXI words, dual-ADC I/Q stream
  separation and the even-I/odd-Q convention.
- Vivado 2025.2 readback/current Tcl shows the existing design still uses a
  partial ADC setup and 32-bit real DAC inputs. That is incompatible with the
  64-bit complex-I/Q PL input frozen here.
- The generated RFDC wrapper independently labels `mXY_axis` as the stream for
  converter XY and shows the same current port widths.

Consequently the current Block Design is not accepted as the target 8 ADC / 8
DAC design. The later BD checkpoint must enable ADC tiles 0..3, DAC tiles 0..1,
set the target rates and DAC I/Q-to-real mixer mode, and read back all 24 data
interfaces before connection.

## Machine-readable authority and tests

`ModelConfig.rfdc_axis` owns interface names, widths, lane order and pack/unpack
helpers. Known-rail vectors include `-32768`, `-1`, `12345` and `32767` to
catch signedness, half-word swaps and sample-order reversals. The packaged and
source-tree `default.json` files must remain byte-identical.
