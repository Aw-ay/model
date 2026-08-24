import unittest

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.cycle.candidate_registry import CANDIDATE_HARDWARE_MODULES
from rfsoc_pulse_model.cycle.dsl.emitter import VerilogEmitter
from rfsoc_pulse_model.cycle.hardware.production_calibrated_hv import RxCalibratedHvFrontend2Spc
from rfsoc_pulse_model.cycle.registry import HARDWARE_MODULES
from rfsoc_pulse_model.ip.types import ImplementationKind


class CandidateHardwareRegistryTest(unittest.TestCase):
    def test_candidates_are_separate_from_legacy_and_not_production(self) -> None:
        self.assertEqual(
            [item.verilog_filename for item in CANDIDATE_HARDWARE_MODULES],
            [
                "rx_2spc_continuous_ingress.v",
                "continuous_stream_timebase.v",
                "tx_2spc_continuous_egress.v",
                "rx_2spc_calibrated_hv_frontend.v",
            ],
        )
        self.assertTrue(
            all(item.implementation_kind is ImplementationKind.ARCHITECTURE_PENDING
                for item in CANDIDATE_HARDWARE_MODULES)
        )
        self.assertTrue(all(not item.production for item in CANDIDATE_HARDWARE_MODULES))
        calibrated = [
            item
            for item in CANDIDATE_HARDWARE_MODULES
            if item.module_name == "rx_2spc_calibrated_hv_frontend"
        ]
        self.assertEqual(len(calibrated), 1)
        self.assertIs(calibrated[0].cycle_class, RxCalibratedHvFrontend2Spc)
        self.assertIs(
            calibrated[0].implementation_kind,
            ImplementationKind.ARCHITECTURE_PENDING,
        )
        self.assertFalse(calibrated[0].production)
        self.assertTrue(calibrated[0].accepts_config)
        self.assertEqual(
            [item.verilog_filename for item in HARDWARE_MODULES],
            ["rx_group_ingress_2spc.v", "tx_iq_axis_boundary_2spc.v"],
        )

    def test_candidate_verilog_is_deterministic_and_has_explicit_clock_reset(self) -> None:
        config = ModelConfig.load_default()
        emitter = VerilogEmitter()
        for item in CANDIDATE_HARDWARE_MODULES:
            first = emitter.emit(item.cycle_class(config) if item.accepts_config else item.cycle_class())
            second = emitter.emit(item.cycle_class(config) if item.accepts_config else item.cycle_class())
            self.assertEqual(first, second)
            self.assertIn(f"module {item.module_name} (", first)
            self.assertIn("input wire clk_i", first)
            self.assertIn("input wire rst_i", first)

    def test_calibrated_hv_candidate_emits_deterministically_with_default_config(self) -> None:
        config = ModelConfig.load_default()
        candidates = [
            item
            for item in CANDIDATE_HARDWARE_MODULES
            if item.module_name == "rx_2spc_calibrated_hv_frontend"
        ]
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        first = VerilogEmitter().emit(candidate.cycle_class(config))
        second = VerilogEmitter().emit(candidate.cycle_class(config))

        self.assertEqual(first, second)
        self.assertIn("module rx_2spc_calibrated_hv_frontend (", first)
        self.assertIn("input wire clk_i", first)
        self.assertIn("input wire rst_i", first)


if __name__ == "__main__":
    unittest.main()
