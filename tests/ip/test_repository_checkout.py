from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class RepositoryCheckoutPolicyTest(unittest.TestCase):
    def test_hash_bound_json_authorities_are_checked_out_with_lf(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        authorities = (
            "config/ip_architecture.json",
            "config/ip_lock.json",
            "src/rfsoc_pulse_model/config/ip_architecture.json",
            "src/rfsoc_pulse_model/config/ip_lock.json",
        )

        result = subprocess.run(
            ["git", "check-attr", "eol", "--", *authorities],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.stdout.splitlines(),
            [f"{path}: eol: lf" for path in authorities],
        )


if __name__ == "__main__":
    unittest.main()
