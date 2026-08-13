# Connected RFDC Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development`. Implement each task with TDD,
> commit it separately, and require an independent task review before moving
> to the next task.

**Goal:** Build and machine-verify a fresh Vivado 2025.2 Block Design containing
the ZU27DR PS, RF Data Converter 2.6, explicit control/reset/interrupt plumbing,
and all 8 ADC plus 8 DAC interfaces at the frozen 250 MHz, 2SPC boundary.

**Architecture:** `ModelConfig` remains the sampling, word-format and physical
mapping authority. Schema-v2 `HardwareArchitectureConfig` advances to a new
configuration revision and materializes the connected platform instances. A
separate packaged `PsPlatformConfig` owns the reviewed PS board properties and
100 MHz AXI-Lite control clock. Python emits deterministic catalog,
connected-realization and verification Tcl. Strict catalog and connected-BD
evidence remain separate, and overall production integration stays false.

**Tech Stack:** Python 3.12, immutable dataclasses/enums, canonical JSON,
`unittest`, Vivado 2025.2 Tcl, Zynq UltraScale+ MPSoC, RF Data Converter 2.6,
AXI SmartConnect, Processor System Reset, SHA-256, Git checkpoints.

## Global Constraints

- Work only in
  `D:\AWAY\RFSOC\.worktrees\connected-bd-rfdc-shell-20260813` on branch
  `connected-bd-rfdc-shell-20260813`; do not modify, merge, push, or delete
  `model-update-20260811`.
- Use
  `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
  with `PYTHONPATH` set to this worktree's `src`.
- Use `D:\app\AMD\2025.2\Vivado\bin\vivado.bat` for real Vivado runs.
- Every implementation task follows RED -> GREEN -> focused regression ->
  full relevant regression -> commit -> independent task review.
- Do not stop for routine approvals. If one technical blocker survives three
  materially different evidence-driven attempts, record the attempts and stop.
- `ModelConfig` remains the only authority for device part, 4 GSPS rates,
  RFDC x8 rate change, 250 MHz data clocks, 2SPC, 8 ADC/8 DAC mapping and AXIS
  word layout.
- RFDC is exactly `xilinx.com:ip:usp_rf_data_converter:2.6`.
- The control domain is explicitly 100 MHz. RX and TX data domains are
  separately 250 MHz.
- The RX candidate common clock is `rfdc_0/clk_adc0` fanned to
  `m0_axis_aclk` through `m3_axis_aclk`. The TX candidate common clock is
  `rfdc_0/clk_dac0` fanned to `s0_axis_aclk` and `s1_axis_aclk`. If real
  Vivado rejects either, fail closed; do not silently add CDC.
- Export exactly 16 ADC component AXIS interfaces and 8 DAC complex AXIS
  interfaces. Never omit Q streams or reinterpret odd ADC streams as physical
  channels.
- No legacy 2SPC RTL, detector, event DMA, TX DMA, DDR data master or GEM data
  plane enters this BD checkpoint.
- Catalog discovery creates no BD/cells/connections. The production lock's
  `generated_tcl_sha256` continues to bind discovery Tcl only.
- Connected realization and verification have separate SHA-256 provenance in
  connected evidence.
- BD automation may not insert an undeclared family or cell.
- Never hand-edit generated Tcl, evidence, candidate lock, production lock,
  manifest, BD, wrapper, or generated RTL.
- A partial/interrupted Vivado evidence file is invalid and cannot make shell
  readiness true.
- `connected.py` is a pure data layer. It must not acquire locks, create
  attempt directories, launch Vivado, run subprocesses, or publish lifecycle
  markers.
- Every real connected attempt first invalidates canonical success with an
  atomically published, run-ID-bound `in_progress` marker under a
  repository-scoped advisory lock. Only an all-green attempt may atomically
  publish `success`; a failed retry can never reuse an older success. This
  lifecycle belongs to Task 5's runner and is exercised with real Vivado only
  in Task 6.
- `production_integration_ready` remains false throughout this plan.
- Do not claim post-route timing, bitstream, MTS runtime, DMA/Ethernet, board
  loopback or analogue mapping closure.

## Preflight State

- Branch base: `dc31c5c`.
- Worktree checkout reproducibility fix: `0acd377`.
- Baseline after the fix: 218 tests passed, 8 Windows symlink-permission skips.
- Design authority:
  `docs/superpowers/specs/2026-08-13-connected-rfdc-shell-design.md`.

## Planned File Structure

| Path | Responsibility |
|---|---|
| `config/ps_platform.json` | Source-tree PS board/platform authority |
| `src/rfsoc_pulse_model/config/ps_platform.json` | Byte-identical package data |
| `src/rfsoc_pulse_model/ip/platform.py` | Strict `PsPlatformConfig` types/parser |
| `src/rfsoc_pulse_model/ip/connected.py` | Connected request/evidence types and validation |
| `src/rfsoc_pulse_model/ip/rfdc_probe.py` | RFDC-only property and port probe Tcl |
| `src/rfsoc_pulse_model/ip/connected_tcl.py` | Deterministic realization/verification Tcl |
| `src/rfsoc_pulse_model/ip/connected_runner.py` | Advisory lock, attempt lifecycle and Vivado launcher |
| `src/rfsoc_pulse_model/ip/generate.py` | Catalog plus connected artifact orchestration |
| `config/ip_architecture.json` | Connected topology, families and instances |
| `src/rfsoc_pulse_model/config/ip_architecture.json` | Byte-identical package authority |
| `config/ip_lock.json` | Newly promoted exact production family lock |
| `src/rfsoc_pulse_model/config/ip_lock.json` | Byte-identical package lock |
| `tests/ip/test_platform.py` | Platform config and extraction tests |
| `tests/ip/test_connected.py` | Request/evidence/readiness tests |
| `tests/ip/test_rfdc_probe.py` | Probe generation and strict diagnostic evidence tests |
| `tests/ip/test_connected_tcl.py` | Generated Tcl structural tests |
| `tests/ip/test_connected_runner.py` | Transactional lifecycle and injected-launcher tests |
| `docs/contracts/connected-rfdc-shell.md` | Published interface and proof contract |
| `docs/verification/connected-rfdc-shell-acceptance.md` | Final measured checkpoint |

---

### Task 1: Extract and freeze the PS platform authority

**Files:**

- Create: `config/ps_platform.json`
- Create: `src/rfsoc_pulse_model/config/ps_platform.json`
- Create: `src/rfsoc_pulse_model/ip/platform.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/ip/test_platform.py`

**Produces:** `PsPlatformConfig.load_default()`, a canonical reviewed PS
property mapping, exact 100 MHz control clock, source provenance, and
byte-identical root/package resources.

- [ ] **Step 1: Write RED platform tests**

Cover exact schema keys, strict scalar types, duplicate-key rejection,
nonblank source provenance, exact device-part cross-check, exact PS VLNV,
`control_clock_hz == 100000000`, immutable property mapping, invalid/unknown
property keys, and byte-identical package data.

- [ ] **Step 2: Prove RED**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\.worktrees\connected-bd-rfdc-shell-20260813\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_platform -v
```

