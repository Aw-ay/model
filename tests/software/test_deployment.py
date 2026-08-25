from __future__ import annotations

from pathlib import Path
import ctypes
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from rfsoc_pulse_model.common.control_abi import ControlAbi
from rfsoc_pulse_model.common.network_protocol import encode_event_datagrams, encode_event_payload
from tests.host.test_calibrator_client import _event


ROOT = Path(__file__).resolve().parents[2]


class DeploymentContractTest(unittest.TestCase):
    def test_c_udp_encoder_is_byte_identical_to_python_protocol(self) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            self.skipTest("gcc is unavailable")
        event = _event()
        payload = encode_event_payload(event)
        dma_event = (
            struct.pack("<IIIIQ", 0x31414D44, 192, event.event_id, event.config_version, event.toa_samples)
            + payload
        )
        self.assertEqual(len(dma_event), 192)
        expected = encode_event_datagrams(event, sequence=77)[0]
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "protocol.dll"
            subprocess.run(
                [compiler, "-shared", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-Isoftware/calibratord/include", "software/calibratord/src/protocol.c",
                 "-o", str(library)],
                cwd=ROOT, check=True, capture_output=True,
            )
            protocol = ctypes.CDLL(str(library))
            protocol.cal_dma_event_to_datagram.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint64,
                ctypes.POINTER(ctypes.c_ubyte),
            ]
            source = (ctypes.c_ubyte * len(dma_event)).from_buffer_copy(dma_event)
            target = (ctypes.c_ubyte * len(expected))()
            size = protocol.cal_dma_event_to_datagram(source, 77, target)
            self.assertEqual(size, len(expected))
            self.assertEqual(bytes(target), expected)
            if hasattr(ctypes, "windll"):
                free_library = ctypes.windll.kernel32.FreeLibrary
                free_library.argtypes = [ctypes.c_void_p]
                free_library.restype = ctypes.c_int
                self.assertNotEqual(free_library(ctypes.c_void_p(protocol._handle)), 0)

    def test_generated_register_header_and_device_tree_match_single_source(self) -> None:
        abi = ControlAbi.load_default()
        self.assertEqual(
            (ROOT / "software/calibratord/include/calibrator_regs.h").read_text("utf-8"),
            abi.emit_c_header(),
        )
        overlay = (ROOT / "petalinux/project-spec/meta-user/recipes-bsp/device-tree/files/system-user.dtsi").read_text("utf-8")
        self.assertIn(
            re.sub(r"\s+", " ", abi.emit_device_tree_binding().strip()),
            re.sub(r"\s+", " ", overlay),
        )

    def test_daemon_is_fail_safe_and_implements_all_v1_commands(self) -> None:
        source = (ROOT / "software/calibratord/src/calibratord.c").read_text("utf-8")
        self.assertLess(source.index("cal_hw_force_safe"), source.index("cal_rfdc_initialize"))
        for command in (
            "get_status", "start", "stop", "set_threshold", "set_calibration",
            "commit_calibration", "run_mts", "clear_errors", "shutdown",
        ):
            self.assertIn(f'"{command}"', source)
        self.assertIn("CAL_PROJECT_ID_OFFSET", source)
        self.assertIn("CAL_ABI_VERSION_OFFSET", source)
        self.assertIn("O_NONBLOCK", source)
        self.assertIn("pthread_join", source)

    def test_dma_proxy_uses_dmaengine_coherent_ring_and_whole_event_reads(self) -> None:
        source = (ROOT / "software/kernel/calibrator_dma_proxy.c").read_text("utf-8")
        for contract in (
            "dma_request_chan", "dma_alloc_coherent", "dmaengine_prep_slave_single",
            "CAL_EVENT_BYTES", "copy_to_user", "dmaengine_terminate_sync", "O_NONBLOCK",
        ):
            self.assertIn(contract, source)

    def test_petalinux_recipe_installs_daemon_module_and_systemd_unit(self) -> None:
        recipe = (ROOT / "petalinux/project-spec/meta-user/recipes-apps/calibratord/calibratord.bb").read_text("utf-8")
        unit = (ROOT / "petalinux/project-spec/meta-user/recipes-apps/calibratord/files/calibratord.service").read_text("utf-8")
        script = (ROOT / "software/petalinux/build_image.sh").read_text("utf-8")
        self.assertIn("inherit module systemd", recipe)
        self.assertIn("file://calibrator_dma_proxy.c", recipe)
        self.assertIn("module_do_install", recipe)
        self.assertIn('FILESEXTRAPATHS:prepend := "${THISDIR}/files:"', recipe)
        self.assertIn('CALIBRATORD_RECIPE_FILES="$PROJECT_PATH/project-spec/meta-user/recipes-apps/calibratord/files"', script)
        self.assertIn('"$REPOSITORY_ROOT/software/calibratord/src/calibratord.c"', script)
        self.assertIn('"$CALIBRATORD_RECIPE_FILES/calibratord.c"', script)
        self.assertIn('"$REPOSITORY_ROOT/software/kernel/Makefile"', script)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("After=network-online.target", unit)

    def test_vitis_platform_script_is_xsa_driven_and_version_locked(self) -> None:
        script = (ROOT / "software/vitis/create_linux_platform.py").read_text("utf-8")
        self.assertIn('EXPECTED_VERSION = "2025.2"', script)
        self.assertIn("create_platform_component", script)
        self.assertIn('os="linux"', script)
        self.assertIn('cpu="psu_cortexa53"', script)
        self.assertIn("no_boot_bsp=True", script)
        self.assertIn("platform.build()", script)
        self.assertIn("Vitis Embedded ZynqMP Linux payload is incomplete", script)

    def test_petalinux_build_script_locks_2025_2_and_packages_boot_and_wic(self) -> None:
        script = (ROOT / "software/petalinux/build_image.sh").read_text("utf-8")
        self.assertIn('REQUIRED_VERSION="2025.2"', script)
        self.assertIn("petalinux-config --get-hw-description", script)
        self.assertIn("petalinux-build", script)
        self.assertIn("petalinux-package --boot", script)
        self.assertIn("petalinux-package --wic", script)


if __name__ == "__main__":
    unittest.main()
