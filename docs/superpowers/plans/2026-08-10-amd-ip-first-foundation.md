# AMD IP-First Hardware Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a machine-verifiable AMD IP-first architecture authority that locks RF Data Converter 2.6, separates RFDC integration metadata from algorithm contracts, classifies all production ownership, and generates reproducible Vivado IP Tcl and manifests without deleting the current verified legacy path.

**Architecture:** `ModelConfig` continues to own mathematical and PL-observable contracts. A separate packaged `HardwareArchitectureConfig` owns Vivado/IP integration. The existing RTL generator remains available but its two current modules are classified `legacy_non_production`; a new architecture generator emits exact RFDC 2.6 checks, catalog-resolved AMD IP skeleton cells and metadata. Later plans replace legacy modules only after AMD IP behavioral and integration gates pass.

**Tech Stack:** Python 3.12, NumPy, immutable dataclasses, JSON package data, unittest, Vivado 2025.2 Tcl, AMD IP Catalog, generated metadata/Tcl, Git checkpoints.

## Global Constraints

- RF Data Converter is exactly `xilinx.com:ip:usp_rf_data_converter:2.6`.
- RFDC owns ADC/DAC, DDC/DUC, RFDC interpolation/decimation, mixer/NCO and converter-internal behavior.
- Golden/Cycle/custom RTL must not reimplement RFDC-owned functions.
- PL AXIS width, I/Q/lane order, 2SPC, channel identity, clock/reset and continuity remain project contracts.
- Standard AXIS, FIR, DDS, complex multiply, CORDIC, memory and DMA functions are AMD IP/XPM-first.
- Existing DSL/RTL is not deleted until replacement simulation and integration gates pass.
- Every block has exactly one implementation classification: `amd_ip`, `xpm_macro`, `custom_rtl`, `custom_hls`, `software_only` or `legacy_non_production`.
- RFDC internal settings are integration metadata and cannot change Golden results.
- Generated Tcl/metadata must be byte-identical across repeated generation.
- Python/XSIM does not prove RFDC readback, CDC, timing, MTS/SYSREF or board RF behavior.
- Use bundled Python `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` with `PYTHONPATH=D:\AWAY\RFSOC\model\src`.
- Work in the existing branch and create one local commit per task; do not push.

---

## File Structure

| Path | Responsibility |
|---|---|
| `config/ip_architecture.json` | Source-tree mirror of IP/Vivado integration authority |
| `src/rfsoc_pulse_model/config/ip_architecture.json` | Installed package-data copy |
| `src/rfsoc_pulse_model/ip/types.py` | Immutable IP, RFDC integration and architecture types |
| `src/rfsoc_pulse_model/ip/registry.py` | Single block-ownership and implementation-kind registry |
| `src/rfsoc_pulse_model/ip/tcl.py` | Deterministic Vivado catalog/skeleton Tcl emitter |
| `src/rfsoc_pulse_model/ip/generate.py` | IP architecture metadata/Tcl generation orchestration |
| `src/rfsoc_pulse_model/ip/catalog.py` | Parse and validate Vivado-resolved IP VLNV evidence |
| `src/rfsoc_pulse_model/ip/__init__.py` | Public architecture API |
| `src/rfsoc_pulse_model/generate.py` | Transitional top-level generator for legacy RTL plus IP artifacts |
| `src/rfsoc_pulse_model/common/rfdc_axis.py` | PL-visible RFDC AXIS word contract only |
| `src/rfsoc_pulse_model/common/config.py` | Algorithm/Cycle configuration only |
| `src/rfsoc_pulse_model/cycle/registry.py` | Legacy RTL registration with explicit non-production status |
| `tests/ip/test_architecture_config.py` | Exact RFDC/version/config separation tests |
| `tests/ip/test_registry.py` | Ownership collision and production-policy tests |
| `tests/ip/test_tcl.py` | Deterministic Tcl and exact-VLNV tests |
| `tests/ip/test_catalog.py` | Vivado resolution evidence parser tests |
| `tests/verilog/test_generate.py` | Transitional combined-manifest regression |
| `docs/contracts/amd-ip-ownership.md` | Published production ownership contract |
| `docs/contracts/rfdc-axis-word-format.md` | PL-only RFDC interface contract |
| `docs/verification/amd-ip-foundation-acceptance.md` | Commands, results and remaining proof boundaries |

