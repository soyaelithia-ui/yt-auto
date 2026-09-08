from pathlib import Path

from lib.subtitles import create_ass_subtitles, validate_subtitle_grammar_and_syntax, _strip_ass_tags


def _stamps(*words: str, t0: float = 0.0, dur: float = 0.35):
    out = []
    t = t0
    for w in words:
        out.append({"word": w, "start": t, "end": t + dur})
        t += dur
    return out


def _dialogue_plain(ass_text: str) -> str:
    parts = []
    for line in ass_text.splitlines():
        if line.startswith("Dialogue:"):
            parts.append(_strip_ass_tags(line.split(",", 9)[-1]))
    return " ".join(parts).replace(r"\N", " ")


def test_preposition_moves_to_next_cue_not_dropped(tmp_path: Path):
    # group_size=2 + max_chars bajo fuerza el corte 'observador a' | 'través'
    words = _stamps("observador", "a", "través", "de", "continentes", "enteros.")
    path = tmp_path / "cue.ass"
    create_ass_subtitles(
        words,
        path,
        template="shorts_creepypasta",
        video_res=(1080, 1920),
        max_chars=12,
        group_size=2,
    )
    validate_subtitle_grammar_and_syntax(path)  # no debe lanzar
    plain = _dialogue_plain(path.read_text(encoding="utf-8"))
    for token in ("observador", "a", "través", "continentes", "enteros"):
        assert token in plain, f"falta {token!r} en {plain!r}"


def test_all_spoken_words_survive_ass_wrap(tmp_path: Path):
    words = _stamps(
        "Si", "ves", "su", "cara,", "el", "observador", "a", "través",
        "de", "la", "grabación", "digital", "emite", "alaridos.",
    )
    spoken = [w["word"].rstrip(".,!?;:") for w in words]
    path = tmp_path / "full.ass"
    create_ass_subtitles(
        words,
        path,
        template="shorts_creepypasta",
        video_res=(1080, 1920),
        max_chars=18,
        group_size=3,
    )
    validate_subtitle_grammar_and_syntax(path)
    plain = _dialogue_plain(path.read_text(encoding="utf-8"))
    missing = [w for w in spoken if w and w not in plain]
    assert missing == [], f"drop silencioso: {missing} / {plain!r}"
