"""
src/curators/tension.py - Progressive tension curve grading, audio pacing, and mood derivation.

Provides algorithms for interpolating progressive tension curves across acts,
mapping tension to Draft-07 audio pacing cues, and deriving contextual environmental moods.
"""
from __future__ import annotations

from typing import List


def interpolate_tension(profile: List[int], offset: int, total: int) -> int:
    """Interpolates smooth progressive tension levels (1..5)."""
    if total <= 1:
        return max(1, min(5, max(profile) if 5 in profile else profile[len(profile) // 2]))
    if len(profile) == 1:
        return max(1, min(5, profile[0]))
    step = (len(profile) - 1) * (offset / (total - 1))
    idx = int(round(step))
    idx = max(0, min(len(profile) - 1, idx))
    return max(1, min(5, profile[idx]))


def resolve_audio_pacing_cue(
    lane_key: str,
    act_num: int,
    tension: int,
    offset: int,
    total_in_act: int,
) -> str:
    """Resolves valid Draft-07 audio pacing cue calibrated to lane dynamics."""
    if act_num == 4:
        # Epilogue / aftermath: whispered_grave for low tension / horror, or steady_dramatic
        if tension <= 2 or offset == total_in_act - 1:
            return "whispered_grave" if ("horror" in lane_key or "scp" in lane_key) else "calm_slow"
        return "steady_dramatic"

    if tension >= 5:
        return "intense_urgent"
    if tension == 4:
        return "intense_urgent" if act_num == 3 else "tense_accelerando"
    if tension == 3:
        return "tense_accelerando"
    if tension == 2:
        return "steady_dramatic"
    return "calm_slow"


def derive_semantic_environmental_mood(text: str, fallback_mood: str, tension: int) -> str:
    """Derives a rich, contextual environmental mood from narration text keywords."""
    t_low = text.lower()
    if any(k in t_low for k in ("faro", "costa", "mar ", "marino", "oceano", "océano", "fosa", "abismo", "olas")):
        return "Faro costero aislado azotado por tormenta y anomalía en fosa oceánica"
    if any(k in t_low for k in ("paramo", "páramo", "estepa", "ceniza", "cenizas", "monolito", "monolitos")):
        return "Páramo desolado de cenizas grises y monolitos ciclópeos en el horizonte"
    if any(k in t_low for k in ("bunker", "búnker", "pasillo", "acero", "alarma", "cimiento", "laboratorio", "camara", "cámara")):
        return "Búnker táctico subterráneo con baliza de alarma estroboscópica y vibraciones"
    if any(k in t_low for k in ("criatura", "monstruo", "titan", "coloso", "demonio", "ojos", "fauce", "garra")):
        return "Manifestación colosal de entidad anómala emergiendo de niebla densa"
    if any(k in t_low for k in ("singularidad", "agujero negro", "vortice", "vórtice", "espacio", "cosmico", "cósmico", "gravedad")):
        return "Singularidad cósmica con distorsión gravitacional y disco de acreción"
    if any(k in t_low for k in ("mente", "cerebro", "conciencia", "sinapsis", "recuerdo", "memoria")):
        return "Matriz neuronal de conciencia bioluminiscente con impulsos sinápticos"
    if any(k in t_low for k in ("radar", "terminal", "clasificado", "pantalla", "expediente", "registro")):
        return "Consola CRT militar de vigilancia táctica con radar y telemetría"
    return fallback_mood


def derive_transition_reason(act_number: int, dramatic_role: str, tension: int, scene_offset: int) -> str:
    """Derives semantic transition motivation for scene changes."""
    reasons = {
        "exposition_inception": "Establecimiento del escenario inicial y presentación de anomalía contextual",
        "rising_action_dread": "Escalada de tensión dramática y desplazamiento hacia zona de peligro inminente",
        "climax_confrontation": "Punto de máxima confrontación y ruptura crítica del entorno",
        "aftermath_revelation": "Desenlace de la crisis y consecuencias permanentes en el entorno",
    }
    base_reason = reasons.get(dramatic_role, "Evolución narrativa y progresión de la atmósfera escénica")
    if tension >= 4:
        return f"{base_reason} (Ruptura crítica bajo tensión nivel {tension})"
    return f"{base_reason} (Transición de plano {scene_offset + 1})"
