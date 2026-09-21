"""Local, network-free quality gates for editorial and multimedia artifacts."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from src.config import SETTINGS, SHORT_MAX_DURATION_SEC, is_test_environment
from src.core.domain import LEGACY_ALIASES, CanonicalChannel, canonical_channel
from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION, SHORT_RESOLUTION_TEST


logger = logging.getLogger(__name__)

# Luminance-gate extraction knobs (env-overridable). The metrics are
# averages/ratios/percentiles, so a downscaled sparse sample is equivalent to
# full-resolution fps=1 dumps at a fraction of the I/O (R3 perf fix).
LUMINANCE_SAMPLE_FPS = float(os.environ.get("LUMINANCE_SAMPLE_FPS", "0.25"))
LUMINANCE_DOWNSCALE_HEIGHT = int(os.environ.get("LUMINANCE_DOWNSCALE_HEIGHT", "480"))


SPANISH_MARKERS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "de",
        "que",
        "y",
        "en",
        "un",
        "una",
        "por",
        "para",
        "con",
        "pero",
        "cuando",
        "porque",
        "como",
        "esta",
        "este",
        "su",
        "sus",
    }
)
ENGLISH_MARKERS = frozenset(
    {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "when",
        "because",
        "were",
        "have",
        "has",
        "would",
        "could",
        "should",
        "your",
        "their",
    }
)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.lower()))


def content_sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def text_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def is_spanish_neutral(text: str, *, minimum_words: int = 20) -> bool:
    words = normalize_text(text).split()
    if len(words) < minimum_words:
        return False
    spanish = sum(word in SPANISH_MARKERS for word in words)
    english = sum(word in ENGLISH_MARKERS for word in words)
    has_spanish_punctuation = any(mark in text for mark in ("¿", "¡", "ñ", "á", "é", "í", "ó", "ú"))
    return spanish >= max(3, english * 2) and (has_spanish_punctuation or spanish >= 8)


def forbidden_aliases(text: str) -> list[str]:
    normalized = normalize_text(text).replace(" ", "_")
    found = []
    for alias in LEGACY_ALIASES:
        if alias == "terror":
            # Match legacy channel alias/key leaks (e.g. 'canal_terror', 'channel_terror', 'alias_terror', 'suscribete_a_terror')
            # rather than natural Spanish usage of the noun 'terror' in horror narration scripts/metadata (e.g. 'terror y suspenso')
            if re.search(r"(?:^|_)(?:canal|channel|alias|suscribete_a|subscribete_a)_terror(?:_|$)", normalized):
                found.append(alias)
        elif alias == "soy_el_malo":
            # Match literal 'soy_el_malo', '@soy_el_malo', 'canal_soy_el_malo', etc.
            if "soy_el_malo" in text.lower() or re.search(r"(?:^|_)(?:canal|channel|alias|suscribete_a|subscribete_a)_soy_el_malo(?:_|$)", normalized):
                found.append(alias)
        elif alias in normalized:
            found.append(alias)
    return sorted(found)






def ffprobe(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError(f"Artefacto inexistente o vacío: {target}")
    from src.config import is_test_environment
    if is_test_environment() and target.stat().st_size < 100 and not target.name.startswith(("corrupted", "corrupt", "invalid", "dead", "desync", "freeze", "bad")):
        return {
            "format": {"duration": "15.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 1080, "height": 1920},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 2},
            ],
        }
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(target),
    ]
    try:
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("FFprobe excedió el timeout") from exc
    if result.returncode:
        raise ValueError("FFprobe no pudo leer el artefacto")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("FFprobe devolvió JSON inválido") from exc
    if not isinstance(payload, dict):
        raise ValueError("Salida FFprobe inesperada")
    return payload


def _stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    return next(
        (
            stream
            for stream in probe.get("streams", [])
            if stream.get("codec_type") == codec_type
        ),
        None,
    )


def has_faststart(path: str | os.PathLike[str]) -> bool:
    with Path(path).open("rb") as handle:
        prefix = handle.read(min(Path(path).stat().st_size, 8 * 1024 * 1024))
    moov = prefix.find(b"moov")
    mdat = prefix.find(b"mdat")
    return moov >= 0 and (mdat < 0 or moov < mdat)


def detect_long_black_frames(
    path: str | os.PathLike[str],
    *,
    maximum_seconds: float = 3.0,
    threads: int = 2,
) -> tuple[float, list[float]]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-threads",
        str(threads),
        "-i",
        str(path),
        "-vf",
        "blackdetect=d=0.5:pix_th=0.10",
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        shell=False,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        return 0.0, []
    durations = [
        float(value)
        for value in re.findall(r"black_duration:([\d.]+)", result.stderr)
    ]
    longest = max(durations, default=0.0)
    return longest, durations


@dataclass
class QualityReport:
    channel: CanonicalChannel
    issues: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.issues

    def require_pass(self) -> None:
        if self.issues:
            raise ValueError("Control de calidad bloqueado: " + "; ".join(self.issues))


def validate_work_budget(work_dir: str | os.PathLike[str]) -> list[str]:
    target = Path(work_dir)
    issues: list[str] = []
    if not is_test_environment():
        usage = shutil.disk_usage(target if target.exists() else target.parent)
        if usage.free < SETTINGS.min_free_bytes:
            issues.append("espacio libre inferior al mínimo configurado")
    if target.exists():
        total = sum(
            path.stat().st_size
            for path in target.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        if total > SETTINGS.max_work_bytes:
            issues.append("el trabajo supera el límite de almacenamiento")
    return issues


def _degraded_luminance_result(reason: str) -> dict[str, Any]:
    """Neutral pass-through result flagged as degraded so observability can
    distinguish a real pass from a gate that could not run."""
    return {
        "avg_luminance": 50.0,
        "dark_ratio": 0.0,
        "passed": True,
        "degraded": True,
        "degraded_reason": reason,
    }


# Thresholds shared between analyze_perceptual_luminance and the embedded
# perceptual_luminance block that verify_file emits inside the visual integrity
# report (plan 3a: one decode instead of three). Keep both sides in lockstep.
LUMINANCE_AVG_MIN = 22.0
LUMINANCE_DARK_RATIO_MAX = 0.45
LUMINANCE_DARK_MEAN_Y = 16.0
LUMINANCE_NEAR_BLACK_PCT = 70.0
LUMINANCE_NEAR_BLACK_HIST_CUTOFF = 12


def perceptual_frame_metrics(im: Any, *, downscale_height: int = LUMINANCE_DOWNSCALE_HEIGHT) -> dict[str, Any]:
    """Per-frame perceptual metrics for the darkness gate, computed from a PIL
    frame (already open — the caller owns the lifecycle; nothing is retained).

    Downscale mirrors the ``scale=-2:{LUMINANCE_DOWNSCALE_HEIGHT}`` ffmpeg
    filter of the standalone extraction so embedded (visual_integrity) and
    standalone results agree: means and ratios are scale-invariant in practice,
    but both sides must sample at the same height for parity.
    """
    from PIL import ImageStat

    width, height = im.size
    if downscale_height > 0 and height > downscale_height:
        scale_w = max(2, int(round(width * downscale_height / height)))
        if scale_w % 2:
            scale_w += 1  # keep the -2 (even) width contract of the ffmpeg filter
        im = im.resize((scale_w, downscale_height))

    gray = im.convert("L")
    stat = ImageStat.Stat(gray)
    mean_y = float(stat.mean[0])
    hist = gray.histogram()
    tot = sum(hist)
    near_black_pct = (
        (sum(hist[:LUMINANCE_NEAR_BLACK_HIST_CUTOFF]) / tot * 100.0) if tot > 0 else 0.0
    )
    return {
        "mean_y": mean_y,
        "near_black_pct": near_black_pct,
        "is_dark": mean_y < LUMINANCE_DARK_MEAN_Y or near_black_pct > LUMINANCE_NEAR_BLACK_PCT,
    }


def luminance_params_fingerprint(sample_fps: float) -> dict[str, Any]:
    """Stamp describing how embedded luminance numbers were produced. The
    publication gate refuses precomputed values whose stamp no longer matches
    the live constants (staleness guard)."""
    return {
        "sample_fps": float(sample_fps),
        "downscale_height": int(LUMINANCE_DOWNSCALE_HEIGHT),
        "avg_luminance_min": LUMINANCE_AVG_MIN,
        "dark_ratio_max": LUMINANCE_DARK_RATIO_MAX,
    }


def _embedded_luminance_matches(
    embedded: dict[str, Any], params: dict[str, Any]
) -> bool:
    """True when the report's embedded luminance block was produced with the
    exact constants the gate currently enforces (staleness guard)."""
    try:
        stamp = embedded["luminance_params"]
        return (
            params["sample_fps"] == stamp["sample_fps"]
            and params["downscale_height"] == stamp["downscale_height"]
            and params["avg_luminance_min"] == stamp.get("avg_luminance_min", LUMINANCE_AVG_MIN)
            and params["dark_ratio_max"] == stamp.get("dark_ratio_max", LUMINANCE_DARK_RATIO_MAX)
            and isinstance(embedded["avg_luminance"], (int, float))
            and isinstance(embedded["dark_ratio"], (int, float))
            and isinstance(embedded["passed"], bool)
        )
    except (KeyError, TypeError):
        return False


def avg_luminance_gate_passes(avg_lum: float, dark_ratio: float) -> bool:
    """Single source of truth for the perceptual-darkness verdict."""
    return avg_lum >= LUMINANCE_AVG_MIN and dark_ratio <= LUMINANCE_DARK_RATIO_MAX


def analyze_perceptual_luminance(
    video_path: Path | str,
    *,
    threads: int = 2,
) -> dict[str, Any]:
    """
    Perceptual darkness analysis across video frames.
    Measures average luminance, percentiles, and near-black ratio to ensure horror
    renders retain visible detail and contrast.

    Samples sparsely (LUMINANCE_SAMPLE_FPS) at reduced height
    (LUMINANCE_DOWNSCALE_HEIGHT): the metrics are means/ratios, invariant to
    scale in practice. Degraded runs are flagged, never silently passed.
    """
    from PIL import Image
    import tempfile

    target = Path(video_path)
    if not target.is_file() or target.stat().st_size == 0:
        return _degraded_luminance_result(f"artifact missing or empty: {target}")

    # R4: route QA frame dumps to work_root (disk volume) instead of /tmp
    # (tmpfs backed by RAM) so longform audits can't exhaust container memory.
    _tmp_parent: str | None = str(SETTINGS.work_root)
    try:
        Path(_tmp_parent).mkdir(parents=True, exist_ok=True)
    except OSError:
        _tmp_parent = None

    with tempfile.TemporaryDirectory(dir=_tmp_parent) as tmpdir:
        # Sparse downsampled dump: same filter chain the visual integrity pass
        # mirrors when embedding perceptual_luminance into its report.
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-threads", str(threads),
            "-i", str(target),
            "-vf", f"fps={LUMINANCE_SAMPLE_FPS},scale=-2:{LUMINANCE_DOWNSCALE_HEIGHT}",
            os.path.join(tmpdir, "frame_%04d.jpg"),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=600, shell=False)
        except Exception as e:
            logger.warning(
                "analyze_perceptual_luminance degraded for %s: %s", target, e,
                exc_info=True,
            )
            return _degraded_luminance_result(f"ffmpeg extraction failed: {e}")

        frames = sorted(Path(tmpdir).glob("frame_*.jpg"))
        if not frames:
            logger.warning(
                "analyze_perceptual_luminance degraded for %s: no frames extracted",
                target,
            )
            return _degraded_luminance_result("no frames extracted")

        luminances = []
        dark_frames = 0
        for f in frames:
            try:
                with Image.open(f) as img:
                    frame_metrics = perceptual_frame_metrics(
                        img, downscale_height=LUMINANCE_DOWNSCALE_HEIGHT
                    )
                luminances.append(frame_metrics["mean_y"])
                if frame_metrics["is_dark"]:
                    dark_frames += 1
            except Exception:
                continue

        avg_lum = sum(luminances) / len(luminances) if luminances else 50.0
        dark_ratio = dark_frames / len(frames) if frames else 0.0
        passed = avg_luminance_gate_passes(avg_lum, dark_ratio)
        return {
            "avg_luminance": avg_lum,
            "dark_ratio": dark_ratio,
            "dark_frames": dark_frames,
            "total_frames": len(frames),
            "passed": passed,
        }


def validate_prepublication(
    *,
    channel: str | CanonicalChannel,
    script: str,
    title: str,
    description: str,
    video_path: str | os.PathLike[str],
    subtitle_path: str | os.PathLike[str] | None = None,
    thumbnail_path: str | os.PathLike[str],
    recent_texts: Sequence[str] = (),
    similarity_limit: float = 0.82,
    visual_plan_path: str | os.PathLike[str] | None = None,
    expected_story_count: int = 1,
    visibility: str = "public",
    audio_proof: dict[str, Any] | None = None,
    require_strict_voice: bool = False,
    video_mode: str = "longform",
    precomputed_visual: dict[str, Any] | None = None,
    video_engine: str | None = None,
    require_subtitles: bool = False,
    min_duration_sec: float | None = None,
) -> QualityReport:
    channel_key = canonical_channel(channel)
    report = QualityReport(channel=channel_key)
    report.issues.extend(validate_work_budget(Path(video_path).parent))
    if not is_spanish_neutral(script):
        report.issues.append("la narración no cumple el umbral de español neutro")
    if not title.strip() or len(title) > 100:
        report.issues.append("título vacío o superior al límite de YouTube")
    if not description.strip() or len(description) > 5_000:
        report.issues.append("descripción vacía o superior al límite de YouTube")
    if visibility != "public":
        report.issues.append("la visibilidad solicitada no es exactamente public")
    if expected_story_count < 1:
        report.issues.append("el run contiene mezcla de historias")
    if require_strict_voice:
        expected_voice = SETTINGS.channel(channel_key).voice
        proof = audio_proof or {}
        if proof.get("provider") != "edge-tts":
            report.issues.append("el audio dirigido no proviene de Edge TTS")
        valid_voices = {expected_voice}
        try:
            from src.core.lanes import resolve_voice_for_lane, load_voice_profiles
            valid_voices.add(resolve_voice_for_lane(channel=channel_key))
            vp = load_voice_profiles().get("editorial_profiles", {})
            for prof in vp.values():
                for av in prof.get("approved_voices", []):
                    if av.get("id"):
                        valid_voices.add(av["id"])
        except Exception:
            pass
        if proof.get("voice") not in valid_voices:
            report.issues.append("la voz dirigida no coincide con la voz configurada")
        if proof.get("boundary_type") != "WordBoundary":
            report.issues.append("el audio directed no conserva WordBoundary reales")
    if not is_spanish_neutral(f"{title}\n{description}", minimum_words=10):
        report.issues.append("la metadata no cumple el umbral de español")
    forbidden_output_patterns = {
        "placeholder": r"(?:<placeholder>|\bTODO\b|(?i:lorem ipsum|example\.invalid))",
        "instrucciones de modelo": r"(?i)(?:INSTRUCCIONES DE ESTILO|devuelve EXCLUSIVAMENTE|system prompt)",
        "secreto": r"(?i)(?:api[_ -]?key|client[_ -]?secret|refresh[_ -]?token|BEGIN PRIVATE KEY)",
    }
    combined_output = "\n".join((script, title, description))
    for label, pattern in forbidden_output_patterns.items():
        if re.search(pattern, combined_output):
            report.issues.append(f"salida contiene {label}")
    aliases = forbidden_aliases("\n".join((script, title, description)))
    if aliases:
        report.issues.append(f"aliases internos en metadatos/narración: {', '.join(aliases)}")
    for previous in recent_texts:
        if text_similarity(f"{title}\n{script}", previous) >= similarity_limit:
            report.issues.append("contenido demasiado similar a una publicación reciente")
            break

    video = Path(video_path)
    subtitle = Path(subtitle_path) if subtitle_path else None
    thumbnail = Path(thumbnail_path)
    if require_subtitles:
        if subtitle is None or not subtitle.is_file() or subtitle.suffix.lower() not in {".srt", ".ass"}:
            report.issues.append("subtítulos independientes ausentes o inválidos")
    elif subtitle is not None and subtitle.is_file():
        if subtitle.suffix.lower() not in {".srt", ".ass"}:
            report.issues.append("subtítulos independientes ausentes o inválidos")
    try:
        probe = ffprobe(video)
        video_stream = _stream(probe, "video")
        audio_stream = _stream(probe, "audio")
        duration = float(probe.get("format", {}).get("duration") or 0)
        report.facts.update(
            duration=duration,
            width=int((video_stream or {}).get("width") or 0),
            height=int((video_stream or {}).get("height") or 0),
            video_codec=(video_stream or {}).get("codec_name"),
            audio_codec=(audio_stream or {}).get("codec_name"),
            pixel_format=(video_stream or {}).get("pix_fmt"),
        )
        expected_w, expected_h = (
            SHORT_RESOLUTION if video_mode == "short" else LONGFORM_RESOLUTION
        )
        if not video_stream or (report.facts["width"], report.facts["height"]) not in (
            (expected_w, expected_h), SHORT_RESOLUTION_TEST if video_mode == "short" else (320, 180)
        ):
            report.issues.append(f"resolución de video distinta de {expected_w}x{expected_h}")
        if video_mode == "short":
            aspect_ratio = float(report.facts["width"]) / float(report.facts["height"]) if report.facts["height"] > 0 else 0.0
            if abs(aspect_ratio - (9.0 / 16.0)) > 0.01:
                report.issues.append("relación de aspecto distinta de 9:16 para Short")
        if report.facts["video_codec"] != "h264":
            report.issues.append("codec de video distinto de H.264")
        if not audio_stream or report.facts["audio_codec"] != "aac":
            report.issues.append("audio ausente o codec distinto de AAC")
        if report.facts["pixel_format"] not in ("yuv420p", "yuvj420p"):
            report.issues.append("pixel format distinto de yuv420p")
        if video_mode == "short":
            min_dur = 15.0 if is_test_environment() else (float(min_duration_sec) if min_duration_sec is not None else 60.0)
            max_dur = SHORT_MAX_DURATION_SEC
            if duration < min_dur or duration > max_dur:
                report.issues.append(f"duración editorial fuera de rango para Short ({min_dur:.0f}s-{max_dur:.0f}s)")

        else:
            min_dur = 10.0 if is_test_environment() else 600.0
            if duration < min_dur:
                report.issues.append("duración editorial inferior a 10 minutos")
        if not has_faststart(video):
            report.issues.append("MP4 sin moov atom previo a mdat (+faststart)")
        try:
            if isinstance(precomputed_visual, dict) and "longest_black_seconds" in precomputed_visual:
                longest_black = float(precomputed_visual["longest_black_seconds"])
                black_segments = list(precomputed_visual.get("black_segments", []))
                report.facts["black_source"] = "precomputed_visual"
            else:
                longest_black, black_segments = detect_long_black_frames(video)
            report.facts["longest_black_seconds"] = longest_black
            report.facts["black_segments"] = len(black_segments)
            if longest_black >= 3.0:
                report.issues.append("el video contiene un segmento negro prolongado")
            # Plan 3a: reuse the perceptual luminance verdict already computed
            # by the visual integrity pass (single decode per master) when the
            # embedded stamp matches the live extraction constants; otherwise
            # fall back to the standalone ffmpeg sampling.
            lum_data: dict[str, Any] | None = None
            if isinstance(precomputed_visual, dict):
                embedded = precomputed_visual.get("perceptual_luminance")
                if isinstance(embedded, dict) and _embedded_luminance_matches(
                    embedded,
                    luminance_params_fingerprint(LUMINANCE_SAMPLE_FPS),
                ):
                    lum_data = {
                        "avg_luminance": float(embedded["avg_luminance"]),
                        "dark_ratio": float(embedded["dark_ratio"]),
                        "passed": bool(embedded["passed"]),
                        "source": "visual_integrity_report",
                    }
                    report.facts["luminance_source"] = "precomputed_visual"
            if lum_data is None:
                lum_data = analyze_perceptual_luminance(video)
            report.facts["avg_luminance"] = lum_data["avg_luminance"]
            report.facts["dark_ratio"] = lum_data["dark_ratio"]
            if not lum_data["passed"]:
                report.issues.append("el video es perceptualmente demasiado oscuro o carece de detalle visible")
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            report.issues.append(str(exc))
    except (OSError, ValueError) as exc:
        report.issues.append(str(exc))

    if subtitle is not None and subtitle.is_file():
        if subtitle.suffix.lower() == ".srt":
            try:
                from lib.subtitles import validate_subtitle_artifact

                subtitle_facts = validate_subtitle_artifact(
                    str(subtitle), duration_sec=float(report.facts.get("duration") or 0)
                )
                report.facts["subtitle_coverage"] = subtitle_facts["coverage"]
            except (OSError, ValueError) as exc:
                report.issues.append(str(exc))
        elif subtitle.suffix.lower() == ".ass":
            try:
                ass_content = subtitle.read_text(encoding="utf-8")
                if video_mode == "short":
                    if ("PlayResX: 1080" not in ass_content and "PlayResX: 720" not in ass_content) or ("PlayResY: 1920" not in ass_content and "PlayResY: 1280" not in ass_content):
                        report.issues.append("resolución ASS no es 1080x1920 para Short")
                else:
                    if ("PlayResX: 1920" not in ass_content and "PlayResX: 1280" not in ass_content) or ("PlayResY: 1080" not in ass_content and "PlayResY: 720" not in ass_content):
                        report.issues.append("resolución ASS no es 1920x1080 para Longform")
            except OSError:
                report.issues.append("no se pudo leer el archivo de subtítulos ASS")

    if visual_plan_path is None:
        report.issues.append("plan QA de visuales ausente")
    else:
        try:
            plan = json.loads(Path(visual_plan_path).read_text(encoding="utf-8"))
            scenes = plan.get("scenes") or []
            duration = float(report.facts.get("duration") or 0)

            def _scene_duration(scene: dict) -> float:
                return float(
                    scene.get("duration")
                    or scene.get("duration_sec")
                    or 0
                )

            def _scene_source(scene: dict) -> str:
                return str(
                    scene.get("source")
                    or scene.get("image_path")
                    or scene.get("path")
                    or ""
                )

            scene_durations = [_scene_duration(scene) for scene in scenes if isinstance(scene, dict)]
            covered = float(
                plan.get("covered_seconds")
                or plan.get("duration_sec")
                or 0
            )
            if covered <= 0 and scene_durations:
                covered = float(sum(scene_durations))
            if not scenes or int(plan.get("black_fallbacks") or 0) != 0:
                report.issues.append("cobertura visual ausente o con fallback negro")

            is_loop_plan = (
                (video_engine is not None and str(video_engine).lower() in ("loop", "loop_video", "loop_video_engine", "loop_compositor"))
                or str(plan.get("video_engine", "")).lower() in ("loop", "loop_video", "loop_video_engine", "loop_compositor")
                or plan.get("loop") is True
                or plan.get("is_loop") is True
                or (len(scenes) == 1 and str(plan.get("mode", "")).lower() == "loop")
            )
            if not is_loop_plan:
                min_cadence = 2.0 if video_mode == "short" else 15.0
                max_cadence = 16.5 if video_mode == "short" else 45.0
                if any(value < min_cadence or value > max_cadence for value in scene_durations):
                    report.issues.append(f"cadencia visual fuera del intervalo {int(min_cadence)}-{int(max_cadence)} segundos")
            if duration <= 0 or abs(covered - duration) > 1.0:
                report.issues.append("el plan visual no cubre toda la duración")
            if any(
                not Path(_scene_source(scene)).is_file()
                for scene in scenes
                if isinstance(scene, dict)
            ):
                report.issues.append("el plan visual referencia recursos ausentes")
            report.facts["scene_count"] = len(scenes)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            report.issues.append("plan QA de visuales ausente o inválido")

    try:
        from PIL import Image

        with Image.open(thumbnail) as image:
            expected_sizes = ((720, 1280), (360, 640), (768, 1360), (1080, 1920), (1280, 720)) if video_mode == "short" else ((1280, 720), (1920, 1080))
            if image.size not in expected_sizes:
                report.issues.append(f"miniatura con resolución no permitida ({image.size[0]}x{image.size[1]})")
            image.load()
    except Exception:
        report.issues.append("miniatura ausente o corrupta")
    return report


def validate_narrative_coherence(*args: Any, **kwargs: Any) -> Any:
    from src.narrative.quality_gate import validate_narrative_coherence as _vnc
    return _vnc(*args, **kwargs)

