# Implementation History

This lineage records engineering checkpoints and their review outcomes. It intentionally preserves superseded conclusions so a new engineer can distinguish historical evidence from current authority.

## Golden/Common Foundation

- `commit:52b42f1` established the standalone model repository.
- `commit:162956f` introduced unified configuration and validation.
- `commit:cda9845` completed physical IQ/power format contracts.
- Shared contracts then froze the physical map, RFDC word format, stream PDW semantics, fixed delay, and numeric widths through `commit:496dc40`, `commit:419c4cb`, `commit:4155baf`, `commit:86428de`, and `commit:4db1915`.
- Current truth: Golden/common types define physical units and mathematical behavior, but do not constitute timing or hardware evidence.

## Polarimetric Golden System

- Design and staged implementation began at `commit:5e281d8` and `commit:8f0d52f`.
- Contracts and Golden kernels were added through `commit:eb92242`, `commit:2131003`, `commit:b395c30`, `commit:96ae69d`, `commit:22b29fe`, `commit:edbc8c9`, `commit:0632247`, and `commit:e58cf7d`.
- `commit:1672443` recorded Golden acceptance; `commit:9efb2bd` and `commit:8f8c1f2` closed pre-Cycle and continuous-reflection contract defects.
- Final state: the Golden continuous dual-polarization reflection oracle is accepted within its mathematical scope, including detector independence. It is deliberately buffer-backed and is not a bounded Cycle implementation.

## Cycle 2SPC and Legacy Reference

- `commit:77b58be` started the restricted Cycle 2SPC ingress architecture.
- `commit:b1c6bef` made armed stream gaps fail closed; `commit:3567771` separated normalized and physical delay time; `commit:aeee0a9` froze the IQ-to-real TX boundary.
- XSim evidence exists for the generated ingress testbench, but the current production architecture classifies the old ingress and TX boundary as legacy references.
- Production RX/TX 2SPC responsibilities continue to exist and cannot be fulfilled by renaming or reusing these legacy files.

## AMD IP Schema and Catalog Evidence

- The AMD-IP-first foundation ran from `commit:64d2df6` through `commit:37e218a` and proved catalog availability plus an unconnected skeleton only.
- Schema-v2 normalization began at `commit:05e0cd2`; `commit:723772f` separated family, instance, block, and responsibility objects.
- Registry ownership, discovery/realization separation, strict evidence grammar, and complete catalog binding were implemented through `commit:79d905f`, `commit:19c5344`, `commit:74e8bb6`, `commit:9823c56`, `commit:e3a7696`, and `commit:6ca93fc`.
- Current meaning: catalog evidence proves exact tool-visible IP identity. It does not prove a cell is connected, accepted, timed, or running.

## Production Lock and Legacy RTL Isolation

- Exact production-lock promotion began at `commit:273cb4b` and was hardened across recoverability, process locking, path safety, handle-bound journal reads, and strict journal grammar through `commit:7f2c694`, `commit:172df13`, `commit:ed48b5a`, `commit:3a2d946`, and `commit:aee78d6`.
- `commit:ec995f9` split production RTL from legacy reference RTL; `commit:b5ace6e` hardened generated output paths.
- `commit:82ceeb9` bound Vivado catalog context to the configured device part. `commit:dbf4b96` tool-promoted the real Vivado 2025.2 lock.
- `commit:b75bc3e` added an existing-project exact-part guard; `commit:dc31c5c` refreshed the accepted normalization evidence.
- Final normalization state: responsibility complete, catalog complete, and production lock valid, while production integration remains false.

## Connected RFDC Shell Task 1

- Base: `commit:cc54bf5` froze the ZU27DR PS platform authority from SHA-bound legacy BD readback.
- Repairs: `commit:dd46ba2` added explicit fail-closed GEM3 board-I/O responsibility; `commit:a9b8d19` corrected the provenance base to caller-supplied external workspace root.
- Review: CLEAN.
- Bounded evidence: focused 59 tests and full 231 tests with 8 host-dependent symlink skips; fresh Vivado PS 3.5 property readback. ENET3/MDIO was disabled in the legacy source, so GEM3 physical enablement remains pending.

## Connected RFDC Shell Task 2