---

### Task 1: Add the packaged IP architecture authority and exact RFDC 2.6 gate

**Files:**
- Create: `config/ip_architecture.json`
- Create: `src/rfsoc_pulse_model/config/ip_architecture.json`
- Create: `src/rfsoc_pulse_model/ip/__init__.py`
- Create: `src/rfsoc_pulse_model/ip/types.py`
- Modify: `pyproject.toml`
- Create: `tests/ip/__init__.py`
- Create: `tests/ip/test_architecture_config.py`

**Interfaces:**
- Consumes: installed JSON package data.
- Produces: `ImplementationKind`, `ExternalIpSpec`, `RfdcIntegrationMetadata`, and `HardwareArchitectureConfig.load_default()`.

- [ ] **Step 1: Write the failing exact-version and package-data tests**

Create `tests/ip/test_architecture_config.py` with these minimum behaviors:

```python
import dataclasses
import json
from pathlib import Path
import unittest

from rfsoc_pulse_model.ip.types import (
    HardwareArchitectureConfig,
    ImplementationKind,
)


class HardwareArchitectureConfigTest(unittest.TestCase):
    @staticmethod
    def root_payload() -> dict:
        root = Path(__file__).resolve().parents[2]
        return json.loads(
            (root / "config/ip_architecture.json").read_text(encoding="utf-8")
        )

    def test_default_locks_exact_rfdc_2_6_black_box(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        self.assertEqual(
            config.rfdc.ip.vlnv,
            "xilinx.com:ip:usp_rf_data_converter:2.6",
        )
        self.assertEqual(config.rfdc.ip.kind, ImplementationKind.AMD_IP)
        self.assertEqual(config.vivado_version, "2025.2")
        self.assertEqual(config.generation_mode, "vivado_ip_first")
        self.assertEqual(
            set(config.rfdc.owned_functions),
            {"adc", "dac", "ddc", "duc", "decimation", "interpolation", "mixer", "nco"},
        )

    def test_other_rfdc_version_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["rfdc"]["ip"]["vlnv"] = (
            "xilinx.com:ip:usp_rf_data_converter:2.7"
        )
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            HardwareArchitectureConfig.from_mapping(payload)

    def test_installed_and_root_config_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "config/ip_architecture.json").read_bytes(),
            (root / "src/rfsoc_pulse_model/config/ip_architecture.json").read_bytes(),
        )

    def test_dataclass_replace_cannot_bypass_rfdc_gate(self) -> None:
        config = HardwareArchitectureConfig.load_default()
        bad_ip = dataclasses.replace(
            config.rfdc.ip,
            vlnv="xilinx.com:ip:usp_rf_data_converter:2.5",
        )
        with self.assertRaisesRegex(ValueError, "usp_rf_data_converter:2.6"):
            dataclasses.replace(config.rfdc, ip=bad_ip)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_architecture_config -v
```

Expected: import failure for `rfsoc_pulse_model.ip.types` or missing `ip_architecture.json`.

- [ ] **Step 3: Add the exact JSON authority**

Both JSON copies must be byte-identical and start with this complete top-level contract:

