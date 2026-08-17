# Portable RFSoC Project Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-contained Markdown handoff package that lets a fresh Codex chat resume the complete RFSoC project without old chat records or local Codex databases.

**Architecture:** Ten focused files under `docs/handoff/` form a single-entry, layered evidence package. All claims are derived from tracked authorities, Git commits, reproducible tests, or bounded Vivado evidence; a standard-library unittest module enforces structure, portability, link integrity, commit validity, mirrored authorities, and absence of raw chat or credential material.

**Tech Stack:** Markdown, Git, Python 3.12 standard library, `unittest`, PowerShell, existing RFSoC model tests and Vivado evidence.

## Global Constraints

- Implement only on branch `connected-bd-rfdc-shell-20260813`; do not modify `model-update-20260811`.
- Treat `89a2362` as the connected-shell implementation anchor; later handoff-only commits do not imply that Task 5 is fixed.
- Do not copy or quote raw user/assistant chat, Codex session data, SQLite databases, memory files, agent messages, approval history, tokens, OAuth state, or secrets.
- Use repository-relative Markdown links. An external authority may be described only by role, SHA-256, locator rule, and fail-closed behavior.
- Every engineering claim must bind to a tracked file, a resolvable Git commit, a reproducible command, a hash, or a tool readback.
- Preserve evidence boundaries: Python/XSIM results do not prove Vivado CDC, timing, implementation, MTS runtime, Ethernet, or board behavior.
- Preserve the current stop condition: Task 5 report/MTS evidence is blocked after three attempts; Task 6 real connected-shell Vivado execution has not started.
- `docs/handoff/README.md` is the sole entry point. A fresh chat must not need to load all history at once.
- Keep the handoff package free of `C:\Users\...`, `.codex` paths, session identifiers, transcript annotations, and authentication filenames.
- Generated RTL remains derived from the Cycle model; the handoff task must not modify generated RTL, model behavior, architecture config, IP lock, Tcl, runner, or Vivado project files.
- Use the fixed interpreter `C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` for local verification, but write portable commands in the handoff as `<PYTHON_3_12>` plus an environment-discovery note.

---

### Task 1: Create the handoff entry point and current-state snapshot

**Files:**
- Create: `docs/handoff/README.md`
- Create: `docs/handoff/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-08-17-project-handoff-design.md`, Git worktree metadata, `.superpowers/sdd/2026-08-13-connected-rfdc-shell/progress.md`.
- Produces: the sole fresh-chat entry point and the stable implementation-state anchor consumed by every later handoff document.

- [ ] **Step 1: Capture the live repository facts before writing**

Run:

```powershell
git branch --show-current
git rev-parse HEAD
git worktree list --porcelain
git status --short
git cat-file -t 89a2362
git cat-file -t dc31c5c
```

Expected:

```text
connected-bd-rfdc-shell-20260813
<full hash beginning 89a2362>
...
commit
commit
```

The worktree must have no tracked modifications before Task 1 starts.

- [ ] **Step 2: Write `CURRENT_STATE.md` with stable snapshot semantics**

Use these exact top-level headings:

```markdown
# Current Project State
## Snapshot Semantics
## Repository and Branches
## Completed Gates
## Current Blocker
## Work Not Started
## Verification Boundary
## Resume Condition
```

Record:

- main development branch `model-update-20260811`, snapshot `commit:dc31c5c`;
- connected-shell branch `connected-bd-rfdc-shell-20260813`;
- implementation anchor `commit:89a2362`;
- handoff-only commits may follow the implementation anchor and do not change hardware readiness;
- Tasks 1–4 complete and independently reviewed;
- Task 5 blocked after `commit:86af2d5`, `commit:ed8933f`, and `commit:89a2362`;
- Task 6 and all downstream connected-shell integration tasks not started;
- the exact two remaining blockers: impossible synthetic report markers and unprobed MTS properties;
- a fresh chat must live-check its actual HEAD rather than treating the document-generation HEAD as immutable truth.

- [ ] **Step 3: Write `README.md` as the sole routed entry point**

Use these exact headings:

