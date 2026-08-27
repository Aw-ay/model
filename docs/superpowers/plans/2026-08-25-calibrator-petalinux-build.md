# Calibrator PetaLinux 2025.2 build continuation

## Goal

Build and verify the calibrator PetaLinux image from the already verified
Vivado 2025.2 embedded-bit XSA in the user-provided Ubuntu 22.04 VM.

## Global constraints

- Use only Vivado/PetaLinux 2025.2 artifacts; never mix 2025.1 payloads.
- Use `build/calibrator_project/calibrator.xsa` and verify its SHA-256 is
  `4a2decaebadb0e92dc4b6e6eddf1fae3a765db3b5ffddde148b22d87029db211`.
- Treat `petalinux/`, `software/`, RTL and machine-readable configuration as
  source. Treat generated VM projects and `build/` outputs as disposable.
- Preserve fail-safe DAC mute and the fixed v1 register/network ABI.
- Do not claim board operation until JTAG/eMMC/RF/Ethernet tests run on the
  physical board.

## Task 1: Stage reproducible inputs in the VM

- Confirm Ubuntu 22.04 and PetaLinux 2025.2.
- Transfer only the repository inputs required by `software/petalinux/build_image.sh`
  plus `calibrator.xsa` into a fresh VM staging directory.
- Verify the transferred XSA hash.

## Task 2: Build the PetaLinux project and image

- Source `/home/petalinux/petalinux/2025.2/settings.sh`.
- Run `software/petalinux/build_image.sh` against a new project directory.
- Diagnose and fix source-controlled recipes, device tree, daemon or kernel
  module when the real build exposes defects; rerun until success or a true
  external blocker is demonstrated.

## Task 3: Verify and hand off generated artifacts

- Verify `BOOT.BIN`, `Image`, `boot.scr`, rootfs output and the WIC image.
- Record sizes and SHA-256 hashes and copy the deployable artifacts back under
  the local ignored `build/petalinux_output/` directory.
- Re-run repository deployment tests and update deployment documentation with
  fresh build evidence and any remaining board-only gates.

## Task 2 remediation: deploy the daemon, module, and embedded bitstream

**Goal:** Make the source build path reliably place `calibratord`, its
systemd/default files, `calibrator_dma_proxy.ko`, and the XSA-embedded FPGA
bitstream in the packaged image.

**Architecture:** Keep the user-space daemon in its own systemd recipe and
the kernel module in a separate `module.bbclass` recipe, because that class
deliberately makes its `${PN}` package empty.  Register the daemon in the
PetaLinux rootfs menu and select only the confirmed 2025.2 rootfs symbols.
The build script extracts the single embedded XSA bitstream atomically and
compares its hash with the archive payload before boot packaging.

### Task A: Behavioral deployment tests

- [ ] Add a deployment test which executes the bitstream helper against a
  temporary XSA fixture and asserts the emitted file is byte-identical;
  assert an XSA with no `.bit` fails.
- [ ] Add deployment assertions which evaluate the rootfs registration and
  recipe package behavior: selected `calibratord` maps to a non-module daemon
  recipe containing `/usr/sbin/calibratord`, unit/default files, and an
  RDEPENDS edge to `kernel-module-calibrator-dma-proxy`; the module recipe
  owns the `.ko` through module splitting.
- [ ] Run the focused deployment tests and capture their expected RED result.

### Task B: Minimal source repair

- [ ] Add `meta-user/conf/user-rootfsconfig` registration for `CONFIG_calibratord`.
- [ ] Replace invalid rootfs selections with `CONFIG_packagegroup-networking-stack`
  and `CONFIG_Init-manager-systemd`; retain valid libmetal, libxrfdc, and UIO
  module selections.
- [ ] Split the daemon and kernel module recipes, leaving each with only its
  own build/install/package responsibilities.
- [ ] Add the tested embedded-XSA bitstream helper and invoke it after
  `petalinux-config --get-hw-description` but before boot packaging.
- [ ] Run focused tests to GREEN, then the repository regression suite; commit
  only the remediation source/tests.

### Task C: VM acceptance

- [ ] Stage the committed source subset into the existing VM project, apply
  hardware/rootfs silent configuration, and rebuild.
- [ ] Verify the generated rootfs contains the daemon, its service/default
  file, the proxy `.ko`, libmetal/libxrfdc, and UIO support.
- [ ] Regenerate BOOT.BIN/WIC with the source-owned helper and verify their
  hashes/partition and boot-container contents.  Do not claim a board run.
