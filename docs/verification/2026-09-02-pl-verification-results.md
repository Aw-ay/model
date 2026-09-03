# PL verification results — 2026-09-02

## Scope and candidate identity

These results execute the host-side gates in
`docs/superpowers/plans/2026-09-02-pl-verification.md` against commit
`c4b38738bfbaeb27828d109aa54f264200bc68f6` on branch
`calibrator-vivado-vitis-20260825`.

The candidate remains classified as `integration_skeleton`, so these results
must not be interpreted as final PL acceptance. The immutable local identity
record is `build/pl_verification/identity.json`.

The first identity audit found that the older
`build/calibrator_project_gate/calibrator.bit` predated the current generated
register reset header and the eight-channel calibration snapshot CDC wiring.
That historical image was rejected as evidence for the current commit. A clean
Vivado build was therefore performed in `build/calibrator_pl_verify`.

Current generated artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `calibrator.bit` | 34,437,496 | `36e4a2269893c011864f39122393a465418521c3dc807652b2a8276f8b3dcd61` |
| `calibrator.xsa` | 1,944,470 | `68a56a02ec80ae1cd663776e418b137e3c2a9f08a503d0717c0580e3294a8a65` |

The XSA contains the exact 34,437,496-byte bitstream above; extraction and
byte-for-byte SHA-256 comparison passed.

## Gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| PL-G0 candidate identity | PASS | Current commit, Vivado/Vitis/PetaLinux 2025.2, `xczu27dr-fsve1156-2-i`, RFDC 2.6 and nine artifact hashes verified. |
| PL-G1 Golden/Cycle numeric model | PASS | 117 Golden tests and 66 Cycle tests passed. Supplemental integer-delay, normalized fractional-delay, complex-gain and auto-range boundary vectors passed. |
| PL-G2 RTL/AXIS/CDC/event queue | PASS for current integration scope | 45 focused tests passed, including real XSIM AXI-Lite and DAC-mute simulations plus real Vivado 2025.2 candidate synthesis. |
| PL-G3 clean Vivado implementation | PASS | BD validation, synthesis, placement, routing, bitstream and embedded-bit XSA completed from current sources. |
| PL-G4 JTAG and board smoke | BLOCKED before programming | Vivado 2025.2 `hw_server` and `cs_server` started, but no hardware target was present. Windows enumerated no Xilinx, Digilent or FTDI JTAG USB device. No board state was changed. |
| PL-G5 RFDC/MTS and routing | NOT RUN | Requires a visible JTAG/boot target, stable RF clocks/SYSREF and low-power RF equipment. |
| PL-G6 final calibration/range/detector | NOT ELIGIBLE | Required final production owners remain `architecture_pending`. |
| PL-G7 PDW/IQ/DMA | PARTIAL HOST PASS | Event format, ordering, once-only behavior and whole-event drop policy passed model tests; board DMA behavior was not run. |
| PL-G8 recovery/endurance | NOT RUN | Requires final DSP image and working board access. |

## Vivado sign-off

| Check | Result |
| --- | ---: |
| Setup WNS / TNS / failing endpoints | `+0.255 ns / 0.000 ns / 0` |
| Hold WHS / THS / failing endpoints | `+0.012 ns / 0.000 ns / 0` |
| Minimum bus-skew slack | `+2.951 ns` |
| Routable / fully routed nets | `49,479 / 49,479` |
| Routing errors | `0` |
| CDC | `0 Critical`, `21 Info`, `188 CDC-15 Warning` |
| DRC | `0 Error`, `4 Warning` |
| Unconstrained internal endpoints | `0` |

The two `check_timing` no-clock pins are inside the RFDC hard macro:
`tx0_u_dac/INTERNAL_CLK_DIG` and `tx1_u_dac/INTERNAL_CLK_DIG`. No user-logic
unconstrained internal endpoint was reported. The CDC-15 set remains the
documented RFDC/vendor and AMD asynchronous FIFO warning class; the new
calibration/control/status crossings appear as synchronized handshake CDCs.

Post-route utilization is 23,894 CLB LUTs (5.62%), 31,725 CLB registers
(3.73%), 2.5 BRAM tiles (0.23%), 3 URAMs (3.75%) and 32 DSPs (0.75%).

## Release limits and next executable gate

`config/ip_architecture.json` still marks `integer_delay_bank`,
`fractional_delay_bank` and `adc_calibrated_frontend` as
`architecture_pending`; automatic H/V range selection and the complete
specified adaptive detector are therefore not present in this bitstream.
Passing PL-G0 through PL-G3 does not prove their function.

The next executable action is to restore USB enumeration of the JTAG download
cable. After the cable appears in Windows and Vivado exposes a hardware target,
repeat the read-only probe, then program only with DAC mute asserted and verify
project ID, ABI version and reset values before enabling RFDC or acquisition.

## 2026-09-03 JTAG retest

The PL-G4 entry probe was repeated without programming the board. Windows still
reported no connected or historical Xilinx, Digilent or FTDI JTAG USB device,
and it reported no present USB device in an error state. The installed driver
store does contain Digilent, FTDI and Xilinx Platform Cable packages, so absence
of the driver packages is not the current failure boundary.

Vivado 2025.2 successfully launched and connected its standard `hw_server` and
`cs_server`, then failed `get_hw_targets` with `No matching targets found on
connected servers: localhost`. This reproduces the PL-G4 blocker before FPGA
device discovery. The current evidence localizes the problem to USB enumeration
of the download cable or the cable hardware/power path; no bitstream was loaded
and no board state was changed.
