# ZU27DR v2.1 Physical Channel Mapping Contract

Status: originally frozen at ModelConfig schema/config `7/10`; carried
unchanged by the current `9/16` authority.

This contract separates two kinds of evidence:

- `RFDC -> package bank -> carrier endpoint` is taken from page 9 of
  `D:\AWAY\RFSOC\save_v2.1\XCZU27DR-v2.1.pdf`.
- `carrier endpoint -> polarization/range/role` is the project wiring
  contract. The ADC contract follows the approved dual-polarization plan; the
  DAC contract follows the explicitly approved DAC0..7 assignment.

The carrier schematic proves that all eight RFADC converters and all eight
RFDAC converters leave the XCZU27DR package. It does not prove that the J4
mezzanine, cables or external +20/0/-20 dB analogue paths are populated and
wired according to the project-role columns. Board acceptance must therefore
perform continuity and low-power tone checks before enabling normal RF power.

## ADC mapping

| Logical | RFDC tile/slice | Bank/net | Carrier endpoint | Project role |
|---|---|---|---|---|
| ADC0 | 0/0 | 224 / ADC224_VIN01 | U13 | H +20 dB echo |
| ADC1 | 0/2 | 224 / ADC224_VIN23 | U11 | H 0 dB echo |
| ADC2 | 1/0 | 225 / ADC225_VIN01 | UY7 | H -20 dB echo |
| ADC3 | 1/2 | 225 / ADC225_VIN23 | UY18 | H calibration/reference |
| ADC4 | 2/0 | 226 / ADC226_VIN01 | J4-1 P31/N33 | V +20 dB echo |
| ADC5 | 2/2 | 226 / ADC226_VIN23 | J4-1 P39/N41 | V 0 dB echo |
| ADC6 | 3/0 | 227 / ADC227_VIN01 | J4-1 P49/N47 | V -20 dB echo |
| ADC7 | 3/2 | 227 / ADC227_VIN23 | J4-1 P57/N55 | V calibration/reference |

ADC slice identifiers use the RF Data Converter IP spelling (`00`, `02`,
`10`, `12`, `20`, `22`, `30`, `32`), not a dense software-only 0..7 slice
number.

## DAC mapping

| Logical | RFDC tile/slice | Bank/net | Carrier endpoint | Project role |
|---|---|---|---|---|
| DAC0 | 0/0 | 228 / DAC228_VOUT0 | J4-2 N63/P65 | V +20 dB echo |
| DAC1 | 0/1 | 228 / DAC228_VOUT1 | J4-2 N71/P73 | H +20 dB echo |
| DAC2 | 0/2 | 228 / DAC228_VOUT2 | J4-2 N79/P81 | V 0 dB echo |
| DAC3 | 0/3 | 228 / DAC228_VOUT3 | J4-2 N87/P89 | H 0 dB echo |
| DAC4 | 1/0 | 229 / DAC229_VOUT0 | UY3 | V -20 dB echo |
| DAC5 | 1/1 | 229 / DAC229_VOUT1 | UY5 | H -20 dB echo |
| DAC6 | 1/2 | 229 / DAC229_VOUT2 | U10 | V calibration/cancellation |
| DAC7 | 1/3 | 229 / DAC229_VOUT3 | U16 | H calibration/cancellation |

## Machine-readable authority

The installed authority is
`src/rfsoc_pulse_model/config/default.json`; `config/default.json` is its
byte-identical source-tree mirror. Each channel entry contains:

```text
index
rfdc_tile
rfdc_slice
package_bank
board_net
board_endpoint
polarization
gain_range
allowed_roles
nominal_gain_db
digital_scale
enabled
```

`ModelConfig` rejects missing fields, duplicate RFDC routes, incomplete route
sets and a logical channel index detached from its canonical tile/slice.

## Hardware acceptance still required

Before this gate is considered physically proven on a populated system:

1. Check J4-1 and J4-2 mezzanine population and pin continuity.
2. Inject a low-power tone into ADC0..7 one at a time and read back the RFDC
   tile/slice named above; all other channels must remain below the crosstalk
   limit.
3. Drive DAC0..7 one at a time at low amplitude and measure only the named
   endpoint.
4. Verify the external H/V labels and +20/0/-20 dB voltage ratios.
5. Record serial number, mezzanine revision, cable/harness revision and the
   measured mapping in the board acceptance artifact.

No Cycle or Block Design implementation may introduce a second channel map.
They must consume this configuration contract.
