"""Live scene-director mix. No catalog bake.

Settled shots share one already-decided background (it may move; it is not
negotiated). Designed shots are the minority the director varies in the moment,
spread through the timeline so the cut feels intentional rather than clustered.
"""

from __future__ import annotations

SETTLED = "settled"
DESIGNED = "designed"


def designed_count(n: int) -> int:
    if n <= 0:
        return 0
    return min(n // 2, (n * 2) // 5)


def assign_roles(n: int) -> list[str]:
    """Return shot roles with designed beats spread across the timeline."""
    designed = designed_count(n)
    if n <= 0:
        return []
    roles = [SETTLED] * n
    if designed <= 0:
        return roles

    # Place designed shots at even interior fractions (not piled at the end).
    used: set[int] = set()
    for i in range(designed):
        idx = int(round((i + 1) * (n - 1) / (designed + 1)))
        idx = max(0, min(n - 1, idx))
        if idx in used:
            for candidate in list(range(idx + 1, n)) + list(range(idx - 1, -1, -1)):
                if candidate not in used:
                    idx = candidate
                    break
        used.add(idx)
        roles[idx] = DESIGNED
    return roles


def video_filter_for_role(role: str, width: int, height: int, fps: int) -> str:
    """Settled = clean geometry + light polish. Designed = cinematic accent grade.

    Grades stay subtle so stream/re-encode looks coherent and beautiful rather
    than crushed/neon. Designed keeps a soft cool lift (still uses
    colorchannelmixer) without the old muddy desat.
    """
    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p"
    )
    # Light polish on every shot: gentle contrast, preserve color for YouTube.
    settled = f"{base},eq=contrast=1.06:saturation=0.92:brightness=0.01"
    if role == DESIGNED:
        return (
            f"{base},eq=contrast=1.14:saturation=0.78:brightness=-0.015:gamma=0.96,"
            "colorchannelmixer=rr=0.88:rg=0.02:rb=0.04:gr=0.02:gg=0.90:gb=0.06:"
            "br=0.03:bg=0.04:bb=1.05"
        )
    return settled
