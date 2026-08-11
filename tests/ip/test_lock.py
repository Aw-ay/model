import copy
import hashlib
import inspect
from importlib import resources
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from rfsoc_pulse_model.ip.evidence import build_catalog_request, canonical_json_bytes
from rfsoc_pulse_model.ip.lock import (
    main,
    promote_candidate_lock,
    validate_production_lock,
)
from rfsoc_pulse_model.ip.tcl import emit_catalog_discovery_tcl
from rfsoc_pulse_model.ip.types import HardwareArchitectureConfig


def valid_lock_fixture() -> dict[str, object]:
    config = HardwareArchitectureConfig.load_default()
    config_bytes = resources.files("rfsoc_pulse_model.config").joinpath(
        "ip_architecture.json"
    ).read_bytes()
    discovery_tcl_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
    request_payload = build_catalog_request(
        config,
        architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        generated_tcl_sha256=hashlib.sha256(discovery_tcl_bytes).hexdigest(),
    )
    request_bytes = canonical_json_bytes(request_payload)
    families = {
        family.family_id: (
            family.vlnv
            if family.vlnv is not None
            else family.catalog_pattern[:-1] + "1.0"
        )
        for family in config.required_families()
    }
    lock_payload = {
        "lock_schema_version": 1,
        "architecture_config_sha256": request_payload["architecture_config_sha256"],
        "generated_tcl_sha256": request_payload["generated_tcl_sha256"],
        "catalog_request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "vivado_version": "2025.2",
        "families": families,
    }
    return {
        "config": config,
        "request_bytes": request_bytes,
        "discovery_tcl_bytes": discovery_tcl_bytes,
        "lock_payload": lock_payload,
    }


class ProductionLockTest(unittest.TestCase):
    def test_lock_family_set_must_equal_required_family_set(self) -> None:
        fixture = valid_lock_fixture()
        self.assertTrue(validate_production_lock(**fixture).valid)

        missing = copy.deepcopy(fixture["lock_payload"])
        missing["families"].pop("axi_dma")
        with self.assertRaisesRegex(ValueError, "missing.*axi_dma"):
            validate_production_lock(**{**fixture, "lock_payload": missing})

        extra = copy.deepcopy(fixture["lock_payload"])
        extra["families"]["not_required"] = "xilinx.com:ip:xlconstant:1.1"
        with self.assertRaisesRegex(ValueError, "extra.*not_required"):
            validate_production_lock(**{**fixture, "lock_payload": extra})

    def test_lock_binds_discovery_not_realization_tcl(self) -> None:
        fixture = valid_lock_fixture()
        self.assertTrue(validate_production_lock(**fixture).valid)
        self.assertNotIn("realization_tcl_sha256", fixture["lock_payload"])
        self.assertNotIn(
            "realization_tcl_bytes",
            inspect.signature(validate_production_lock).parameters,
        )

        with self.assertRaisesRegex(ValueError, "generated_tcl_sha256"):
            validate_production_lock(
                **{
                    **fixture,
                    "discovery_tcl_bytes": b"changed discovery\n",
                }
            )

    def test_lock_rejects_wildcard_and_non_2_6_rfdc(self) -> None:
        fixture = valid_lock_fixture()
        wildcard = copy.deepcopy(fixture["lock_payload"])
        wildcard["families"]["axi_dma"] = "xilinx.com:ip:axi_dma:*"
        with self.assertRaisesRegex(ValueError, "version"):
            validate_production_lock(**{**fixture, "lock_payload": wildcard})

        stale_rfdc = copy.deepcopy(fixture["lock_payload"])
        stale_rfdc["families"]["rfdc"] = "xilinx.com:ip:usp_rf_data_converter:2.7"
        with self.assertRaisesRegex(ValueError, "2.6"):
            validate_production_lock(**{**fixture, "lock_payload": stale_rfdc})

    def test_promotion_writes_byte_identical_source_and_package_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(canonical_json_bytes(valid_lock_fixture()["lock_payload"]))
            promote_candidate_lock(
                candidate,
                root / "config/ip_lock.json",
                root / "src/rfsoc_pulse_model/config/ip_lock.json",
            )
            self.assertEqual(
                (root / "config/ip_lock.json").read_bytes(),
                (root / "src/rfsoc_pulse_model/config/ip_lock.json").read_bytes(),
            )

    def test_invalid_promotion_does_not_modify_either_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_text("{}\n", encoding="utf-8")
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            root_lock.parent.mkdir(parents=True)
            package_lock.parent.mkdir(parents=True)
            root_lock.write_bytes(b"previous-root\n")
            package_lock.write_bytes(b"previous-package\n")

            with self.assertRaisesRegex(ValueError, "lock"):
                promote_candidate_lock(candidate, root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), b"previous-root\n")
            self.assertEqual(package_lock.read_bytes(), b"previous-package\n")

    def test_promotion_cli_uses_explicit_candidate_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(canonical_json_bytes(valid_lock_fixture()["lock_payload"]))
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"

            self.assertEqual(
                main(
                    [
                        "promote",
                        "--candidate",
                        str(candidate),
                        "--root-lock",
                        str(root_lock),
                        "--package-lock",
                        str(package_lock),
                    ]
                ),
                0,
            )
            self.assertEqual(root_lock.read_bytes(), package_lock.read_bytes())

    def test_module_cli_does_not_preimport_its_own_main_module(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "rfsoc_pulse_model.ip.lock", "--help"],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("RuntimeWarning", completed.stderr)


if __name__ == "__main__":
    unittest.main()