Expected: import/resource failures because the authority does not exist.

- [ ] **Step 3: Perform the one-time read-only PS extraction**

Use a disposable build directory and Vivado 2025.2 to open an upgraded copy of
`D:\AWAY\RFSOC\save_v2.1\XCZU27_MEM_TEST_TOP\XCZU27_TOP.srcs\sources_1\bd\design_1\design_1.bd`,
never the original. The GTY example BD is not a board PS/DDR authority. Record
the source BD SHA-256.
Collect only writable `CONFIG.PSU__*` properties required to reproduce DDR,
MIO, GEM3 board pins, PL0 clock/reset, HPM0 and IRQ capabilities. Exclude
derived `ACT_*`, GUI-only, read-only and generated values. Apply the extracted
mapping to a fresh PS cell in a temporary project and require exact readback of
every retained property before committing it.

- [ ] **Step 4: Implement the strict immutable type and package data**

The normal loader must not read `save_v2.1`. It reads only the packaged JSON,
rejects duplicate keys, checks the device part against `ModelConfig`, and
exposes properties through an immutable mapping snapshot.

- [ ] **Step 5: GREEN and regressions**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_platform tests.golden.test_config tests.ip.test_architecture_config -v
git diff --check
```

- [ ] **Step 6: Commit and independently review**

```powershell
git add config/ps_platform.json src/rfsoc_pulse_model/config/ps_platform.json src/rfsoc_pulse_model/ip/platform.py src/rfsoc_pulse_model/ip/__init__.py pyproject.toml tests/ip/test_platform.py
git commit -m "feat: freeze ZU27DR PS platform authority"
```

---

### Task 2: Advance the connected authority and refresh the exact IP lock

**Files:**

- Modify: `config/ip_architecture.json`
- Modify: `src/rfsoc_pulse_model/config/ip_architecture.json`
- Modify: `src/rfsoc_pulse_model/ip/types.py`
- Modify: `src/rfsoc_pulse_model/ip/registry.py`
- Modify: `tests/ip/test_architecture_config.py`
- Modify: `tests/ip/test_catalog.py`
- Modify: `tests/ip/test_registry.py`
- Modify: `tests/ip/test_lock.py`
- Tool-promote: `config/ip_lock.json`
- Tool-promote: `src/rfsoc_pulse_model/config/ip_lock.json`

**Produces:** architecture config revision for `connected_rfdc_shell`, exact
expanded family and materialized platform declarations, current Vivado catalog
evidence, and byte-identical explicitly promoted production locks. No connected
request or Tcl may be accepted before this task completes.

- [ ] **Step 1: Write RED schema, ownership and lock tests**

Assert schema v2 remains, config revision advances, topology is exactly
`connected_rfdc_shell`, the five platform families and seven platform
instances are declared, the exact complete family set is enforced, RFDC and
platform owners remain unaccepted, pending algorithm owners remain unchanged,
and production readiness remains false.

- [ ] **Step 2: Prove RED and implement config/type changes**

Update both architecture JSON copies byte-identically. Do not fabricate a new
lock. Development mode must report stale/invalid lock truthfully; production
mode must fail closed until promotion.

- [ ] **Step 3: Generate discovery inputs in development mode**

Use a clean build output. Record the architecture, discovery Tcl and catalog
request hashes. Confirm discovery contains the exact required family set and
contains no BD/cell/connection commands.

- [ ] **Step 4: Run real Vivado 2025.2 discovery**

Run the generated discovery Tcl with its three provenance hashes. Require exit
zero, canonical complete evidence, exact RFDC 2.6 and exact platform-family
identities. Remove any partial evidence before the next attempt.

- [ ] **Step 5: Generate candidate and explicitly promote**

Use only the project lock CLI. Verify candidate family set, candidate hash,
root/package lock byte equality, discovery-only provenance, and production
generation success.

- [ ] **Step 6: Focused regression, commit and independent review**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests/ip -v
git diff --check
git add config/ip_architecture.json src/rfsoc_pulse_model/config/ip_architecture.json src/rfsoc_pulse_model/ip/types.py src/rfsoc_pulse_model/ip/registry.py tests/ip/test_architecture_config.py tests/ip/test_catalog.py tests/ip/test_registry.py tests/ip/test_lock.py config/ip_lock.json src/rfsoc_pulse_model/config/ip_lock.json
git commit -m "build: lock connected RFDC platform IP"
```