```json
{
  "architecture_schema_version": 1,
  "architecture_config_version": 1,
  "vivado_version": "2025.2",
  "generation_mode": "vivado_ip_first",
  "topology_status": "unconnected_skeleton",
  "rfdc": {
    "ip": {
      "logical_name": "rfdc",
      "kind": "amd_ip",
      "vlnv": "xilinx.com:ip:usp_rf_data_converter:2.6",
      "catalog_pattern": "xilinx.com:ip:usp_rf_data_converter:2.6"
    },
    "owned_functions": ["adc", "dac", "ddc", "duc", "decimation", "interpolation", "mixer", "nco"],
    "configuration_authority": "vivado_block_design",
    "dac_analog_output_type": "real",
    "dac_mixer_mode": "iq_to_real",
    "dac_mixer_scale_mode": "unity_0db",
    "dac_nco_frequency_hz": 2800000000,
    "proof_status": "unverified"
  },
  "required_ip_families": [
    {"logical_name": "axis_register_slice", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_register_slice:*"},
    {"logical_name": "axis_data_fifo", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_data_fifo:*"},
    {"logical_name": "axis_clock_converter", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_clock_converter:*"},
    {"logical_name": "axis_dwidth_converter", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_dwidth_converter:*"},
    {"logical_name": "axis_combiner", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_combiner:*"},
    {"logical_name": "axis_broadcaster", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_broadcaster:*"},
    {"logical_name": "axis_switch", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axis_switch:*"},
    {"logical_name": "fir_compiler", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:fir_compiler:*"},
    {"logical_name": "dds_compiler", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:dds_compiler:*"},
    {"logical_name": "complex_multiplier", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:cmpy:*"},
    {"logical_name": "cordic", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:cordic:*"},
    {"logical_name": "axi_dma", "kind": "amd_ip", "catalog_pattern": "xilinx.com:ip:axi_dma:*"}
  ]
}
```

- [ ] **Step 4: Implement immutable typed loading**

In `ip/types.py`, implement `str, Enum` `ImplementationKind` with all six values from Global Constraints. Implement immutable dataclasses with validation in `__post_init__`:

```python
RFDC_2_6_VLNV = "xilinx.com:ip:usp_rf_data_converter:2.6"

@dataclass(frozen=True)
class ExternalIpSpec:
    logical_name: str
    kind: ImplementationKind
    catalog_pattern: str
    vlnv: str | None = None

@dataclass(frozen=True)
class RfdcIntegrationMetadata:
    ip: ExternalIpSpec
    owned_functions: tuple[str, ...]
    configuration_authority: str
    dac_analog_output_type: str
    dac_mixer_mode: str
    dac_mixer_scale_mode: str
    dac_nco_frequency_hz: int
    proof_status: str

@dataclass(frozen=True)
class HardwareArchitectureConfig:
    architecture_schema_version: int
    architecture_config_version: int
    vivado_version: str
    generation_mode: str
    topology_status: str
    rfdc: RfdcIntegrationMetadata
    required_ip_families: tuple[ExternalIpSpec, ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "HardwareArchitectureConfig": ...

    @classmethod
    def load_default(cls) -> "HardwareArchitectureConfig": ...
```

Validation must require exact RFDC VLNV, `amd_ip`, Vivado `2025.2`, generation mode `vivado_ip_first`, topology status `unconnected_skeleton`, nonempty unique logical names, and exactly the eight RFDC-owned functions in the JSON above.

Modify package data to include both JSON resources:

```toml
[tool.setuptools.package-data]
"rfsoc_pulse_model.config" = ["default.json", "ip_architecture.json"]
```

- [ ] **Step 5: Run focused and full tests**

Run the focused test, then `python -m unittest discover -s tests -v`. Expected: all existing tests plus the new architecture tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add pyproject.toml config/ip_architecture.json src/rfsoc_pulse_model/config/ip_architecture.json src/rfsoc_pulse_model/ip tests/ip
git commit -m "feat: add AMD IP architecture authority"
```

---

### Task 2: Separate RFDC internal metadata from the PL word contract

**Files:**
- Modify: `config/default.json`
- Modify: `src/rfsoc_pulse_model/config/default.json`
- Modify: `src/rfsoc_pulse_model/common/rfdc_axis.py`
- Modify: `src/rfsoc_pulse_model/common/config.py`
- Modify: `tests/golden/test_config.py`
- Modify: `tests/ip/test_architecture_config.py`
- Modify: `tests/verilog/test_generate.py`

**Interfaces:**
- Consumes: `HardwareArchitectureConfig.rfdc` from Task 1.
- Produces: PL-only `RfdcAxisWordFormat`; `ModelConfig` schema/config `13/19`.

- [ ] **Step 1: Write failing separation tests**

Add assertions that `RfdcAxisWordFormat` exposes only the digital interface and that integration metadata owns the removed fields:

```python
def test_rfdc_axis_contract_excludes_converter_internal_metadata(self) -> None:
    axis = ModelConfig.load_default().rfdc_axis
    for name in (
        "dac_analog_output_type",
        "dac_mixer_mode",
        "dac_mixer_scale_mode",
        "dac_nco_frequency_hz",
    ):
        self.assertFalse(hasattr(axis, name), name)

