from src.media.lavfi_palettes import resolve_lavfi_palette, LAVFI_CATEGORY_PALETTES
from pathlib import Path

def test_shared_palette_ssot():
    assert "scp" in LAVFI_CATEGORY_PALETTES
    assert resolve_lavfi_palette("SCP") == LAVFI_CATEGORY_PALETTES["scp"]
    proc = Path("src/media/proc_engine.py").read_text()
    worker = Path("src/media/loop_worker.py").read_text()
    assert "resolve_lavfi_palette" in proc
    assert "resolve_lavfi_palette" in worker
    assert 'category_palettes = {' not in worker