---

### Task 3: Define canonical connected request and evidence

**Files:**

- Create: `src/rfsoc_pulse_model/ip/connected.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Create: `tests/ip/test_connected.py`

**Produces:** immutable connected-shell request/evidence objects, canonical
JSON encoding, strict duplicate/unknown-key rejection, exact-set comparison,
and `rfdc_shell_structural_ready` evaluation independent from overall
production readiness.

- [ ] **Step 1: Write RED request/evidence tests**

The request must derive the exact expected cell set, VLNV family references,
24-interface inventory, requested RFDC semantics, control/RX/TX clocks, reset
domains, address path and MTS grouping from the three authorities. No second
channel or sample-rate mapping is allowed.

Evidence tests must reject stale hashes, wrong part/Vivado version, missing or
extra cells/interfaces, wrong I/Q identity, width drift, clock-net split,
cross-domain reset reuse, invalid address paths, `validate_bd_design=false`,
synthesis failure, unsafe CDC, runtime MTS overclaim, duplicate keys, unknown
keys and noncanonical bytes.

The schema includes exact `ctrl_clock_locked`, `rx_clock_locked` and
`tx_clock_locked` memberships for the three `proc_sys_reset/dcm_locked` pins.
Task 3 tests only canonical request/evidence values and pure validation. They
must not require a runner, advisory lock, lifecycle marker, attempt directory,
subprocess, Tcl emitter, or Vivado installation. Publication state is not part
of the Task 3 evidence dataclass.

- [ ] **Step 2: Prove RED**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_connected -v
```

- [ ] **Step 3: Implement minimal strict types and validator**