def test_rfdc_internal_settings_live_only_in_architecture_config(self) -> None:
    architecture = HardwareArchitectureConfig.load_default()
    self.assertEqual(architecture.rfdc.dac_mixer_mode, "iq_to_real")
    self.assertEqual(architecture.rfdc.dac_nco_frequency_hz, 2_800_000_000)
```

Change the generation test to require these values under `manifest["ip_architecture"]["rfdc"]`, not top-level algorithm fields.

- [ ] **Step 2: Run and verify RED**

Expected: `hasattr(axis, ...)` is still true and the transitional manifest has no `ip_architecture` object.

- [ ] **Step 3: Remove the four integration fields from the PL contract**

Remove the fields, mapping loads and internal-setting validation from `RfdcAxisWordFormat`. Keep these fields unchanged:

```text
dac_data_type
dac_component_width_bits
dac_axis_width_bits
dac_complex_samples_per_cycle
dac_component_order
dac_axis_names
```

Delete the four fields from both `default.json` `rfdc_axis_format` objects. Remove this algorithm coupling from `ModelConfig.validate()`:

```python
if self.rfdc_axis.dac_nco_frequency_hz != self.center_frequency_hz:
    raise ValueError(...)
```

Set both model JSON copies to `model_schema_version=13` and `config_version=19` and update exact-version tests/documentation references.

- [ ] **Step 4: Preserve PL rate validation**

Keep and test the equations that affect the PL boundary:

```text
ADC PL complex rate = ADC converter rate / RFDC decimation
ADC PL complex rate = fabric clock * ADC complex SPC
DAC PL complex rate = DAC converter rate / RFDC interpolation
DAC PL complex rate = fabric clock * DAC complex SPC
```

These equations describe observable ports, not a local implementation of RFDC internals.

- [ ] **Step 5: Run focused and full tests**

Expected: config mirrors are byte-identical; no Golden module imports `rfsoc_pulse_model.ip`; all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add config/default.json src/rfsoc_pulse_model/config/default.json src/rfsoc_pulse_model/common/rfdc_axis.py src/rfsoc_pulse_model/common/config.py tests/golden/test_config.py tests/ip/test_architecture_config.py tests/verilog/test_generate.py
git commit -m "refactor: separate RFDC metadata from PL contracts"
```

---

### Task 3: Add the single production-ownership registry and classify legacy RTL

**Files:**
- Create: `src/rfsoc_pulse_model/ip/registry.py`
- Modify: `src/rfsoc_pulse_model/cycle/registry.py`
- Create: `tests/ip/test_registry.py`

**Interfaces:**
- Consumes: `ImplementationKind` and architecture IP specs.
- Produces: `ArchitectureBlock`, `ArchitectureRegistry.default()`, `production_blocks()`, and `legacy_blocks()`.

- [ ] **Step 1: Write failing ownership tests**

