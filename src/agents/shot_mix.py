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


def video_filter_for_role(role: str, width: int, height: int, fps: int) -> str:
    """Settled = scale/crop only. Designed = live grade, not a catalog file."""
    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p"
    )
    if role == DESIGNED:
        return (
            f"{base},eq=saturation=0.35:contrast=1.2,"
            "colorchannelmixer=rr=0.2:gg=0.5:bb=0.9"
        )
    return base