```markdown
# RFSoC Project Handoff
## Start Here
## Evidence Priority
## Reading Routes
## Portability Rules
## What Is Deliberately Excluded
## First Verification Commands
```

The reading routes must be:

| New task | Read next |
|---|---|
| Understand current state | `CURRENT_STATE.md`, `OPEN_ISSUES.md` |
| Change algorithms/models | `ARCHITECTURE.md`, `DECISIONS.md`, `FILE_INDEX.md` |
| Change RFDC/IP/BD | `ARCHITECTURE.md`, `VERIFICATION_EVIDENCE.md`, `OPEN_ISSUES.md` |
| Continue implementation | `CURRENT_STATE.md`, `NEXT_STEPS.md`, `FILE_INDEX.md` |
| Audit past work | `IMPLEMENTATION_HISTORY.md`, `VERIFICATION_EVIDENCE.md` |

State that the project directory and Git data are sufficient; no old chat database is required.

- [ ] **Step 4: Review the two files against source evidence**

Run:

```powershell
rg -n "Task 5|89a2362|86af2d5|ed8933f|Task 6|model-update-20260811" docs/handoff
rg -n "C:\\Users\\|\.codex|session[_ -]?id|auth\.json|Response annotations|Message Type:" docs/handoff
git diff --check
```

Expected: the first command finds every required state marker; the second prints no matches; `git diff --check` exits 0.

- [ ] **Step 5: Commit the entry/current-state pair**

```powershell
git add docs/handoff/README.md docs/handoff/CURRENT_STATE.md
git diff --cached --check
git commit -m "docs: add RFSoC handoff entry state"
```

### Task 2: Document architecture and frozen decisions

**Files:**
- Create: `docs/handoff/ARCHITECTURE.md`
- Create: `docs/handoff/DECISIONS.md`

**Interfaces:**
- Consumes: tracked contracts/configuration plus reviewed specs and acceptance files.
- Produces: the architecture and decision authority used by fresh-chat implementation routing.

- [ ] **Step 1: Read the exact architecture authorities**

Read these files completely before drafting:

```text
config/default.json
config/ip_architecture.json
config/ps_platform.json
docs/contracts/zu27dr-v2.1-physical-channel-map.md
docs/contracts/rfdc-axis-word-format.md
docs/contracts/fixed-point-widths.md
docs/contracts/fixed-internal-delay.md
docs/contracts/stream-status-online-pdw.md
docs/contracts/amd-ip-ownership.md
docs/superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md
docs/superpowers/specs/2026-08-11-ip-architecture-normalization-design.md
docs/superpowers/specs/2026-08-13-connected-rfdc-shell-design.md
```

- [ ] **Step 2: Write `ARCHITECTURE.md`**

Use these exact headings:

```markdown
# System Architecture
## Mission and Data Policy
## Physical 8-ADC / 8-DAC Mapping
## Sampling and Clock Domains
## Golden -> Cycle -> Generated Verilog
## Polarimetric Reflection Chain
## Monitor Pulse Event Chain
## AMD IP and Connected Block Design
## Software and Network Boundary
## Validation Layers
```

Include exact facts:

- 2.8 GHz RF carrier/NCO target;
- V/H high, mid, low paths and V/H calibration/active-cancellation paths;
- `+20/0/-20 dB` range semantics where applicable to the receive model;
- RFDC 4 GSPS converter rate, DDC/DUC ×8, 500 MSPS complex component domain, PL 2:1 decimation, 250 MSPS detector domain;
- RX 16 component AXIS interfaces at 32 bits and TX 8 complex AXIS interfaces at 64 bits, both at 250 MHz as measured in the RFDC probe;
- PS `pl_clk0=100 MHz` is control-plane only;
- pulse data policy is hit IQ windows plus coarse PDW, never continuous background IQ;
- IP blocks are black boxes and generated Verilog comes only from Cycle hardware models;
- model, HDL/XSIM, Vivado structural, CDC/timing, MTS runtime, DMA/Ethernet, and board loopback are separate gates.

- [ ] **Step 3: Write `DECISIONS.md` as a source-bound table**

Use these headings:

