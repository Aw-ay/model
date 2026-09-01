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

The current gate-enabled implementation is retained in
`build/calibrator_project_gate/`. It includes the reset-safe DAC AXIS gates
driven by the synchronized loopback and mute controls. The build produced:

- `build/calibrator_project_gate/calibrator.bit`, SHA-256
  `a5a6a7a3c7eda7a0185a1666fcccbb7835424c29d4a66d8266193afdb43cbf70`;
- `build/calibrator_project_gate/calibrator.xsa`, SHA-256
  `91b1ccdcfd2903afe186059b05b01ff7c0558318a834bf8e664fa41abe098ee0`.

The embedded-bit XSA was reopened and checked for `xsa.json`, `xsa.xml` and
the exact generated `calibrator.bit` bytes.

## Vivado implementation evidence

The foreground 2025.2 build completed block-design validation, synthesis,
placement, routing, sign-off reports, bitstream and XSA export.

| Check | Result |
| --- | --- |
| Route status | 0 failed, 0 unrouted, 0 partially routed, 0 overlaps |
| Setup | WNS +0.308 ns, TNS 0, 0 failing endpoints |
| Hold | WHS +0.010 ns, THS 0, 0 failing endpoints |
| Bus skew | all met; minimum reported slack +2.846 ns |
| CDC | 0 critical; 188 CDC-15 warnings confined to RFDC vendor false paths and AMD asynchronous FIFO structures |
| DRC | 0 critical/errors; four AMD-IP advisory warnings (DMA BRAM collision advisories and reset nets with no routable loads) |

The old CDC-15 evidence freeze is recorded as risk and is not a release gate.
New critical CDC, negative setup/hold slack, or implementation DRC errors make
the generated Tcl fail.

## Vitis 2025.2 Linux platform

The platform is generated only from the embedded-bit XSA. On Windows use the
XSCT launcher, which validates the 2025.2 tool payload, refuses stale output
directories, and verifies the exact generated XPFM instead of trusting the
XSCT process exit code alone:

```powershell
python software\vitis\build_linux_platform.py `
  --vitis-root 'C:\AMDDesignTools\2025.2\Vitis' `
  build\calibrator_project_gate\calibrator.xsa `
  build\vitis_platform
```

The required ZynqMP Embedded Linux payload is:

```text
C:\AMDDesignTools\2025.2\Vitis\data\emulation\platforms\zynqmp\sw\a53_linux\qemu
```

Do not copy a 2025.1 payload into 2025.2: mixed tool versions are explicitly
rejected. Successful completion prints `CALIBRATOR_XPFM=<path>`. The existing
Unified Vitis Python flow in `create_linux_platform.py` remains available, but
the XSCT flow is the qualified Windows path because it does not depend on the
Unified Vitis Server Java selector. Delete or choose a new output directory
before rebuilding; an existing directory is rejected to prevent stale XPFM
reuse.

## Build PetaLinux and an eMMC image

Use a supported Ubuntu 22.04 VM with PetaLinux 2025.2 installed and sourced:

```bash
source /opt/petalinux/2025.2/settings.sh
cd /path/to/RFSOC-model-calibrator
bash software/petalinux/build_image.sh \
  build/calibrator_project_gate/calibrator.xsa \
  /work/calibrator-petalinux
