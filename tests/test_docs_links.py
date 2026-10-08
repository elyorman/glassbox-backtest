"""Relative Markdown links in governing docs must resolve; broken links hide superseded rules."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def governing_documents():
    # Plans and specs under docs/superpowers quote link text inside code blocks; they are not governing docs.
    documents = [path for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts]
    return [ROOT / "README.md", ROOT / "PROJECT.md", ROOT / "AGENTS.md"] + sorted(documents)


class DocsLinkTest(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for document in governing_documents():
            for match in LINK.finditer(document.read_text(encoding="utf-8")):
                target = match.group(1)
                if re.match(r"[a-z]+://", target) or target.startswith("mailto:"):
                    continue
                if not (document.parent / target).exists():
                    broken.append(f"{document.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [], "Broken relative links:\n" + "\n".join(broken))

    def test_governing_documents_exist(self):
        for name in ("STRATEGY_EVIDENCE.md", "RESEARCH_LEDGER.md"):
            self.assertTrue((ROOT / "docs" / name).exists(), f"docs/{name} is required by the standard")