```python
import unittest

from rfsoc_pulse_model.ip.registry import (
    ArchitectureBlock,
    ArchitectureRegistry,
)
from rfsoc_pulse_model.ip.types import ImplementationKind


class ArchitectureRegistryTest(unittest.TestCase):
    def test_rfdc_functions_have_one_amd_ip_owner(self) -> None:
        registry = ArchitectureRegistry.default()
        rfdc = registry.by_name("rfdc")
        self.assertEqual(rfdc.kind, ImplementationKind.AMD_IP)
        self.assertEqual(rfdc.vlnv, "xilinx.com:ip:usp_rf_data_converter:2.6")

    def test_current_generated_adapters_are_explicitly_legacy(self) -> None:
        registry = ArchitectureRegistry.default()
        self.assertEqual(
            {block.logical_name for block in registry.legacy_blocks()},
            {"rx_group_ingress_2spc", "tx_iq_axis_boundary_2spc"},
        )

    def test_duplicate_production_function_owner_is_rejected(self) -> None:
        duplicate = ArchitectureBlock(
            logical_name="custom_nco",
            kind=ImplementationKind.CUSTOM_RTL,
            responsibilities=("nco",),
            production=True,
        )
        with self.assertRaisesRegex(ValueError, "nco.*multiple production owners"):
            ArchitectureRegistry((*ArchitectureRegistry.default().blocks, duplicate))
```

- [ ] **Step 2: Run and verify RED**

Expected: import failure for `ip.registry`.

- [ ] **Step 3: Implement the immutable registry**

Use this public shape:

```python
@dataclass(frozen=True)
class ArchitectureBlock:
    logical_name: str
    kind: ImplementationKind
    responsibilities: tuple[str, ...]
    production: bool
    vlnv: str | None = None
    source: str | None = None

@dataclass(frozen=True)
class ArchitectureRegistry:
    blocks: tuple[ArchitectureBlock, ...]

    @classmethod
    def default(cls) -> "ArchitectureRegistry": ...
    def by_name(self, logical_name: str) -> ArchitectureBlock: ...
    def production_blocks(self) -> tuple[ArchitectureBlock, ...]: ...
    def legacy_blocks(self) -> tuple[ArchitectureBlock, ...]: ...
```

`default()` must register RFDC 2.6 and the standard AMD IP responsibilities from the design. Register both current Cycle modules as `legacy_non_production`, `production=False`, with their Python source paths. Validation rejects duplicate logical names, empty responsibilities, `production=True` with `legacy_non_production`, and duplicate production ownership of one responsibility.

Add `implementation_kind=ImplementationKind.LEGACY_NON_PRODUCTION` and `production=False` to each `HardwareModuleRegistration`. The legacy generator may still emit them during migration.

- [ ] **Step 4: Run registry, generation and full tests**

Expected: existing RTL generation remains reproducible; registry reports no custom production owner for RFDC, AXIS transport or FIR.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/rfsoc_pulse_model/ip/registry.py src/rfsoc_pulse_model/cycle/registry.py tests/ip/test_registry.py
git commit -m "feat: classify AMD IP and legacy hardware ownership"
```

---

### Task 4: Generate reproducible IP architecture metadata beside legacy RTL

**Files:**
- Create: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/generate.py`
- Modify: `tests/verilog/test_generate.py`
- Create: `tests/ip/test_generate_architecture.py`

**Interfaces:**
- Consumes: `HardwareArchitectureConfig` and `ArchitectureRegistry`.
- Produces: `generate_ip_architecture(output_root: Path) -> dict[str, object]`, `build/metadata/ip_architecture.json`, and combined `manifest.json`.

- [ ] **Step 1: Write failing architecture-manifest tests**

```python
def test_architecture_manifest_separates_external_ip_and_legacy_rtl(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = generate(Path(temporary))
        architecture = manifest["ip_architecture"]
        self.assertEqual(
            architecture["rfdc"]["vlnv"],
            "xilinx.com:ip:usp_rf_data_converter:2.6",
        )
        self.assertEqual(architecture["topology_status"], "unconnected_skeleton")
        self.assertFalse(architecture["integration_accepted"])
        self.assertEqual(
            {module["implementation_kind"] for module in manifest["modules"]},
            {"legacy_non_production"},
        )
        self.assertTrue(all(not module["production"] for module in manifest["modules"]))
```

Also assert `ip_architecture.json` equals the returned nested object and has hashes for both source architecture JSON and generated Tcl once Task 5 adds it.

