"""Relative Markdown links in governing docs must resolve; broken links hide superseded rules."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")
SCHEME = re.compile(r"[a-z]+://", re.IGNORECASE)


def governing_documents():
    # Plans and specs under docs/superpowers quote link text inside code blocks; they are not governing docs.
    documents = [path for path in DOCS.rglob("*.md") if path.relative_to(DOCS).parts[0] != "superpowers"]
    return [ROOT / "README.md", ROOT / "PROJECT.md", ROOT / "AGENTS.md"] + sorted(documents)


def link_is_broken(document, target):
    """A link must resolve to a tracked-location file inside the repository, never under ignored local/."""
    resolved = (document.parent / target).resolve()
    inside_repo = ROOT == resolved or ROOT in resolved.parents
    under_local = ROOT / "local" in resolved.parents
    return not resolved.exists() or not inside_repo or under_local


class DocsLinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for document in governing_documents():
            for match in LINK.finditer(document.read_text(encoding="utf-8")):
                target = match.group(1)
                if SCHEME.match(target) or target.startswith("mailto:"):
                    continue
                if link_is_broken(document, target):
                    broken.append(f"{document.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [], "Broken relative links:\n" + "\n".join(broken))

    def test_governing_documents_exist(self):
        for name in ("STRATEGY_EVIDENCE.md", "RESEARCH_LEDGER.md"):
            self.assertTrue((DOCS / name).exists(), f"docs/{name} is required by the standard")
