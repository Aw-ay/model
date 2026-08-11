# IP Architecture Normalization Design

**Date:** 2026-08-11  
**Status:** Approved design  
**Target branch:** `model-update-20260811`

## 1. Purpose

Normalize the AMD IP-first architecture before any connected Block Design is
built. The normalized model must distinguish an IP catalog family, a concrete
IP instance, and an architecture block; bind Vivado catalog evidence to the
exact architecture inputs that produced it; prove complete responsibility
ownership; and prevent legacy reference RTL from entering production sources.

This design is a metadata, validation, and generation-boundary change. It does
not freeze the multi-target fractional-delay implementation and does not move
converter-rate or clocking fields out of `ModelConfig` in this batch.

## 2. Scope

This batch implements:

1. schema v2 for the hardware architecture configuration;
2. separate IP family, IP instance, and architecture block types;
3. complete responsibility ownership validation;
4. independent ownership-completeness and production-readiness results;
5. exact binding between architecture configuration, generated Tcl, catalog
   request, Vivado evidence, and a candidate IP lock;
6. catalog discovery for every required AMD IP family without dummy BD cells;
7. materialization of only explicitly materialized IP instances;
8. isolation of legacy generated RTL under `build/reference_rtl/`;
9. Python and Vivado verification gates for these behaviors.

This batch does not implement:

- RFDC, FIR, DDS, CMPY, CORDIC, DMA, or AXIS parameter dictionaries;
- connected AXI4-Stream topology;
- a choice among independent, multichannel, time-division, coefficient-bank,
  or Farrow fractional-delay implementations;
- `ModelConfig` rate and clocking migration;
- `validate_bd_design`, CDC closure, timing closure, or board loopback.

## 3. Schema v2 boundaries

`HardwareArchitectureConfig` has five top-level domains: four architecture
object collections plus one RFDC integration domain.

```text
HardwareArchitectureConfig
├── rfdc_integration
├── ip_families
├── ip_instances
├── architecture_blocks
└── required_responsibilities
```

The hard type invariant is:

```text
IP Family != IP Instance != Architecture Block
```

### 3.1 IP families

An IP family describes catalog identity and discovery policy only. It does not
own algorithm or transport responsibilities and does not imply that a BD cell
exists.

Each family contains:

- a stable family identifier;
- implementation kind `amd_ip`;
- a catalog pattern used only during development discovery;
- whether the family is required;
- an optional exact VLNV supplied by the production lock.

The family collection includes RF Data Converter, AXIS infrastructure, FIR
Compiler, DDS Compiler, Complex Multiplier, CORDIC, and AXI DMA.

### 3.2 IP instances

An IP instance describes one intentional BD cell. Each instance has:

- a stable instance name;
- one `family_ref`;
- one lifecycle value;
- parameter and connection status values;
- a stable logical role;
- optional parameter and interface data added by later integration batches.

The lifecycle enum is exactly:

```text
planned | materialized | retired
```

The parameter-status enum is exactly:

```text
unspecified | drafted | frozen | vivado_verified
```

The connection-status enum is exactly:

```text
unconnected | partial | connected | vivado_verified
```

Only `lifecycle == materialized` permits `create_bd_cell`. Planned instances
appear in manifests but must not be emitted into the Block Design. Retired
instances remain traceable but must not be materialized or treated as current
implementation.

The initial normalized configuration declares:

```text
rfdc_0:
    family_ref = rfdc
    lifecycle = materialized
    parameter_status = unspecified
    connection_status = unconnected

monitor_fir_dec2_0:
    family_ref = fir_compiler
    lifecycle = planned
    parameter_status = drafted
    connection_status = unconnected
```

No fractional-delay FIR instances are declared until the multi-target
implementation is frozen.

### 3.3 Architecture blocks

An architecture block is the only object that owns architecture
responsibilities. A block may be implemented by AMD IP instances, custom RTL,
an XPM macro, or a future composition whose implementation is not yet frozen.

Each block contains:

- a stable block identifier;
- implementation kind;
- a nonempty responsibility list;
- zero or more `instance_refs`;
- architecture status;
- `production_accepted` as a strict boolean;
- an optional source for custom or legacy implementation.

The implementation-kind enum is exactly:

```text
amd_ip | custom_rtl | xpm_macro | architecture_pending |
legacy_non_production
```

The architecture-status enum is exactly:

```text
frozen | architecture_pending
```

The two fields are constrained rather than independently selectable:

```text
implementation_kind == architecture_pending
if and only if
architecture_status == architecture_pending
```

An `architecture_pending` block must have `production_accepted == false`, an
empty `instance_refs` list, and no production source. A block with any other
implementation kind must have `architecture_status == frozen`. This makes the
pending implementation state explicit in the same type system used for AMD IP,
custom RTL, and XPM ownership while preventing contradictory combinations.

`fractional_delay_bank` owns fractional-delay processing and coefficient-set
scheduling while remaining truthful about its maturity:

```text
fractional_delay_bank:
    implementation_kind = architecture_pending
    architecture_status = architecture_pending
    production_accepted = false
    instance_refs = []
```

Its responsibilities remain stable when a later batch chooses and attaches a
physical implementation.

### 3.4 RFDC integration

`rfdc_integration` does not define another RFDC identity. It contains only
Vivado/RFDC-specific integration configuration and evidence state, attached by:

```text
instance_ref = rfdc_0
```

The referenced instance must exist, must reference the RFDC family, and must
not be retired. This prevents competing authorities such as an RFDC logical
name in the integration object and a different concrete IP instance.

### 3.5 Required responsibilities

`required_responsibilities` is the exact required set for production
architecture ownership. Validation compares it with responsibilities owned by
architecture blocks.

For every required responsibility there must be exactly one block owner:

- a missing owner is an error;
- multiple owners are an error;
- a block declaring an unknown responsibility is an error.

A block may own a responsibility while `production_accepted` is false. This is
necessary for an architecture-pending block to remain the unambiguous owner
without falsely claiming that its implementation is ready.

## 4. Independent architecture results

The architecture exposes three independent results:

```text
responsibility_complete
catalog_resolution_complete
production_integration_ready
```

`responsibility_complete` is true when required responsibilities and block
ownership form an exact one-owner mapping. It does not inspect physical
implementation maturity.

`catalog_resolution_complete` is true only when current, strongly bound Vivado
evidence resolves every required IP family.

`production_integration_ready` is a derived value, never a user-configurable
flag. It is true if and only if all of the following predicates are true:

```text
responsibility_complete
and catalog_resolution_complete
and production_lock_valid
and every required-responsibility owner has production_accepted == true
and no required-responsibility owner has
    implementation_kind == architecture_pending
and every AMD-IP owner references at least one IP instance
and every instance referenced by an accepted AMD-IP owner has
    lifecycle == materialized
and every such materialized instance has
    parameter_status == vivado_verified
and connection_status == vivado_verified
and every accepted custom-RTL or XPM owner has a valid production source
and rfdc_integration proof_status == vivado_verified
and the production source manifest contains no reference RTL
```

`production_lock_valid` is the exact lock predicate defined in Section 7.
Planned or retired instances that are not referenced by accepted production
blocks do not by themselves affect readiness. Dangling instance references are
configuration errors and therefore cannot produce a readiness result.

Consequently, this batch can produce:

```text
responsibility_complete = true
catalog_resolution_complete = true
production_integration_ready = false
```

This is the expected truthful foundation state.

## 5. Catalog discovery and architecture realization

Catalog discovery and architecture realization are separate phases.

### 5.1 Catalog discovery

Discovery queries every required family with `get_ipdefs`. It does not call
`create_bd_cell`. Development discovery may use the configured wildcard
pattern and resolves a candidate exact VLNV. Production and CI may use only
exact VLNV values from the checked-in lock.

The discovery set is derived from all required families in schema v2. There is
no smaller hard-coded initial-family tuple and no global resolved status based
on a subset.

### 5.2 Architecture realization

The realization phase iterates IP instances, not families. It emits a BD cell
only for a materialized instance and uses the instance name as the stable cell
name. Planned and retired instances never produce cells.

The normalized skeleton therefore materializes `rfdc_0` but does not create
dummy AXIS, FIR, DDS, CMPY, CORDIC, or DMA cells merely to prove catalog
availability.

## 6. Strong evidence binding

Hashes are generated in the following strict acyclic order:

```text
1. canonical architecture config bytes
       -> architecture_config_sha256
2. generated Tcl bytes
       -> generated_tcl_sha256
3. canonical catalog_request.json bytes
       -> catalog_request_sha256
4. external Vivado catalog evidence
5. validated ip_lock.candidate.json
```

The Tcl is generated from the parsed architecture configuration but contains
none of `generated_tcl_sha256`, `catalog_request_sha256`, or the future evidence
hash. Therefore it never includes its own digest. The request is generated only
after the Tcl bytes are final and records:

- architecture schema and configuration versions;
- `architecture_config_sha256`;
- `generated_tcl_sha256`;
- required Vivado version;
- the complete required family set and catalog identities.

The request uses canonical UTF-8 JSON with sorted keys and one trailing newline;
its SHA-256 covers those exact bytes. The Vivado invocation passes the three
current hashes to the generated Tcl as explicit Tcl arguments. The Tcl validates
the argument count and writes those values into the external evidence. It does
not rewrite the request or regenerate any input artifact.

Vivado discovery writes evidence containing:

- `architecture_config_sha256`;
- `generated_tcl_sha256`;
- `catalog_request_sha256`;
- the actual full Vivado version;
- a run identifier;
- the exact resolved VLNV for every required family.

Python accepts evidence only when all three hashes match current files, the
Vivado version satisfies the frozen version requirement, and the resolved
family set is exact. Missing, duplicate, additional, or identity-mismatched
families are errors.