```markdown
# Frozen Engineering Decisions
## Numeric and Sampling Contracts
## RFDC and AXI Contracts
## Polarimetric and Range Contracts
## Model-to-RTL Contracts
## Block Design and IP Contracts
## Event and Software Contracts
## Pending Responsibilities
```

Each frozen decision row must have columns `Decision`, `Frozen value`, `Authority`, and `Consequence`. Pending responsibilities must be in a separate table and must not use the word “frozen”.

At minimum include ties-away-from-zero rounding, explicit clipping sideband, contiguous-main-peak FWHM, `PulseRecord` sample domain/rate/IQ width/power unit, 31-sample fixed internal delay convention, RFDC 2.6, exact production family lock, legacy RTL isolation, PS 100 MHz, RF data 250 MHz, and event-only upload.

- [ ] **Step 4: Cross-check every numeric claim**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest `
  tests.golden.test_config `
  tests.golden.test_common `
  tests.ip.test_architecture_config `
  tests.ip.test_platform -v
git diff --check
```

Expected: all selected tests pass; `git diff --check` exits 0.

- [ ] **Step 5: Commit architecture and decisions**

```powershell
git add docs/handoff/ARCHITECTURE.md docs/handoff/DECISIONS.md
git diff --cached --check
git commit -m "docs: capture RFSoC architecture decisions"
```

### Task 3: Consolidate verification evidence and implementation history

**Files:**
- Create: `docs/handoff/VERIFICATION_EVIDENCE.md`
- Create: `docs/handoff/IMPLEMENTATION_HISTORY.md`

**Interfaces:**
- Consumes: tracked acceptance documents, Git history, RFDC probe report summaries, production lock/config, and the SDD progress ledger.
- Produces: reproducible evidence and a compact engineering lineage without transcript content.

- [ ] **Step 1: Re-derive commits and immutable hashes**

Run:

```powershell
git log --oneline --decorate --all
Get-FileHash config/default.json -Algorithm SHA256
Get-FileHash config/ip_architecture.json -Algorithm SHA256
Get-FileHash config/ip_lock.json -Algorithm SHA256
Get-FileHash config/ps_platform.json -Algorithm SHA256
```

Copy only hashes that are used to identify an authority or lock. Commit references in handoff documents must use the syntax `commit:<7-or-more-lowercase-hex>` so Task 5 can validate them.

- [ ] **Step 2: Write `VERIFICATION_EVIDENCE.md`**

Use headings:

```markdown
# Verification Evidence
## Reproduction Environment
## Golden and Cycle Tests
## Generated RTL and Equivalence
## AMD IP Catalog and Production Lock
## RFDC 2.6 Probe
## Connected-Shell Tasks 1-5
## Evidence Not Yet Obtained
```

The RFDC probe section must record the reviewed attempt-6 facts: Vivado 2025.2, part `xczu27dr-fsve1156-2-i`, RFDC 2.6, 868 CONFIG records, 48 interfaces, 156 scalar pins, and mandatory `WARNING`, `CRITICAL_WARNING`, `ERROR` counts all zero. It must say these facts do not prove common-clock legality, CDC, implementation timing, MTS runtime, DMA/Ethernet, or board behavior.

The connected-shell section must record the latest known full suite at implementation anchor as 274 passed and 8 host-dependent symlink skips, while labeling Task 5 structurally blocked despite green Python tests.

- [ ] **Step 3: Write `IMPLEMENTATION_HISTORY.md`**

Use one section per phase:

```markdown
# Implementation History
## Golden/Common Foundation
## Polarimetric Golden System
## Cycle 2SPC and Legacy Reference
## AMD IP Schema and Catalog Evidence
## Production Lock and Legacy RTL Isolation
## Connected RFDC Shell Task 1
## Connected RFDC Shell Task 2
## Connected RFDC Shell Task 3
## Connected RFDC Shell Task 4
## Connected RFDC Shell Task 5
## Superseded Conclusions
```

For each connected-shell task list the base implementation commit, repair commits, final review state, and bounded test evidence. The Task 5 section must list all three attempts and end in `BLOCKED`; it must not call `commit:89a2362` complete.

- [ ] **Step 4: Validate every recorded commit manually before automated tests exist**

Run:

```powershell
$refs = Select-String -Path docs/handoff/*.md -Pattern 'commit:([0-9a-f]{7,40})' -AllMatches |
  ForEach-Object { $_.Matches } |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
foreach ($ref in $refs) { git cat-file -e "$ref^{commit}"; if ($LASTEXITCODE -ne 0) { throw "missing commit $ref" } }
git diff --check
```

Expected: every commit resolves and the diff check exits 0.

- [ ] **Step 5: Commit evidence and history**

```powershell
git add docs/handoff/VERIFICATION_EVIDENCE.md docs/handoff/IMPLEMENTATION_HISTORY.md
git diff --cached --check
git commit -m "docs: consolidate RFSoC verification history"
```

### Task 4: Define blockers, next steps, file index, and fresh-chat prompt

**Files:**
- Create: `docs/handoff/OPEN_ISSUES.md`
- Create: `docs/handoff/NEXT_STEPS.md`
- Create: `docs/handoff/FILE_INDEX.md`
- Create: `docs/handoff/NEW_CHAT_PROMPT.md`

**Interfaces:**
- Consumes: Tasks 1–3 handoff documents and current tracked authorities.
- Produces: the actionable resume boundary and the exact prompt used on a new computer.

- [ ] **Step 1: Write `OPEN_ISSUES.md` with machine-actionable exit gates**

Use a table with columns `ID`, `Status`, `Evidence`, `Impact`, `Exit gate`, and `Forbidden claim`.

Required issue IDs and statuses:

```text
BD-T5-REPORT-PROTOCOL    blocked
BD-T5-MTS-AUTHORITY     blocked
GEM3-BOARD-IO           pending
PRODUCTION-2SPC         pending
MONITOR-EVENT-CHAIN     pending
EVENT-DMA               pending
GEM3-DATA-PLANE         pending
CDC-TIMING              pending
MTS-RUNTIME             pending
BOARD-LOOPBACK          pending
```

`BD-T5-REPORT-PROTOCOL` must state that generated Tcl/standard Vivado reports do not produce `CDC_SAFE`, `CLOCK_SAFE`, or `TIMING_CONSTRAINED`. `BD-T5-MTS-AUTHORITY` must state that guessed `ADCn/DACn_Multi_Tile_Sync` properties are not Task-4-probed authority.

- [ ] **Step 2: Write `NEXT_STEPS.md` as a strictly ordered gate chain**

Use exact order:

1. Probe the actual Vivado 2025.2 report grammar and RFDC MTS property names in an RFDC-only temporary project.
2. Amend Task 5 request/evidence protocol so generated Tcl emits measured, canonical status records rather than test-only markers.
3. Independently review Task 5 and require a fake unsafe report plus a real clean Vivado report to produce opposite outcomes.
4. Run Task 6 through the runner in a disk-backed exact-part project; validate, synthesize, open `synth_1`, and collect CDC/clock/timing/utilization reports.
5. Add production 2SPC reflection chain only after the shell is structurally ready.
6. Add monitor pulse IQ/PDW event chain.
7. Add event DMA and GEM3 only after board I/O authority closes.
8. Complete implementation timing, MTS runtime, 24-hour stability, and board loopback acceptance.

Each step must list prerequisites, files likely to change, required tests, independent review checkpoint, and stop condition.

- [ ] **Step 3: Write `FILE_INDEX.md` using real relative links**

Use sections for Common/Golden, Cycle/Verilog, RFDC/IP, physical/contracts, plans/specs, tests, and verification. Every listed path must be a Markdown link relative to `docs/handoff/FILE_INDEX.md`, for example:

```markdown
- [ModelConfig](../../config/default.json)
- [RFDC word format](../contracts/rfdc-axis-word-format.md)
- [Connected-shell design](../superpowers/specs/2026-08-13-connected-rfdc-shell-design.md)
```

Do not list ignored SDD paths as future authorities. Their project-relevant conclusions must already be consolidated into tracked handoff files.

- [ ] **Step 4: Write `NEW_CHAT_PROMPT.md` as a copy-ready prompt**

The prompt must tell the new chat to:

```text
Read docs/handoff/README.md and CURRENT_STATE.md first.
Live-check git branch, HEAD, status, worktrees, and the implementation anchor.
Use FILE_INDEX.md to locate authorities before editing.
Treat Python, Vivado structural, CDC/timing, MTS runtime, DMA/Ethernet, and board validation as separate gates.
Do not repeat reviewed-complete Tasks 1-4.
Do not start Task 6 until both BD-T5 blockers are closed and independently reviewed.
Use the current repository files as truth when a handoff statement has drifted.
Report any drift before changing code.
```

It must not contain an old computer username or require access to old chat/session data.

- [ ] **Step 5: Run manual link and exclusion checks**

```powershell
rg -n "C:\\Users\\|\.codex|session[_ -]?id|auth\.json|Response annotations|Message Type:|<oai-mem-citation>" docs/handoff
rg -n "BD-T5-REPORT-PROTOCOL|BD-T5-MTS-AUTHORITY|Task 6|89a2362" docs/handoff
git diff --check
```

Expected: the exclusion scan prints no matches; all required blocker markers are present; diff check exits 0.

- [ ] **Step 6: Commit the actionable handoff files**

```powershell
git add docs/handoff/OPEN_ISSUES.md docs/handoff/NEXT_STEPS.md docs/handoff/FILE_INDEX.md docs/handoff/NEW_CHAT_PROMPT.md
git diff --cached --check
git commit -m "docs: add RFSoC fresh-chat resume guide"
```

### Task 5: Add automated portability validation and perform handoff acceptance

**Files:**
- Create: `tests/handoff/__init__.py`
- Create: `tests/handoff/test_handoff_docs.py`
- Modify: any `docs/handoff/*.md` only when the validator exposes a real defect.

**Interfaces:**
- Consumes: the exact ten-file handoff package from Tasks 1–4.
- Produces: a repeatable acceptance gate runnable by a new chat without access to old Codex data.

- [ ] **Step 1: Write strict structural acceptance tests**

Create `tests/handoff/test_handoff_docs.py` with these constants and tests:

```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs" / "handoff"
EXPECTED = {
    "README.md",
    "CURRENT_STATE.md",
    "ARCHITECTURE.md",
    "DECISIONS.md",
    "VERIFICATION_EVIDENCE.md",
    "IMPLEMENTATION_HISTORY.md",
    "OPEN_ISSUES.md",
    "NEXT_STEPS.md",
    "FILE_INDEX.md",
    "NEW_CHAT_PROMPT.md",
}
FORBIDDEN = (
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"\.codex(?:[/\\]|$)", re.IGNORECASE),
    re.compile(r"session[_ -]?id", re.IGNORECASE),
    re.compile(r"auth\.json", re.IGNORECASE),
    re.compile(r"Response annotations|Message Type:|<oai-mem-citation>", re.IGNORECASE),
)
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
COMMIT = re.compile(r"commit:([0-9a-f]{7,40})")


class HandoffDocsTest(unittest.TestCase):
    def docs(self) -> dict[str, str]:
        return {path.name: path.read_text(encoding="utf-8") for path in HANDOFF.glob("*.md")}

    def test_exact_document_set(self) -> None:
        self.assertEqual({path.name for path in HANDOFF.glob("*.md")}, EXPECTED)

    def test_no_local_codex_or_raw_chat_material(self) -> None:
        for name, text in self.docs().items():
            for pattern in FORBIDDEN:
                self.assertIsNone(pattern.search(text), f"{name}: {pattern.pattern}")

    def test_all_relative_markdown_links_resolve(self) -> None:
        for path in HANDOFF.glob("*.md"):
            for target in LINK.findall(path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "#")):
                    continue
                self.assertFalse(Path(target).is_absolute(), f"absolute link in {path.name}: {target}")
                self.assertTrue((path.parent / target.split("#", 1)[0]).resolve().exists(), f"broken link: {target}")

    def test_all_commit_markers_resolve(self) -> None:
        refs = {ref for text in self.docs().values() for ref in COMMIT.findall(text)}
        self.assertIn("89a2362", refs)
        for ref in refs:
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"missing commit {ref}: {result.stderr}")

    def test_authority_mirrors_are_byte_identical(self) -> None:
        for name in ("default.json", "ip_architecture.json", "ip_lock.json", "ps_platform.json"):
            self.assertEqual(
                (ROOT / "config" / name).read_bytes(),
                (ROOT / "src" / "rfsoc_pulse_model" / "config" / name).read_bytes(),
                name,
            )

    def test_entrypoint_and_blockers_are_explicit(self) -> None:
        docs = self.docs()
        self.assertIn("CURRENT_STATE.md", docs["README.md"])
        self.assertIn("NEW_CHAT_PROMPT.md", docs["README.md"])
        self.assertIn("BD-T5-REPORT-PROTOCOL", docs["OPEN_ISSUES.md"])
        self.assertIn("BD-T5-MTS-AUTHORITY", docs["OPEN_ISSUES.md"])
        self.assertIn("Do not start Task 6", docs["NEW_CHAT_PROMPT.md"])


if __name__ == "__main__":
    unittest.main()
```

Create an empty `tests/handoff/__init__.py`.

- [ ] **Step 2: Run the tests and observe any real defects**

```powershell
$env:PYTHONPATH = "$PWD\src"
& 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.handoff.test_handoff_docs -v
```

Expected: a correct handoff package passes. Any broken link, forbidden local material, malformed commit marker, missing entry route, or mirror drift fails with the exact document/path in the assertion and must be repaired in Step 3.

- [ ] **Step 3: Repair only defects reported by the validator**

For each failure, edit the responsible `docs/handoff/*.md`; do not relax `EXPECTED`, `FORBIDDEN`, the link resolver, commit validation, mirror checks, or blocker assertions merely to obtain green tests.

- [ ] **Step 4: Run focused and full verification**

```powershell
$env:PYTHONPATH = "$PWD\src"
$python = 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -m unittest tests.handoff.test_handoff_docs -v
& $python -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected:

- all six handoff tests pass;
- the full existing suite plus the six new tests passes, with only the known host-dependent Windows symlink skips;
- `git diff --check` exits 0;
- status lists only Task 5 files before commit.

- [ ] **Step 5: Simulate a fresh-chat read without SDD or Codex records**

Give an independent reviewer only these inputs:

```text
docs/handoff/README.md
the repository working tree
```

Require it to report, without reading `.superpowers/sdd`:

1. active connected-shell branch and implementation anchor;
2. completed Tasks 1–4;
3. both Task 5 blockers;
4. why Task 6 cannot start;
5. authoritative files for model, RFDC, physical mapping, and tests;
6. the exact next gate;
7. which validation claims remain forbidden.

Any incorrect answer is a documentation defect and must be fixed before commit.

- [ ] **Step 6: Commit the acceptance gate and final repairs**

```powershell
git add tests/handoff/__init__.py tests/handoff/test_handoff_docs.py docs/handoff
git diff --cached --check
git commit -m "test: verify portable RFSoC handoff"
git status --short
```

Expected: clean worktree after commit. Do not merge, push, create a transfer archive, or copy local Codex records as part of this plan.

## Final Acceptance Checklist

- [ ] Exactly ten Markdown files exist under `docs/handoff/`.
- [ ] `README.md` is the sole entry point and routes reading by task.
- [ ] `CURRENT_STATE.md` distinguishes implementation anchor from later documentation commits.
- [ ] All engineering history from Golden through connected-shell Task 5 is represented without transcript text.
- [ ] Every commit marker resolves and every relative Markdown link exists.
- [ ] Root/package copies of all four authority JSON files are byte-identical.
- [ ] Task 5 remains blocked and Task 6 remains unstarted.
- [ ] No raw chat, Codex local-state path, session identifier, credential filename, token, or secret appears.
- [ ] Focused handoff tests and the full repository suite pass.
- [ ] An independent fresh-chat simulation reconstructs the correct state using only `README.md` and repository files.
