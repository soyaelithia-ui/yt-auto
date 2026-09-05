# Design: Standardize ASS Safe Zones and Stream-Copy Preservation

## Technical Approach

Standardize Advanced SubStation Alpha (`.ass`) subtitle safe zones across 9:16 portrait and 16:9 landscape layouts while enforcing FFmpeg stream-copy (`-c:v copy`) when subtitles are inactive.

1. **Dynamic Margins**: Pure helpers (`calculate_safe_margins`, `calculate_font_size`). In 9:16 portrait ($1080\times 1920$), subtitles enforce $MarginV \ge 480\text{px}$ (+30px drift $\to \ge 510\text{px}$), right rail $MarginR \ge 130\text{px}$, left $MarginL \ge 64\text{px}$. In 16:9 landscape ($1920\times 1080$), $MarginV \ge 130\text{px}$, $MarginL/R \ge 40\text{px}$.
2. **Dialogue Sentinel**: `has_active_subtitles(path)` verifies existence, size > 0, and $\ge 1$ non-whitespace `Dialogue:` event; empty/header-only files safely degrade.
3. **Stream-Copy Preservation**: Engines (`LoopVideoEngine`, `MultiSceneCompositor`, `MultiActVideoRenderer`) evaluate `has_active_subtitles()`. Inactive subtitles bypass filtergraphs, retaining lossless `-c:v copy` muxing under single-pass DSP and EBU R128 standards.
4. **Path Sanitization**: Centralized `escape_ffmpeg_filter_path()` secures filter paths against injection.

## Architecture Decisions

| Option | Tradeoffs | Decision & Rationale |
|---|---|---|
| **Margins** | Static 40px vs dynamic calculation | **Dynamic Calculation**: $MarginV \ge 480\text{px}$ (+drift), $MarginR \ge 130\text{px}$ (9:16); $MarginV \ge 130\text{px}$ (16:9). Clears mobile UI controls. |
| **Sentinel** | File check vs dialogue parse | **Dialogue-Aware (`has_active_subtitles`)**: Header-only files degrade to stream-copy, preventing multi-minute video transcodes. |
| **Stream-Copy** | Re-encode when `include_subtitles=True` | **Conditional Preservation**: Keeps `-c:v copy` when `burn_subtitles` or `has_active_subtitles()` is False. Preserves ~2s renders. |
| **Path Escaping** | Ad-hoc `.replace()` vs helper | **Centralized `escape_ffmpeg_filter_path`**: Escapes colons, backslashes, quotes uniformly across engines, preventing filter injection. |

## Data Flow

```
Narration Words / Transcript
         │
         ▼
ASSSubtitleGenerator ──> calculate_safe_margins() / calculate_font_size()
         │               (9:16: MarginV>=480, R>=130; 16:9: MarginV>=130)
         ▼
    .ass File
         │
         ▼
has_active_subtitles(path)?
  ├── FALSE (None / 0-byte / 0 Dialogue)
  │         │
  │         ▼
  │    Engines bypass filter ──> Stream Copy (-c:v copy)
  │
  └── TRUE (>=1 Dialogue event)
            │
            ▼
       escape_ffmpeg_filter_path(path)
            │
            ▼
       Engines transcode video via libass (libx264, single-pass DSP)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/media/subtitles_ass.py` | Modify | Implement `has_active_subtitles`, `calculate_safe_margins`, `calculate_font_size`, `escape_ffmpeg_filter_path`; update ASS defaults. |
| `src/media/loop_engine.py` | Modify | Gate subtitle filter on `has_active_subtitles`; preserve `-c:v copy`; escape filter paths. |
| `src/media/compositor.py` | Modify | Gate `has_ass_burn` / `video_copy` on `has_active_subtitles`; escape paths; preserve `-c:v copy`. |
| `src/media/multi_act_renderer.py` | Modify | Align safe margins; gate subtitle filter on `has_active_subtitles`; escape paths. |
| `tests/unit/test_subtitles_ass.py` | Modify | Unit tests for safe margins, font scaling, escaping, and sentinel checks. |
| `tests/unit/test_subtitle_safe_zone.py` | Create | Stream-copy preservation vs transcode gating across orientations and drift. |

## Interfaces / Contracts

```python
def has_active_subtitles(path: Path | str | None) -> bool:
    """True iff path is regular file, size > 0, and has >=1 valid Dialogue line."""

def calculate_safe_margins(
    video_width: int, video_height: int, downward_drift_px: int = 0
) -> tuple[int, int, int]:
    """Return (MarginL, MarginR, MarginV) for canvas orientation and drift."""

def calculate_font_size(video_width: int, video_height: int) -> int:
    """Return height-scaled font size (52px at 1920h vertical, 38px at 1080h horizontal)."""

def escape_ffmpeg_filter_path(path: Path | str) -> str:
    """Escape backslashes, colons, and single quotes for FFmpeg filter arguments."""
```

- **Portrait Margin**: $MarginV = \max(480, \text{int}(H \times 0.25)) + \max(0, \Delta y)$, $MarginR = \max(130, \text{int}(W \times 0.12))$, $MarginL = \max(64, \text{int}(W \times 0.06))$.
- **Landscape Margin**: $MarginV = \max(130, \text{int}(H \times 0.12)) + \max(0, \Delta y)$, $MarginL/R = 40$.
- **Font Size**: Portrait $\text{round}(52 \times (H / 1920))$; Landscape $\text{round}(38 \times (H / 1080))$.
- **Chunking**: $\le 3$ words/cue, non-overlapping ($end_1 \le start_2$).

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| **Unit** | `has_active_subtitles` | None, missing, 0B, header-only, valid Dialogue, whitespace text. |
| **Unit** | Margins & Font Scaling | Assert margins and font sizes across 1080x1920, 1920x1080, drift (+30px). |
| **Unit** | Path Escaping | Windows drives `C:\`, single quotes `'`, colons `:`. |
| **Integration** | `LoopVideoEngine` stream-copy | Assert `-c:v copy` when subtitles inactive; assert `libass` filter when active. |
| **Integration** | `MultiSceneCompositor` mux | Assert `video_copy=True` and no `ass=` filter when subtitles inactive. |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| **Filtergraph colons/delimiters** | Applicable | `escape_ffmpeg_filter_path` escapes colons (`\:`) preventing filter chain breakout. | `test_escape_filter_path_colons` |
| **Single-quote argument** | Applicable | Escapes single quotes (`\'`) in filter arguments (`subtitles='...'`). | `test_escape_filter_path_quotes` |
| **Empty/corrupt subtitle** | Applicable | `has_active_subtitles` fails closed (`False`), bypassing filtergraph on 0B/corrupt files. | `test_has_active_subtitles_empty` |
| **Subprocess execution** | Applicable | Engines invoke `subprocess.run(cmd, shell=False)` list form; never `shell=True`. | Unit test inspection |

## Migration / Rollout

No migrations required. Backward compatible with existing calls; engines fall back to stream-copy.

## Open Questions

None. Architectural contracts and safe zones are fully specified.
