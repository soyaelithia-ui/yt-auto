"""Unit tests for repository documentation integrity, links, formatting and line budgets."""
from __future__ import annotations

import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"

ACTIVE_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "PROJECT.md",
    DOCS_DIR / "README.md",
    DOCS_DIR / "ARQUITECTURA.md",
    DOCS_DIR / "FLUJO_VIDEOS.md",
    DOCS_DIR / "MULTICHANNEL_PIPELINE.md",
    DOCS_DIR / "OPERACION.md",
    DOCS_DIR / "CONFIGURACION_SECRETOS.md",
    DOCS_DIR / "INTEGRACIONES_Y_SERVICIOS.md",
    DOCS_DIR / "AGENTES_IA_Y_POLITICA.md",
    DOCS_DIR / "TROUBLESHOOTING.md",
    DOCS_DIR / "REFERENCIAS_Y_VERSIONES.md",
]


class TestDocumentationIntegrity:
    """Verifies that all active documentation adheres to quality and format standards."""

    def test_all_active_docs_exist(self) -> None:
        """Every expected consolidated documentation file must exist."""
        for doc in ACTIVE_DOCS:
            assert doc.is_file(), f"Missing required document: {doc}"

    def test_no_foreign_moku_paths_in_active_docs(self) -> None:
        """No hardcoded /home/Moku/ or foreign paths allowed in active docs."""
        for doc in ACTIVE_DOCS:
            content = doc.read_text(encoding="utf-8")
            assert "/home/Moku" not in content, f"Found foreign /home/Moku path in {doc.name}"

    def test_all_relative_links_resolve(self) -> None:
        """All relative links within active markdown files must resolve to existing files."""
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        broken_links = []

        for doc in ACTIVE_DOCS:
            content = doc.read_text(encoding="utf-8")
            for match in link_pattern.finditer(content):
                text, url = match.group(1), match.group(2)
                if url.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                clean_url = url.split("#")[0]
                if not clean_url:
                    continue
                target = (doc.parent / clean_url).resolve()
                if not target.exists():
                    broken_links.append(f"{doc.name} -> [{text}]({url}) [Target: {target}]")

        assert not broken_links, f"Broken relative links detected:\n" + "\n".join(broken_links)

    def test_code_blocks_are_tagged(self) -> None:
        """All code fences in active docs must specify a syntax language."""
        untagged_blocks = []
        for doc in ACTIVE_DOCS:
            lines = doc.read_text(encoding="utf-8").splitlines()
            in_fence = False
            for line_idx, line in enumerate(lines, 1):
                if line.startswith("```"):
                    tag = line[3:].strip()
                    if not in_fence:
                        in_fence = True
                        if not tag:
                            untagged_blocks.append(f"{doc.name}:{line_idx}")
                    else:
                        in_fence = False

        assert not untagged_blocks, f"Untagged code blocks detected:\n" + "\n".join(untagged_blocks)

    def test_total_lines_budget_under_1000(self) -> None:
        """Total lines in active docs must remain compact and condensed (<= 1000 lines)."""
        total_lines = sum(len(doc.read_text(encoding="utf-8").splitlines()) for doc in ACTIVE_DOCS)
        assert total_lines <= 1000, f"Active docs exceed line budget: {total_lines} > 1000"
