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


def write_recovery_transaction(root: Path, transaction: Path) -> tuple[Path, Path, Path]:
    root_lock = root / "config/ip_lock.json"
    package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
    root_lock.parent.mkdir(parents=True, exist_ok=True)
    package_lock.parent.mkdir(parents=True, exist_ok=True)
    root_before = b"root-before"
    package_before = b"package-before"
    root_lock.write_bytes(root_before)
    package_lock.write_bytes(package_before)
    new_lock = candidate_bytes()
    transaction.mkdir(parents=True)
    (transaction / "new.lock").write_bytes(new_lock)
    (transaction / "root.before").write_bytes(root_before)
    (transaction / "package.before").write_bytes(package_before)
    journal = {
        "transaction_schema_version": 1,
        "root_lock_path": str(root_lock.resolve()),
        "package_lock_path": str(package_lock.resolve()),
        "root_snapshot": {
            "exists": True,
            "sha256": hashlib.sha256(root_before).hexdigest(),
        },
        "package_snapshot": {
            "exists": True,
            "sha256": hashlib.sha256(package_before).hexdigest(),
        },
        "new_lock_sha256": hashlib.sha256(new_lock).hexdigest(),
    }
    (transaction / "journal.json").write_bytes(canonical_json_bytes(journal))
    return root_lock, package_lock, new_lock


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

            transaction_dirs = list(
                lock_module._transaction_root(root_lock, package_lock).glob("*")
            )
            self.assertEqual(len(transaction_dirs), 1)
            self.assertTrue((transaction_dirs[0] / "journal.json").is_file())
            self.assertTrue((transaction_dirs[0] / "root.before").is_file())
            self.assertTrue((transaction_dirs[0] / "package.before").is_file())
            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertEqual(package_lock.read_bytes(), b"old-package")

            recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(root_lock.read_bytes(), expected)
            self.assertEqual(package_lock.read_bytes(), expected)
            self.assertFalse(list(lock_module._transaction_root(root_lock, package_lock).glob("*")))

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

            transactions = list(
                lock_module._transaction_root(root_lock, package_lock).glob("*")
            )
            self.assertEqual(len(transactions), 1)
            self.assertTrue((transactions[0] / "journal.json").is_file())
            self.assertTrue((transactions[0] / "root.before").is_file())

    @unittest.skipIf(os.name == "nt", "Windows has no unprivileged directory symlink")
    def test_recovery_rejects_transaction_entry_symlink_without_touching_external_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external"
            transaction = external / ("a" * 32)
            root_lock, package_lock, _ = write_recovery_transaction(root, transaction)
            marker = external / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            transaction_root = lock_module._transaction_root(root_lock, package_lock)
            transaction_root.mkdir()
            os.symlink(transaction, transaction_root / transaction.name, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, "symlink|unsafe"):
                recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(marker.read_bytes(), b"external data")
            self.assertEqual(root_lock.read_bytes(), b"root-before")
            self.assertEqual(package_lock.read_bytes(), b"package-before")

    def test_recovery_rejects_windows_reparse_transaction_entry_without_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            transaction_root = lock_module._transaction_root(root_lock, package_lock)
            transaction = transaction_root / ("b" * 32)
            transaction.mkdir(parents=True)
            marker = transaction / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            original = lock_module._is_link_or_reparse

            with mock.patch.object(
                lock_module,
                "_is_link_or_reparse",
                side_effect=lambda path: Path(path) == transaction or original(path),
            ):
                with self.assertRaisesRegex(RuntimeError, "reparse|unsafe"):
                    recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(marker.read_bytes(), b"external data")

    def test_recovery_rejects_windows_reparse_transaction_root_without_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_lock = root / "config/ip_lock.json"
            package_lock = root / "src/rfsoc_pulse_model/config/ip_lock.json"
            transaction_root = lock_module._transaction_root(root_lock, package_lock)
            transaction_root.mkdir(parents=True)
            marker = transaction_root / "do-not-delete.txt"
            marker.write_bytes(b"external data")
            original = lock_module._is_link_or_reparse

            with mock.patch.object(
                lock_module,
                "_is_link_or_reparse",
                side_effect=lambda path: Path(path) == transaction_root or original(path),
            ):
                with self.assertRaisesRegex(RuntimeError, "reparse|unsafe"):
                    recover_interrupted_promotion(root_lock, package_lock)

            self.assertEqual(marker.read_bytes(), b"external data")

    def test_recovery_rejects_reparse_journal_without_touching_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = root / ".ip_lock.transactions" / ("d" * 32)
            root_lock, package_lock, _ = write_recovery_transaction(root, transaction)
            journal = transaction / "journal.json"
            original = lock_module._is_link_or_reparse

            with mock.patch.object(
                lock_module,
                "_is_link_or_reparse",
                side_effect=lambda path: Path(path) == journal or original(path),
            ):
                with self.assertRaisesRegex(RuntimeError, "reparse|unsafe"):
                    recover_interrupted_promotion(root_lock, package_lock)

            self.assertTrue(journal.is_file())
            self.assertEqual(root_lock.read_bytes(), b"root-before")
            self.assertEqual(package_lock.read_bytes(), b"package-before")

    def test_transaction_cleanup_rejects_unknown_entry_and_preserves_all_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = root / ".ip_lock.transactions" / ("c" * 32)
            root_lock, package_lock, _ = write_recovery_transaction(root, transaction)
            unknown = transaction / "unexpected.txt"
            unknown.write_bytes(b"do not delete")

            with self.assertRaisesRegex(RuntimeError, "unknown transaction entry"):
                lock_module._remove_transaction(transaction)

            self.assertTrue((transaction / "journal.json").is_file())
            self.assertTrue((transaction / "new.lock").is_file())
            self.assertEqual(unknown.read_bytes(), b"do not delete")
            self.assertTrue(root_lock.is_file())
            self.assertTrue(package_lock.is_file())


if __name__ == "__main__":
    unittest.main()
