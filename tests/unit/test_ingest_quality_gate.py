"""Ingest path must apply hybrid Reddit quality scoring before enqueue."""
from __future__ import annotations

from src.core.scoring import (
    estimate_spoken_seconds,
    first_spoken_hook,
    opening_hook_within_budget,
)


def test_spoken_hook_budget_helpers():
    hook = first_spoken_hook(
        "Cuatro píxeles. Bastó para matar un batallón. Luego vino el resto.",
        max_seconds=3.0,
    )
    assert estimate_spoken_seconds(hook) <= 3.05
    ok, secs, _ = opening_hook_within_budget(
        "x", "Cuatro píxeles. Bastó para matar un batallón."
    )
    assert ok is True
    assert secs <= 3.05


def test_long_opening_flagged():
    long_open = (
        "Si sientes un cosquilleo inexplicable bajo tu piel, aléjate de esta celda "
        "de inmediato porque las criaturas ya están escuchando tu respiración."
    )
    ok, secs, trimmed = opening_hook_within_budget("SCP", long_open)
    assert secs > 3.0
    assert ok is False
    assert estimate_spoken_seconds(trimmed) <= 3.05
