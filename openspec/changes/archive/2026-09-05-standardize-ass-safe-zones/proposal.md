# Proposal: Standardize ASS Safe Zones and Stream-Copy Preservation

## Intent
Standardize ASS subtitle safe zones across 9:16 portrait and 16:9 landscape to eliminate UI collisions, and enforce strict FFmpeg stream-copy (`-c:v copy`) preservation when subtitles are absent or inactive.

## Scope
- **In Scope**:
  - Update `src/media/subtitles_ass.py` margins:
    - 9:16 portrait: $MarginV \ge 480\text{px}$ (clearing 450px UI floor), $MarginL \ge 64\text{px}$, $MarginR \ge 130\text{px}$ (clearing right action bar), dynamic 2.5D drift (+30px $\to MarginV \ge 510\text{px}$).
    - 16:9 landscape: $MarginV \ge 130\text{px}$.
  - Adaptive font scaling proportional to canvas height.
  - Implement sentinel `has_active_subtitles(path)` (checks existence, size > 0, $\ge 1$ `Dialogue:` line).
  - Preserve `-c:v copy` in `loop_engine.py`, `compositor.py`, and `multi_act_renderer.py` when subtitles inactive.
  - Consistent FFmpeg filter escaping (colons, backslashes, quotes).
  - Graceful handling of empty/null transcripts.
  - Unit tests for margins, drift, sentinel, and stream copy.
- **Out of Scope**:
  - STT transcription or alignment generation changes.
  - Deprecating legacy Pillow drawer.

## Capabilities
- **New Capabilities**: None.
- **Modified Capabilities**:
  - `subtitles-safe-zone`: Aligns ASS margins ($MarginV \ge 480/130\text{px}$, $MarginR \ge 130\text{px}$) and font scaling with safe-zone specs.
  - `media-processing-performance-policy`: Preserves `-c:v copy` when subtitles are omitted or contain no dialogue.

## Approach
1. **Dynamic Layout**: Compute margins and font sizes from canvas dimensions and camera drift in `subtitles_ass.py`.
2. **Sentinel Check**: Provide `has_active_subtitles()` to detect actual dialogue events.
3. **Filtergraph Bypass**: Omit subtitle filter and retain stream copy across video engines when subtitles are inactive.
4. **Escaping**: Unify subtitle path escaping across FFmpeg command builders.

## Affected Areas
| Component | Files | Modifications |
| :--- | :--- | :--- |
| **Subtitles** | `src/media/subtitles_ass.py` | Safe margins, font scaling, `has_active_subtitles` helper. |
| **Media Engines** | `src/media/loop_engine.py`<br>`src/media/compositor.py`<br>`src/media/multi_act_renderer.py` | Preserve stream copy, sentinel gating, filter escaping. |
| **Tests** | `tests/unit/test_subtitles_ass.py`<br>`tests/unit/test_subtitle_safe_zone.py` | Margin assertions, drift scaling, sentinel, stream-copy tests. |

## Risks & Rollback
- **Risks**: Text clipping on long cues. *Mitigation*: Chunking ($\le 3$ words/cue) and height-scaled fonts.
- **Rollback**: Revert git commits on branch. No DB or schema changes.

## Dependencies
- FFmpeg with `libass` support.

## Success Criteria
- [ ] 9:16 portrait ASS files enforce $MarginV \ge 480\text{px}$ (drift-adjusted) and $MarginR \ge 130\text{px}$.
- [ ] 16:9 landscape ASS files enforce $MarginV \ge 130\text{px}$.
- [ ] `has_active_subtitles()` returns `True` only with $\ge 1$ `Dialogue:` line.
- [ ] Engines bypass subtitle filter and keep `-c:v copy` when subtitles are inactive.
- [ ] Unit tests pass with 100% success.
