# Task 3 — verified PetaLinux artifact handoff

## Scope and source evidence

- VM source: `/home/petalinux/work/calibrator-petalinux/images/linux`.
- VM environment: Ubuntu 22.04.5 LTS and `PETALINUX_VER=2025.2`.
- Gate-enabled XSA: `build/calibrator_project_gate/calibrator.xsa`, 1,964,999
  bytes, SHA-256
  `91b1ccdcfd2903afe186059b05b01ff7c0558318a834bf8e664fa41abe098ee0`.
- Fresh 2026-08-28 incremental `petalinux-build`: `6,498/6,498` tasks
  successful, with 6,438 tasks reused.
- No Vivado or PetaLinux 2025.1 payload was used. Bootgen identifies itself as
  v2025.2.

## Artifact verification and copyback

The following source artifacts were non-empty, copied to the ignored local
`build/petalinux_output_gate/` directory without removing unrelated files, then
hashed with Windows SHA-256.  The VM and Windows values exactly match.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `BOOT.BIN` | 36,177,568 | `42dca14ef82ff06109c4ccf52f9dff88aee77bb7d682c4058150685261b874c5` |
| `Image` | 32,371,200 | `a7660de82ddff9fc6b7d49b5c82df21e88f4e2cc534339f4269cd6d7399c3ba5` |
| `boot.scr` | 3,837 | `d54bbcd5bb8112c53d22d340752c80309c8c9dcf1e91edc86448eef3416c6309` |
| `rootfs.tar.gz` | 46,752,507 | `7d97cbf82fad6b26a5127a030f588cb36368a12ad41af1af12fc166c93b0040f` |
| `rootfs.ext4` | 200,197,120 | `1a87221b21f4944ff8146a72d6244fb19239242614b560d004fb7b69ac4e900a` |
| `petalinux-sdimage.wic` | 6,442,455,040 | `4d6946121e1d896b12ed9ed763bbb1afddbdec0fb75d4e4424b7d819e3d83076` |
| `system.dtb` | 42,825 | `e3089512849a4593cb0e62c20a26f49773e437654974828117a13b4eda3bb0ae` |
| `system.bit` | 34,437,496 | `a5a6a7a3c7eda7a0185a1666fcccbb7835424c29d4a66d8266193afdb43cbf70` |

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
`uio_pdrv_genirq` autoload, and `of_id=generic-uio`. The packaged
`system.bit` is byte-identical to the gate-enabled Vivado bitstream extracted
from the XSA. The daemon binary contains the absolute TCP request-deadline
diagnostic.

## Local verification

```text
PYTHONPATH=src python -m unittest tests.software.test_deployment -q
Ran 17 tests ... OK

Fresh detached-worktree regression at aaec37a:
Ran 420 tests ... OK (skipped=9)

Post-review regression after evidence reconciliation and the stalled-beat
DAC-gate transition test:
Ran 420 tests ... OK (skipped=9)

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
