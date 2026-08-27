# Task 3 — verified PetaLinux artifact handoff

## Scope and source evidence

- VM source: `/home/petalinux/work/calibrator-petalinux/images/linux`.
- VM environment: Ubuntu 22.04.5 LTS and `PETALINUX_VER=2025.2`.
- Build evidence carried forward from the fresh 2026-08-27 acceptance build:
  untargeted `petalinux-build` completed `6,498/6,498` tasks successfully.
- No PetaLinux 2025.1 payload was used.  The PetaLinux 2025.2 Bootgen binary
  identifies itself as `v2025.1-Merged`; that is its vendor build label, not a
  mixed-toolchain input.

## Artifact verification and copyback

The following source artifacts were non-empty, copied to the ignored local
`build/petalinux_output/` directory without removing unrelated files, then
hashed with Windows SHA-256.  The VM and Windows values exactly match.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `BOOT.BIN` | 36,177,568 | `6bfa16054cf149dc1915c6d96237bb51f3b47352f0e53bf190e11dc3a826fdd2` |
| `Image` | 32,371,200 | `a7660de82ddff9fc6b7d49b5c82df21e88f4e2cc534339f4269cd6d7399c3ba5` |
| `boot.scr` | 3,837 | `d54bbcd5bb8112c53d22d340752c80309c8c9dcf1e91edc86448eef3416c6309` |
| `rootfs.tar.gz` | 46,729,879 | `9e8fd4108444bcd732b5470ae97c9eb77aef1e85e1c09a2b56b3b19894fdab39` |
| `rootfs.ext4` | 200,064,000 | `f1a0cb043b64b046288ab253a9f159656a5bbe1d6c5b8a20d4d24b8234da3ea3` |
| `petalinux-sdimage.wic` | 6,442,455,040 | `750906412879f6cdc5c545bd7fdd5ae0f6f2d0a5563b383555015840ef99d402` |
| `system.dtb` | 42,817 | `bdfb2911d6c9a4f8c91f2b621a9f4049648bb4bb785953aab7097734743c0fab` |
| `system.bit` | 34,437,496 | `307d36a1cb6f1af449fb34c146cacc1db2c58c0ce8dac2f8997961e3c3ce8f88` |

`docs/deployment/petalinux-2025.2-artifacts.json` is the committed,
machine-readable manifest; the same file is placed in the local ignored
handoff directory.

## Image-content checks

`rootfs.ext4` contains the deployed runtime payload:

- `/usr/sbin/calibratord` — 67,560 bytes;
- `/usr/lib/systemd/system/calibratord.service` — 458 bytes;
- `/etc/default/calibratord` — 156 bytes;
- `/usr/lib/modules/6.12.40-xilinx-g31626ef92ff1/updates/calibrator_dma_proxy.ko`
  — 12,288 bytes.

A fresh read-only Bootgen inspection reports six boot images, including
`zynqmp_fsbl.elf`, PL-destination `system.bit`, `bl31.elf`, `system.dtb`, and
`u-boot.elf`.  The WIC inspection reports a bootable 2 GiB FAT32 partition
and a 4 GiB Linux partition.

## Local verification

```text
PYTHONPATH=src python -m unittest tests.software.test_deployment -v
Ran 12 tests ... OK

bash -n software/petalinux/build_image.sh
BASH_SYNTAX_EXIT=0
```

## Remaining gates

No physical-board run is claimed.  JTAG/eMMC boot, real RFDC clocks/SYSREF and
MTS, low-power RF loopback, DMA/event acquisition, GEM3 traffic, ten cold
boots, and the two-hour/100,000-event acceptance remain board-only gates.
The deployed RTL is still the documented raw ADC-to-DAC/skeleton signal path;
the full delay/correction/filter/H-V algorithm has not been integrated into
the bitstream.
