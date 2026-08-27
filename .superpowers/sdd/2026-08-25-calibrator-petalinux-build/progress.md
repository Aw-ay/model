# SDD ledger — plan: docs/superpowers/plans/2026-08-25-calibrator-petalinux-build.md

## Pre-flight interface scan

| Tasks | Producer / consumer | Finding |
| --- | --- | --- |
| 1 → 2 | staged XSA and repository subset → `build_image.sh` | consistent; Task 1 must retain repository-relative `petalinux/` and `software/` paths |
| 2 → 3 | PetaLinux `images/linux` → artifact verification/copyback | consistent; exact output filenames are tool-generated and Task 3 verifies rather than assumes them |
| 1 | VM/version/hash checks and staging | internally consistent |
| 2 | clean project, source-controlled fixes, repeat build | internally consistent; generated VM project remains disposable |
| 3 | hash/copyback/tests/docs | internally consistent; board operation remains explicitly out of scope |

Pre-flight result: no conflict with the global constraints or between task interfaces.

Task 1: fix round 1/5 (4 addressed, 0 open; external VM staging, no git commits)

Task 1: complete (commits b3b95f9..b3b95f9, review clean)

Task 2: Ruling: after repeated recipe-specific SPDX collisions, replace per-recipe cleanup with one evidence-based inventory of all zero-byte generated SPDX JSON and only their matching generated links — repeated failures show one corrupted generated-state class rather than independent recipe defects — if this classification is wrong, the cost is regenerating affected disposable SPDX outputs, not source or user data.

Task 2: Ruling: do not globally delete zero-byte pkgdata; current-build zero-byte pkgdata can be valid, so repair only old, error-listed, manifest-unowned paths and verify each affected recipe plus an independent sample — this is slower, but avoids deleting legitimate generated package metadata.

Task 2: complete (commits b3b95f9..90e717c, final review approved; PetaLinux 6498/6498, calibrator runtime rootfs payload, BOOT.BIN, and WIC verified)

Task 3: complete (VM-source and Windows-copy SHA-256 equality for all eight deployable artifacts; local ignored handoff includes both rootfs forms and manifest; deployment tests 12/12 and shell syntax pass; physical-board gates remain open)
