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

Task 4: Ruling: define TCP control as one newline-terminated request per connection; execute the first line and close, so behavior is independent of TCP segmentation, while a bounded read timeout prevents an incomplete client from blocking the single-threaded control loop — if this interpretation is wrong, the cost is changing both endpoints to a persistent multi-request protocol.

Task 4: complete (commits f891fcd..b82f63e; clean hardware authorities committed, TCP Linux socket contract passed, calibratord/device-tree targeted builds passed)

Task 5: complete (PetaLinux 6498/6498 with 6475 reused; BOOT.BIN/WIC repackaged; DTB selects mmcblk0p2; WIC FAT and ext4 contents inspected directly; eight fresh artifact hashes recorded; physical-board gates remain open)

Task 2: reopened by final whole-branch review. Commit `306d49d` adds the
reset-safe DAC AXIS gate, carries the two DAC controls through the existing
handshake CDC, bounds the TCP read by an absolute monotonic deadline, and
documents the non-root XSCT `libtinfo.so.5` setup. The previously verified
hardware/XSA/image artifacts predate this source change and must be regenerated
by the controller's single consolidated Vivado/PetaLinux run; they are not
claimed as gate-enabled artifacts.

Task 2: reclosed after regeneration. The Vivado 2025.2 gate-enabled build
completed implementation with setup WNS +0.308 ns, hold WHS +0.010 ns, zero
route failures, and zero DRC errors. The regenerated XSA SHA-256 is
`91b1ccdcfd2903afe186059b05b01ff7c0558318a834bf8e664fa41abe098ee0`;
its embedded `system.bit` SHA-256 is
`a5a6a7a3c7eda7a0185a1666fcccbb7835424c29d4a66d8266193afdb43cbf70`.
PetaLinux completed 6,498/6,498 tasks, then regenerated BOOT.BIN and WIC.
Both WIC partitions, the daemon/service/UIO/DMA payload, the absolute TCP
deadline diagnostic, Bootgen's six-image container, and VM-to-Windows hashes
were verified. Commits `042eaaa`, `aaec37a`, and `98e35de` record the
reproducibility fix, regression correction, and evidence reconciliation.
Post-review regression: 420 tests passed with 9 environment skips. Physical
board, RF/MTS, eMMC cold-boot, network-load, and two-hour acceptance gates
remain open.
