import copy
import hashlib
import inspect
from importlib import resources
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import rfsoc_pulse_model.ip.lock as lock_module
from rfsoc_pulse_model.ip.evidence import build_catalog_request, canonical_json_bytes
from rfsoc_pulse_model.ip.lock import (
    main,
    promote_candidate_lock,
    recover_interrupted_promotion,
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


def candidate_bytes() -> bytes:
    return canonical_json_bytes(valid_lock_fixture()["lock_payload"])


def candidate_with_duplicate_top_level_key() -> bytes:
    canonical = candidate_bytes().decode("utf-8")
    return (canonical.removesuffix("}\n") + ',\n  "vivado_version": "2025.2"\n}\n').encode(
        "utf-8"
    )


def candidate_with_duplicate_family_key() -> bytes:
    payload = valid_lock_fixture()["lock_payload"]
    families = payload["families"]
    family_json = json.dumps(families, sort_keys=True)
    duplicated = family_json.replace(
        '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0",',
        '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0", '
        '"axis_broadcaster": "xilinx.com:ip:axis_broadcaster:1.0",',
    )
    payload_json = json.dumps(
        {**payload, "families": None}, sort_keys=True
    ).replace('"families": null', f'"families": {duplicated}')
    return payload_json.encode("utf-8")


def hold_repository_lock(root_lock: str, package_lock: str, ready, release) -> None:
    from rfsoc_pulse_model.ip.lock import _repository_promotion_lock

    with _repository_promotion_lock(Path(root_lock), Path(package_lock)):
        ready.set()
        release.wait(15)


def write_recovery_journal(root: Path) -> tuple[Path, Path, Path, Path]:
    root_lock = root / "config/ip_lock.json"
    package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
    root_lock.parent.mkdir(parents=True, exist_ok=True)
    package_lock.parent.mkdir(parents=True, exist_ok=True)
    root_before = b"root-before"
    package_before = b"package-before"
    root_lock.write_bytes(root_before)
    package_lock.write_bytes(package_before)
    new_lock = candidate_bytes()
    journal_path = root_lock.parent / ".ip_lock.promotion.json"
    journal = {
        "journal_schema_version": 1,
        "phase": "prepared",
        "root_lock_path": str(root_lock.resolve()),
        "package_lock_path": str(package_lock.resolve()),
        "root_snapshot": {
            "exists": True,
            "sha256": hashlib.sha256(root_before).hexdigest(),
            "contents_hex": root_before.hex(),
        },
        "package_snapshot": {
            "exists": True,
            "sha256": hashlib.sha256(package_before).hexdigest(),
            "contents_hex": package_before.hex(),
        },
        "new_lock_hex": new_lock.hex(),
        "new_lock_sha256": hashlib.sha256(new_lock).hexdigest(),
    }
    journal_path.write_bytes(canonical_json_bytes(journal))
    return root_lock, package_lock, new_lock, journal_path


def rewrite_journal(journal_path: Path, mutate) -> None:
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    mutate(payload)
    journal_path.write_bytes(canonical_json_bytes(payload))


class ProductionLockTest(unittest.TestCase):
    def test_promoted_default_lock_is_current_and_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        root_bytes = (root / "config/ip_lock.json").read_bytes()
        package_bytes = (
            root / "src/rfsoc_pulse_model/config/ip_lock.json"
        ).read_bytes()
        self.assertEqual(root_bytes, package_bytes)

        config = HardwareArchitectureConfig.load_default()
        config_bytes = (
            root / "src/rfsoc_pulse_model/config/ip_architecture.json"
        ).read_bytes()
        discovery_bytes = emit_catalog_discovery_tcl(config).encode("utf-8")
        request_bytes = canonical_json_bytes(
            build_catalog_request(
                config,
                architecture_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                generated_tcl_sha256=hashlib.sha256(discovery_bytes).hexdigest(),
            )
        )
        validation = validate_production_lock(
            config,
            request_bytes,
            discovery_bytes,
            json.loads(root_bytes),
        )
        self.assertTrue(validation.valid)
        self.assertEqual(
            set(json.loads(root_bytes)["families"]),
            {family.family_id for family in config.required_families()},
        )
        self.assertNotIn("realization_tcl_sha256", json.loads(root_bytes))

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

    def test_promotion_rejects_duplicate_top_level_and_family_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            for name, raw_bytes in (
                ("duplicate-top.json", candidate_with_duplicate_top_level_key()),
                ("duplicate-family.json", candidate_with_duplicate_family_key()),
            ):
                candidate = root / name
                candidate.write_bytes(raw_bytes)
                with self.subTest(candidate=name):
                    with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                        promote_candidate_lock(candidate, root_lock, package_lock)
                    self.assertFalse(root_lock.exists())
                    self.assertFalse(package_lock.exists())

    def test_leftover_lock_path_from_a_crashed_owner_does_not_block_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(candidate_bytes())
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            lock_path = lock_module._promotion_lock_path(root_lock, package_lock)
            lock_path.write_text("other promotion", encoding="utf-8")

            promote_candidate_lock(candidate, root_lock, package_lock)
            self.assertEqual(root_lock.read_bytes(), package_lock.read_bytes())
            self.assertEqual(recover_interrupted_promotion(root_lock, package_lock), 0)

    def test_supported_concurrent_writer_is_rejected_by_os_advisory_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(candidate_bytes())
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            release = context.Event()
            holder = context.Process(
                target=hold_repository_lock,
                args=(str(root_lock), str(package_lock), ready, release),
            )
            holder.start()
            self.assertTrue(ready.wait(10), "lock holder did not become ready")
            try:
                with self.assertRaisesRegex(RuntimeError, "another participating writer"):
                    promote_candidate_lock(candidate, root_lock, package_lock)
            finally:
                release.set()
                holder.join(10)
            self.assertEqual(holder.exitcode, 0)

    def test_promotion_rejects_targets_outside_the_exact_repository_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(candidate_bytes())

            with self.assertRaisesRegex(ValueError, "exactly"):
                promote_candidate_lock(
                    candidate,
                    root / "different/ip_lock.json",
                    root / "src/rfsoc_pulse_model/config/ip_lock.json",
                )

    def test_snapshot_retains_the_exact_initial_bytes_for_its_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "ip_lock.json"
            target.write_bytes(b"initial-bytes")
            snapshot = lock_module._snapshot_target(target)
            target.write_bytes(b"external-later-bytes")

            self.assertEqual(snapshot.contents, b"initial-bytes")

    def test_promotion_recheck_refuses_external_edit_since_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(candidate_bytes())
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            root_lock.parent.mkdir(parents=True)
            package_lock.parent.mkdir(parents=True)
            root_lock.write_bytes(b"old-root")
            package_lock.write_bytes(b"old-package")
            original = lock_module._assert_snapshot_current
            edited = False

            def external_edit_then_check(target, snapshot):
                nonlocal edited
                if not edited and target == root_lock:
                    target.write_bytes(b"external-editor")
                    edited = True
                return original(target, snapshot)

            with mock.patch.object(
                lock_module,
                "_assert_snapshot_current",
                side_effect=external_edit_then_check,
            ):
                with self.assertRaisesRegex(RuntimeError, "changed since snapshot"):
                    promote_candidate_lock(candidate, root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), b"external-editor")
            self.assertEqual(package_lock.read_bytes(), b"old-package")

    def test_nonparticipating_edit_in_replace_window_is_outside_lock_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            expected = candidate_bytes()
            candidate.write_bytes(expected)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            root_lock.parent.mkdir(parents=True)
            package_lock.parent.mkdir(parents=True)
            root_lock.write_bytes(b"old-root")
            package_lock.write_bytes(b"old-package")
            real_replace = lock_module.os.replace

            def external_edit_before_real_replace(source, destination):
                if Path(destination) == root_lock:
                    root_lock.write_bytes(b"manual-editor")
                return real_replace(source, destination)

            with mock.patch.object(
                lock_module.os,
                "replace",
                side_effect=external_edit_before_real_replace,
            ):
                promote_candidate_lock(candidate, root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertIn(
                "cannot atomically protect non-participating editors",
                lock_module.LOCK_WRITER_CONCURRENCY_CONTRACT,
            )

    def test_failed_rollback_retains_recovery_data_and_recover_rolls_forward(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            expected = candidate_bytes()
            candidate.write_bytes(expected)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            root_lock.parent.mkdir(parents=True)
            package_lock.parent.mkdir(parents=True)
            root_lock.write_bytes(b"old-root")
            package_lock.write_bytes(b"old-package")
            real_replace = lock_module.os.replace
            root_replaced = False

            def fail_package_replace_and_root_rollback(source, destination):
                nonlocal root_replaced
                if Path(destination) == package_lock:
                    raise OSError("injected package replacement failure")
                if Path(destination) == root_lock and root_replaced:
                    raise OSError("injected root rollback failure")
                result = real_replace(source, destination)
                if Path(destination) == root_lock:
                    root_replaced = True
                return result

            with mock.patch.object(
                lock_module.os,
                "replace",
                side_effect=fail_package_replace_and_root_rollback,
            ):
                with self.assertRaisesRegex(RuntimeError, "recovery required"):
                    promote_candidate_lock(candidate, root_lock, package_lock)

            journal_path = lock_module._promotion_journal_path(root_lock, package_lock)
            self.assertTrue(journal_path.is_file())
            journal = lock_module.decode_production_lock_json(
                journal_path.read_bytes(), "test promotion journal"
            )
            self.assertEqual(journal["new_lock_hex"], expected.hex())
            self.assertEqual(journal["root_snapshot"]["contents_hex"], b"old-root".hex())
            self.assertEqual(
                journal["package_snapshot"]["contents_hex"], b"old-package".hex()
            )
            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertEqual(package_lock.read_bytes(), b"old-package")

            recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertEqual(package_lock.read_bytes(), expected)
            self.assertFalse(journal_path.exists())

    def test_directory_flush_failure_after_root_replace_preserves_recovery_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            expected = candidate_bytes()
            candidate.write_bytes(expected)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            root_lock.parent.mkdir(parents=True)
            package_lock.parent.mkdir(parents=True)
            root_lock.write_bytes(b"old-root")
            package_lock.write_bytes(b"old-package")
            original_flush = lock_module._flush_directory

            def fail_after_root_replace(directory):
                if (
                    Path(directory) == root_lock.parent
                    and root_lock.exists()
                    and root_lock.read_bytes() == expected
                ):
                    raise RuntimeError("injected directory flush failure")
                return original_flush(directory)

            with mock.patch.object(
                lock_module,
                "_flush_directory",
                side_effect=fail_after_root_replace,
            ):
                with self.assertRaisesRegex(RuntimeError, "recovery required"):
                    promote_candidate_lock(candidate, root_lock, package_lock)

            journal_path = lock_module._promotion_journal_path(root_lock, package_lock)
            self.assertTrue(journal_path.is_file())

    @unittest.skipIf(os.name == "nt", "Windows symlink permission is host dependent")
    def test_recovery_rejects_journal_symlink_without_touching_external_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock, package_lock, _, journal_path = write_recovery_journal(root)
            external = root / "external-journal.json"
            external.write_bytes(journal_path.read_bytes())
            marker = root / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            journal_path.unlink()
            os.symlink(external, journal_path)

            with self.assertRaisesRegex(RuntimeError, "symlink|unsafe"):
                recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(marker.read_bytes(), b"external data")
            self.assertEqual(external.read_bytes(), canonical_json_bytes(lock_module.decode_production_lock_json(external.read_bytes(), "external")))
            self.assertEqual(root_lock.read_bytes(), b"root-before")
            self.assertEqual(package_lock.read_bytes(), b"package-before")

    @unittest.skipUnless(os.name == "nt", "real NTFS junction probe")
    def test_recovery_rejects_windows_junction_journal_without_touching_external_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock, package_lock, _, journal_path = write_recovery_journal(root)
            external = root / "external"
            external.mkdir()
            marker = external / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            journal_path.unlink()
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(journal_path), str(external)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with self.assertRaisesRegex(RuntimeError, "reparse|unsafe"):
                recover_interrupted_promotion(root_lock, package_lock)
            self.assertEqual(marker.read_bytes(), b"external data")

    @unittest.skipUnless(os.name == "nt", "real NTFS junction probe")
    def test_windows_journal_handle_survives_junction_swap_without_external_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock, package_lock, expected, journal_path = write_recovery_journal(root)
            external = root / "external"
            external.mkdir()
            marker = external / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            original_read = lock_module._read_descriptor_bytes
            swapped = False

            def swap_after_handle_is_open(descriptor):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    journal_path.unlink()
                    completed = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(journal_path), str(external)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                return original_read(descriptor)

            with mock.patch.object(
                lock_module, "_read_descriptor_bytes", side_effect=swap_after_handle_is_open
            ):
                with self.assertRaisesRegex(RuntimeError, "unsafe promotion journal directory"):
                    recover_interrupted_promotion(root_lock, package_lock)

            self.assertTrue(swapped)
            self.assertEqual(marker.read_bytes(), b"external data")
            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertEqual(package_lock.read_bytes(), expected)
            journal_path.rmdir()

    def test_journal_cleanup_unlinks_a_swapped_symlink_not_external_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = root / "config/.ip_lock.promotion.json"
            journal.parent.mkdir()
            external = root / "external-journal.json"
            external.write_bytes(b"external data")
            try:
                os.symlink(external, journal)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            lock_module._remove_promotion_journal(journal)

            self.assertFalse(journal.exists())
            self.assertEqual(external.read_bytes(), b"external data")

    def test_recovery_rejects_duplicate_journal_keys_without_target_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock, package_lock, _, journal_path = write_recovery_journal(root)
            raw = journal_path.read_text(encoding="utf-8")
            journal_path.write_text(
                raw.removesuffix("}\n") + ',\n  "phase": "prepared"\n}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), b"root-before")
            self.assertEqual(package_lock.read_bytes(), b"package-before")

    def test_recovery_rejects_noninteger_journal_schema_before_target_write(self) -> None:
        for invalid_version in (True, 1.0, "1"):
            with self.subTest(invalid_version=invalid_version), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                root_lock, package_lock, _, journal_path = write_recovery_journal(root)
                rewrite_journal(
                    journal_path,
                    lambda payload, value=invalid_version: payload.__setitem__(
                        "journal_schema_version", value
                    ),
                )

                with self.assertRaisesRegex(RuntimeError, "journal schema"):
                    recover_interrupted_promotion(root_lock, package_lock)

                self.assertEqual(root_lock.read_bytes(), b"root-before")
                self.assertEqual(package_lock.read_bytes(), b"package-before")
                self.assertTrue(journal_path.is_file())

    def test_recovery_rejects_noncanonical_journal_target_paths(self) -> None:
        cases = (
            (
                "root dotdot",
                "root_lock_path",
                lambda root_lock, package_lock: str(
                    root_lock.parent / ".." / "config" / "ip_lock.json"
                ),
            ),
            (
                "package trailing whitespace",
                "package_lock_path",
                lambda root_lock, package_lock: str(package_lock) + " ",
            ),
        )
        for name, field, value_for in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                root_lock, package_lock, _, journal_path = write_recovery_journal(root)
                rewrite_journal(
                    journal_path,
                    lambda payload: payload.__setitem__(
                        field, value_for(root_lock, package_lock)
                    ),
                )

                with self.assertRaisesRegex(RuntimeError, "noncanonical .*_lock_path"):
                    recover_interrupted_promotion(root_lock, package_lock)

                self.assertEqual(root_lock.read_bytes(), b"root-before")
                self.assertEqual(package_lock.read_bytes(), b"package-before")
                self.assertTrue(journal_path.is_file())

    def test_recovery_rejects_noncanonical_hex_and_scalar_types(self) -> None:
        cases = (
            (
                "new hex whitespace",
                lambda payload: payload.__setitem__(
                    "new_lock_hex", payload["new_lock_hex"][:2] + " " + payload["new_lock_hex"][2:]
                ),
            ),
            (
                "new hex uppercase",
                lambda payload: payload.__setitem__("new_lock_hex", payload["new_lock_hex"].upper()),
            ),
            ("new hex odd", lambda payload: payload.__setitem__("new_lock_hex", "a")),
            (
                "snapshot hex whitespace",
                lambda payload: payload["root_snapshot"].__setitem__("contents_hex", "72 6f6f74"),
            ),
            ("new hex bool", lambda payload: payload.__setitem__("new_lock_hex", True)),
            ("phase bool", lambda payload: payload.__setitem__("phase", True)),
            ("root path bool", lambda payload: payload.__setitem__("root_lock_path", True)),
            ("hash bool", lambda payload: payload.__setitem__("new_lock_sha256", True)),
            (
                "exists integer",
                lambda payload: payload["root_snapshot"].__setitem__("exists", 1),
            ),
            (
                "snapshot hash integer",
                lambda payload: payload["root_snapshot"].__setitem__("sha256", 1),
            ),
            (
                "snapshot hex integer",
                lambda payload: payload["root_snapshot"].__setitem__("contents_hex", 1),
            ),
        )
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                root_lock, package_lock, _, journal_path = write_recovery_journal(root)
                rewrite_journal(journal_path, mutate)

                with self.assertRaises(RuntimeError):
                    recover_interrupted_promotion(root_lock, package_lock)

                self.assertEqual(root_lock.read_bytes(), b"root-before")
                self.assertEqual(package_lock.read_bytes(), b"package-before")
                self.assertTrue(journal_path.is_file())

    def test_recovery_rejects_noncanonical_raw_journal_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock, package_lock, _, journal_path = write_recovery_journal(root)
            journal_path.write_bytes(journal_path.read_bytes() + b"\n")

            with self.assertRaisesRegex(RuntimeError, "not canonical"):
                recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), b"root-before")
            self.assertEqual(package_lock.read_bytes(), b"package-before")


if __name__ == "__main__":
    unittest.main()
