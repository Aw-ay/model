# IP Architecture Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current IP-family skeleton with schema-v2 family, instance, block, responsibility, evidence, and lock authorities that are truthful, reproducible, and safe to use as the foundation for a future connected Block Design.

**Architecture:** A single packaged `HardwareArchitectureConfig` declares four architecture object collections plus RFDC integration metadata. Separate discovery and realization Tcl emitters preserve the boundary between IP catalog provenance and BD-cell materialization. Strongly bound Vivado evidence produces a candidate lock; only an explicit promotion creates the production lock, while ownership completeness and production readiness remain independent machine-derived results.

**Tech Stack:** Python 3.12, immutable dataclasses and enums, canonical JSON, strict TSV evidence, `unittest`, generated Verilog-2001 reference RTL, Vivado 2025.2 Tcl, AMD IP Catalog, SHA-256, Git checkpoints.

## Global Constraints

- Work in `D:\AWAY\RFSOC\model` on branch `model-update-20260811`; create local commits only and do not push.
- RF Data Converter is exactly `xilinx.com:ip:usp_rf_data_converter:2.6`.
- `IP Family != IP Instance != Architecture Block` is a hard invariant.
- `rfdc_integration` references `rfdc_0`; it does not define a second RFDC identity.
- `architecture_pending` is a formal `ImplementationKind` and is equivalent to `ArchitectureStatus.ARCHITECTURE_PENDING`.
- Production and legacy reference responsibility namespaces are disjoint.
- Every production `required_responsibility` has exactly one non-legacy architecture-block owner; missing, duplicate, and unknown production responsibilities are errors.
- `responsibility_complete`, `catalog_resolution_complete`, and `production_integration_ready` are independent derived results.
- Hash order is exactly architecture config, discovery Tcl, catalog request, external evidence, candidate lock.
- In requests, evidence, and locks, `generated_tcl_sha256` means only the SHA-256 of `build/vivado/discover_ip_catalog.tcl`.
- `realize_ip_architecture.tcl` uses separate `realization_tcl_sha256` provenance and does not affect IP-lock validity.
- A production lock must match the required IP-family set exactly; both missing and extra families are errors.
- Catalog discovery must query every required family and must not create BD cells.
- Only `IpInstanceLifecycle.MATERIALIZED` instances may emit `create_bd_cell`.
- Legacy Cycle-derived Verilog is generated only under `build/reference_rtl/` and never appears in the production source list.
- Do not migrate `ModelConfig`, choose a multi-target fractional-delay implementation, add IP parameter dictionaries, connect AXIS, run `validate_bd_design`, or claim CDC/timing/board closure in this plan.
- Use `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` with `PYTHONPATH=D:\AWAY\RFSOC\model\src`.
- Never hand-edit generated Tcl, metadata, candidate locks, manifests, or Verilog.

---

## File Structure

| Path | Responsibility |
|---|---|
| `config/ip_architecture.json` | Source-tree schema-v2 architecture authority |
| `src/rfsoc_pulse_model/config/ip_architecture.json` | Byte-identical installed schema-v2 package data |
| `config/ip_lock.json` | Explicitly promoted production catalog lock |
| `src/rfsoc_pulse_model/config/ip_lock.json` | Byte-identical installed production lock |
| `src/rfsoc_pulse_model/ip/types.py` | Family, instance, RFDC integration, block, enum, and config types |
| `src/rfsoc_pulse_model/ip/registry.py` | Production ownership map and exact readiness evaluation |
| `src/rfsoc_pulse_model/ip/tcl.py` | Separate deterministic discovery and realization Tcl emitters |
| `src/rfsoc_pulse_model/ip/catalog.py` | Exact IP-family/VLNV identity and resolved-set validation |
| `src/rfsoc_pulse_model/ip/evidence.py` | Canonical request, strict evidence, binding, and candidate-lock logic |
| `src/rfsoc_pulse_model/ip/lock.py` | Production-lock validation and explicit candidate promotion CLI |
| `src/rfsoc_pulse_model/ip/generate.py` | Architecture artifact orchestration and derived statuses |
| `src/rfsoc_pulse_model/ip/__init__.py` | Stable public architecture API |
| `src/rfsoc_pulse_model/generate.py` | Top generator, production/reference RTL separation, CLI mode |
| `pyproject.toml` | Package-data inclusion for architecture config and production lock |
| `tests/ip/test_architecture_config.py` | Schema-v2 types, enums, config-copy, and cross-reference tests |
| `tests/ip/test_registry.py` | Production/legacy ownership and readiness predicate tests |
| `tests/ip/test_tcl.py` | Discovery/realization separation and deterministic hash tests |
| `tests/ip/test_catalog.py` | Exact complete required-family catalog tests |
| `tests/ip/test_evidence.py` | Acyclic request/evidence binding and stale evidence tests |
| `tests/ip/test_lock.py` | Exact-set production-lock and promotion tests |
| `tests/verilog/test_generate.py` | Reference RTL isolation and combined manifest regression |
| `docs/contracts/amd-ip-ownership.md` | Published family/instance/block and responsibility contract |
| `docs/verification/amd-ip-normalization-acceptance.md` | Recorded Python and Vivado evidence and remaining gates |

---

### Task 1: Replace the schema-v1 family list with typed schema-v2 architecture objects

**Files:**
- Modify: `config/ip_architecture.json`
- Modify: `src/rfsoc_pulse_model/config/ip_architecture.json`
- Modify: `src/rfsoc_pulse_model/ip/types.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Modify: `tests/ip/test_architecture_config.py`

**Interfaces:**
- Consumes: the approved schema in `docs/superpowers/specs/2026-08-11-ip-architecture-normalization-design.md`.
- Produces: `ImplementationKind`, `IpInstanceLifecycle`, `ParameterStatus`, `ConnectionStatus`, `ArchitectureStatus`, `IpFamilySpec`, `IpInstanceSpec`, `RfdcIntegrationMetadata`, `ArchitectureBlockSpec`, and `HardwareArchitectureConfig.load_default()`.

- [ ] **Step 1: Write failing schema-v2 type and package-data tests**

Replace the schema-v1 assumptions in `tests/ip/test_architecture_config.py` with tests containing these exact expectations:

```python
EXPECTED_FAMILIES = {
    "rfdc",
    "axis_register_slice",
    "axis_data_fifo",
    "axis_clock_converter",
    "axis_dwidth_converter",
    "axis_combiner",
    "axis_broadcaster",
    "axis_switch",
    "fir_compiler",
    "dds_compiler",
    "complex_multiplier",
    "cordic",
    "axi_dma",
}