Use frozen dataclasses, tuples and read-only mapping snapshots. Canonical JSON
is UTF-8, sorted, compact, and ends in exactly one LF. Readiness reasons are
stable machine strings and never alter `production_integration_ready`. All
functions are deterministic and side-effect free apart from explicitly reading
the caller-supplied evidence bytes.

- [ ] **Step 4: GREEN and regressions**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_connected tests.ip.test_registry tests.ip.test_evidence tests.ip.test_lock -v
git diff --check
```

- [ ] **Step 5: Commit and independently review**

```powershell
git add src/rfsoc_pulse_model/ip/connected.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_connected.py
git commit -m "feat: define connected RFDC shell evidence"
```

---

### Task 4: Probe the RFDC 2.6 parameter and port contract

**Files:**

- Create: `src/rfsoc_pulse_model/ip/rfdc_probe.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Create: `tests/ip/test_rfdc_probe.py`
- Generated locally: `build/vivado/probe_rfdc_contract.tcl`
- Generated locally: `build/metadata/rfdc_probe_evidence.json`

**Produces:** a deterministic RFDC-only probe, actual Vivado 2025.2 property
and pin readback, and an evidence-backed property/port spelling used by Task 5.

- [ ] **Step 1: Write RED probe tests**

Assert an exact-part temporary project, exactly one RFDC 2.6 cell, requested
semantic configuration for ADC tiles 0-3 and DAC tiles 0-1, no PS/BD transport
cells, and deterministic machine output. The probe must enumerate writable
`CONFIG.*` properties, internal RFDC interface pins, scalar pins, directions,
widths, `FREQ_HZ`, `CLK_DOMAIN`, associated clocks/resets and validation errors.

Negative tests cover wrong part/Vivado version, missing RFDC 2.6, duplicate or
partial evidence, unexpected extra IP, unsafe Tcl quoting and noncanonical
probe output.

- [ ] **Step 2: Prove RED**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_rfdc_probe -v
```

- [ ] **Step 3: Implement and execute the deterministic probe**

Start from the existing RFDC property spellings only as candidate inputs. Run
the probe with real Vivado 2025.2. Record which requested properties are
writable, their actual readback, the complete 16 ADC plus 8 DAC internal
interface set, component widths, clock/reset pins and RF external interfaces.
Do not infer common-clock legality from MTS alone.

- [ ] **Step 4: Resolve mismatches with bounded TDD**

For each observed mismatch, add a failing test for the real Vivado result,
change one candidate property spelling/value, regenerate from scratch and
retry. Stop after three failed attempts on the same blocking condition.

- [ ] **Step 5: GREEN, evidence report, commit and independent review**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_rfdc_probe tests.golden.test_config -v
git diff --check
git add src/rfsoc_pulse_model/ip/rfdc_probe.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_rfdc_probe.py
git commit -m "test: probe RFDC 2.6 connected contract"
```

---

### Task 5: Generate connected realization and verification Tcl

**Files:**

