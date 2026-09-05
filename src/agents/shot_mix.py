"""Live scene-director mix. No catalog bake.

Settled shots share one already-decided background (it may move; it is not
negotiated). Designed shots are the minority the director varies in the moment.
"""

from __future__ import annotations

SETTLED = "settled"
DESIGNED = "designed"


def designed_count(n: int) -> int:
    if n <= 0:
        return 0
    return min(n // 2, (n * 2) // 5)


def assign_roles(n: int) -> list[str]:
    designed = designed_count(n)
    return [SETTLED] * (n - designed) + [DESIGNED] * designed
