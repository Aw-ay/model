# AMD IP-first foundation acceptance

Acceptance date: 2026-08-11 (Asia/Shanghai)

## Scope under test

- Branch: `agent/model-update-20260810`
- Implementation commit before acceptance documentation:
  `37e218a62232f180c67e68a7caaa12b170957276`
- Python: `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Vivado: `D:\app\AMD\2025.2\Vivado\bin\vivado.bat`, v2025.2 build 6299465
- Device: `xczu27dr-fsve1156-2-i`

This checkpoint accepts configuration separation, ownership classification,
deterministic generation and initial IP Catalog resolution. It does not accept
a connected Block Design.

## Automated evidence

- Python unit tests: 149 passed, 0 failed.
- Repeated generation: byte-identical file hashes across two consecutive runs.
- Vivado exit code: 0 when run outside the filesystem sandbox required for its
  user Tcl Store writes.
- Vivado status line: `IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON`.
- `topology_status`: `unconnected_skeleton`.
- `integration_accepted`: `false`.
- Catalog status after strict TSV validation: `vivado_2025_2_resolved`.

The initial sandboxed Vivado launch failed before sourcing the generated Tcl
with `Failed to install all user apps`. Re-running the identical command with
normal user-data write access succeeded. This identifies the failure as a
Vivado Tcl Store startup-permission issue, not an RFDC/IP architecture error.

## SHA-256 authorities and outputs

| Artifact | SHA-256 |
|---|---|
| `config/default.json` | `d181d16d3eaede23978aaefc0ed022a10a7284686c5ec228647d3c08d1fbb5e4` |
| `config/ip_architecture.json` | `e7130a2daf267d6ac5fc06862697889d0948a096e501ed0423b952ec8d48d371` |
| `build/vivado/create_ip_architecture.tcl` | `26c0707956024d3f7d4253861a1334d8a33382b23174794cd311c5cefefee9e7` |
| `build/metadata/ip_architecture.json` | `c2abf640f4d1f116dfb699e71560408a4dad161ee4e2ce845455e095cdefc878` |
| `build/metadata/resolved_ip_vlnv.json` | `36fec08e5e94ad1f4dc3e3a8507d074fce44a773077e571ca64dbcc4c4051343` |
| `build/manifest.json` | `da556aa55a7d3f3e1685835b1b9589e70fff340af9f0835ca87b618a220ad65b` |

## Vivado 2025.2 resolved VLNV evidence

| Logical name | Resolved VLNV |
|---|---|
| `rfdc` | `xilinx.com:ip:usp_rf_data_converter:2.6` |
| `axis_register_slice` | `xilinx.com:ip:axis_register_slice:1.1` |
| `axis_data_fifo` | `xilinx.com:ip:axis_data_fifo:2.0` |
| `axis_clock_converter` | `xilinx.com:ip:axis_clock_converter:1.1` |
| `axis_dwidth_converter` | `xilinx.com:ip:axis_dwidth_converter:1.1` |
| `axis_combiner` | `xilinx.com:ip:axis_combiner:1.1` |
| `axis_broadcaster` | `xilinx.com:ip:axis_broadcaster:1.1` |
| `axis_switch` | `xilinx.com:ip:axis_switch:1.1` |
| `fir_compiler` | `xilinx.com:ip:fir_compiler:7.2` |

The parser rejects malformed rows, duplicates, a missing initial family, a
wrong family identity and every RFDC version other than exact 2.6. Resolved
versions are never guessed.

## Explicitly open gates

- exact RFDC, AXIS and FIR property dictionaries and readback;
- all AXIS/RFDC/FIR connections and address assignments;
- vendor behavioral simulation against Golden/Cycle boundary vectors;
- `validate_bd_design` on a connected design;
- RFDC common-clock, reset, MTS and SYSREF proof;
- `report_cdc`, synthesis, implementation and timing closure;
- board-level eight-channel loopback, phase alignment and RF performance;
- replacement gate for `rx_group_ingress_2spc` and later
  `tx_iq_axis_boundary_2spc`;
- RFDC/DMA/GEM data-plane integration and hit-only IQ/PDW transport.

No open gate is implied by the successful skeleton run. No legacy DSL or RTL
may be removed until its named replacement gate passes.
