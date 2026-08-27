# Calibrator Vivado + Linux deployment

This is the execution record and handoff for the XCZU27DR v2.1 calibrator.
Generated content under `build/` is evidence only; the source authorities are
the JSON configuration, Python generators, RTL, Linux sources and PetaLinux
layer committed in this repository.

## Frozen platform

| Item | Authority |
| --- | --- |
| Device | `xczu27dr-fsve1156-2-i` |
| Toolchain | Vivado, Vitis and PetaLinux 2025.2 only |
| GEM3 | RTL8211FD, PHY address 7, `rgmii-id`, MIO 64–77 |
| PHY reset | active-low `PS_POR_B`; optional MIO24 route not populated |
| eMMC | SD0, 8-bit, MIO 13–23 |
| RFDC | 8 ADC / 8 DAC, 2 complex samples per 250 MHz fabric cycle |
| DMA | AXI DMA SG S2MM, 128-bit AXIS, PS HP0 |
| Control | TCP JSON-lines on port 47001 |
| Events | UDP v1 on port 47000 |

The board values came from `E:\temp\save_v2.1\XCZU27DR-v2.1.pdf` and the
legacy block design. The legacy BD SHA-256 is
`63dc103980f369d1ba7246652cd533382b9ab96bed9ccede4b2dd5536df8517a`.
`config/calibrator_platform.json` is the machine-readable authority.

## Reproduce the Vivado build

Run in a PowerShell opened in the repository root:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:XILINX_LOCAL_USER_DATA = 'no'
$env:CALIBRATOR_SOURCE_DIR = (Get-Location).Path
$env:CALIBRATOR_BUILD_DIR = (Join-Path (Get-Location) 'build\calibrator_project')

python -m rfsoc_pulse_model.ip.calibrator_build build\calibrator_generated
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' `
  -mode batch -source build\calibrator_generated\build_calibrator.tcl
python -m rfsoc_pulse_model.ip.calibrator_build --finalize-xsa `
  build\calibrator_project\calibrator_no_bit.xsa `
  build\calibrator_project\calibrator.bit `
  build\calibrator_project\calibrator.xsa
```

The completed local build produced:

- `build/calibrator_project/calibrator.bit`, SHA-256
  `307d36a1cb6f1af449fb34c146cacc1db2c58c0ce8dac2f8997961e3c3ce8f88`;
- `build/calibrator_project/calibrator.xsa`, SHA-256
  `4a2decaebadb0e92dc4b6e6eddf1fae3a765db3b5ffddde148b22d87029db211`.

The embedded-bit XSA was reopened and checked for `xsa.json`, `xsa.xml` and
the exact generated `calibrator.bit` bytes.

## Vivado implementation evidence

The foreground 2025.2 build completed block-design validation, synthesis,
placement, routing, sign-off reports, bitstream and XSA export.

| Check | Result |
| --- | --- |
| Route status | 0 failed, 0 unrouted, 0 partially routed, 0 overlaps |
| Setup | WNS +0.181 ns, TNS 0, 0 failing endpoints |
| Hold | WHS +0.013 ns, THS 0, 0 failing endpoints |
| Bus skew | all met; minimum reported slack +3.691 ns |
| CDC | 0 critical; 188 CDC-15 warnings confined to RFDC vendor false paths and AMD asynchronous FIFO structures |
| DRC | 0 critical/errors; four AMD-IP advisory warnings (DMA BRAM collision advisories and reset nets with no routable loads) |

The old CDC-15 evidence freeze is recorded as risk and is not a release gate.
New critical CDC, negative setup/hold slack, or implementation DRC errors make
the generated Tcl fail.

## Vitis 2025.2 Linux platform

The platform is generated only from the embedded-bit XSA:

```powershell
& 'C:\AMDDesignTools\2025.2\Vitis\bin\vitis.bat' -s `
  software\vitis\create_linux_platform.py `
  build\calibrator_project\calibrator.xsa `
  build\vitis_workspace
```

On the current workstation this correctly stops before generation because the
2025.2 installation lacks:

```text
C:\AMDDesignTools\2025.2\Vitis\data\emulation\platforms\zynqmp\sw\a53_linux\qemu
```

Repair the 2025.2 installation by adding its ZynqMP Embedded Linux platform
payload, then rerun the command. Do not copy the available 2025.1 payload into
2025.2: mixed tool versions are explicitly rejected. Successful completion
prints `CALIBRATOR_XPFM=<path>` and also verifies that an `.xpfm` was actually
created, because the Vitis launcher may return zero after a Python-side error.

## Build PetaLinux and an eMMC image

Use a supported Ubuntu 22.04 VM with PetaLinux 2025.2 installed and sourced:

```bash
source /opt/petalinux/2025.2/settings.sh
cd /path/to/RFSOC-model-calibrator
bash software/petalinux/build_image.sh \
  build/calibrator_project/calibrator.xsa \
  /work/calibrator-petalinux