```

PetaLinux 2025.2's XSCT tools require `libtinfo.so.5`, which is not normally
installed on Ubuntu 22.04.  Extract it without root privileges before the
build; this does not modify the VM or pollute ordinary BitBake recipes:

```bash
COMPAT_ROOT="$HOME/.local/calibrator-xsct-libtinfo5"
mkdir -p "$COMPAT_ROOT/pkg" "$COMPAT_ROOT/root"
(
  cd "$COMPAT_ROOT/pkg"
  apt download libtinfo5
  dpkg-deb -x libtinfo5_*.deb "$COMPAT_ROOT/root"
)
export CALIBRATOR_XSCT_LIBTINFO_DIR="$COMPAT_ROOT/root/lib/x86_64-linux-gnu"
test -f "$CALIBRATOR_XSCT_LIBTINFO_DIR/libtinfo.so.5"
```

`build_image.sh` uses that directory only for its parse-time launcher and the
four XSCT-invoking recipes (`device-tree`, `bitstream-extraction`,
`pmu-firmware`, and `fsbl-firmware`); normal tasks keep both `LD_PRELOAD` and
`LIBRARY_PATH` empty.

The script refuses an existing destination, verifies Ubuntu/tool versions,
creates a ZynqMP project, imports the XSA and repository `meta-user` layer,
builds Linux, packages `BOOT.BIN`, and emits the WIC image. The image must be
written to the intended eMMC target only after independently confirming the
target device name.

The packaged root filesystem contains:

- `/usr/sbin/calibratord`;
- the `calibratord.service` systemd unit;
- the DMA proxy module plus UIO autoload configuration;
- the configuration required for UDP events and all nine TCP v1 commands.

After successful driver probe on the physical board, the service is designed
to create `/dev/calibrator-events` backed by a 256-entry coherent DMA ring,
validate RFDC state, run DAC0–1 / ADC0–3 MTS, and keep the DAC fail-safe muted
until initialization succeeds. These runtime outcomes remain board-only gates.

Commission TCP control only on an isolated control LAN. The shipped defaults
bind TCP to `127.0.0.1` and allow only that peer, so remote RF commands remain
disabled until `/etc/default/calibratord` sets `CALIBRATOR_CONTROL_BIND` to the
board's GEM3 IPv4 address and `CALIBRATOR_CONTROL_PEER` to the one authorized
Windows PC IPv4 address. Never configure a wildcard bind.

Provision a separate 256-bit shared secret on the board before starting the
service. The file is deliberately absent from the image:

```sh
install -d -m 0700 /etc/calibratord
openssl rand -hex 32 > /etc/calibratord/control.token
chown root:root /etc/calibratord/control.token
chmod 0600 /etc/calibratord/control.token
```

Copy that token through the commissioning channel to a Windows file readable
only by the operator. Every TCP request is strict, bounded JSON and must carry
the token; malformed, duplicate, unknown or unauthenticated fields are
rejected. Missing or insecure token configuration makes the service fail
closed while the DAC remains muted. Set the UDP receiver address in
`/etc/default/calibratord`. The `shutdown` command stops acquisition and the
service; it powers off Linux only when `CALIBRATOR_ALLOW_POWEROFF=1` is
explicitly enabled.

### Gate-enabled secure PetaLinux artifact handoff — offline-inspected (2026-08-31)

The authenticated and peer-restricted runtime from commit `9b3b14f` was rebuilt
with PetaLinux 2025.2 in the Ubuntu 22.04.5 VM. The untargeted incremental build
completed `6,498/6,498` tasks successfully, with 6,474 reused. Before the build,
SHA-256 checks confirmed that the ten daemon, protocol-header, recipe, default
and systemd-unit inputs in the VM were byte-identical to the current branch.

The fresh release is retained in
`/home/petalinux/work/calibrator-secure-20260830`. It has not been copied back
to a Windows handoff directory; the older ignored `build/petalinux_output_gate/`
contents remain superseded historical evidence. No VM-to-Windows hash
comparison is claimed for the fresh release. The machine-readable record is
[`petalinux-2025.2-artifacts.json`](petalinux-2025.2-artifacts.json).

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `BOOT.BIN` | 36,177,568 | `42dca14ef82ff06109c4ccf52f9dff88aee77bb7d682c4058150685261b874c5` |
| `Image` | 32,371,200 | `a7660de82ddff9fc6b7d49b5c82df21e88f4e2cc534339f4269cd6d7399c3ba5` |
| `boot.scr` | 3,837 | `d54bbcd5bb8112c53d22d340752c80309c8c9dcf1e91edc86448eef3416c6309` |
| `rootfs.tar.gz` | 46,750,951 | `4e4326c5893afdd7a03845ec2ce4acab6b8b7e099b22c79afa2319835081a001` |
| `rootfs.ext4` | 200,202,240 | `e22f74dc67cf612598b35ddfae8753d00670ddf7f60783ffc3a1bf0c031f985b` |
| `petalinux-sdimage.wic` | 6,442,455,040 | `352e12ce7663d02c5e08adf5ddde33c3dba3adf19d4831451aca86df57efa041` |
| `system.dtb` | 42,825 | `e3089512849a4593cb0e62c20a26f49773e437654974828117a13b4eda3bb0ae` |
| `system.bit` | 34,437,496 | `a5a6a7a3c7eda7a0185a1666fcccbb7835424c29d4a66d8266193afdb43cbf70` |

The rootfs and direct read-only WIC inspections prove the current runtime
payload: `/usr/sbin/calibratord` (67,632 bytes),
`/usr/lib/systemd/system/calibratord.service` (498 bytes),
`/etc/default/calibratord` (435 bytes), and
`/usr/lib/modules/6.12.40-xilinx-g31626ef92ff1/updates/calibrator_dma_proxy.ko`
(12,288 bytes). The root-owned `/etc/calibratord` directory is mode `0700`
and empty: `control.token` is deliberately not preprovisioned. The enabled
systemd service keeps `NoNewPrivileges`, a strict read-only system view,
private temporary storage and `UMask=0077`. The shipped TCP defaults bind to
and authorize only `127.0.0.1` until commissioning supplies explicit GEM3 and
operator-PC addresses.

The unchanged deterministic `BOOT.BIN` contains the previously inspected six
boot images, including the FSBL, PL `system.bit`, BL31, `system.dtb`, and
U-Boot. WIC inspection identifies a 2 GiB FAT32 partition and a 4 GiB ext4
partition. The FAT
partition contains `BOOT.BIN`, `Image`, `boot.scr`, and the rebuilt
`system.dtb`. The DTB selects `root=/dev/mmcblk0p2 rootwait rw`; the unchanged
kernel has no bootable embedded rootfs/initramfs. Direct read-only WIC
inspection verifies `/usr/sbin/calibratord` and the enabled
`calibratord.service`; rootfs inspection also verifies `uio_pdrv_genirq`
autoload, `of_id=generic-uio`, the DMA proxy module, and the daemon's absolute
TCP request-deadline diagnostic. The packaged `system.bit` hash exactly
matches the gate-enabled Vivado bitstream and the bitstream embedded in the
recorded XSA.

This is the current commissioning candidate, but physical-board execution
remains pending. Actual boot, driver probe, RFDC/MTS, DMA, GEM3, eMMC cold boot,
and the two-hour/100,000-event acceptance are not claimed by this offline
artifact inspection.

## Windows control and capture

Install the repository package, then use the generated console command:

```powershell
python -m pip install -e .
calibrator-cli control 192.168.1.10 get_status --token-file .\control.token
calibrator-cli control 192.168.1.10 set_threshold `
  --token-file .\control.token --parameters '{"threshold":1000000}'
calibrator-cli control 192.168.1.10 start --token-file .\control.token
calibrator-cli receive --bind 0.0.0.0 --port 47000 `
  --output acceptance-capture --duration 7200 --require-events 100000
calibrator-cli control 192.168.1.10 stop --token-file .\control.token
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

1. The generated design and packaged artifacts now gate every ADC-to-DAC route
   through reset-safe loopback/mute control. The Cycle/Golden implementation of
   the 0–2047 integer delay, 63-tap fractional delay, s24.Q20 complex correction,
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
