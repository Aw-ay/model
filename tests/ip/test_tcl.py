import hashlib
from pathlib import Path
import tempfile
import unittest

from rfsoc_pulse_model.ip.generate import generate_ip_architecture
from rfsoc_pulse_model.ip.registry import ArchitectureRegistry
from rfsoc_pulse_model.ip.tcl import emit_ip_skeleton_tcl
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


class IpSkeletonTclTest(unittest.TestCase):
    @staticmethod
    def emitted() -> str:
        return emit_ip_skeleton_tcl(
            HardwareArchitectureConfig.load_default(),
            ArchitectureRegistry.default(),
        )

    def test_tcl_requires_exact_rfdc_and_marks_skeleton_nonaccepted(self) -> None:
        tcl = self.emitted()

        self.assertIn(
            "set rfdc_vlnv {xilinx.com:ip:usp_rf_data_converter:2.6}",
            tcl,
        )
        self.assertIn("require_exact_ip $rfdc_vlnv", tcl)
        self.assertIn(
            "create_bd_cell -type ip -vlnv $rfdc_vlnv rfdc", tcl
        )
        self.assertIn("set topology_status {unconnected_skeleton}", tcl)
        self.assertIn("set integration_accepted 0", tcl)
        self.assertIn("IP_ARCHITECTURE_STATUS=UNCONNECTED_SKELETON", tcl)
        self.assertNotIn("validate_bd_design", tcl)

    def test_tcl_declares_initial_axis_and_fir_cells(self) -> None:
        tcl = self.emitted()

        for logical_name in (
            "axis_register_slice",
            "axis_data_fifo",
            "axis_clock_converter",
            "axis_dwidth_converter",
            "axis_combiner",
            "axis_broadcaster",
            "axis_switch",
            "fir_compiler",
        ):
            self.assertIn(f"resolve_catalog_ip {{{logical_name}}}", tcl)
            self.assertIn(
                f"create_bd_cell -type ip -vlnv $resolved_vlnv {{{logical_name}}}",
                tcl,
            )
        self.assertNotIn("rx_group_ingress_2spc", tcl)
        self.assertNotIn("tx_iq_axis_boundary_2spc", tcl)

    def test_generated_metadata_hashes_the_exact_tcl_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            architecture = generate_ip_architecture(root)
            tcl_bytes = (root / "vivado/create_ip_architecture.tcl").read_bytes()

            self.assertEqual(
                architecture["generated_tcl_sha256"],
                hashlib.sha256(tcl_bytes).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
