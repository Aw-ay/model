# AMD IP-first ownership contract

Status: schema-v2 ownership is complete; production integration is not yet
accepted. The configured topology remains an unconnected skeleton.

`HardwareArchitectureConfig` is the source authority. `ArchitectureRegistry`
derives and validates responsibility ownership from it; generated metadata is a
record of that authority, not a replacement for it.

## Architecture identities

The following identities are deliberately distinct:

| Identity | Meaning | Authority |
|---|---|---|
| IP family | An AMD catalog requirement, such as `fir_compiler`, with a catalog pattern and resolved VLNV evidence. | `ip_families` |
| IP instance | One named Vivado cell candidate, such as `rfdc_0`, with lifecycle, parameter, and connection maturity. | `ip_instances` |
| Architecture block | A functional owner such as `rfdc_frontend` or `fractional_delay_bank`. It may refer to zero or more IP instances. | `architecture_blocks` |
| Production responsibility | A semantic function in the exact `required_responsibilities.production` set. | `ArchitectureRegistry.production_owner_map` |
| Legacy reference responsibility | A non-production, `legacy_reference.`-prefixed function retained solely for reference/equivalence work. | `ArchitectureRegistry.reference_responsibility_map` |

RF Data Converter is the required family
`xilinx.com:ip:usp_rf_data_converter:2.6`; its integration metadata refers to
the single instance `rfdc_0`. An integration record never defines a second
RFDC identity.

## Ownership rules

Every production responsibility has exactly one non-legacy architecture-block
owner. The registry rejects unknown production responsibilities, missing
owners, duplicate owners, duplicate block names, and use of the reserved
`legacy_reference.` prefix in the production namespace.

Legacy blocks own only reference responsibilities. Their entries never enter
the production-owner map, cannot fulfill a required production responsibility,
and cannot satisfy the continuous-reflection chain.

The ordered `continuous_dual_polar_reflection` chain is frozen at 16 items,
from `rx_2spc_continuous_ingress` through
`tx_2spc_continuous_egress`. Each item must occur in the required production
set and resolve through the production-owner map to exactly one non-legacy
block. Monitor, PDW, event, status, and DDR responsibilities remain production
side branches; they do not join this chain.

## Independent machine-derived results

The architecture reports three independent values:

| Result | True only when |
|---|---|
| `responsibility_complete` | The production-owner keys exactly equal the required production set and the frozen ordered reflection chain resolves entirely through those owners. |
| `catalog_resolution_complete` | Current strongly bound Vivado evidence resolves the exact required IP-family set. |
| `production_integration_ready` | Ownership is complete; catalog and production lock are current; all required owners are accepted and non-pending; AMD instances are materialized and Vivado-verified; accepted custom/XPM owners have production sources; RFDC integration proof is Vivado-verified; and production sources contain no reference RTL. |

Consequently, `responsibility_complete=true` may coexist with
`catalog_resolution_complete=true` and
`production_integration_ready=false`. This is the truthful default foundation:
the architecture has an exact owner for every responsibility, but its pending
blocks, unverified instance maturity, RFDC proof, and integration work are not
yet production-ready.

`ArchitectureRegistry.evaluate_readiness()` exposes stable blocking reasons for
each false predicate, including catalog or lock invalidity and reference RTL in
the production source list. It does not claim connected Block Design validity,
CDC, timing, MTS/SYSREF, DMA/Ethernet, or board-loopback closure.
