# AMD IP-first ownership contract

Status: foundation accepted for architecture generation and Vivado 2025.2 IP
Catalog resolution. The generated topology remains an unconnected skeleton.

`HardwareArchitectureConfig`, `ArchitectureRegistry` and the generated
`metadata/ip_architecture.json` are the machine-readable authorities. A
responsibility may have only one production owner. RF Data Converter is locked
to `xilinx.com:ip:usp_rf_data_converter:2.6`; other AMD IP versions are resolved
from the Vivado 2025.2 catalog and recorded as build evidence.

| Logical block | Kind | Production | Responsibilities | Catalog pattern, exact VLNV or source |
|---|---|---:|---|---|
| `rfdc` | `amd_ip` | yes | ADC, DAC, DDC, DUC, decimation, interpolation, mixer, NCO | `xilinx.com:ip:usp_rf_data_converter:2.6` |
| `axis_register_slice` | `amd_ip` | yes | AXIS register pipeline | `xilinx.com:ip:axis_register_slice:*` |
| `axis_data_fifo` | `amd_ip` | yes | AXIS buffering | `xilinx.com:ip:axis_data_fifo:*` |
| `axis_clock_converter` | `amd_ip` | yes | AXIS CDC | `xilinx.com:ip:axis_clock_converter:*` |
| `axis_dwidth_converter` | `amd_ip` | yes | AXIS width conversion | `xilinx.com:ip:axis_dwidth_converter:*` |
| `axis_combiner` | `amd_ip` | yes | AXIS combining | `xilinx.com:ip:axis_combiner:*` |
| `axis_broadcaster` | `amd_ip` | yes | AXIS broadcasting | `xilinx.com:ip:axis_broadcaster:*` |
| `axis_switch` | `amd_ip` | yes | AXIS switching | `xilinx.com:ip:axis_switch:*` |
| `fir_compiler` | `amd_ip` | yes | monitor FIR/DEC2, fractional-delay FIR | `xilinx.com:ip:fir_compiler:*` |
| `dds_compiler` | `amd_ip` | yes | Doppler phasor | `xilinx.com:ip:dds_compiler:*` |
| `complex_multiplier` | `amd_ip` | yes | complex multiplication | `xilinx.com:ip:cmpy:*` |
| `cordic` | `amd_ip` | yes | frequency-estimator atan2 | `xilinx.com:ip:cordic:*` |
| `axi_dma` | `amd_ip` | yes | event-to-DDR transport | `xilinx.com:ip:axi_dma:*` |
| `integer_delay_memory` | `xpm_macro` | yes | integer-delay storage | `xpm_memory_sdpram` |
| `rx_stream_control` | `custom_rtl` | yes | acquisition epoch, stream-integrity status | planned Cycle/custom RTL |
| `auto_hold_range_selector` | `custom_rtl` | yes | H/V AUTO_HOLD selection | planned Cycle/custom RTL |
| `target_scheduler` | `custom_rtl` | yes | target scheduling, maximum-target control | planned Cycle/custom RTL |
| `circular_delay_controller` | `custom_rtl` | yes | delay addressing, lane scheduling | planned Cycle/custom RTL |
| `fractional_delay_scheduler` | `custom_rtl` | yes | coefficient-set scheduling | planned Cycle/custom RTL |
| `target_alignment_accumulator` | `custom_rtl` | yes | multi-target alignment and accumulation | planned Cycle/custom RTL |
| `pulse_detector` | `custom_rtl` | yes | adaptive threshold, N/M vote, TOA, contiguous-main-peak FWHM, coarse PDW | planned Cycle/custom RTL |
| `event_control` | `custom_rtl` | yes | hit-IQ framing, overflow/BIT/fault status | planned Cycle/custom RTL |
| `rx_group_ingress_2spc` | `legacy_non_production` | no | legacy RX word-order/epoch reference | `cycle/hardware/rx_group_ingress.py` |
| `tx_iq_axis_boundary_2spc` | `legacy_non_production` | no | legacy TX packing/underrun reference | `cycle/hardware/tx_iq_axis_boundary.py` |

RFDC 2.6 and AMD standard IP are production targets.
`rx_group_ingress_2spc` and `tx_iq_axis_boundary_2spc` are legacy references.
They remain generated and tested until their AMD-IP replacements pass explicit
replacement gates. No DSL file is deleted in this foundation checkpoint.

The current `ip_architecture_skeleton` is not a connected or validated Block
Design. It proves only exact RFDC availability, initial AXIS/FIR catalog
resolution and deterministic architecture generation. It does not prove IP
properties, connectivity, CDC, timing, MTS/SYSREF or board behavior.