- [ ] **Step 2: Run and verify RED**

Expected: missing `ip_architecture` manifest member.

- [ ] **Step 3: Implement deterministic metadata generation**

`generate_ip_architecture()` returns JSON-serializable data containing:

```text
architecture_schema_version
architecture_config_version
vivado_version
generation_mode
topology_status
integration_accepted = false
rfdc {logical_name, kind, vlnv, owned_functions, integration metadata}
required_ip_families [{logical_name, kind, catalog_pattern}]
blocks [{logical_name, kind, production, responsibilities, vlnv/source}]
source_config_sha256
```

Write sorted, indented JSON plus one trailing newline. Modify the transitional top generator so each legacy module includes `implementation_kind` and `production`, and the top manifest contains `ip_architecture` plus its SHA-256. Do not remove existing numeric-format and legacy RTL hashes.

- [ ] **Step 4: Run generation twice and compare hashes**

Generate into one temporary directory twice. Hash every file before and after; require no differences.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/generate.py tests/ip/test_generate_architecture.py tests/verilog/test_generate.py
git commit -m "feat: generate IP architecture manifest"
```

---

### Task 5: Emit an explicit non-accepted Vivado IP skeleton Tcl

**Files:**
- Create: `src/rfsoc_pulse_model/ip/tcl.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Create: `tests/ip/test_tcl.py`

**Interfaces:**
- Consumes: architecture config and registry.
- Produces: `emit_ip_skeleton_tcl(config, registry) -> str` and `build/vivado/create_ip_architecture.tcl`.

- [ ] **Step 1: Write failing exact-Tcl tests**

```python
def test_tcl_requires_exact_rfdc_and_marks_skeleton_nonaccepted(self) -> None:
    tcl = emit_ip_skeleton_tcl(
        HardwareArchitectureConfig.load_default(),
        ArchitectureRegistry.default(),
    )
    self.assertIn(
        "set rfdc_vlnv {xilinx.com:ip:usp_rf_data_converter:2.6}",
        tcl,
    )
    self.assertIn("require_exact_ip $rfdc_vlnv", tcl)
    self.assertIn("create_bd_cell -type ip -vlnv $rfdc_vlnv rfdc", tcl)
    self.assertIn("set topology_status {unconnected_skeleton}", tcl)
    self.assertIn("set integration_accepted 0", tcl)
    self.assertNotIn("validate_bd_design", tcl)

def test_tcl_declares_initial_axis_and_fir_cells(self) -> None:
    tcl = emit_ip_skeleton_tcl(...)
    for logical_name in (
        "axis_register_slice",
        "axis_data_fifo",
        "axis_clock_converter",
        "axis_dwidth_converter",
        "axis_combiner",
        "axis_broadcaster",
        "axis_switch",
        "fir_compiler",
    ):
        self.assertIn(f"resolve_catalog_ip {{{logical_name}}}", tcl)
```

- [ ] **Step 2: Run and verify RED**

Expected: import failure for `ip.tcl`.

- [ ] **Step 3: Implement deterministic Tcl emission**

The emitted script must:

1. check Vivado version begins `2025.2`;
2. create an in-memory project for `xczu27dr-fsve1156-2-i` if no project exists;
3. create BD `ip_architecture_skeleton` if no BD is open;
4. define `require_exact_ip` that errors unless the exact RFDC 2.6 VLNV resolves;
5. define `resolve_catalog_ip` that sorts `get_ipdefs -all $pattern` and selects the highest catalog version deterministically;
6. create the RFDC cell with the exact VLNV;
7. create the eight initial AXIS/FIR skeleton cells listed in the test using resolved VLNVs;
8. write `logical_name<TAB>resolved_vlnv` evidence to `build/metadata/resolved_ip_vlnv.tsv`;
9. print `IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON`;
10. omit all net connections, RFDC property acceptance, `validate_bd_design` and acceptance claims.

The skeleton is intentionally non-accepted. It proves catalog availability and exact ownership only. A later topology plan adds explicit IP properties and connections.

