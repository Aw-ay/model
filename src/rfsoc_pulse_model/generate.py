from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .common.config import ModelConfig
from .common.types import SampleTimeReference
from .cycle.dsl.emitter import VerilogEmitter
from .cycle.registry import HARDWARE_MODULES
from .ip.types import HardwareArchitectureConfig


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ports(module) -> list[dict[str, object]]:
    return [
        {
            "name": port.name,
            "direction": port.direction,
            "width": port.width,
            "registered": port.registered,
        }
        for port in module.ports
    ]


def generate(output_root: Path) -> dict[str, object]:
    """Regenerate all registered hardware RTL and its machine manifest."""

    root = Path(output_root)
    rtl_root = root / "rtl"
    metadata_root = root / "metadata"
    rtl_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)

    config = ModelConfig.load_default()
    architecture = HardwareArchitectureConfig.load_default()
    emitter = VerilogEmitter()
    modules = []
    expected_files = set()
    for registration in HARDWARE_MODULES:
        module = registration.cycle_class(config)
        rtl = emitter.emit(module).encode("utf-8")
        path = rtl_root / registration.verilog_filename
        path.write_bytes(rtl)
        expected_files.add(path.name)
        modules.append(
            {
                "module_name": module.module_name,
                "cycle_class": (
                    f"{registration.cycle_class.__module__}."
                    f"{registration.cycle_class.__qualname__}"
                ),
                "verilog_file": f"rtl/{path.name}",
                "rtl_sha256": _sha256(rtl),
                "latency_cycles": module.latency_cycles,
                "samples_per_cycle": module.samples_per_cycle,
                "accepts_backpressure": module.accepts_backpressure,
                "ports": _ports(module),
            }
        )

    stale = [path for path in rtl_root.glob("*.v") if path.name not in expected_files]
    if stale:
        raise RuntimeError(
            "unregistered generated RTL exists: " + ", ".join(path.name for path in stale)
        )

    numeric_formats = config.numeric_formats.as_tuples()
    numeric_bytes = json.dumps(
        numeric_formats,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    (metadata_root / "numeric_formats.json").write_bytes(numeric_bytes)

    manifest = {
        "model_schema_version": config.model_schema_version,
        "config_version": config.config_version,
        "device_part": config.device_part,
        "rx_fabric_clock_hz": config.rx_fabric_clock_hz,
        "rfdc_complex_samples_per_cycle": config.rfdc_complex_samples_per_cycle,
        "rfdc_dac_pl_data_type": config.rfdc_axis.dac_data_type,
        "rfdc_dac_axis_width_bits": config.rfdc_axis.dac_axis_width_bits,
        "rfdc_dac_complex_samples_per_cycle": (
            config.rfdc_axis.dac_complex_samples_per_cycle
        ),
        "rfdc_adc_clocking_mode": config.rfdc_adc_clocking_mode.value,
        "rfdc_adc_clocking_proof_status": (
            config.rfdc_adc_clocking_proof_status.value
        ),
        "rfdc_dac_clocking_mode": config.rfdc_dac_clocking_mode.value,
        "rfdc_dac_clocking_proof_status": (
            config.rfdc_dac_clocking_proof_status.value
        ),
        "single_clock_ingress_integration_ready": (
            config.single_clock_ingress_integration_ready
        ),
        "single_clock_tx_integration_ready": (
            config.single_clock_tx_integration_ready
        ),
        "golden_dac_time_reference": (
            SampleTimeReference.LATENCY_NORMALIZED.value
        ),
        "fractional_delay_kernel_center_samples": (
            config.fractional_delay_taps - 1
        ) // 2,
        "fixed_internal_delay_source": "calibration_profile_measurement",
        "numeric_formats_sha256": _sha256(numeric_bytes),
        "ip_architecture": {
            "architecture_schema_version": (
                architecture.architecture_schema_version
            ),
            "architecture_config_version": (
                architecture.architecture_config_version
            ),
            "vivado_version": architecture.vivado_version,
            "generation_mode": architecture.generation_mode,
            "topology_status": architecture.topology_status,
            "rfdc": {
                "vlnv": architecture.rfdc.ip.vlnv,
                "kind": architecture.rfdc.ip.kind.value,
                "owned_functions": list(architecture.rfdc.owned_functions),
                "configuration_authority": (
                    architecture.rfdc.configuration_authority
                ),
                "dac_analog_output_type": (
                    architecture.rfdc.dac_analog_output_type
                ),
                "dac_mixer_mode": architecture.rfdc.dac_mixer_mode,
                "dac_mixer_scale_mode": (
                    architecture.rfdc.dac_mixer_scale_mode
                ),
                "dac_nco_frequency_hz": (
                    architecture.rfdc.dac_nco_frequency_hz
                ),
                "proof_status": architecture.rfdc.proof_status,
            },
        },
        "modules": modules,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (root / "manifest.json").write_bytes(manifest_bytes)
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Cycle-derived Verilog")
    parser.add_argument("--output", type=Path, default=Path("build"))
    args = parser.parse_args(list(argv) if argv is not None else None)
    generate(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
