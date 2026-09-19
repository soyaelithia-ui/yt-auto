"""
Narrative synthesis templates for YouTube automation pipelines.
Provides channel-isolated narrative builders for Moku (Horror/SCP), Aelithia (Drama/AITA),
and Singularidad (Sci-Fi), free of vocalized structural headers, with rich first-person
immersion, dialogue, and zero mechanical repetition.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional, Sequence

from src.branding import resolve_channel_key
from src.core.scp_lore import lookup_scp
from src.templates.loader import load_template_json, render_paragraphs

# Load externalized structured templates
_moku_tpl = load_template_json("narratives_moku.json")
_MOKU_SITES: list[str] = _moku_tpl["sites"]
_MOKU_MTF: list[str] = _moku_tpl["mtf"]
_MOKU_PERSONNEL: list[str] = _moku_tpl["personnel"]
_MOKU_SUBJECTS: list[str] = _moku_tpl["subjects"]
_MOKU_TIMES: list[str] = _moku_tpl["times"]
_MOKU_SCP_PROTOCOLS: list[str] = _moku_tpl["scp_protocols"]
_MOKU_SCP_INCIDENTS: list[str] = _moku_tpl["scp_incidents"]
_MOKU_SCP_OUTROS: list[str] = _moku_tpl["scp_outros"]
_MOKU_HORROR_ARCHETYPES: list[dict[str, Any]] = _moku_tpl["horror_archetypes"]

_aelithia_tpl = load_template_json("narratives_aelithia.json")
_AELITHIA_NAMES: list[str] = _aelithia_tpl["names"]
_AELITHIA_ROLES: list[str] = _aelithia_tpl["roles"]
_AELITHIA_AMOUNTS: list[str] = _aelithia_tpl["amounts"]
_AELITHIA_TIMEFRAMES: list[str] = _aelithia_tpl["timeframes"]
_AELITHIA_ARCHETYPES: list[dict[str, Any]] = _aelithia_tpl["archetypes"]


def _build_single_moku_scp_candidate(
    clean_topic: str,
    digest: bytes,
    attempt: int,
    site: str,
    mtf: str,
    personnel: str,
    subject: str,
    time_str: str,
    scp_entry: Any,
    scp_match: Any,
) -> str:
    inc_raw = _MOKU_SCP_INCIDENTS[(digest[5] + attempt) % len(_MOKU_SCP_INCIDENTS)]
    incident = inc_raw.format(site=site, mtf=mtf, personnel=personnel, subject=subject, time=time_str)
    proto = _MOKU_SCP_PROTOCOLS[(digest[6] + attempt) % len(_MOKU_SCP_PROTOCOLS)]
    outro = _MOKU_SCP_OUTROS[(digest[7] + attempt) % len(_MOKU_SCP_OUTROS)]

    if scp_entry:
        scp_id = scp_entry.get("scp_id", "")
        obj_class = scp_entry.get("object_class", "Euclid")
        facts = list(scp_entry.get("key_facts", ()))
        sensory = scp_entry.get("sensory_cues", {})
        hooks = scp_entry.get("narrative_hooks", ())
        summary = scp_entry.get("containment_summary", "")
        canonical_name = scp_entry.get("canonical_name", {}).get("es", "")
        name_phrase = f", conocido como {canonical_name}," if canonical_name else ""
        hook = (
            f"{hooks[0]} Expediente clasificado de la Fundación para {scp_id}{name_phrase}, bajo clasificación {obj_class}."
            if hooks
            else f"Expediente clasificado de la Fundación para {scp_id}{name_phrase}, bajo clasificación {obj_class}: {clean_topic}."
        )
        facts_text = " ".join(facts[:3]) if facts else ""
        sensory_text = f" Los reportes describen {sensory.get('visual', '').lower()}." if sensory.get("visual") else ""
        containment_text = f" {summary}" if summary else ""
        core_lore = f"{facts_text}{sensory_text}{containment_text}"
        return f"{hook}\n\n{core_lore} {proto}\n\n{incident}\n\n{outro}"

    scp_id = f"SCP-{scp_match.group(1)}" if scp_match else "SCP-Anomalía"
    cl_m = re.search(r"(?i)\b(keter|euclid|safe|apollyon|thaumiel)\b", clean_topic)
    obj_class = cl_m.group(1).capitalize() if cl_m else "Euclid"
    hook = f"Expediente clasificado de la Fundación para {scp_id}, catalogado bajo estricta clasificación de contención {obj_class}."
    core_lore = (
        f"La anomalía designada como {scp_id} constituye una de las prioridades de vigilancia más rigurosas "
        f"de la Fundación SCP en el {site}. Las propiedades anómalas registradas durante las inspecciones perimétricas "
        "desafían las leyes conocidas de la física y la conservación de la materia, obligando a mantener barreras blindadas herméticas."
    )
    return f"{hook}\n\n{core_lore} {proto}\n\n{incident}\n\n{outro}"


def _build_single_moku_horror_candidate(
    clean_topic: str,
    digest: bytes,
    attempt: int,
    time_str: str,
) -> str:
    arch_idx = (digest[5] + attempt) % len(_MOKU_HORROR_ARCHETYPES)
    arch = _MOKU_HORROR_ARCHETYPES[arch_idx]
    subs = {"topic": clean_topic, "time": time_str}
    hook = arch["hooks"][(digest[6] + attempt) % len(arch["hooks"])].format(**subs)
    ctx = arch["contexts"][(digest[7] + attempt) % len(arch["contexts"])].format(**subs)
    esc = arch["escalations"][(digest[8] + attempt) % len(arch["escalations"])].format(**subs)
    clm = arch["climaxes"][(digest[9] + attempt) % len(arch["climaxes"])].format(**subs)
    res = arch["resolutions"][(digest[10] + attempt) % len(arch["resolutions"])].format(**subs)
    outro = arch["outros"][(digest[11] + attempt) % len(arch["outros"])].format(**subs)
    return f"{hook}\n\n{ctx} {esc} {clm} {res}\n\n{outro}"


def build_moku_short_narrative(
    topic: str,
    channel: str = "moku",
    seed_offset: int = 0,
    recent_texts: Sequence[str] = (),
    **kwargs: Any,
) -> str:
    """
    Build a high-retention Short narrative for Moku (Horror/SCP).
    Calibrated strictly to 230-280 words for optimal 75-110s pacing at 160 WPM.
    """
    clean_topic = re.sub(r"[""'']", "", topic).strip()

    if not recent_texts:
        try:
            from src.config import DEFAULT_DB_PATH
            from src.core.repository import QueueRepository
            recent_texts = QueueRepository(DEFAULT_DB_PATH).recent_published_texts("moku")
        except Exception:
            recent_texts = ()

    scp_entry = lookup_scp(topic)
    scp_match = re.search(r"(?i)\bscp[-_\s]*(\d+)\b", clean_topic)
    is_scp = bool(scp_entry or scp_match or "fundación" in clean_topic.lower() or "scp" in clean_topic.lower())

    best_narrative = ""
    min_sim = 1.0

    for attempt in range(12):
        comb_seed = f"{clean_topic}:{seed_offset + attempt}"
        digest = hashlib.sha256(comb_seed.encode("utf-8")).digest()

        site = _MOKU_SITES[(digest[0] + attempt) % len(_MOKU_SITES)]
        mtf = _MOKU_MTF[(digest[1] + attempt) % len(_MOKU_MTF)]
        personnel = _MOKU_PERSONNEL[(digest[2] + attempt) % len(_MOKU_PERSONNEL)]
        subject = _MOKU_SUBJECTS[(digest[3] + attempt) % len(_MOKU_SUBJECTS)]
        time_str = _MOKU_TIMES[(digest[4] + attempt) % len(_MOKU_TIMES)]

        if is_scp:
            candidate = _build_single_moku_scp_candidate(
                clean_topic=clean_topic,
                digest=digest,
                attempt=attempt,
                site=site,
                mtf=mtf,
                personnel=personnel,
                subject=subject,
                time_str=time_str,
                scp_entry=scp_entry,
                scp_match=scp_match,
            )
        else:
            candidate = _build_single_moku_horror_candidate(
                clean_topic=clean_topic,
                digest=digest,
                attempt=attempt,
                time_str=time_str,
            )

        if not recent_texts:
            return candidate

        from src.core.quality import text_similarity

        max_sim_for_cand = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim_for_cand < 0.70:
            return candidate
        if max_sim_for_cand < min_sim:
            min_sim = max_sim_for_cand
            best_narrative = candidate

    return best_narrative or candidate


def build_aelithia_short_narrative(
    topic: str,
    channel: str = "aelithia",
    seed_offset: int = 0,
    recent_texts: Sequence[str] = (),
    **kwargs: Any,
) -> str:
    """
    Build a high-retention Short narrative for Aelithia (Drama / AITA / Moral Dilemmas).
    Calibrated strictly to 200-280 words for optimal 70-105s pacing at 160 WPM.
    """
    clean_topic = re.sub(r"[""'']", "", topic).strip()

    best_narrative = ""
    min_sim = 1.0

    for attempt in range(12):
        comb_seed = f"{clean_topic}:{seed_offset + attempt}"
        digest = hashlib.sha256(comb_seed.encode("utf-8")).digest()

        arch_idx = (digest[0] + attempt) % len(_AELITHIA_ARCHETYPES)
        arch = _AELITHIA_ARCHETYPES[arch_idx]

        name = _AELITHIA_NAMES[(digest[1] + attempt) % len(_AELITHIA_NAMES)]
        role = _AELITHIA_ROLES[(digest[2] + attempt) % len(_AELITHIA_ROLES)]
        amount = _AELITHIA_AMOUNTS[(digest[3] + attempt) % len(_AELITHIA_AMOUNTS)]
        timeframe = _AELITHIA_TIMEFRAMES[(digest[4] + attempt) % len(_AELITHIA_TIMEFRAMES)]

        hook_raw = arch["hooks"][(digest[5] + attempt) % len(arch["hooks"])]
        ctx_raw = arch["contexts"][(digest[6] + attempt) % len(arch["contexts"])]
        esc_raw = arch["escalations"][(digest[7] + attempt) % len(arch["escalations"])]
        clm_raw = arch["climaxes"][(digest[8] + attempt) % len(arch["climaxes"])]
        res_raw = arch["resolutions"][(digest[9] + attempt) % len(arch["resolutions"])]
        out_raw = arch["outros"][(digest[10] + attempt) % len(arch["outros"])]

        subs = {
            "topic": clean_topic,
            "name": name,
            "role": role,
            "amount": amount,
            "timeframe": timeframe,
        }

        hook = hook_raw.format(**subs)
        ctx = ctx_raw.format(**subs)
        esc = esc_raw.format(**subs)
        clm = clm_raw.format(**subs)
        res = res_raw.format(**subs)
        outro = out_raw.format(**subs)

        candidate = f"{hook}\n\n{ctx}{esc}{clm}{res}\n\n{outro}"

        if not recent_texts:
            return candidate

        from src.core.quality import text_similarity

        max_sim_for_cand = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim_for_cand < 0.70:
            return candidate
        if max_sim_for_cand < min_sim:
            min_sim = max_sim_for_cand
            best_narrative = candidate

    return best_narrative or candidate


def build_scp3000_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 12.0,
    **kwargs: Any,
) -> str:
    """Builds an in-depth documentary narrative for SCP-3000 (Anantashesha)."""
    tpl = load_template_json("narratives_moku.json")
    return render_paragraphs(tpl["scp3000_paragraphs"], {"topic": topic})


def build_moku_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Build a rich, non-repeating first-person horror narrative (>=2800 words)."""
    norm_topic = topic.lower()
    if "3000" in norm_topic or "anantashesha" in norm_topic:
        return build_scp3000_longform_narrative(
            topic,
            channel=channel,
            target_duration_minutes=target_duration_minutes,
            **kwargs,
        )
    from src.templates.longform_stories import get_moku_longform_story
    return get_moku_longform_story(topic, **kwargs)


