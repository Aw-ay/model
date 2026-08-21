from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from rfsoc_pulse_model.ip.environment import (
    AUTHORITY_FILENAMES,
    PYTHON_PACKAGE_NAMES,
    EnvironmentManifest,
    EnvironmentReady,
    authority_absolute_path_violations,
    authority_package_mismatches,
    authority_sha256,
    capture_environment_manifest,
    parse_environment_manifest,
    parse_environment_ready,
    python_package_audit,
    vivado_identity,
)
from rfsoc_pulse_model.ip.environment import _assert_fresh_build_root


class EnvironmentProvenanceTests(unittest.TestCase):
    @staticmethod
    def _packages() -> dict[str, str]:
        return {name: "present" for name in PYTHON_PACKAGE_NAMES}

    def test_manifest_is_canonical_and_hashable(self) -> None:
        manifest = EnvironmentManifest(
            host="new_machine",
            os="Windows 11",
            python="3.12.9",
            vivado="2025.2",
            vivado_build="6299465",
            repo_root="E:/AWAY/RFSOC-model",
            git_commit="0" * 40,
            timezone="Asia/Shanghai",
            git_status_clean=True,
            vivado_executable="C:/Xilinx/2025.2/Vivado/bin/vivado.bat",
        )

        raw = manifest.bytes()

        self.assertEqual(parse_environment_manifest(raw), manifest)
        self.assertEqual(len(manifest.sha256), 64)
        self.assertEqual(manifest.sha256, manifest.sha256)

    def test_ready_payload_must_match_ready_state(self) -> None:
        ready = EnvironmentReady(
            ready=True,
            reasons=(),
            environment_manifest_sha256="a" * 64,
            git_commit="1" * 40,
            git_status_clean=True,
            authority_sha256={name: "b" * 64 for name in AUTHORITY_FILENAMES},
            python_packages=self._packages(),
        )
        self.assertEqual(parse_environment_ready(ready.bytes()), ready)

        with self.assertRaisesRegex(ValueError, "clean Git"):
            parse_environment_ready(
                EnvironmentReady(
                    ready=True,
                    reasons=(),
                    environment_manifest_sha256="a" * 64,
                    git_commit="1" * 40,
                    git_status_clean=False,
                    authority_sha256={name: "b" * 64 for name in AUTHORITY_FILENAMES},
                    python_packages=self._packages(),
                ).bytes()
            )

        blocked = EnvironmentReady(
            ready=False,
            reasons=("git_working_tree_not_clean",),
            environment_manifest_sha256="a" * 64,
            git_commit="1" * 40,
            git_status_clean=False,
            authority_sha256={name: "b" * 64 for name in AUTHORITY_FILENAMES},
            python_packages=self._packages(),
        )
        self.assertEqual(parse_environment_ready(blocked.bytes()), blocked)

        with self.assertRaisesRegex(ValueError, "failure reasons"):
            parse_environment_ready(
                ready.bytes().replace(b'"ready": true', b'"ready": true')
                .replace(b'"reasons": []', b'"reasons": ["tampered"]')
            )

    def test_python_package_audit_reports_requested_inventory(self) -> None:
        packages = python_package_audit()

        self.assertEqual(set(packages), set(PYTHON_PACKAGE_NAMES))
        self.assertNotEqual(packages["unittest"], "missing")
        self.assertTrue(all(isinstance(value, str) and value for value in packages.values()))

    def test_authority_files_are_fixed_and_portable(self) -> None:
        expected = {
            "default.json": "d92c4a334728af441b22fa907e55cf4d6d236d899f46cbe3cd3ed7f26f9d5eb3",
            "ip_architecture.json": "36034e9c7b64061cdd449fb43030aea96368c95d6e88c8c6a0a9154da9e0bd96",
            "ip_lock.json": "0b1c92166b605a0a56c867fb144896d23599ade95538a29b72c9c274437fbe97",
            "ps_platform.json": "a1243d78a90ccb8e00f34749a8c3f18bf55870130c8f8372402407cf5591d11f",
        }
        repository_root = __import__("pathlib").Path(__file__).resolve().parents[2]

        self.assertEqual(authority_sha256(repository_root), expected)
        self.assertEqual(authority_absolute_path_violations(repository_root), ())

    def test_manifest_hash_changes_when_environment_changes(self) -> None:
        base = EnvironmentManifest(
            host="machine-a",
            os="Windows 11",
            python="3.12.9",
            vivado="2025.2",
            vivado_build="6299465",
            repo_root="E:/AWAY/RFSOC-model",
            git_commit="2" * 40,
            timezone="Asia/Shanghai",
            git_status_clean=True,
            vivado_executable="C:/Xilinx/2025.2/Vivado/bin/vivado.bat",
        )
        changed = replace(base, host="machine-b")

        self.assertNotEqual(base.sha256, changed.sha256)

    def test_vivado_identity_parses_version_command_output(self) -> None:
        version_output = """vivado v2025.1 (64-bit)
Tool Version Limit: 2025.05
SW Build 6140274 on Thu May 22 00:12:29 MDT 2025
"""
        with patch(
            "rfsoc_pulse_model.ip.environment.subprocess.run",
            return_value=SimpleNamespace(
                returncode=1, stdout=version_output, stderr=""
            ),
        ):
            self.assertEqual(
                vivado_identity(Path("C:/Xilinx/vivado.bat")),
                ("2025.1", "6140274"),
            )

    def test_vivado_identity_parses_report_style_build_output(self) -> None:
        report_style = (
            "Vivado v.2025.2 (win64) Build 6299465 Fri Nov 14 19:35:11 GMT 2025\n"
        )
        with patch(
            "rfsoc_pulse_model.ip.environment.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=report_style, stderr=""),
        ):
            self.assertEqual(
                vivado_identity(Path("C:/Xilinx/vivado.bat")),
                ("2025.2", "6299465"),
            )

    def test_missing_vivado_executable_is_a_blocked_probe(self) -> None:
        with patch(
            "rfsoc_pulse_model.ip.environment.subprocess.run",
            side_effect=FileNotFoundError("vivado.bat"),
        ):
            self.assertIsNone(vivado_identity(Path("C:/missing/vivado.bat")))

    def test_packaged_authority_drift_is_detected(self) -> None:
        root_bytes = {name: b"root" for name in AUTHORITY_FILENAMES}

        class FakePackagedRoot:
            def joinpath(self, filename):
                return SimpleNamespace(
                    read_bytes=lambda: b"packaged" if filename == "default.json" else b"root"
                )

        with patch(
            "rfsoc_pulse_model.ip.environment.authority_bytes",
            return_value=root_bytes,
        ), patch(
            "rfsoc_pulse_model.ip.environment.resources.files",
            return_value=FakePackagedRoot(),
        ):
            self.assertEqual(
                authority_package_mismatches(Path("E:/AWAY/RFSOC-model")),
                ("default.json",),
            )

    def test_manifest_persists_explicit_vivado_installation(self) -> None:
        with patch(
            "rfsoc_pulse_model.ip.environment.git_identity",
            return_value=("3" * 40, True),
        ), patch(
            "rfsoc_pulse_model.ip.environment.vivado_identity",
            return_value=("2025.2", "6299465"),
        ):
            manifest = capture_environment_manifest(
                Path("E:/AWAY/RFSOC-model"),
                vivado_executable=Path("C:/Xilinx/2025.2/Vivado/bin/vivado.bat"),
                timezone="Asia/Shanghai",
            )

        self.assertEqual(
            manifest.vivado_executable,
            "C:\\Xilinx\\2025.2\\Vivado\\bin\\vivado.bat",
        )
        self.assertEqual(parse_environment_manifest(manifest.bytes()), manifest)

    def test_fresh_migration_removes_root_attempt_local_artifacts(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as temporary:
            repository_root = Path(temporary)
            (repository_root / "build" / "old").mkdir(parents=True)
            (repository_root / "build" / "old" / "evidence.json").write_text("old")
            for dirname in (".Xil", ".runs", ".gen"):
                (repository_root / dirname).mkdir()
            for filename in ("project.xpr", "old_shell.xpr", "journal.log", "vivado.jou"):
                (repository_root / filename).write_text("machine-local")
            (repository_root / "source.txt").write_text("keep")

            fresh_build = _assert_fresh_build_root(
                repository_root, repository_root / "build"
            )

            self.assertEqual(fresh_build, repository_root / "build")
            self.assertEqual(list(fresh_build.iterdir()), [])
            for dirname in (".Xil", ".runs", ".gen"):
                self.assertFalse((repository_root / dirname).exists())
            for filename in ("project.xpr", "old_shell.xpr", "journal.log", "vivado.jou"):
                self.assertFalse((repository_root / filename).exists())
            self.assertEqual((repository_root / "source.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
