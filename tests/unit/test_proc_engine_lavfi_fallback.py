"""proc_engine fallback must be FFmpeg lavfi (near-zero RAM), not numpy frame pump."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_generate_fallback_loop_uses_lavfi_not_numpy():
    src = Path("src/media/proc_engine.py").read_text(encoding="utf-8")
    # Method body after def _generate_fallback_loop
    idx = src.index("def _generate_fallback_loop")
    body = src[idx : idx + 1800]
    assert "lavfi" in body
    assert "gradients=" in body
    assert "np.zeros" not in body
    assert "import numpy" not in body
    assert "from PIL" not in body


def test_generate_fallback_loop_writes_mp4(tmp_path: Path):
    from src.media.proc_engine import ProceduralVideoEngine

    out = tmp_path / "fb.mp4"
    eng = ProceduralVideoEngine()
    path = eng._generate_fallback_loop("dark_ambient", 320, 180, 24, 1.0, out)
    assert path.is_file()
    assert path.stat().st_size > 0
