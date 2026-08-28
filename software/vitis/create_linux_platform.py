"""Create the reproducible Vitis 2025.2 Linux XPFM from calibrator.xsa.

Run with: vitis -s create_linux_platform.py <xsa> <workspace>
"""

from pathlib import Path
import os
import sys

EXPECTED_VERSION = "2025.2"


def prepare_new_workspace(workspace: Path) -> None:
    if workspace.exists():
        raise RuntimeError(f"refusing to reuse existing workspace: {workspace}")
    workspace.mkdir(parents=True)


def find_built_xpfm(workspace: Path) -> Path:
    component = workspace / "calibrator_platform"
    candidates = sorted(component.rglob("calibrator_platform.xpfm"))
    if len(candidates) != 1 or not candidates[0].is_file():
        raise RuntimeError(
            "Vitis build must produce exactly one calibrator_platform.xpfm "
            "inside the newly created component"
        )
    return candidates[0]


def main() -> int:
    import vitis

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
    prepare_new_workspace(workspace)

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
        built_xpfm = find_built_xpfm(workspace)
        print(f"CALIBRATOR_XPFM={built_xpfm}")
    finally:
        vitis.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