Evidence that parses correctly but is bound to older inputs produces:

```text
catalog_resolution_status = stale_evidence
catalog_resolution_complete = false
production_integration_ready = false
```

It must not generate a current candidate lock. Evidence with malformed or
internally inconsistent content is rejected as an error rather than classified
as stale.

## 7. IP lock lifecycle

Vivado evidence and the production lock have different ownership.

Validated discovery produces:

```text
build/metadata/ip_lock.candidate.json
```

The candidate contains exact VLNV values plus the configuration, Tcl, request,
and Vivado-version bindings. Normal build generation never mutates the source
configuration.

An explicit promotion action copies a valid candidate into the versioned
package-data authority:

```text
config/ip_lock.json
src/rfsoc_pulse_model/config/ip_lock.json
```

Promotion must preserve byte equality between the source-tree mirror and the
installed package-data copy. Development discovery may run without a lock.
Production and CI modes require a current, complete lock and reject wildcard
selection or an incompatible Vivado version.

The production-lock family predicate is exact set equality:

```text
set(ip_lock.families.keys())
==
set(family.id for family in ip_families if family.required)
```

Both a missing required family and an extra family are errors. For every entry,
the locked VLNV must be an exact `vendor:library:name:version` value whose first
three components match the configured family catalog identity. The RF Data
Converter entry must equal the frozen RFDC 2.6 VLNV. The lock is valid only when
its schema version, architecture-configuration hash, generated-Tcl hash,
catalog-request hash, and Vivado version also match the current production
inputs. This complete conjunction is `production_lock_valid`; partial or stale
locks are never accepted.

## 8. Legacy RTL isolation

The current non-production Cycle modules remain available for reference and
equivalence tests, but their generated Verilog moves to:

```text
build/reference_rtl/
```

`build/rtl/` is reserved for production RTL. The manifest exposes separate
`production_rtl` and `reference_rtl` lists with exact paths and hashes. Vivado
production source selection consumes the explicit production list; directory
globbing is not an authority.

Reference RTL does not contribute to production integration readiness and must
not be listed as a production architecture implementation.

## 9. Failure handling

Architecture generation fails immediately for:

- unsupported schema versions or enum values;
- contradictory implementation-kind and architecture-status combinations;
- blank, duplicate, or dangling identifiers;
- an instance referencing an unknown family;
- RFDC integration referencing a non-RFDC or retired instance;
- missing, duplicate, or unknown responsibility ownership;
- Tcl attempting to materialize a planned or retired instance;
- incomplete or identity-mismatched resolved catalogs;
- incomplete production locks;
- production locks with extra families or stale input bindings;
- wildcard version selection in production or CI mode.

Stale, well-formed evidence is a non-ready diagnostic state, not successful
resolution. Malformed evidence is an error. No failure may silently fall back
to old evidence or a latest-version wildcard.

## 10. Verification gates

### 10.1 Schema and registry checkpoint

Tests prove:

- parsing and strict enum validation;
- unique family, instance, and block identifiers;
- valid cross-references;
- exact missing, duplicate, and unknown responsibility rejection;
- strict `architecture_pending` implementation-kind invariants;
- independent responsibility and production-readiness results;
- every individual `production_integration_ready` predicate can force a false
  result without changing ownership completeness;
- RFDC integration attaches only to `rfdc_0`.

### 10.2 Evidence and Tcl checkpoint

Tests prove:

- every required family is queried;
- discovery creates no dummy cell;
- only materialized instances create cells;
- planned and retired instances do not create cells;
- wrong configuration, Tcl, or request hashes yield stale evidence;
- the config-to-Tcl-to-request hash order is deterministic and acyclic;
- malformed, incomplete, duplicate, extra, or wrong-family evidence fails;
- a wrong Vivado version fails;
- only complete current evidence creates a candidate lock.

Vivado 2025.2 must run the generated Tcl and resolve all configured required
families before this checkpoint is accepted.

### 10.3 Generator and legacy checkpoint

Tests prove:

- reference RTL is emitted only under `build/reference_rtl/`;
- production and reference entries are distinct in the manifest;
- repeated generation without external evidence is byte-deterministic;
- candidate lock generation is deterministic for identical accepted evidence;
- a production lock requires exact required-family set equality and rejects
  both missing and extra families;
- all existing Golden, Cycle, equivalence, and Verilog tests remain passing.

## 11. Acceptance boundary

The batch is accepted when all three checkpoints pass, the design and package
configuration copies are byte-identical, and Vivado 2025.2 resolves all
required families with current bound evidence.

Acceptance means the AMD IP-first foundation has a truthful, traceable chain:

```text
responsibility
→ architecture block
→ IP instance
→ IP family
→ resolved VLNV
→ candidate or production lock
→ future parameter set
→ future BD cell and connection
→ future Vivado evidence
```

Acceptance does not claim connected Block Design validity, parameter readback,
CDC closure, timing closure, or board-level signal processing success.