```

The script refuses an existing destination, verifies Ubuntu/tool versions,
creates a ZynqMP project, imports the XSA and repository `meta-user` layer,
builds Linux, packages `BOOT.BIN`, and emits the WIC image. The image must be
written to the intended eMMC target only after independently confirming the
target device name.

The installed system contains:

- `/usr/sbin/calibratord`;
- `/dev/calibrator-events`, backed by a 256-entry coherent DMA ring;
- the `calibratord.service` systemd unit;
- automatic RFDC validation and DAC0–1 / ADC0–3 MTS;
- fail-safe DAC mute until initialization succeeds;
- UDP events and all nine TCP v1 commands.

Set the receiver address in `/etc/default/calibratord`. The `shutdown`
command stops acquisition and the service; it powers off Linux only when
`CALIBRATOR_ALLOW_POWEROFF=1` is explicitly enabled.

### Verified PetaLinux artifact handoff (2026-08-27)

The PetaLinux 2025.2 build in the Ubuntu 22.04.5 VM completed its untargeted
incremental build with `6,498/6,498` tasks successful.  The exact generated
artifacts were then verified in
`/home/petalinux/work/calibrator-petalinux/images/linux`, copied to the
ignored local handoff directory `build/petalinux_output/`, and hashed again on
Windows.  Each local SHA-256 exactly matched the VM source.  The
machine-readable source manifest is
[`petalinux-2025.2-artifacts.json`](petalinux-2025.2-artifacts.json); an
identical copy is placed alongside the ignored local artifacts.

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

The `rootfs.ext4` inspection proves the runtime payload: `/usr/sbin/calibratord`
(67,560 bytes), `/usr/lib/systemd/system/calibratord.service` (458 bytes),
`/etc/default/calibratord` (156 bytes), and
`/usr/lib/modules/6.12.40-xilinx-g31626ef92ff1/updates/calibrator_dma_proxy.ko`
(12,288 bytes).  A fresh Bootgen read finds six boot images, including the
FSBL, PL `system.bit`, BL31, `system.dtb`, and U-Boot.  `fdisk` identifies a
bootable 2 GiB FAT32 WIC partition and a 4 GiB Linux partition.

## Windows control and capture

Install the repository package, then use the generated console command:

```powershell
python -m pip install -e .
calibrator-cli control 192.168.1.10 get_status
calibrator-cli control 192.168.1.10 set_threshold `
  --parameters '{"threshold":1000000}'
calibrator-cli control 192.168.1.10 start
calibrator-cli receive --bind 0.0.0.0 --port 47000 `
  --output acceptance-capture --duration 7200 --require-events 100000
calibrator-cli control 192.168.1.10 stop
```

The receiver rejects bad magic/version/length/CRC, tracks 64-bit sequence
gaps, duplicates and reordering, bounds incomplete fragment state, writes
PDWs to `events.jsonl`, and writes fixed IQ16 records to `events.iq16le`.

## Verified scope and remaining release gates

Verified on this workstation:

- reproducible Vivado implementation and embedded-bit XSA;
- 250 MHz implementation timing, routing, DRC and CDC report gates;
- 8-channel RFDC I/Q reorder and requested ADC-to-DAC physical mapping;
- 128-bit, 12-beat/192-byte event framing and DMA integration;
- threshold-hit PDW plus exact 16-before/16-after IQ capture skeleton;
- common ABI generation across RTL/C/device-tree/Python;
- C/Python UDP byte and CRC equivalence;
- host control, reassembly, sequence accounting and archive tests.

Not yet release-verified:

1. The deployable RTL still uses a direct raw ADC-to-DAC loopback and a simple
   `I²+Q² >= threshold` hit detector. The Cycle/Golden implementation of the
   0–2047 integer delay, 63-tap fractional delay, s24.Q20 complex correction,
   H/V automatic range selection, 15-tap decimating FIR, adaptive noise,
   moving average and 3/5 vote has not yet been integrated into the bitstream.
2. The PetaLinux image and runtime payload are now built and hash-verified,
   but their actual boot, service start, DMA, RFDC and network behavior remain
   board-only gates.
3. The Vitis `.xpfm` is blocked by the incomplete local 2025.2 installation
   described above.
4. JTAG load, real RFDC clocks/SYSREF, MTS, low-power RF loopback, GEM3 traffic,
   ten cold boots, eMMC boot and the two-hour/100,000-event acceptance require
   the physical board and have not been claimed.

The project is therefore at a reproducible hardware/software integration
milestone, not final operational acceptance. These four items must be closed
before stating that the complete calibrator is production-runnable.