- [ ] **Step 4: Add Tcl hash to architecture metadata**

Write `build/vivado/create_ip_architecture.tcl` before serializing architecture JSON. Add `generated_tcl_sha256` and verify repeated generation is byte-identical.

- [ ] **Step 5: Run focused, generation and full tests**

Expected: exact RFDC 2.6 appears once as the RFDC cell VLNV; no legacy RTL is called production; all tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/rfsoc_pulse_model/ip/tcl.py src/rfsoc_pulse_model/ip/generate.py tests/ip/test_tcl.py
git commit -m "feat: emit Vivado AMD IP skeleton Tcl"
```

---

### Task 6: Resolve and validate the Vivado 2025.2 IP catalog evidence

**Files:**
- Create: `src/rfsoc_pulse_model/ip/catalog.py`
- Create: `tests/ip/test_catalog.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`

**Interfaces:**
- Consumes: `resolved_ip_vlnv.tsv` written by generated Tcl.
- Produces: `parse_resolved_ip_vlnv(text: str) -> dict[str, str]` and `validate_resolved_catalog(config, resolved) -> None`.

- [ ] **Step 1: Write failing parser and validation tests**

```python
def test_catalog_parser_requires_exact_rfdc_2_6(self) -> None:
    resolved = parse_resolved_ip_vlnv(
        "rfdc\txilinx.com:ip:usp_rf_data_converter:2.6\n"
        "fir_compiler\txilinx.com:ip:fir_compiler:7.2\n"
    )
    self.assertEqual(resolved["rfdc"], RFDC_2_6_VLNV)
    validate_resolved_catalog(HardwareArchitectureConfig.load_default(), resolved)

def test_catalog_validation_rejects_wrong_rfdc_version(self) -> None:
    with self.assertRaisesRegex(ValueError, "RF Data Converter 2.6"):
        validate_resolved_catalog(
            HardwareArchitectureConfig.load_default(),
            {"rfdc": "xilinx.com:ip:usp_rf_data_converter:2.7"},
        )

def test_catalog_parser_rejects_duplicate_logical_name(self) -> None:
    with self.assertRaisesRegex(ValueError, "duplicate"):
        parse_resolved_ip_vlnv("rfdc\ta:1\nrfdc\ta:2\n")
```

- [ ] **Step 2: Run and verify RED**

Expected: import failure for `ip.catalog`.

- [ ] **Step 3: Implement strict TSV parsing and validation**

Reject blank logical names/VLNVs, malformed rows, duplicates, missing RFDC, wrong RFDC, and any missing required initial skeleton family. Do not accept a family by substring; compare each resolved VLNV vendor/library/name against the configured catalog pattern after removing its terminal `:*`.

- [ ] **Step 4: Execute generated Tcl with Vivado 2025.2**

Run:

```powershell
& 'D:\app\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source 'D:\AWAY\RFSOC\model\build\vivado\create_ip_architecture.tcl' -notrace
```

Expected: exit code 0, `IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON`, exact RFDC 2.6 resolution, and a TSV row for every initial skeleton IP. This does not run `validate_bd_design` because the topology is deliberately unconnected.

- [ ] **Step 5: Validate and publish resolved evidence**

Parse the TSV, validate it, and write sorted `build/metadata/resolved_ip_vlnv.json` with a trailing newline. Add its SHA-256 and `catalog_resolution_status="vivado_2025_2_resolved"` to the architecture manifest only after validation succeeds. If Vivado cannot resolve an IP, leave status `unverified` and fail this task rather than inventing a version.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/rfsoc_pulse_model/ip/catalog.py src/rfsoc_pulse_model/ip/generate.py tests/ip/test_catalog.py
git commit -m "test: validate Vivado AMD IP catalog resolution"
```

---

### Task 7: Publish the new authority and close the foundation checkpoint

**Files:**
- Create: `docs/contracts/amd-ip-ownership.md`
- Modify: `docs/contracts/rfdc-axis-word-format.md`
- Modify: `README.md`
- Create: `docs/verification/amd-ip-foundation-acceptance.md`
- Modify: `docs/verification/polarimetric-golden-acceptance.md`

