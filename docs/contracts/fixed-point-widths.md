# Fixed-Point Width Contract

Status: frozen for ModelConfig schema/config `9/16`.

`ModelConfig.numeric_formats` is the single machine-readable authority. The
two installed JSON copies must remain byte-identical, and the loader rejects a
missing, extra or changed format. `sN.QF` means signed width `N` with `F`
fractional bits; `uN.QF` is unsigned.

## RFDC, decimator and detector

| Node | Format | Overflow | Reason |
| --- | --- | --- | --- |
| ADC component | s16.Q0 | error | RFDC interface code |
| FIR coefficient | s18.Q17 | error | shared 15-tap Q17 table |
| FIR product | s34.Q17 | error | 16 + 18 bits |
| FIR accumulator | s38.Q17 | error | product plus ceil(log2(15)) |
| FIR output | s16.Q0 | saturate | rounded detector IQ boundary |
| one I/Q square | u31.Q0 | error | maximum is 32768 squared |
| I squared + Q squared | u32.Q0 | error | exact power |
| 8-sample moving sum | u35.Q0 | error | power plus 3 bits |
| 16384-sample boot sum | u46.Q0 | error | power plus 14 bits |
| noise estimate | u32.Q0 | saturate | adaptive state boundary |
| threshold scale | u32.Q16 | error | code 905413 for -ln(1e-6) |
| threshold product | u64.Q16 | error | full multiply intermediate |
| threshold | u32.Q0 | saturate | rounded power-domain threshold |
| 5-sample vote population | u3.Q0 | error | represents 0 through 5 |

## PDW, event and addressing

| Node | Format | Overflow |
| --- | --- | --- |
| absolute sample index / ToA | u64.Q0 | error |
| pulse width and IQ count | u32.Q0 | error |
| range ID / selected range | u2.Q0 | error |
| physical channel index | u3.Q0 | error |
| polarization | u1.Q0 | error |
| event ID | u32.Q0 | wrap |
| eight-channel mask | u8.Q0 | error |
| flags | u16.Q0 | error |
| signed frequency word | s32.Q31 | saturate |
| config version | u32.Q0 | error |
| target count | u4.Q0 | error |
| integer target delay | u21.Q0 | error |
| fractional target delay | u18.Q17 | error |

The 21-bit delay field intentionally represents the configured inclusive
maximum of 1,048,576 samples. If the RAM contract later changes to a depth with
exclusive upper bound, both the capacity and this width must change together.

## Dual-polarization reflection path

| Node | Format | Overflow | Derivation |
| --- | --- | --- | --- |
| common reflection component | s24.Q4 | saturate | 40 dB range span plus headroom |
| fractional-delay coefficient | s18.Q17 | error | 63-tap coefficient |
| fractional-delay product | s42.Q21 | error | 24 + 18 bits |
| 63-tap fractional accumulator | s48.Q21 | error | product plus 6 bits |
| calibration/matrix coefficient | s24.Q20 | saturate | component range approximately -8 to +8 |
| calibration product | s48.Q24 | error | 24 + 24 bits |
| 2x2 complex matrix accumulator | s50.Q24 | error | complex add plus two-input sum |
| target/scattering coefficient | s32.Q20 | saturate | component range approximately -2048 to +2048 |
| target product | s56.Q24 | error | sample times target coefficient |
| eight-target accumulator | s61.Q24 | error | complex/polarization adds plus 3 target bits |

The `s24.Q4` reflection boundary spans -524288 through 524287.9375 in the
common ADC-code-equivalent scale. An ideal -20 dB receive path reaches about
327680 at ADC full scale, leaving about 4 dB numerical headroom. Accepted
calibration or scenario values can still exceed a saturating coefficient or
sample boundary; Cycle must raise a sticky numeric-overflow status and
equivalence vectors must distinguish representable from deliberate saturation
cases. Golden remains floating-point and does not silently redefine this
fixed-point boundary.

## NCO, TX and DAC

| Node | Format | Overflow |
| --- | --- | --- |
| phase accumulator | u32.Q32 turns | wrap |
| signed phase increment | s32.Q31 turns/sample | wrap |
| NCO phasor component | s18.Q17 | saturate |
| reflection x phasor product | s42.Q21 | error |
| complex NCO result | s43.Q21 | error |
| sine LUT | s16.Q15 | saturate |
| TX amplitude | u16.Q15 | saturate |
| TX scale product | s32.Q30 | error |
| RFDC DAC sample | s16.Q0 | saturate |

## Arithmetic rules

- Every fractional-bit reduction rounds to nearest, ties away from zero.
- `error` is mandatory for an intermediate designed to be lossless; Cycle
  simulation raises on overflow and generated RTL must prove the range or set
  an assertion/status rather than silently truncate.
- `saturate` is allowed only at the named quantization/state boundaries.
- `wrap` is allowed only for phase modulo arithmetic and event-ID rollover.
- Complex multiplication uses full real products before the declared add;
  truncation between partial products is forbidden.

This checkpoint freezes formats, not implementation success. Cycle arithmetic,
per-cycle overflow signaling and Golden-to-fixed equivalence remain separate
verification gates.
