"""Ensure src.media package import does not eagerly load wgpu / native_procedural."""

from __future__ import annotations

import sys


def test_import_src_media_does_not_load_native_procedural():
    """Package import must not require wgpu; NativeProceduralEngine is lazy via __getattr__."""
    for key in list(sys.modules):
        if key == "src.media" or key.startswith("src.media."):
            del sys.modules[key]

    import src.media as media

    assert "src.media.native_procedural" not in sys.modules
    assert "NativeProceduralEngine" in media.__all__
    assert hasattr(media, "__getattr__")