**Interfaces:**
- Consumes: all generated and Vivado evidence from Tasks 1-6.
- Produces: human-readable ownership, migration status and verification boundaries.

- [ ] **Step 1: Document exact ownership and current migration state**

`amd-ip-ownership.md` must list each registry block, implementation kind, production flag, responsibility and IP catalog pattern/VLNV. State explicitly:

```text
RFDC 2.6 and AMD standard IP are production targets.
rx_group_ingress_2spc and tx_iq_axis_boundary_2spc are legacy references.
The skeleton is not a connected or validated Block Design.
No DSL file is deleted in this foundation checkpoint.
```

- [ ] **Step 2: Update the RFDC word contract**

Keep PL word layout unchanged, but remove statements that make mixer/NCO fields part of `RfdcAxisWordFormat`. Link them to `HardwareArchitectureConfig.rfdc` and state that Golden/Cycle cannot depend on them.

- [ ] **Step 3: Record acceptance evidence**

The acceptance document records:

- branch and commit under test;
- Python executable and test count;
- SHA-256 for both configuration authorities, generated Tcl and manifests;
- exact RFDC resolution row;
- every resolved initial IP VLNV from Vivado 2025.2;
- repeated-generation result;
- `topology_status=unconnected_skeleton` and `integration_accepted=false`;
- open gates: IP properties, connections, behavioral IP simulations, BD validation, CDC, timing and board loopback.

- [ ] **Step 4: Run final foundation verification**

Run in this order:

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\model\src'
$python='C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -m unittest discover -s tests -v
& $python -m rfsoc_pulse_model.generate --output build
& $python -m rfsoc_pulse_model.generate --output build
& 'D:\app\AMD\2025.2\Vivado\bin\vivado.bat' -mode batch -source 'D:\AWAY\RFSOC\model\build\vivado\create_ip_architecture.tcl' -notrace
git diff --check
```

Compare file hashes around the two generation calls. Acceptance requires zero Python failures, byte-identical repeated generation, Vivado exit 0, exact RFDC 2.6, every initial catalog family resolved, and clean diff checks. Do not run or claim connected-BD validation.

- [ ] **Step 5: Commit the foundation checkpoint**

```powershell
git add README.md docs/contracts docs/verification
git commit -m "docs: accept AMD IP-first foundation"
```

- [ ] **Step 6: Review checkpoint**

Confirm the branch is clean and list the next implementation plan scope: explicit RFDC/AXIS/FIR properties, connected RX monitor topology, FIR Compiler behavioral vectors, and replacement gating for `rx_group_ingress_2spc`. No other legacy module may be removed before that plan passes.

---

## Self-Review

- **Spec coverage:** The plan covers exact RFDC 2.6 locking, configuration separation, AMD IP ownership, legacy classification, deterministic Tcl/metadata generation, Vivado catalog evidence and published proof boundaries. It intentionally defers connected topology, complete IP parameterization and legacy deletion as required by the design scope.
- **No placeholders:** Every deferred item is an explicit later-plan scope, not an unspecified requirement of this plan. The first Tcl output is deliberately and machine-readably `unconnected_skeleton` with `integration_accepted=false`.
- **Type consistency:** Tasks consistently use `HardwareArchitectureConfig`, `RfdcIntegrationMetadata`, `ExternalIpSpec`, `ImplementationKind`, `ArchitectureBlock`, `ArchitectureRegistry`, `generate_ip_architecture`, `emit_ip_skeleton_tcl`, `parse_resolved_ip_vlnv` and `validate_resolved_catalog`.
- **Safety:** The plan does not edit the live Block Design, remove the DSL, claim timing/CDC closure, or infer unavailable IP versions.

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-08-10-amd-ip-first-foundation.md`.

Execution is intended to run inline in the current branch using `superpowers:executing-plans`, in batches with a local commit and review checkpoint after each task. No push is authorized.
