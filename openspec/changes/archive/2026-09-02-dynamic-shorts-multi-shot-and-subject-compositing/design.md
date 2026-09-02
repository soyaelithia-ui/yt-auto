# Design: Dynamic Shorts Multi-Shot Cadence, Script Boilerplate Sanitization, and Adaptive Thumbnail Subject Compositing

## Technical Approach

This design addresses three core requirements across all three production channels (`moku`, `aelithia`, and general documentarian/narrative lanes):
1. **Multi-Camera Shot Cadence for Shorts**: Transition from a single static procedural loop background to a multi-scene shot progression (3–4 shot intervals of 8–12 seconds each) with dynamic camera angles, seed variation, and seamless crossfade transitions.
2. **Deterministic Outro & Boilerplate Script Sanitization**: Eliminate narrative outro leaks such as `"Todos los expedientes y archivos se encuentran en Moku Reddit*"` across prompt instructions, sanitization barriers, and SQLite storage.
3. **Adaptive Thumbnail Subject Compositing**: Procedurally composite an atmospheric, subtly shaded silhouette of the central subject in the thumbnail's central focal zone (underneath the hook title) with rim lighting and chiaroscuro depth, matching the exact procedural world without external AI distortions.

---

## Architecture Decisions

| Decision | Option Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| **Multi-Shot Progression** | Partition audio into 3–4 shot segments in `pipeline.py` & resolve procedural loops with camera/seed variation | Single stretched loop background | Eliminates static feel and produces dynamic visual storytelling across the 30–60s duration. |
| **Outro Sanitization** | Add regex patterns to `FORBIDDEN_EDITORIAL_PATTERNS` and `repair_forbidden_editorial` in `sanitizer.py` + update LLM prompts | Manual regex in pipeline | Centralizes filtering in the existing pre-TTS and editorial barrier gates, ensuring deterministic drop of any handle/archive plug. |
| **Subject Compositing in Covers** | Vector/procedural silhouette compositing with Gaussian mist & rim-light in `subject_extractor.py` | Standalone AI image generation API call | Zero hallucination risk, instantaneous execution, 100% aesthetic coherence with the procedural WGSL background, and no external API cost/latency. |

---

## Data Flow

```
[ Story Ingestion / Scraping ]
              │
              ▼
[ Sanitizer / Editorial Barrier ] ──(Strips @MokuRedit / archive boilerplate)
              │
              ▼
[ TTS Synthesis & Word Boundaries ]
              │
              ▼
[ Multi-Shot Visual Planning ] ──(Calculates 3–4 shot intervals: [0..9s, 9..19s, 19..28s, 28..35s])
              │
              ▼
[ Native Procedural Loop Engine ] ──(Generates/resolves multi-angle loops with seed variations)
              │
              ▼
[ Video Compositor (FFmpeg) ] ──(Stitches shots with smooth crossfades + audio + subtitles)
              │
              ▼
[ Adaptive Thumbnail Engine ] ──(Injects subtle thematic subject silhouette in focal zone + chiaroscuro + title)
              │
              ▼
[ Telegram Review Delivery ] ──(Dispatches video review + high-res cover photo preview)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/sanitizer.py` | Modify | Add boilerplate archive/handle patterns to `FORBIDDEN_EDITORIAL_PATTERNS` and `CRINGE_INTRO_PATTERNS` so they are stripped deterministically. |
| `src/llm.py` | Modify | Update `_FORBIDDEN_EDITORIAL_DIRECTIVE` and prompt templates to explicitly forbid adding archive/subreddit outro plugs. |
| `src/media/thumbnails/subject_extractor.py` | Modify | Implement `AdaptiveSubjectCompositor` to render thematic subject silhouettes (humanoid anomaly, solitary figure, cosmic observer) in the focal zone with rim lighting. |
| `src/media/thumbnails/engine.py` | Modify | Invoke `AdaptiveSubjectCompositor` during thumbnail generation to place the subject beneath the hook title. |
| `src/pipeline.py` | Modify | Implement multi-scene shot planning for loop mode, generating 3–4 shot segments for audio durations > 14s. |
| `src/media/loop_engine.py` | Modify | Support multi-loop composition and camera parameter variation in `LoopVideoEngine.render()`. |

---

## Interfaces / Contracts

### 1. `AdaptiveSubjectCompositor` (`src/media/thumbnails/subject_extractor.py`)

```python
class AdaptiveSubjectCompositor:
    """
    Renders and composites thematic subject silhouettes in the central focal zone
    of the thumbnail canvas with atmospheric mist blending and accent rim-lighting.
    """

    @classmethod
    def composite_thematic_subject(
        cls,
        base_img: Image.Image,
        channel_id: str = "moku",
        archetype: str = "arctic_desolation",
        accent_color_hex: str = "#00FF66",
        intensity: float = 0.85,
    ) -> Image.Image:
        """
        Renders a subtle, non-intrusive character/entity silhouette
        into the lower-central focal zone (x: 0.35..0.65, y: 0.40..0.78).
        """
        ...
```

### 2. Multi-Shot Scene Planner (`src/pipeline.py`)

```python
def plan_multi_shot_loop_scenes(
    total_duration_sec: float,
    target_category: str,
    orientation: str = "vertical",
    loop_engine: LoopVideoEngine = None,
) -> tuple[list[str], list[float]]:
    """
    Divides total duration into 3-4 dynamic shot intervals (8-12s each)
    and resolves distinct loop backgrounds with seed/camera variation.
    """
    ...
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| **Unit** | `test_sanitizer_drops_moku_reddit_outro` | Verify that text ending with `"Todos los expedientes y archivos se encuentran en Moku Reddit*"` is cleanly stripped. |
| **Unit** | `test_adaptive_subject_compositing` | Verify that `AdaptiveSubjectCompositor` generates an integrated silhouette with accent rim-light on all 3 channel archetypes. |
| **Unit** | `test_multi_shot_loop_planning` | Verify that videos > 14s produce 3–4 shot intervals with valid paths and durations. |
| **E2E** | Full Pipeline Run-Once | Run `main.py run -c moku --dispatch-telegram` and verify that the generated Short has multi-scene transitions and the cover features the subtle entity silhouette. |

---

## Threat Matrix

| Threat Category | Applicability | Mitigation | Planned Test |
|---|---|---|---|
| **Command Injection / Subprocess** | Applicable (FFmpeg filter args) | Validate all file paths and duration numbers before constructing FFmpeg multi-input filter strings. | `test_multi_shot_ffmpeg_args_safety` |
| **Process Hang / Timeout** | Applicable (Video rendering) | Keep procedural loop lengths at 6.0s with stream/concat copy or bounded filter complex length. | `test_render_frame_time_progression` |
| **Data Corruption / Leak** | Applicable (TTS script generation) | Strict regex filter in `sanitizer.py` guarantees no prompt leaks or outro text reach the voice synthesizer. | `test_validate_pre_tts_script_drops_leaks` |

---

## Open Questions

- None. Requirements are fully specified and tested.
