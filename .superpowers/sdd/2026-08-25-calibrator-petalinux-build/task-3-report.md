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
| `BOOT.BIN` | 36,177,568 | `de74686e9edfe3af91741d727d15a74fa5e593099afb3069d2a43ea7e27fff45` |
| `Image` | 32,371,200 | `a7660de82ddff9fc6b7d49b5c82df21e88f4e2cc534339f4269cd6d7399c3ba5` |
| `boot.scr` | 3,837 | `d54bbcd5bb8112c53d22d340752c80309c8c9dcf1e91edc86448eef3416c6309` |
| `rootfs.tar.gz` | 46,730,469 | `0af88c64fba63a229ee9098c98b57210376c9fc38e25eb780506174f1c0e4b70` |
| `rootfs.ext4` | 200,074,240 | `0bf1931564bfaa9c5305179a971c4760369efa8bd21063aa3e82d0eddc316e62` |
| `petalinux-sdimage.wic` | 6,442,455,040 | `ecfa72c53c5d63db0defcad780c1cdfab0ea7b799ba73cf34ba1889c2a0cf01c` |
| `system.dtb` | 42,825 | `e3089512849a4593cb0e62c20a26f49773e437654974828117a13b4eda3bb0ae` |
| `system.bit` | 34,437,496 | `307d36a1cb6f1af449fb34c146cacc1db2c58c0ce8dac2f8997961e3c3ce8f88` |

`docs/deployment/petalinux-2025.2-artifacts.json` is the committed,
machine-readable manifest; the same file is placed in the local ignored
handoff directory.

## Image-content checks

`rootfs.ext4` contains the deployed runtime payload:

- `/usr/sbin/calibratord` — 67,560 bytes;
- `/usr/lib/systemd/system/calibratord.service` — 487 bytes;
- `/etc/default/calibratord` — 156 bytes;
- `/usr/lib/modules/6.12.40-xilinx-g31626ef92ff1/updates/calibrator_dma_proxy.ko`
  — 12,288 bytes.

A fresh read-only Bootgen inspection reports six boot images, including
`zynqmp_fsbl.elf`, PL-destination `system.bit`, `bl31.elf`, `system.dtb`, and
`u-boot.elf`.  The WIC inspection reports a bootable 2 GiB FAT32 partition
and a 4 GiB Linux partition. The rebuilt FAT partition contains
`BOOT.BIN`, `Image`, `boot.scr`, and `system.dtb`; the DTB selects the ext4
root with `root=/dev/mmcblk0p2 rootwait rw`. Direct read-only inspection of
the WIC's second partition confirms `calibratord`, its enabled service,
`uio_pdrv_genirq` autoload, and `of_id=generic-uio`.

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
