# AMD IP architecture normalization acceptance

Acceptance date: 2026-08-12 (Asia/Shanghai)

## Scope and authority

- Branch under test: `model-update-20260811`.
- Commit under test: `dbf4b96` (`build: lock Vivado 2025.2 AMD IP catalog`),
  before this acceptance-document commit.
- Schema-v2 design:
  [`2026-08-11-ip-architecture-normalization-design.md`](../superpowers/specs/2026-08-11-ip-architecture-normalization-design.md).
- Implementation plan:
  [`2026-08-11-ip-architecture-normalization.md`](../superpowers/plans/2026-08-11-ip-architecture-normalization.md).
- Python:
  `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
- Vivado catalog/realization evidence: Vivado v2025.2 (64-bit), SW Build
  6299465, IP Build 6300035.
- Cross-authority-checked `device_part`: `xczu27dr-fsve1156-2-i`.

This accepts deterministic source-driven generation, exact catalog discovery
provenance, the explicit production lock, and an unconnected `rfdc_0`
realization. It does not accept a connected Block Design or production
integration.

## Hash chain and mirror checks

| Artifact | SHA-256 |
| --- | --- |
| `config/default.json` | `d181d16d3eaede23978aaefc0ed022a10a7284686c5ec228647d3c08d1fbb5e4` |
| `config/ip_architecture.json` | `2cad67a144b60411c0d7b39a845c7616ff2537b052e07dd9d4523589f1271647` |
| `build/vivado/discover_ip_catalog.tcl` | `13ac8327c36879910a44b2eb924d2f0ce0f7fdb85ad7f6dae125a06ffabdaee8` |
| `build/metadata/catalog_request.json` | `9dbb0ae0de091a461ae88cef055d999b4fa1452788c9ae9e594d0807a0cda552` |
| `build/metadata/catalog_evidence.tsv` | `58bf0631271a1492166d8a5b286e47ca05e406c73ff515f4db2d2e9086b18cc8` |
| `config/ip_lock.json` | `b6b5955df8ec8c8054d58bb68f0bd8a704af88bf4206e43be97b6448b4af66bc` |
| `build/vivado/realize_ip_architecture.tcl` | `b97b1286024da85bd290bf43300faece6a4ec2691b3153b56e370478207c20ce` |
| `build/metadata/ip_architecture.json` | `899252b34fca1da65881ae81f40f77cf7d29e5790e1645a179f21041eff58cff` |
| `build/manifest.json` | `cbdc3a6cbed124d711fa69fda2c7d7cf8484f0ad0f0a35d074f3e9d4b139cbf2` |

`config/ip_architecture.json` and its packaged copy are byte-identical.
`config/ip_lock.json` and its packaged copy are byte-identical. The current
tool-written `build/metadata/ip_lock.candidate.json` is byte-identical to the
promoted production lock. The lock binds the discovery Tcl only; it contains
no realization-Tcl hash.

Both generated Tcl scripts derive the same fixed part from the parsed,
cross-authority-checked architecture config. The request, strict TSV evidence,
candidate, and lock carry the same config/discovery/request provenance hashes
in that order; none carries an independent device-part authority.

## Exact catalog result

The strict evidence has six metadata rows and exactly these 13 resolved
required families:

| Family | Resolved VLNV |
| --- | --- |
| `rfdc` | `xilinx.com:ip:usp_rf_data_converter:2.6` |
| `axis_register_slice` | `xilinx.com:ip:axis_register_slice:1.1` |
| `axis_data_fifo` | `xilinx.com:ip:axis_data_fifo:2.0` |
| `axis_clock_converter` | `xilinx.com:ip:axis_clock_converter:1.1` |
| `axis_dwidth_converter` | `xilinx.com:ip:axis_dwidth_converter:1.1` |
| `axis_combiner` | `xilinx.com:ip:axis_combiner:1.1` |
| `axis_broadcaster` | `xilinx.com:ip:axis_broadcaster:1.1` |
| `axis_switch` | `xilinx.com:ip:axis_switch:1.1` |
| `fir_compiler` | `xilinx.com:ip:fir_compiler:7.2` |
| `dds_compiler` | `xilinx.com:ip:dds_compiler:6.0` |
| `complex_multiplier` | `xilinx.com:ip:cmpy:6.0` |
| `cordic` | `xilinx.com:ip:cordic:6.0` |
| `axi_dma` | `xilinx.com:ip:axi_dma:7.1` |

Discovery contains exactly one fixed-part in-memory `create_project` and one
`update_ip_catalog`. It contains no `create_bd_design`, `create_bd_cell`,
`connect_bd*`, or `validate_bd_design`. Its real Vivado evidence therefore
proves catalog discovery only. The separately generated realization Tcl
creates exactly one cell, `rfdc_0`, and contains no connection or validation
command. Its real Vivado run is an unconnected realization only.

## Determinism, manifest, and Python regression

Two consecutive production invocations used this exact PowerShell command:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.generate --output 'D:\AWAY\RFSOC\model\build' --ip-mode production
```

The following hashes were identical on both runs:

| Artifact | SHA-256 |
| --- | --- |
| `build/vivado/discover_ip_catalog.tcl` | `13ac8327c36879910a44b2eb924d2f0ce0f7fdb85ad7f6dae125a06ffabdaee8` |
| `build/vivado/realize_ip_architecture.tcl` | `b97b1286024da85bd290bf43300faece6a4ec2691b3153b56e370478207c20ce` |
| `build/metadata/catalog_request.json` | `9dbb0ae0de091a461ae88cef055d999b4fa1452788c9ae9e594d0807a0cda552` |
| `build/metadata/ip_architecture.json` | `899252b34fca1da65881ae81f40f77cf7d29e5790e1645a179f21041eff58cff` |
| `build/manifest.json` | `cbdc3a6cbed124d711fa69fda2c7d7cf8484f0ad0f0a35d074f3e9d4b139cbf2` |

The current production manifest declares zero `production_rtl` files and two
`reference_rtl` files. The reference files are the older 2SPC ingress and TX
boundary only; they are not production implementations.

The full regression command was:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

It completed with `Ran 216 tests in 3.487s`, `OK (skipped=8)`, and process exit
code 0.

## Derived readiness result and remaining gates

Production generation reports:

```text
responsibility_complete=true
catalog_resolution_complete=true
production_lock_valid=true
production_integration_ready=false
```

The recorded blockers are `production_block_not_accepted`,
`architecture_pending`, `amd_ip_owner_instance_not_materialized`,
`materialized_instance_parameters_not_vivado_verified`,
`materialized_instance_connections_not_vivado_verified`, and
`rfdc_integration_not_vivado_verified`.

The production 2SPC ingress and egress remain pending. The previous
Cycle-derived 2SPC artifacts remain reference-only and do not satisfy either
production boundary. This acceptance does not establish IP parameter readback,
a connected Block Design, `validate_bd_design`, CDC, synthesis or timing,
MTS/SYSREF, DMA/Ethernet integration, or board loopback. It makes no claim
about any of those gates.

The older `amd-ip-foundation-acceptance.md` is a preserved historical record;
its superseded script/status terminology is not a live instruction or current
contract.
