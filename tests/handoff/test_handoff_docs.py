from __future__ import annotations

import re
import subprocess
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs" / "handoff"
EXPECTED = {
    "README.md",
    "CURRENT_STATE.md",
    "ARCHITECTURE.md",
    "DECISIONS.md",
    "VERIFICATION_EVIDENCE.md",
    "IMPLEMENTATION_HISTORY.md",
    "OPEN_ISSUES.md",
    "NEXT_STEPS.md",
    "FILE_INDEX.md",
    "NEW_CHAT_PROMPT.md",
}
FORBIDDEN = (
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"\.codex(?:[/\\]|$)", re.IGNORECASE),
    re.compile(r"session[_ -]?id", re.IGNORECASE),
    re.compile(r"auth\.json", re.IGNORECASE),
    re.compile(r"Response annotations|Message Type:|<oai-mem-citation>", re.IGNORECASE),
)
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
COMMIT = re.compile(r"commit:([0-9a-f]{7,40})")


class HandoffDocsTest(unittest.TestCase):
    def docs(self) -> dict[str, str]:
        return {path.name: path.read_text(encoding="utf-8") for path in HANDOFF.glob("*.md")}

    def test_exact_document_set(self) -> None:
        self.assertEqual({path.name for path in HANDOFF.glob("*.md")}, EXPECTED)

    def test_no_local_codex_or_raw_chat_material(self) -> None:
        for name, text in self.docs().items():
            for pattern in FORBIDDEN:
                self.assertIsNone(pattern.search(text), f"{name}: {pattern.pattern}")

    def test_all_relative_markdown_links_resolve(self) -> None:
        for path in HANDOFF.glob("*.md"):
            for target in LINK.findall(path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "#")):
                    continue
                self.assertFalse(Path(target).is_absolute(), f"absolute link in {path.name}: {target}")
                self.assertTrue((path.parent / target.split("#", 1)[0]).resolve().exists(), f"broken link: {target}")

    def test_all_commit_markers_resolve(self) -> None:
        refs = {ref for text in self.docs().values() for ref in COMMIT.findall(text)}
        self.assertIn("89a2362", refs)
        for ref in refs:
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"missing commit {ref}: {result.stderr}")

    def test_authority_mirrors_are_byte_identical(self) -> None:
        for name in ("default.json", "ip_architecture.json", "ip_lock.json", "ps_platform.json"):
            self.assertEqual(
                (ROOT / "config" / name).read_bytes(),
                (ROOT / "src" / "rfsoc_pulse_model" / "config" / name).read_bytes(),
                name,
            )

    def test_entrypoint_and_blockers_are_explicit(self) -> None:
        docs = self.docs()
        self.assertIn("CURRENT_STATE.md", docs["README.md"])
        self.assertIn("NEW_CHAT_PROMPT.md", docs["README.md"])
        self.assertIn("BD-T5-REPORT-PROTOCOL", docs["OPEN_ISSUES.md"])
        self.assertIn("BD-T5-MTS-AUTHORITY", docs["OPEN_ISSUES.md"])
        self.assertIn("Do not start Task 6", docs["NEW_CHAT_PROMPT.md"])


if __name__ == "__main__":
    unittest.main()