def _build_moku_radio_base(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Mountain Radio Station Operator longform narrative base."""
    tpl = load_template_json("narratives_moku.json")
    return render_paragraphs(tpl["radio_paragraphs"], {"topic": topic})


def build_aelithia_longform_narrative(
    topic: str,
    channel: str = "aelithia",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Build a multi-case longform drama narrative for Aelithia."""
    from src.templates.longform_stories import get_aelithia_longform_story
    return get_aelithia_longform_story(topic, **kwargs)


def _build_aelithia_family_debt_base(
    topic: str,
    channel: str = "aelithia",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Birthday Loan & Secret Will multi-case longform narrative base."""
    tpl = load_template_json("narratives_aelithia.json")
    return render_paragraphs(tpl["family_debt_paragraphs"], {"topic": topic})


def build_scifi_short_narrative(
    topic: str,
    channel: str = "scifi",
    **kwargs: Any,
) -> str:
    """Build a high-retention Short narrative for SciFi (Hard SciFi / Singularidad)."""
    tpl = load_template_json("narratives_scifi.json")
    hook = tpl["short_hook"].replace("{topic}", topic)
    body = tpl["short_body"].replace("{topic}", topic)
    outro = tpl["short_outro"].replace("{topic}", topic)
    return f"{hook}\n\n{body}\n\n{outro}"


def build_scifi_longform_narrative(
    topic: str,
    channel: str = "scifi",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Build an immersive 10-15 minute deep-dive SciFi documentary script."""
    tpl = load_template_json("narratives_scifi.json")
    return render_paragraphs(tpl["longform_paragraphs"], {"topic": topic})


def build_channel_narrative(
    topic: str,
    channel: str = "moku",
    video_mode: str = "longform",
    duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Router dispatching to the appropriate channel and format narrative generator."""
    actual_channel = kwargs.get("ch") or channel
    actual_duration = kwargs.get("target_mins") or duration_minutes
    canon_ch = resolve_channel_key(actual_channel)
    if canon_ch == "aelithia":
        if video_mode == "short":
            return build_aelithia_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_aelithia_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)
    elif canon_ch == "scifi":
        if video_mode == "short":
            return build_scifi_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_scifi_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)
    else:
        if video_mode == "short":
            return build_moku_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_moku_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)


def build_narrative(
    topic: str,
    *,
    channel: str = "moku",
    length: str = "short",
    target_minutes: float | None = None,
) -> str:
    """Single narrative router (lane-aware)."""
    return build_channel_narrative(
        topic,
        channel=channel,
        video_mode=length,
        duration_minutes=target_minutes if target_minutes is not None else 10.5,
    )


def build_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Compatibility alias for legacy orchestrators and test harnesses."""
    return build_channel_narrative(topic, channel=channel, video_mode="longform", duration_minutes=target_duration_minutes, **kwargs)


def build_short_narrative(
    topic: str,
    channel: str = "moku",
    **kwargs: Any,
) -> str:
    """Compatibility alias for legacy orchestrators and test harnesses."""
    return build_channel_narrative(topic, channel=channel, video_mode="short", **kwargs)


def get_fallback_story(
    channel: str = "moku",
    *,
    topic: str | None = None,
    is_short: bool = True,
    seed: int | None = None,
    **kwargs: Any,
) -> str:
    """Returns an authentic channel-specific fallback story."""
    ch = (channel or "moku").strip().lower()
    canon_ch = resolve_channel_key(ch)
    if canon_ch == "aelithia" or ch in ("aelithia", "drama", "aita"):
        default_topic = topic or "la herencia familiar y el límite del perdón"
        if is_short:
            return build_aelithia_short_narrative(default_topic, channel="aelithia", **kwargs)
        return build_aelithia_longform_narrative(default_topic, channel="aelithia", target_duration_minutes=10.5, **kwargs)
    elif canon_ch == "scifi" or ch in ("scifi", "singularidad", "sci_fi"):
        default_topic = topic or "el horizonte de sucesos y la paradoja del tiempo"
        if is_short:
            return build_scifi_short_narrative(default_topic, channel="scifi", **kwargs)
        return build_scifi_longform_narrative(default_topic, channel="scifi", target_duration_minutes=10.5, **kwargs)

    default_topic = topic or "SCP-087 y la escalera del silencio"
    if is_short:
        return build_moku_short_narrative(default_topic, channel="moku", **kwargs)
    return build_moku_longform_narrative(default_topic, channel="moku", target_duration_minutes=10.5, **kwargs)