def test_default_uses_schema_v2_and_separates_family_instance_block(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    self.assertEqual(config.architecture_schema_version, 2)
    self.assertEqual({family.family_id for family in config.ip_families}, EXPECTED_FAMILIES)
    self.assertEqual(
        {instance.instance_name for instance in config.ip_instances},
        {"rfdc_0", "monitor_fir_dec2_0"},
    )
    self.assertEqual(config.rfdc_integration.instance_ref, "rfdc_0")
    self.assertEqual(
        config.instance_by_name("rfdc_0").family_ref,
        "rfdc",
    )


def test_fractional_delay_is_pending_without_fake_instances(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    block = config.block_by_name("fractional_delay_bank")
    self.assertEqual(block.implementation_kind, ImplementationKind.ARCHITECTURE_PENDING)
    self.assertEqual(block.architecture_status, ArchitectureStatus.ARCHITECTURE_PENDING)
    self.assertFalse(block.production_accepted)
    self.assertEqual(block.instance_refs, ())
    self.assertFalse(
        any(instance.instance_name.startswith("fractional_delay_fir_")
            for instance in config.ip_instances)
    )


def test_pending_kind_and_status_cannot_disagree(self) -> None:
    with self.assertRaisesRegex(ValueError, "architecture_pending.*equivalent"):
        ArchitectureBlockSpec(
            block_name="bad_pending",
            implementation_kind=ImplementationKind.ARCHITECTURE_PENDING,
            responsibilities=("fractional_delay_processing",),
            reference_responsibilities=(),
            instance_refs=(),
            architecture_status=ArchitectureStatus.FROZEN,
            production_accepted=False,
            source=None,
        )
```

Retain the existing exact RFDC 2.6 and byte-identical config-copy tests, updating access from `config.rfdc.ip` to `config.family_by_id("rfdc")` and `config.rfdc_integration`.

- [ ] **Step 2: Run Task 1 tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_architecture_config -v
```

Expected: failures because schema version 1 has no `ip_families`, `ip_instances`, `architecture_blocks`, `ArchitectureStatus`, or `ARCHITECTURE_PENDING` kind.

- [ ] **Step 3: Implement the strict enums and immutable object types**

In `src/rfsoc_pulse_model/ip/types.py`, add these exact enum members:

```python
class ImplementationKind(str, Enum):
    AMD_IP = "amd_ip"
    XPM_MACRO = "xpm_macro"
    CUSTOM_RTL = "custom_rtl"
    CUSTOM_HLS = "custom_hls"
    SOFTWARE_ONLY = "software_only"
    ARCHITECTURE_PENDING = "architecture_pending"
    LEGACY_NON_PRODUCTION = "legacy_non_production"


class IpInstanceLifecycle(str, Enum):
    PLANNED = "planned"
    MATERIALIZED = "materialized"
    RETIRED = "retired"


class ParameterStatus(str, Enum):
    UNSPECIFIED = "unspecified"
    DRAFTED = "drafted"
    FROZEN = "frozen"
    VIVADO_VERIFIED = "vivado_verified"


class ConnectionStatus(str, Enum):
    UNCONNECTED = "unconnected"
    PARTIAL = "partial"
    CONNECTED = "connected"
    VIVADO_VERIFIED = "vivado_verified"


class ArchitectureStatus(str, Enum):
    FROZEN = "frozen"
    ARCHITECTURE_PENDING = "architecture_pending"


class IntegrationProofStatus(str, Enum):
    UNVERIFIED = "unverified"
    VIVADO_VERIFIED = "vivado_verified"
```

Add frozen dataclasses with these exact fields:

```python
@dataclass(frozen=True)
class IpFamilySpec:
    family_id: str
    implementation_kind: ImplementationKind
    catalog_pattern: str
    required: bool
    vlnv: str | None = None


@dataclass(frozen=True)
class IpInstanceSpec:
    instance_name: str
    family_ref: str
    logical_role: str
    lifecycle: IpInstanceLifecycle
    parameter_status: ParameterStatus
    connection_status: ConnectionStatus


@dataclass(frozen=True)
class RfdcIntegrationMetadata:
    instance_ref: str
    configuration_authority: str
    dac_analog_output_type: str
    dac_mixer_mode: str
    dac_mixer_scale_mode: str
    dac_nco_frequency_hz: int
    proof_status: IntegrationProofStatus


@dataclass(frozen=True)
class ArchitectureBlockSpec:
    block_name: str
    implementation_kind: ImplementationKind
    responsibilities: tuple[str, ...]
    reference_responsibilities: tuple[str, ...]
    instance_refs: tuple[str, ...]
    architecture_status: ArchitectureStatus
    production_accepted: bool
    source: str | None = None


@dataclass(frozen=True)
class HardwareArchitectureConfig:
    architecture_schema_version: int
    architecture_config_version: int
    vivado_version: str
    generation_mode: str
    topology_status: str
    rfdc_integration: RfdcIntegrationMetadata
    ip_families: tuple[IpFamilySpec, ...]
    ip_instances: tuple[IpInstanceSpec, ...]
    architecture_blocks: tuple[ArchitectureBlockSpec, ...]
    required_responsibilities: tuple[str, ...]
```

Provide `family_by_id()`, `instance_by_name()`, `block_by_name()`, and `required_families()` methods that raise `KeyError` for an unknown stable ID. Enforce these constructor invariants:

```python
pending_kind = self.implementation_kind is ImplementationKind.ARCHITECTURE_PENDING
pending_status = self.architecture_status is ArchitectureStatus.ARCHITECTURE_PENDING
if pending_kind != pending_status:
    raise ValueError("architecture_pending kind and status must be equivalent")
if pending_kind and (
    self.production_accepted or self.instance_refs or self.source is not None
):
    raise ValueError("architecture_pending block cannot be production accepted or implemented")
```

For legacy blocks, require empty `responsibilities`, nonempty `reference_responsibilities`, `legacy_reference.` prefixes, and `production_accepted=False`. For every non-legacy block, require nonempty `responsibilities`, empty `reference_responsibilities`, and reject the reserved legacy prefix.

- [ ] **Step 4: Replace both configuration copies with schema v2**

Use these exact top-level keys:

```json
{
  "architecture_schema_version": 2,
  "architecture_config_version": 2,
  "vivado_version": "2025.2",
  "generation_mode": "vivado_ip_first",
  "topology_status": "unconnected_skeleton",
  "rfdc_integration": {},
  "ip_families": [],
  "ip_instances": [],
  "architecture_blocks": [],
  "required_responsibilities": []
}
```

Declare all 13 family IDs from `EXPECTED_FAMILIES`. RFDC uses exact pattern and exact VLNV `xilinx.com:ip:usp_rf_data_converter:2.6`; the other 12 use their existing catalog patterns. Declare exactly these two instances:

```json
[
  {
    "instance_name": "rfdc_0",
    "family_ref": "rfdc",
    "logical_role": "rfdc_frontend",
    "lifecycle": "materialized",
    "parameter_status": "unspecified",
    "connection_status": "unconnected"
  },
  {
    "instance_name": "monitor_fir_dec2_0",
    "family_ref": "fir_compiler",
    "logical_role": "monitor_decimator",
    "lifecycle": "planned",
    "parameter_status": "drafted",
    "connection_status": "unconnected"
  }
]
```

Move current RFDC integration settings under `rfdc_integration`, replace the nested IP object with `"instance_ref": "rfdc_0"`, and retain exact mixer/NCO/output/proof values. Populate architecture blocks and required responsibilities with the exact production ownership names currently present in `ip/registry.py`, with these deliberate changes:

- `rfdc_frontend` references `rfdc_0` and owns the eight RFDC functions;
- `monitor_decimator` references planned `monitor_fir_dec2_0` and owns `monitor_fir_dec2`;
- `fractional_delay_bank` is `architecture_pending`, references no instance, and owns `fractional_delay_processing` plus `fractional_delay_coefficient_set_scheduling`;
- remove the separate production `fractional_delay_scheduler` owner;
- all other AMD, XPM, and custom blocks retain their current responsibility names;
- legacy blocks use only `legacy_reference.rx_group_ingress_2spc` and `legacy_reference.tx_iq_axis_boundary_2spc` as `reference_responsibilities`.

The exact production `required_responsibilities` set is:

```python
{
    "adc", "dac", "ddc", "duc", "decimation", "interpolation", "mixer", "nco",
    "axis_register_pipeline", "axis_buffering", "axis_clock_domain_crossing",
    "axis_width_conversion", "axis_combining", "axis_broadcasting", "axis_switching",
    "monitor_fir_dec2", "fractional_delay_processing",
    "fractional_delay_coefficient_set_scheduling", "doppler_phasor",
    "complex_multiplication", "frequency_estimator_atan2", "event_to_ddr_transport",
    "integer_delay_storage", "acquisition_epoch", "stream_integrity_status",
    "auto_hold_range_selection", "target_scheduling", "maximum_target_control",
    "circular_delay_addressing", "lane_scheduling", "multi_target_output_alignment",
    "multi_target_accumulation", "adaptive_noise", "adaptive_threshold", "nm_voting",
    "toa", "contiguous_main_peak_fwhm", "coarse_pdw", "hit_iq_event_framing",
    "overflow_status", "bit_status", "fault_management",
}
```

Copy the final JSON bytes to `src/rfsoc_pulse_model/config/ip_architecture.json` without reformatting differences.

- [ ] **Step 5: Run Task 1 tests and the existing config tests**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_architecture_config tests.common.test_config -v
```

Expected: PASS; `ModelConfig` tests remain unchanged.

- [ ] **Step 6: Commit Task 1**

```powershell
git add config/ip_architecture.json src/rfsoc_pulse_model/config/ip_architecture.json src/rfsoc_pulse_model/ip/types.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_architecture_config.py
git commit -m "refactor: add schema v2 IP architecture objects"
```

---

### Task 2: Derive exact production ownership and machine readiness

**Files:**
- Modify: `src/rfsoc_pulse_model/ip/registry.py`
- Modify: `tests/ip/test_registry.py`
- Modify: `docs/contracts/amd-ip-ownership.md`

**Interfaces:**
- Consumes: `HardwareArchitectureConfig`, `ArchitectureBlockSpec`, and strict enum types from Task 1.
- Produces: `ArchitectureRegistry.from_config(config: HardwareArchitectureConfig) -> ArchitectureRegistry`, `ArchitectureReadiness`, `ArchitectureRegistry.responsibility_complete`, and `ArchitectureRegistry.evaluate_readiness(*, catalog_resolution_complete: bool, production_lock_valid: bool, production_sources_contain_reference: bool) -> ArchitectureReadiness`.

- [ ] **Step 1: Write failing ownership-scope and readiness tests**

Add tests with these exact behaviors:

```python
def test_production_owner_map_exactly_matches_required_set(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.from_config(config)
    self.assertTrue(registry.responsibility_complete)
    self.assertEqual(
        set(registry.production_owner_map),
        set(config.required_responsibilities),
    )


def test_legacy_reference_responsibilities_are_out_of_production_scope(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.from_config(config)
    self.assertNotIn(
        "legacy_reference.rx_group_ingress_2spc",
        registry.production_owner_map,
    )
    self.assertEqual(
        set(registry.reference_responsibility_map),
        {
            "legacy_reference.rx_group_ingress_2spc",
            "legacy_reference.tx_iq_axis_boundary_2spc",
        },
    )


def test_missing_extra_and_duplicate_production_responsibilities_fail(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    missing = dataclasses.replace(
        config,
        required_responsibilities=config.required_responsibilities[:-1],
    )
    with self.assertRaisesRegex(ValueError, "unknown production responsibility"):
        ArchitectureRegistry.from_config(missing)

    duplicate_block = dataclasses.replace(
        config.architecture_blocks[0],
        block_name="duplicate_adc",
        responsibilities=("adc",),
    )
    with self.assertRaisesRegex(ValueError, "multiple production owners"):
        ArchitectureRegistry.from_config(
            dataclasses.replace(
                config,
                architecture_blocks=(*config.architecture_blocks, duplicate_block),
            )
        )


def test_default_is_complete_but_not_production_ready(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    registry = ArchitectureRegistry.from_config(config)
    readiness = registry.evaluate_readiness(
        catalog_resolution_complete=True,
        production_lock_valid=True,
        production_sources_contain_reference=False,
    )
    self.assertTrue(readiness.responsibility_complete)
    self.assertTrue(readiness.catalog_resolution_complete)
    self.assertFalse(readiness.production_integration_ready)
    self.assertIn("architecture_pending", readiness.blocking_reasons)
```

Add this explicit predicate table to the same test class:

```python
def test_each_external_readiness_gate_has_a_stable_blocking_reason(self) -> None:
    registry = ArchitectureRegistry.default()
    cases = (
        (
            {"catalog_resolution_complete": False, "production_lock_valid": True,
             "production_sources_contain_reference": False},
            "catalog_resolution_incomplete",
        ),
        (
            {"catalog_resolution_complete": True, "production_lock_valid": False,
             "production_sources_contain_reference": False},
            "production_lock_invalid",
        ),
        (
            {"catalog_resolution_complete": True, "production_lock_valid": True,
             "production_sources_contain_reference": True},
            "reference_rtl_in_production_sources",
        ),
    )
    for arguments, expected_reason in cases:
        with self.subTest(expected_reason=expected_reason):
            result = registry.evaluate_readiness(**arguments)
            self.assertFalse(result.production_integration_ready)
            self.assertIn(expected_reason, result.blocking_reasons)


def test_default_instance_and_block_maturity_reasons_are_explicit(self) -> None:
    result = ArchitectureRegistry.default().evaluate_readiness(
        catalog_resolution_complete=True,
        production_lock_valid=True,
        production_sources_contain_reference=False,
    )
    self.assertIn("architecture_pending", result.blocking_reasons)
    self.assertIn("production_block_not_accepted", result.blocking_reasons)
    self.assertIn("materialized_instance_parameters_not_vivado_verified", result.blocking_reasons)
    self.assertIn("materialized_instance_connections_not_vivado_verified", result.blocking_reasons)
    self.assertIn("rfdc_integration_not_vivado_verified", result.blocking_reasons)
```

- [ ] **Step 2: Run registry tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_registry -v
```

Expected: failures because the current registry constructs owners from hard-coded families, has no reference namespace, and has no readiness evaluator.

- [ ] **Step 3: Implement config-derived ownership maps**

Replace `_AMD_IP_RESPONSIBILITIES` and `_PROJECT_AND_LEGACY_BLOCKS` with configuration-derived blocks. `ArchitectureRegistry.from_config()` must build:

```python
production_owner_map: dict[str, str]
reference_responsibility_map: dict[str, str]
```

Reject duplicate block names, duplicate owners, missing required owners, unknown production responsibilities, legacy responsibilities outside the reserved prefix, and production responsibilities using the reserved prefix. Keep `ArchitectureRegistry.default()` as a thin call to `from_config(HardwareArchitectureConfig.load_default())`.

- [ ] **Step 4: Implement the exact readiness conjunction**

Add:

```python
@dataclass(frozen=True)
class ArchitectureReadiness:
    responsibility_complete: bool
    catalog_resolution_complete: bool
    production_lock_valid: bool
    production_integration_ready: bool
    blocking_reasons: tuple[str, ...]
```

`evaluate_readiness()` must return true only when every predicate frozen in design Section 4 is true: current catalog and lock, all required owners accepted, no pending owner, all accepted AMD owners reference materialized and Vivado-verified instances, accepted custom/XPM owners have production sources, RFDC proof is Vivado-verified, and the production source list contains no reference RTL. Use stable reason strings so tests can assert each failed predicate.

- [ ] **Step 5: Update and run the ownership contract tests**

Update `docs/contracts/amd-ip-ownership.md` to describe family, instance, block, production responsibility, legacy reference responsibility, and the three independent result values. Then run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_registry tests.ip.test_architecture_config -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/rfsoc_pulse_model/ip/registry.py tests/ip/test_registry.py docs/contracts/amd-ip-ownership.md
git commit -m "feat: enforce complete production architecture ownership"
```

---

### Task 3: Split catalog discovery Tcl from architecture realization Tcl

**Files:**
- Modify: `src/rfsoc_pulse_model/ip/tcl.py`
- Create: `src/rfsoc_pulse_model/ip/evidence.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `tests/ip/test_tcl.py`
- Modify: `tests/ip/test_generate_architecture.py`

**Interfaces:**
- Consumes: schema-v2 families and instances from Task 1 and registry from Task 2.
- Produces: `emit_catalog_discovery_tcl(config: HardwareArchitectureConfig) -> str`, `emit_architecture_realization_tcl(config: HardwareArchitectureConfig, resolved_vlnv: Mapping[str, str] | None = None) -> str`, `canonical_json_bytes(payload: Mapping[str, object]) -> bytes`, `build_catalog_request(config: HardwareArchitectureConfig, architecture_config_sha256: str, generated_tcl_sha256: str) -> dict[str, object]`, and deterministic `catalog_request.json` generation.

- [ ] **Step 1: Write failing dual-Tcl and no-dummy-cell tests**

Replace old skeleton assertions with:

```python
def test_discovery_queries_every_required_family_without_creating_cells(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    tcl = emit_catalog_discovery_tcl(config)
    for family in config.required_families():
        self.assertIn(f"{{{family.family_id}}}", tcl)
        self.assertIn(f"{{{family.catalog_pattern}}}", tcl)
    self.assertNotIn("create_bd_cell", tcl)
    self.assertIn("llength $argv", tcl)
    self.assertIn("catalog_evidence.tsv", tcl)


def test_realization_creates_only_materialized_instances(self) -> None:
    config = HardwareArchitectureConfig.load_default()
    tcl = emit_architecture_realization_tcl(config)
    self.assertIn("create_bd_cell", tcl)
    self.assertIn("{rfdc_0}", tcl)
    self.assertNotIn("monitor_fir_dec2_0", tcl)
    self.assertNotIn("axis_data_fifo", tcl)
    self.assertNotIn("validate_bd_design", tcl)


def test_request_hash_order_and_tcl_provenance_are_deterministic(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        architecture = generate_ip_architecture(root)
        discovery = (root / "vivado/discover_ip_catalog.tcl").read_bytes()
        realization = (root / "vivado/realize_ip_architecture.tcl").read_bytes()
        request_bytes = (root / "metadata/catalog_request.json").read_bytes()
        request = json.loads(request_bytes)
        self.assertEqual(request["architecture_config_sha256"], architecture["source_config_sha256"])
        self.assertEqual(request["generated_tcl_sha256"], hashlib.sha256(discovery).hexdigest())
        self.assertEqual(architecture["realization_tcl_sha256"], hashlib.sha256(realization).hexdigest())
        self.assertEqual(architecture["catalog_request_sha256"], hashlib.sha256(request_bytes).hexdigest())
        self.assertNotIn(request["generated_tcl_sha256"], discovery.decode("utf-8"))
```

- [ ] **Step 2: Run Tcl tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_tcl tests.ip.test_generate_architecture -v
```

Expected: failures because only `emit_ip_skeleton_tcl()` and `create_ip_architecture.tcl` exist.

- [ ] **Step 3: Implement discovery Tcl for the full required family set**

Remove `INITIAL_SKELETON_IP`. `emit_catalog_discovery_tcl()` must derive its catalog array from `config.required_families()`, require exactly three Tcl arguments, query all family patterns with `get_ipdefs`, preserve exact RFDC 2.6, and write strict evidence rows. It must contain no `create_project`, `create_bd_design`, or `create_bd_cell` command.

Use this evidence row grammar:

```text
meta<TAB>evidence_schema_version<TAB>1
meta<TAB>architecture_config_sha256<TAB><64 lowercase hex>
meta<TAB>generated_tcl_sha256<TAB><64 lowercase hex>
meta<TAB>catalog_request_sha256<TAB><64 lowercase hex>
meta<TAB>vivado_version<TAB><version -short result>
meta<TAB>run_id<TAB><pid>-<clock milliseconds>
ip<TAB><family_id><TAB><exact VLNV>
```

- [ ] **Step 4: Implement realization Tcl over concrete instances**

`emit_architecture_realization_tcl()` must create the in-memory ZU27DR project and unconnected BD, iterate `config.ip_instances`, skip planned and retired instances, and emit stable cell names only for materialized instances. In the initial config it creates exactly `rfdc_0`. Emit `IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON`; do not call `validate_bd_design`.

- [ ] **Step 5: Implement the acyclic request-generation order**

In `generate_ip_architecture()`:

1. hash installed `ip_architecture.json` bytes;
2. emit and write `discover_ip_catalog.tcl`;
3. hash the exact discovery Tcl bytes;
4. emit and write `realize_ip_architecture.tcl` and record its independent hash;
5. serialize canonical `catalog_request.json` with sorted keys, indentation, UTF-8, and one trailing newline;
6. hash exact request bytes;
7. write architecture metadata containing all three provenance fields.

Do not include any hash in the discovery Tcl itself.

- [ ] **Step 6: Run dual-Tcl tests and commit Task 3**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_tcl tests.ip.test_generate_architecture -v
```

Expected: PASS.

```powershell
git add src/rfsoc_pulse_model/ip/tcl.py src/rfsoc_pulse_model/ip/evidence.py src/rfsoc_pulse_model/ip/generate.py tests/ip/test_tcl.py tests/ip/test_generate_architecture.py
git commit -m "feat: split IP discovery and realization Tcl"
```

---

### Task 4: Bind full-catalog Vivado evidence and generate candidate locks

**Files:**
- Modify: `src/rfsoc_pulse_model/ip/evidence.py`
- Modify: `src/rfsoc_pulse_model/ip/catalog.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Create: `tests/ip/test_evidence.py`
- Modify: `tests/ip/test_catalog.py`

**Interfaces:**
- Consumes: exact request hashes and complete required family set from Task 3.
- Produces: `CatalogResolutionStatus`, `CatalogEvidence`, `parse_catalog_evidence(text: str) -> CatalogEvidence`, `validate_catalog_evidence(config: HardwareArchitectureConfig, request_bytes: bytes, discovery_tcl_bytes: bytes, evidence: CatalogEvidence) -> ValidatedCatalogEvidence`, and `build_candidate_lock(config: HardwareArchitectureConfig, evidence: ValidatedCatalogEvidence) -> dict[str, object]`.

- [ ] **Step 1: Write failing complete-set and stale-binding tests**

Create `tests/ip/test_evidence.py` with this concrete fixture builder. It derives one exact resolved VLNV per configured family, using RFDC 2.6 and syntactically valid `:1.0` versions for non-RFDC test identities:

```python
def make_evidence_fixture():
    config = HardwareArchitectureConfig.load_default()
    config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    discovery_tcl_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_payload = build_catalog_request(
        config,
        architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        generated_tcl_sha256=hashlib.sha256(discovery_tcl_bytes).hexdigest(),
    )
    request_bytes = canonical_json_bytes(request_payload)
    resolved = {}
    for family in config.required_families():
        resolved[family.family_id] = (
            family.vlnv
            if family.vlnv is not None
            else family.catalog_pattern[:-1] + "1.0"
        )
    evidence = CatalogEvidence(
        evidence_schema_version=1,
        architecture_config_sha256=request_payload["architecture_config_sha256"],
        generated_tcl_sha256=request_payload["generated_tcl_sha256"],
        catalog_request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        vivado_version="2025.2",
        run_id="unit-test-1",
        resolved_vlnv=tuple(sorted(resolved.items())),
    )
    return config, request_bytes, discovery_tcl_bytes, evidence


def test_current_complete_evidence_is_resolved(self) -> None:
    config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
    result = validate_catalog_evidence(
        config,
        request_bytes,
        discovery_tcl_bytes,
        evidence,
    )
    self.assertEqual(result.status, CatalogResolutionStatus.ALL_REQUIRED_IP_RESOLVED)
    self.assertEqual(
        set(result.resolved_vlnv),
        {family.family_id for family in config.required_families()},
    )


def test_old_hashes_are_stale_not_resolved(self) -> None:
    config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
    evidence = dataclasses.replace(
        evidence,
        generated_tcl_sha256="0" * 64,
    )
    result = validate_catalog_evidence(
        config,
        request_bytes,
        discovery_tcl_bytes,
        evidence,
    )
    self.assertEqual(result.status, CatalogResolutionStatus.STALE_EVIDENCE)
    self.assertFalse(result.catalog_resolution_complete)


def test_missing_extra_duplicate_and_wrong_identity_fail(self) -> None:
    config, request_bytes, discovery_tcl_bytes, evidence = make_evidence_fixture()
    resolved = dict(evidence.resolved_vlnv)

    missing = dict(resolved)
    missing.pop("axi_dma")
    with self.assertRaisesRegex(ValueError, "family set"):
        validate_catalog_evidence(
            config, request_bytes, discovery_tcl_bytes,
            dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(missing.items()))),
        )

    extra = dict(resolved)
    extra["not_required"] = "xilinx.com:ip:xlconstant:1.1"
    with self.assertRaisesRegex(ValueError, "family set"):
        validate_catalog_evidence(
            config, request_bytes, discovery_tcl_bytes,
            dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(extra.items()))),
        )

    wrong = dict(resolved)
    wrong["fir_compiler"] = "xilinx.com:ip:dds_compiler:6.0"
    with self.assertRaisesRegex(ValueError, "does not match"):
        validate_catalog_evidence(
            config, request_bytes, discovery_tcl_bytes,
            dataclasses.replace(evidence, resolved_vlnv=tuple(sorted(wrong.items()))),
        )

    with self.assertRaisesRegex(ValueError, "duplicate"):
        parse_catalog_evidence(
            "ip\trfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
            "ip\trfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
        )
```

Add a generation test that writes a current fixture as strict TSV, reruns `generate_ip_architecture()`, and requires `ip_lock.candidate.json`. Replace its `generated_tcl_sha256` row with 64 zeros, rerun generation, and require status `stale_evidence` plus absence of `ip_lock.candidate.json`. The generator must remove only that known derived candidate path when evidence is absent or stale; it must not delete unrelated metadata.

Add a separate regression that writes only the legacy path `metadata/resolved_ip_vlnv.tsv`, runs generation, and requires `catalog_resolution_status == "unverified"` plus no candidate lock. The schema-v1 TSV must never be read as schema-v2 evidence.

- [ ] **Step 2: Run evidence tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_evidence tests.ip.test_catalog -v
```

Expected: import failure for `ip.evidence` and old tests still accepting the nine-row legacy TSV subset.

- [ ] **Step 3: Replace subset catalog validation with exact required-set validation**

Delete imports and logic tied to `INITIAL_SKELETON_IP`. `validate_resolved_catalog()` must enforce:

```python
expected = {family.family_id for family in config.required_families()}
actual = set(resolved)
if actual != expected:
    raise ValueError(f"resolved family set mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
```

Then validate every exact VLNV identity and exact RFDC 2.6.

- [ ] **Step 4: Implement strict evidence parsing and stale classification**

Add these exact public types:

```python
class CatalogResolutionStatus(str, Enum):
    UNVERIFIED = "unverified"
    STALE_EVIDENCE = "stale_evidence"
    ALL_REQUIRED_IP_RESOLVED = "all_required_ip_resolved"


@dataclass(frozen=True)
class CatalogEvidence:
    evidence_schema_version: int
    architecture_config_sha256: str
    generated_tcl_sha256: str
    catalog_request_sha256: str
    vivado_version: str
    run_id: str
    resolved_vlnv: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ValidatedCatalogEvidence:
    status: CatalogResolutionStatus
    catalog_resolution_complete: bool
    resolved_vlnv: Mapping[str, str]
    evidence: CatalogEvidence
```

Parse the exact three-column grammar from Task 3. Reject unknown row kinds, duplicate metadata, duplicate families, missing metadata, padded values, malformed SHA-256, blank run IDs, and malformed VLNV values. Treat a hash or Vivado-version mismatch as `STALE_EVIDENCE` only after the evidence is structurally valid and its resolved family set is exact. Treat malformed content and wrong family identities as errors.

Remove schema-v1 ingestion of `metadata/resolved_ip_vlnv.tsv`; schema v2 reads only `metadata/catalog_evidence.tsv`.

- [ ] **Step 5: Generate the deterministic candidate lock**

For accepted evidence write `build/metadata/ip_lock.candidate.json` containing:

```json
{
  "lock_schema_version": 1,
  "architecture_config_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "generated_tcl_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "catalog_request_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "vivado_version": "2025.2",
  "families": {
    "rfdc": "xilinx.com:ip:usp_rf_data_converter:2.6"
  }
}
```

The actual `families` object must contain all 13 required family IDs. Use canonical JSON and one trailing newline. If evidence is absent, set status `unverified`; if current inputs do not match, set `stale_evidence`; if accepted, set `all_required_ip_resolved`. Ensure a candidate from an earlier run is not reported or accepted when current evidence is absent or stale.

- [ ] **Step 6: Run evidence tests and commit Task 4**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_evidence tests.ip.test_catalog tests.ip.test_generate_architecture -v
```

Expected: PASS.

```powershell
git add src/rfsoc_pulse_model/ip/evidence.py src/rfsoc_pulse_model/ip/catalog.py src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_evidence.py tests/ip/test_catalog.py tests/ip/test_generate_architecture.py
git commit -m "feat: bind complete Vivado catalog evidence"
```

---

### Task 5: Add exact production-lock validation and explicit promotion

**Files:**
- Create: `src/rfsoc_pulse_model/ip/lock.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/generate.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/ip/test_lock.py`

**Interfaces:**
- Consumes: `ip_lock.candidate.json` from Task 4.
- Produces: `GenerationMode`, `ProductionLock`, `validate_production_lock(config: HardwareArchitectureConfig, request_bytes: bytes, discovery_tcl_bytes: bytes, lock_payload: Mapping[str, object]) -> ProductionLockValidation`, `promote_candidate_lock(candidate_path: Path, root_lock_path: Path, package_lock_path: Path) -> None`, and `python -m rfsoc_pulse_model.ip.lock promote`.

- [ ] **Step 1: Write failing exact-set and provenance tests**

Create `tests/ip/test_lock.py` with:

```python
def valid_lock_fixture():
    config = HardwareArchitectureConfig.load_default()
    config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    discovery_tcl_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_payload = build_catalog_request(
        config,
        architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        generated_tcl_sha256=hashlib.sha256(discovery_tcl_bytes).hexdigest(),
    )
    request_bytes = canonical_json_bytes(request_payload)
    families = {
        family.family_id: (
            family.vlnv
            if family.vlnv is not None
            else family.catalog_pattern[:-1] + "1.0"
        )
        for family in config.required_families()
    }
    lock_payload = {
        "lock_schema_version": 1,
        "architecture_config_sha256": request_payload["architecture_config_sha256"],
        "generated_tcl_sha256": request_payload["generated_tcl_sha256"],
        "catalog_request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "vivado_version": "2025.2",
        "families": families,
    }
    return {
        "config": config,
        "request_bytes": request_bytes,
        "discovery_tcl_bytes": discovery_tcl_bytes,
        "lock_payload": lock_payload,
    }


def test_lock_family_set_must_equal_required_family_set(self) -> None:
    fixture = valid_lock_fixture()
    self.assertTrue(validate_production_lock(**fixture).valid)

    missing = copy.deepcopy(fixture["lock_payload"])
    missing["families"].pop("axi_dma")
    with self.assertRaisesRegex(ValueError, "missing.*axi_dma"):
        validate_production_lock(**{**fixture, "lock_payload": missing})

    extra = copy.deepcopy(fixture["lock_payload"])
    extra["families"]["not_required"] = "xilinx.com:ip:xlconstant:1.1"
    with self.assertRaisesRegex(ValueError, "extra.*not_required"):
        validate_production_lock(**{**fixture, "lock_payload": extra})


def test_lock_binds_discovery_not_realization_tcl(self) -> None:
    fixture = valid_lock_fixture()
    self.assertTrue(validate_production_lock(**fixture).valid)
    self.assertNotIn("realization_tcl_sha256", fixture["lock_payload"])
    self.assertNotIn(
        "realization_tcl_bytes",
        inspect.signature(validate_production_lock).parameters,
    )

    with self.assertRaisesRegex(ValueError, "generated_tcl_sha256"):
        validate_production_lock(
            **{
                **fixture,
                "discovery_tcl_bytes": b"changed discovery\n",
            }
        )


def test_promotion_writes_byte_identical_source_and_package_locks(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        candidate = root / "candidate.json"
        candidate.write_bytes(
            canonical_json_bytes(valid_lock_fixture()["lock_payload"])
        )
        promote_candidate_lock(
            candidate,
            root / "config/ip_lock.json",
            root / "src/rfsoc_pulse_model/config/ip_lock.json",
        )
        self.assertEqual(
            (root / "config/ip_lock.json").read_bytes(),
            (root / "src/rfsoc_pulse_model/config/ip_lock.json").read_bytes(),
        )
```

- [ ] **Step 2: Run lock tests and verify RED**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_lock -v
```

Expected: import failure for `rfsoc_pulse_model.ip.lock`.

- [ ] **Step 3: Implement production-lock parsing and exact validation**

Add these exact types:

```python
class GenerationMode(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ProductionLock:
    lock_schema_version: int
    architecture_config_sha256: str
    generated_tcl_sha256: str
    catalog_request_sha256: str
    vivado_version: str
    families: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProductionLockValidation:
    valid: bool
    lock: ProductionLock
```

Validate exact required-family set equality, exact RFDC 2.6, exact family identities, schema version 1, current architecture-config hash, discovery-Tcl hash, catalog-request hash, and Vivado version. The public validation function must not accept or compare realization Tcl provenance.

Add `GenerationMode.DEVELOPMENT` and `GenerationMode.PRODUCTION`. Development permits a missing source lock and reports `production_lock_valid=False`. Production rejects a missing, stale, wildcard, incomplete, or extra-family lock before emitting a ready manifest.

- [ ] **Step 4: Implement explicit promotion without normal-build source mutation**

The promotion CLI accepts:

```powershell
python -m rfsoc_pulse_model.ip.lock promote --candidate build/metadata/ip_lock.candidate.json --root-lock config/ip_lock.json --package-lock src/rfsoc_pulse_model/config/ip_lock.json
```

It must parse and validate the candidate before writing, create parent directories, write identical canonical bytes to both targets, and fail without modifying either target if validation fails. Normal `generate()` must never call promotion.

Add `ip_lock.json` to package data in `pyproject.toml`. Do not create a production lock from invented test versions; the real checked-in lock is produced by Task 7.

- [ ] **Step 5: Add generation-mode CLI and run lock tests**

Add `--ip-mode development|production` to `rfsoc_pulse_model.generate`. Pass the mode into `generate_ip_architecture()` and publish `production_lock_valid` in architecture metadata.

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_lock tests.ip.test_generate_architecture -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/rfsoc_pulse_model/ip/lock.py src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/generate.py src/rfsoc_pulse_model/ip/__init__.py pyproject.toml tests/ip/test_lock.py tests/ip/test_generate_architecture.py
git commit -m "feat: add exact production IP lock workflow"
```

---

### Task 6: Isolate legacy generated RTL from production artifacts

**Files:**
- Modify: `src/rfsoc_pulse_model/generate.py`
- Modify: `tests/verilog/test_generate.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `HARDWARE_MODULES` production flags and architecture readiness from Tasks 2 and 5.
- Produces: `build/reference_rtl/*.v`, manifest `production_rtl`, manifest `reference_rtl`, and a production source list containing no reference modules.

- [ ] **Step 1: Write failing reference-output isolation tests**

Change `tests/verilog/test_generate.py` to assert:

```python
def test_nonproduction_cycle_rtl_is_emitted_only_as_reference(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest = generate(root)
        self.assertFalse((root / "rtl/rx_group_ingress_2spc.v").exists())
        self.assertFalse((root / "rtl/tx_iq_axis_boundary_2spc.v").exists())
        self.assertTrue((root / "reference_rtl/rx_group_ingress_2spc.v").exists())
        self.assertTrue((root / "reference_rtl/tx_iq_axis_boundary_2spc.v").exists())
        self.assertEqual(manifest["production_rtl"], [])
        self.assertEqual(
            {item["verilog_file"] for item in manifest["reference_rtl"]},
            {
                "reference_rtl/rx_group_ingress_2spc.v",
                "reference_rtl/tx_iq_axis_boundary_2spc.v",
            },
        )
        self.assertFalse(
            manifest["ip_architecture"]["production_integration_ready"]
        )
```

Update the stale-file test to place an unregistered file separately in `rtl/` and `reference_rtl/` and require the error to name the affected scope.

- [ ] **Step 2: Run generator tests and verify RED**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.verilog.test_generate -v
```

Expected: failure because both legacy modules are still written under `rtl/` and the manifest has only one combined `modules` list.

- [ ] **Step 3: Route generated modules by production classification**

For each `HardwareModuleRegistration`, choose `rtl/` only when `registration.production` is true; otherwise choose `reference_rtl/`. Keep exact SHA, port, latency, and Cycle-class metadata. Publish separate `production_rtl` and `reference_rtl` arrays and retain `modules = production_rtl + reference_rtl` for current manifest compatibility.

During the directory migration, remove only old files under `build/rtl/` whose exact names belong to registered `production=False` modules and whose contents match the freshly generated reference bytes. If an old production-directory file with the same name has different bytes, fail as a possible hand edit. Never remove an unknown file.

Run stale-file detection independently for each generated directory. Never use a directory glob as the production source authority; the manifest list is authoritative.

- [ ] **Step 4: Feed reference-source contamination into readiness**

Pass `production_sources_contain_reference` into `ArchitectureRegistry.evaluate_readiness()` based on the explicit production list. A reference path or legacy registration appearing in `production_rtl` must force readiness false and fail the generator test.

- [ ] **Step 5: Update README and run generator regression**

Document `build/rtl/` as production-only, `build/reference_rtl/` as non-production verification output, and both Tcl paths with their distinct provenance.

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.verilog.test_generate tests.ip.test_registry -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/rfsoc_pulse_model/generate.py tests/verilog/test_generate.py README.md
git commit -m "refactor: isolate legacy RTL from production sources"
```

---

### Task 7: Resolve every required AMD IP in Vivado 2025.2 and promote the real lock

**Files:**
- Create: `config/ip_lock.json` from validated Vivado evidence
- Create: `src/rfsoc_pulse_model/config/ip_lock.json` as an identical copy
- Modify: `tests/ip/test_lock.py`
- Modify: `tests/ip/test_architecture_config.py`

**Interfaces:**
- Consumes: generated discovery Tcl, catalog request, evidence parser, candidate-lock builder, and promotion CLI from Tasks 3–5.
- Produces: checked-in exact production lock for the installed Vivado 2025.2 catalog.

- [ ] **Step 1: Run the complete Python suite before external validation**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

Expected: all tests PASS before Vivado evidence is introduced.

- [ ] **Step 2: Generate current discovery inputs in development mode**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.generate --output 'D:\AWAY\RFSOC\model\build' --ip-mode development
```

Read back `build/metadata/catalog_request.json` and verify it contains all 13 required families.

- [ ] **Step 3: Run discovery Tcl with the exact acyclic hash arguments**

```powershell
$request = Get-Content -LiteralPath 'D:\AWAY\RFSOC\model\build\metadata\catalog_request.json' -Raw | ConvertFrom-Json
& 'D:\app\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source 'D:\AWAY\RFSOC\model\build\vivado\discover_ip_catalog.tcl' -notrace -tclargs $request.architecture_config_sha256 $request.generated_tcl_sha256 $request.catalog_request_sha256
```

Expected: exit code 0 and `build/metadata/catalog_evidence.tsv` contains one metadata section plus exactly 13 unique `ip` rows. If the sandbox blocks Vivado user-app storage, rerun the identical command with user approval rather than changing Tcl or evidence paths.

- [ ] **Step 4: Ingest evidence and verify candidate lock provenance**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.generate --output 'D:\AWAY\RFSOC\model\build' --ip-mode development
```

Expected:

```text
catalog_resolution_status = all_required_ip_resolved
catalog_resolution_complete = true
production_lock_valid = false
production_integration_ready = false
```

Verify `build/metadata/ip_lock.candidate.json` family keys exactly equal the schema-v2 required family IDs and RFDC equals 2.6.

- [ ] **Step 5: Promote the candidate and verify byte identity**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.ip.lock promote --candidate 'D:\AWAY\RFSOC\model\build\metadata\ip_lock.candidate.json' --root-lock 'D:\AWAY\RFSOC\model\config\ip_lock.json' --package-lock 'D:\AWAY\RFSOC\model\src\rfsoc_pulse_model\config\ip_lock.json'
Get-FileHash -Algorithm SHA256 'D:\AWAY\RFSOC\model\config\ip_lock.json','D:\AWAY\RFSOC\model\src\rfsoc_pulse_model\config\ip_lock.json'
```

Expected: both SHA-256 values are identical.

- [ ] **Step 6: Verify production mode and realization skeleton separately**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.generate --output 'D:\AWAY\RFSOC\model\build' --ip-mode production
& 'D:\app\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source 'D:\AWAY\RFSOC\model\build\vivado\realize_ip_architecture.tcl' -notrace
```

Expected: production lock validates; realization creates only `rfdc_0`, reports `UNCONNECTED_SKELETON`, and does not call `validate_bd_design`. `production_integration_ready` remains false because parameters, connections, RFDC proof, custom production sources, and fractional-delay architecture are not accepted.

- [ ] **Step 7: Add default-lock regression and commit Task 7**

Add these default-lock assertions:

```python
def test_promoted_default_lock_is_current_and_byte_identical(self) -> None:
    root = Path(__file__).resolve().parents[2]
    root_bytes = (root / "config/ip_lock.json").read_bytes()
    package_bytes = (
        root / "src/rfsoc_pulse_model/config/ip_lock.json"
    ).read_bytes()
    self.assertEqual(root_bytes, package_bytes)

    config = HardwareArchitectureConfig.load_default()
    config_bytes = (
        root / "src/rfsoc_pulse_model/config/ip_architecture.json"
    ).read_bytes()
    discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_bytes = canonical_json_bytes(build_catalog_request(
        config,
        architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        generated_tcl_sha256=hashlib.sha256(discovery_bytes).hexdigest(),
    ))
    validation = validate_production_lock(
        config,
        request_bytes,
        discovery_bytes,
        json.loads(root_bytes),
    )
    self.assertTrue(validation.valid)
    self.assertEqual(
        set(json.loads(root_bytes)["families"]),
        {family.family_id for family in config.required_families()},
    )
    self.assertNotIn("realization_tcl_sha256", json.loads(root_bytes))
```

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_lock tests.ip.test_architecture_config -v
git add config/ip_lock.json src/rfsoc_pulse_model/config/ip_lock.json tests/ip/test_lock.py tests/ip/test_architecture_config.py
git commit -m "build: lock Vivado 2025.2 AMD IP catalog"
```

---

### Task 8: Run final regression and publish bounded acceptance evidence

**Files:**
- Modify: `README.md`
- Modify: `docs/contracts/amd-ip-ownership.md`
- Create: `docs/verification/amd-ip-normalization-acceptance.md`

**Interfaces:**
- Consumes: all code, generated artifacts, promoted lock, Python results, and Vivado logs from Tasks 1–7.
- Produces: auditable acceptance record and explicit remaining integration gates.

- [ ] **Step 1: Regenerate twice and check deterministic tracked inputs**

Run production generation twice, recording SHA-256 for:

```text
build/vivado/discover_ip_catalog.tcl
build/vivado/realize_ip_architecture.tcl
build/metadata/catalog_request.json
build/metadata/ip_architecture.json
build/manifest.json
```

Use:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m rfsoc_pulse_model.generate --output 'D:\AWAY\RFSOC\model\build' --ip-mode production
Get-FileHash -Algorithm SHA256 'build\vivado\discover_ip_catalog.tcl','build\vivado\realize_ip_architecture.tcl','build\metadata\catalog_request.json','build\metadata\ip_architecture.json','build\manifest.json'
```

Expected: identical hashes on both runs when external evidence and source inputs are unchanged.

- [ ] **Step 2: Run the complete Python suite**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

Expected: all tests PASS; record the exact count and elapsed time.

- [ ] **Step 3: Record the bounded Vivado evidence**

Create `docs/verification/amd-ip-normalization-acceptance.md` containing:

- branch and commit under test;
- Vivado full version;
- architecture config, discovery Tcl, request, evidence, lock, and realization Tcl hashes;
- exact resolved VLNV table for all 13 required families;
- proof that discovery created no cells;
- proof that realization created only `rfdc_0`;
- the three derived result values;
- Python test command and exact result;
- explicit statement that connected BD, IP parameters, `validate_bd_design`, CDC, timing, MTS/SYSREF, DMA/Ethernet, and board loopback remain unverified.

- [ ] **Step 4: Update README and ownership contract references**

Link the schema-v2 design, this implementation plan, the production lock, and the acceptance record. Replace old `create_ip_architecture.tcl` instructions with separate discovery and realization commands. Preserve the statement that generated files are not hand-edited.

- [ ] **Step 5: Run documentation and repository checks**

```powershell
rg -n "create_ip_architecture\.tcl|INITIAL_SKELETON_IP|vivado_2025_2_resolved" README.md src tests docs/contracts/amd-ip-ownership.md docs/verification/amd-ip-normalization-acceptance.md
git diff --check
git status --short
```

Expected: no live instruction, current contract, current acceptance record, source code, or test relies on old skeleton names/status; historical plans and the prior foundation acceptance remain unchanged; `git diff --check` passes; only intended documentation files are modified.

- [ ] **Step 6: Commit Task 8**

```powershell
git add README.md docs/contracts/amd-ip-ownership.md docs/verification/amd-ip-normalization-acceptance.md
git commit -m "docs: accept normalized AMD IP architecture"
```

---

## Spec Coverage Map

| Approved design requirement | Implemented and verified by |
|---|---|
| Schema-v2 family, instance, block, RFDC, and responsibility domains | Tasks 1–2 |
| Formal `architecture_pending` kind and status invariants | Tasks 1–2 |
| Production versus legacy responsibility scope isolation | Tasks 1–2 and 6 |
| Exact ownership completeness and independent readiness predicate | Task 2 |
| Catalog discovery versus instance realization separation | Task 3 |
| Acyclic config, discovery Tcl, request, evidence, candidate chain | Tasks 3–4 |
| Discovery-only `generated_tcl_sha256` provenance | Tasks 3–5 |
| Complete required-family evidence and stale-evidence rejection | Task 4 |
| Exact production lock and explicit promotion | Tasks 5 and 7 |
| Legacy RTL production-source isolation | Task 6 |
| Vivado 2025.2 full-family validation and bounded claims | Tasks 7–8 |

---

## Final Verification Checklist

- [ ] `config/ip_architecture.json` and installed package copy are byte-identical.
- [ ] `config/ip_lock.json` and installed package copy are byte-identical.
- [ ] Every required production responsibility has exactly one non-legacy owner.
- [ ] Legacy reference responsibilities use only the reserved namespace and do not enter production maps.
- [ ] Discovery Tcl contains no BD-cell creation.
- [ ] Realization Tcl creates only materialized instances.
- [ ] Discovery evidence resolves exactly all required families.
- [ ] Old or mismatched evidence reports stale and cannot produce a current candidate lock.
- [ ] Production lock family set is exact, uses RFDC 2.6, and binds discovery Tcl only.
- [ ] Legacy Verilog appears only under `build/reference_rtl/`.
- [ ] `responsibility_complete=true` can coexist truthfully with `production_integration_ready=false`.
- [ ] Full Python suite passes.
- [ ] Vivado catalog discovery and unconnected realization both complete under 2025.2.
- [ ] No connected-BD, CDC, timing, MTS/SYSREF, DMA/Ethernet, or board-level claim is made.