- Create: `src/rfsoc_pulse_model/ip/connected_tcl.py`
- Create: `src/rfsoc_pulse_model/ip/connected_runner.py`
- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/ip/__init__.py`
- Create: `tests/ip/test_connected_tcl.py`
- Create: `tests/ip/test_connected_runner.py`
- Modify: `tests/ip/test_generate_architecture.py`

**Produces:** `realize_connected_rfdc_shell.tcl`,
`verify_connected_rfdc_shell.tcl`, canonical connected request metadata, and
separate realization/verification provenance hashes based on Task 4 readback.
It also produces the runner that owns advisory locking, attempt directories,
atomic lifecycle publication and Vivado subprocess invocation. Task 5 unit
tests use an injected fake launcher; they do not claim a successful real
Vivado run.

- [ ] **Step 1: Write RED Tcl tests**

Assert a fresh exact-part project/BD, exact stable cell names, explicit PS and
probe-verified RFDC property dictionaries, 100 MHz control clock, HPM0 control
path, reset inversion and three reset domains, RFDC IRQ path, candidate common
RX/TX data clocks, all 24 external AXIS interfaces, complete RF external
interfaces, address assignment, validation/save order, and absence of
detector/DMA/GEM data cells, legacy RTL, hidden automation and acceptance
claims. Compare internal RFDC pin identities; externalized auto names are only
evidence fields.

Assert explicit exported `ctrl_clock_locked`, `rx_clock_locked` and
`tx_clock_locked` pins and their one-to-one connections to the three
`proc_sys_reset/dcm_locked` inputs.

Negative tests cover wrong existing project part, wrong current BD, unsafe Tcl
word quoting, unknown platform property, unresolved required VLNV, duplicate
instance/interface name and any undeclared cell family.

Runner tests separately assert a repository-scoped advisory lock, a new numeric
run ID, atomic replacement of any old success by `in_progress` before the
injected launcher is called, attempt-local report/evidence paths, atomic
publication only after pure Task 3 validation passes, and fail-closed handling
of success followed by failure, interruption, stale report reuse, malformed
candidate evidence, and concurrent runners. The runner consumes Task 3 types;
Task 3 never imports the runner.

- [ ] **Step 2: Prove RED**

```powershell
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.ip.test_connected_tcl tests.ip.test_connected_runner tests.ip.test_generate_architecture -v
```

- [ ] **Step 3: Implement deterministic emitters**

Do not modify the catalog-discovery grammar except to consume the expanded
required family set later. Write generated files as bytes. Verification Tcl
must write machine fields only after all readbacks and reports complete; on
Tcl error it must leave no valid candidate evidence. The runner owns canonical
publication and must validate the attempt-local candidate through Task 3's pure
parser before publishing it.

- [ ] **Step 4: GREEN, double generation and regression**

Run the focused tests, generate twice to separate temporary output roots, and
compare every controlled file recursively. Run all `tests.ip` tests.

- [ ] **Step 5: Commit and independently review**

```powershell
git add src/rfsoc_pulse_model/ip/connected_tcl.py src/rfsoc_pulse_model/ip/connected_runner.py src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/ip/__init__.py tests/ip/test_connected_tcl.py tests/ip/test_connected_runner.py tests/ip/test_generate_architecture.py
git commit -m "feat: generate connected RFDC shell Tcl"
```

---

### Task 6: Run and verify the real connected Block Design

**Files:**

- Modify only if real readback requires source fixes:
  `src/rfsoc_pulse_model/ip/connected_tcl.py`,
  `src/rfsoc_pulse_model/ip/connected_runner.py`
- Modify covering tests before every source fix:
  `tests/ip/test_connected_tcl.py`, `tests/ip/test_connected.py`
- Generated locally: `build/vivado/connected_rfdc_shell/**`
- Generated locally: `build/metadata/connected_rfdc_shell_state.json`
- Generated locally: `build/metadata/connected_rfdc_shell_evidence.json`
- Generated locally: CDC, clock, synthesis and validation reports

**Produces:** real Vivado 2025.2 connected-shell evidence and diagnostic
reports. Generated project files are not committed.

- [ ] **Step 1: Run production generation into a clean build root**

Confirm catalog lock valid, connected request present, and shell readiness
false before evidence.

- [ ] **Step 2: Execute through the Task 5 runner in Vivado 2025.2**

Require the runner to publish a new `in_progress` marker before it launches the
generated Tcl in a fresh exact-part project. Capture stdout, journal and log in
the run-ID-bound ignored attempt directory. Require exact declared cells. Do
not invoke the Tcl outside the runner for acceptance and do not patch the
generated BD.

- [ ] **Step 3: Handle real property/port mismatches with bounded TDD**

For each mismatch, record the exact Vivado message/readback, add a failing
Python test for that observed contract, make one minimal emitter/config fix,
regenerate from scratch, and retry. After three failed evidence-driven
attempts on the same blocking condition, stop with all logs preserved.

- [ ] **Step 4: Execute verification and synthesis**

Require exact readback and `validate_bd_design`. Run `generate_target all`,
`make_wrapper -top`, `add_files -norecurse`, set the generated wrapper as top,
`launch_runs synth_1 -jobs 1`, `wait_on_run synth_1`, and require
`STATUS == {synth_design Complete!}`. Run `open_run synth_1` before emitting
utilization and timing-summary reports and before running `report_cdc`, clock
interaction and unconstrained-clock checks. No broad false-path or
asynchronous-clock-group waiver may hide an unsafe crossing.

- [ ] **Step 5: Parse evidence and prove shell readiness**

Require the runner to validate and atomically publish the attempt-local
candidate, then use the strict Task 3 parser. Require
`rfdc_shell_structural_ready=true`,
`mts_configuration_verified=true`, `mts_runtime_verified=false`, and
`production_integration_ready=false`.

Exercise at least one controlled failed retry through the runner and prove it
cannot reuse the previous success. Real-Vivado concurrency is not required;
the advisory-lock concurrency contract is established by Task 5's injected
launcher tests.

- [ ] **Step 6: Run focused/full regressions and commit source fixes only**

Commit any TDD source/test fixes in one task-scoped commit. Do not commit the
Vivado project or raw generated artifacts.

- [ ] **Step 7: Independently review actual evidence against the request**

---

### Task 7: Integrate shell readiness into top-level metadata

**Files:**

- Modify: `src/rfsoc_pulse_model/ip/generate.py`
- Modify: `src/rfsoc_pulse_model/generate.py`
- Modify: `tests/ip/test_generate_architecture.py`
- Modify: `tests/verilog/test_generate.py`

**Produces:** deterministic top-level metadata that consumes current connected
lifecycle state plus evidence, reports shell readiness separately, invalidates
stale evidence, and never lets shell readiness satisfy pending production
owners.

- [ ] **Step 1: Write RED top-level status tests**

Cover missing, `in_progress`, `failed`, current-success, state/evidence hash or
run-ID mismatch, stale, partial and malformed connected evidence;
production/development modes; deterministic generation; and explicit false
overall readiness despite true shell readiness.

- [ ] **Step 2: Implement minimal orchestration and GREEN**

The generator deletes no diagnostic report and removes/replaces only the
canonical derived shell status. Evidence parsing happens before any true
status is emitted.

- [ ] **Step 3: Run full suite and double generation**

```powershell
$env:PYTHONPATH='D:\AWAY\RFSOC\.worktrees\connected-bd-rfdc-shell-20260813\src'
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 4: Commit and independently review**

```powershell
git add src/rfsoc_pulse_model/ip/generate.py src/rfsoc_pulse_model/generate.py tests/ip/test_generate_architecture.py tests/verilog/test_generate.py
git commit -m "feat: report connected RFDC shell readiness"
```

---

### Task 8: Publish the contract and acceptance record

**Files:**

- Create: `docs/contracts/connected-rfdc-shell.md`
- Create: `docs/verification/connected-rfdc-shell-acceptance.md`
- Modify: `docs/contracts/amd-ip-ownership.md`
- Modify: `README.md`

**Produces:** exact user-reproducible commands, evidence hashes and explicit
verified/unverified boundaries.

- [ ] **Step 1: Record measured evidence, not planned values**

Include branch/commit, Python/Vivado paths and versions, exact command lines,
test totals/skips, generation hashes, architecture/platform/lock/evidence
hashes, exact cell and interface counts, RFDC property readback, clock/reset
nets, address map, validate/synthesis/CDC results, and all readiness flags.

- [ ] **Step 2: State the remaining gates explicitly**

No claim is made for post-route timing, bitstream, MTS runtime, reflection DSP,
detector/event path, DMA/DDR, GEM3 upload, board mapping or analogue loopback.

- [ ] **Step 3: Reproduce documented commands exactly**

Run the fixed absolute Python command, double production generation, full test
suite, and documented Vivado verification commands. Any bare `python`, `py` or
implicit Vivado PATH command in active instructions is a defect.

- [ ] **Step 4: Commit and independently review**

```powershell
git add docs/contracts/connected-rfdc-shell.md docs/verification/connected-rfdc-shell-acceptance.md docs/contracts/amd-ip-ownership.md README.md
git commit -m "docs: accept connected RFDC shell checkpoint"
```

---

## Final Branch Review

- [ ] Generate a review package from `dc31c5c` through final HEAD.
- [ ] Run the full fixed-Python suite from a clean checkout.
- [ ] Run production generation twice and compare every controlled byte.
- [ ] Validate the exact current lock, connected request and connected evidence.
- [ ] Confirm no tracked `.xpr`, `.Xil`, `.srcs`, `.runs`, `.gen`, journal,
  log, report, candidate, partial evidence or generated RTL artifact.
- [ ] Run `git diff --check dc31c5c..HEAD`.
- [ ] Dispatch an independent high-reasoning whole-branch review.
- [ ] Fix and re-review all load-bearing findings.
- [ ] Keep the branch local and unchanged after the clean final review; do not
  merge, push or delete it unless later directed.

## Completion Boundary

This plan is complete only when current evidence proves the connected RFDC
shell checkpoint. It is not completion of the entire RFSoC product. After the
clean branch review, immediately continue with a new reviewed plan for the
production 2SPC and continuous-reflection chain, followed by event DMA/GEM3
and board/timing acceptance, as listed in the approved design.
