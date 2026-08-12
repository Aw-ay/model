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
from .ip.evidence import canonical_json_bytes
from .ip.generate import generate_ip_architecture
from .ip.lock import GenerationMode
from .ip.registry import ArchitectureRegistry
from .ip.types import ImplementationKind


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


def _reject_unregistered_rtl(
    directory: Path, expected_filenames: set[str], scope: str
) -> None:
    stale = sorted(
        path.name for path in directory.glob("*.v") if path.name not in expected_filenames
    )
    if stale:
        raise RuntimeError(
            f"unregistered generated RTL exists in {scope}: " + ", ".join(stale)
        )


def generate(
    output_root: Path,
    ip_mode: GenerationMode | str = GenerationMode.DEVELOPMENT,
) -> dict[str, object]:
    """Regenerate all registered hardware RTL and its machine manifest."""

    root = Path(output_root)
    config = ModelConfig.load_default()
    ip_architecture = generate_ip_architecture(root, ip_mode)
    rtl_root = root / "rtl"
    reference_rtl_root = root / "reference_rtl"
    metadata_root = root / "metadata"
    rtl_root.mkdir(parents=True, exist_ok=True)
    reference_rtl_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)
    emitter = VerilogEmitter()
    production_rtl = []
    reference_rtl = []
    expected_production_files = set()
    expected_reference_files = set()
    emitted = []
    for registration in HARDWARE_MODULES:
        module = registration.cycle_class(config)
        rtl = emitter.emit(module).encode("utf-8")
        output_directory = rtl_root if registration.production else reference_rtl_root
        output_scope = "rtl" if registration.production else "reference_rtl"
        entry = (
            {
                "module_name": module.module_name,
                "cycle_class": (
                    f"{registration.cycle_class.__module__}."
                    f"{registration.cycle_class.__qualname__}"
                ),
                "verilog_file": f"{output_scope}/{registration.verilog_filename}",
                "rtl_sha256": _sha256(rtl),
                "latency_cycles": module.latency_cycles,
                "samples_per_cycle": module.samples_per_cycle,
                "accepts_backpressure": module.accepts_backpressure,
                "implementation_kind": registration.implementation_kind.value,
                "production": registration.production,
                "ports": _ports(module),
            }
        )
        emitted.append((registration, output_directory / registration.verilog_filename, rtl, entry))
        if registration.production:
            production_rtl.append(entry)
            expected_production_files.add(registration.verilog_filename)
        else:
            reference_rtl.append(entry)
            expected_reference_files.add(registration.verilog_filename)

    for registration, reference_path, reference_bytes, _entry in emitted:
        if registration.production:
            continue
        old_production_path = rtl_root / registration.verilog_filename
        if not old_production_path.exists():
            continue
        if old_production_path.read_bytes() != reference_bytes:
            raise RuntimeError(
                "possible hand edit in old production RTL: "
                f"{old_production_path.name} differs from fresh reference bytes"
            )
        old_production_path.unlink()

    _reject_unregistered_rtl(rtl_root, expected_production_files, "rtl")
    _reject_unregistered_rtl(
        reference_rtl_root, expected_reference_files, "reference_rtl"
    )
    for _registration, path, rtl, _entry in emitted:
        path.write_bytes(rtl)

    modules = production_rtl + reference_rtl
    production_sources_contain_reference = any(
        entry["verilog_file"].startswith("reference_rtl/")
        or entry["implementation_kind"]
        == ImplementationKind.LEGACY_NON_PRODUCTION.value
        for entry in production_rtl
    )
    readiness = ArchitectureRegistry.default().evaluate_readiness(
        catalog_resolution_complete=ip_architecture["catalog_resolution_complete"],
        production_lock_valid=ip_architecture["production_lock_valid"],
        production_sources_contain_reference=production_sources_contain_reference,
    )
    ip_architecture.update(
        {
            "responsibility_complete": readiness.responsibility_complete,
            "production_integration_ready": readiness.production_integration_ready,
            "production_integration_blocking_reasons": list(
                readiness.blocking_reasons
            ),
        }
    )
    ip_architecture_bytes = canonical_json_bytes(ip_architecture)
    (metadata_root / "ip_architecture.json").write_bytes(ip_architecture_bytes)

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
        "ip_architecture": ip_architecture,
        "ip_architecture_sha256": _sha256(ip_architecture_bytes),
        "production_rtl": production_rtl,
        "reference_rtl": reference_rtl,
        "modules": modules,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (root / "manifest.json").write_bytes(manifest_bytes)
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Cycle-derived Verilog")
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument(
        "--ip-mode",
        choices=tuple(mode.value for mode in GenerationMode),
        default=GenerationMode.DEVELOPMENT.value,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    generate(args.output, GenerationMode(args.ip_mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