- Base: `commit:23d957c` advanced the architecture to revision 3, added the exact platform families/cells, ran real Vivado 2025.2 discovery, and promoted the 18-family lock.
- Repairs: `commit:c9dd242` froze materialized shell contracts; `commit:b06f80e` closed extra/planned shell and RFDC-ref drift; `commit:bb28c36` closed kind/status bypasses; `commit:059fb97` made protected owner names mandatory.
- Plan-boundary corrections: `commit:7d9e053` and `commit:1a39bda` separated Task 3 pure evidence from Task 5 runner lifecycle.
- Review: CLEAN after explicit removal/rename/custom/pending owner attacks were rejected.
- Bounded evidence: controller full run reported 243 tests passed with 8 host-dependent skips; exact catalog/lock tests remained valid.

## Connected RFDC Shell Task 3

- Base: `commit:cd0ce18` introduced canonical connected request/evidence/readiness data types and validation only.
- Repair 1: `commit:2403c5b` bound immutable authority bytes, removed hidden package reads, froze the full topology contract, and used canonical compact JSON.
- Repair 2: `commit:79ca1dd` validated discovery/catalog/lock provenance and rebuilt expected topology from passed model, architecture, and platform authorities.
- Review: CLEAN. No runner, Tcl launch, attempt lifecycle, or Vivado subprocess behavior belongs to this task.
- Bounded evidence: 54 focused tests with 2 host skips and 251 full tests with 8 host skips.

## Connected RFDC Shell Task 4

- Base: `commit:67b2106` implemented an RFDC-only property/port probe and obtained real Vivado 2025.2 readback.
- Repair 1: `commit:84166e9` required exact 48-interface/156-scalar inventory and authority-bound CONFIG semantics.
- Repair 2: `commit:85780f7` covered ADC/DAC data type and severe-tool diagnostics.
- Repair 3: `commit:9a28daa` made all three zero/nonzero diagnostic counts mandatory from before the first project action.
- Review: CLEAN.
- Bounded evidence: real attempt 6 measured 868 CONFIG, 48 interfaces, 156 scalar pins, and zero `WARNING`, `CRITICAL_WARNING`, and `ERROR` counts; 47 focused and 262 full tests passed with 8 host skips.

## Connected RFDC Shell Task 5

- Attempt 1, `commit:86af2d5`: added connected Tcl/runner. Review found an incomplete two-field candidate, missing RF external interfaces, and no complete synthesis/readback/report protocol.
- Attempt 2, `commit:ed8933f`: added full TSV, disk-backed project, external RF ports, reset inversion, synthesis and reports. Review showed CDC/clock/MTS readiness was hard-coded and unsafe reports could publish ready.
- Attempt 3, `commit:89a2362`: added report parsing, exact structural readback, lifecycle faults, path safety, and runner tests. Review found the parser requires synthetic `CDC_SAFE`, `CLOCK_SAFE`, and `TIMING_CONSTRAINED` tokens that neither the generated Tcl nor standard Vivado reports emit. It also uses unprobed RFDC MTS property names.
- Final review state: **BLOCKED**, not complete. The same report-to-evidence/MTS-authority blocker survived three implementation/review attempts. Task 6 was not started.
- Bounded evidence: latest fixed-Python suite at this implementation anchor passed 274 tests with 8 host-dependent symlink skips. This only proves the tested Python behavior; it does not make a real connected attempt possible.

## Superseded Conclusions

- The old assumption that four RF channels were the full physical product is superseded by the frozen 8 ADC/8 DAC dual-polarization map.
- The old partial 125 MHz/64-bit ADC stream interpretation is superseded by the measured 250 MHz contract with sixteen 32-bit ADC component streams and eight 64-bit DAC complex streams.
- The 31-sample fractional-FIR centre is not a public fixed delay; deployment delay must be measured across the declared boundaries.
- Legacy 2SPC generated RTL is reference evidence, not production implementation.
- A resolved catalog or unconnected `rfdc_0` skeleton is not a connected Block Design.
- Green Python tests for Task 5 are not connected-shell success while its real report protocol is impossible and MTS properties lack probe authority.
- No documentation-only commit after `commit:89a2362` changes the hardware implementation anchor or clears the blocker.
