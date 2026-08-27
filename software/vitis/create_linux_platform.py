"""Create the reproducible Vitis 2025.2 Linux XPFM from calibrator.xsa.

Run with: vitis -s create_linux_platform.py <xsa> <workspace>
"""

from pathlib import Path
import os
import sys

import vitis


EXPECTED_VERSION = "2025.2"


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: create_linux_platform.py <calibrator.xsa> <workspace>")
    xsa = Path(sys.argv[1]).resolve()
    workspace = Path(sys.argv[2]).resolve()
    if not xsa.is_file():
        raise SystemExit(f"XSA does not exist: {xsa}")
    vitis_root = os.environ.get("XILINX_VITIS", "").replace("\\", "/")
    if EXPECTED_VERSION not in vitis_root:
        raise SystemExit(f"Vitis {EXPECTED_VERSION} required; XILINX_VITIS={vitis_root!r}")
    qemu_payload = Path(vitis_root) / "data/emulation/platforms/zynqmp/sw/a53_linux/qemu"
    if not qemu_payload.is_dir():
        raise SystemExit(
            "Vitis Embedded ZynqMP Linux payload is incomplete; reinstall the 2025.2 "
            f"component that supplies {qemu_payload}"
        )
    workspace.mkdir(parents=True, exist_ok=True)

    port_text = os.environ.get("CALIBRATOR_VITIS_SERVER_PORT")
    client = vitis.create_client(port=int(port_text) if port_text else None)
    try:
        client.set_workspace(str(workspace))
        platform = client.create_platform_component(
            name="calibrator_platform",
            hw_design=str(xsa),
            no_boot_bsp=True,
            generate_dtb=False,
        )
        platform.add_domain(
            cpu="psu_cortexa53",
            os="linux",
            name="linux_a53",
            generate_dtb=True,
            architecture="64-bit",
        )
        platform.report()
        platform.build()
        candidates = sorted(workspace.rglob("*.xpfm"))
        if not candidates:
            raise RuntimeError("Vitis build completed without an XPFM")
        print(f"CALIBRATOR_XPFM={candidates[0]}")
    finally:
        vitis.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
