# Design: Video Duration Calibration and Test Suite Fidelity

## Technical Approach
Calibrate narrative generation and test execution so that longform production channels (`aelithia`, `moku-horror-long`) reliably meet the $\ge 10$ minute ($600\text{s} \le \text{duration} \le 1800\text{s}$) threshold, while isolating heavyweight procedural rendering from unit tests to preserve hermetic sub-second test execution per `pytest.ini`.

```
[Topic / Lore] ──→ [Narrative Template (>=2800w)] ──→ [TTS Synthesis (>=600s)]
                           │                                  │
                           ▼                                  ▼
             [Directed Gate Enforcement] ──────────→ [MultiScene Manifest]
                                                              │
                                    ┌─────────────────────────┴─────────────────────────┐
                                    ▼                                                   ▼
                       [Unit Tests: Mocked Compositor]                     [E2E: WebGPU / FFmpeg Render]
```

## Architecture Decisions

| Decision | Options Considered | Tradeoffs | Selected Choice & Rationale |
|---|---|---|---|
| **Longform Narrative Word Budget** | 1. 1,800–2,100 words<br>2. Dynamic AI loop padding<br>3. Static 2,800–3,200 word templates | Opt 1 yields only 5–7 mins at +6% speech rate.<br>Opt 2 risks incoherent repetition.<br>Opt 3 delivers deterministic 10–14 min voiceover. | **Option 3 (2,800–3,200 words)**: Guarantees $\ge 600\text{s}$ speech without AI quota consumption or repetition. |
| **Directed Story Duration Gate** | 1. Bypass check on directed runs<br>2. Error on <600s<br>3. Autonomous compilation/expansion | Opt 1 allows 1–3 min videos in production directed runs.<br>Opt 2 fails abruptly on short user prompts.<br>Opt 3 handles short prompts smoothly. | **Option 3 (Auto-expand or fail-closed below minimum)**: Ensures `--topic` produces full $\ge 10$ min videos. |
| **Unit Test Compositor Isolation** | 1. Real Mesa Lavapipe render in unit tests<br>2. Truncate video to 2s in tests<br>3. Mock `MultiSceneCompositor` in unit layer | Opt 1 takes 8+ minutes per unit test (violates `pytest.ini`).<br>Opt 2 distorts real pipeline timing.<br>Opt 3 provides <200ms hermetic unit execution. | **Option 3 (`MultiSceneCompositor` mock in unit layer)**: Reserves real WebGPU/FFmpeg renders for `tests/e2e`. |

## Data Flow
1. **Topic Ingestion**: `_prepare_topic_story` invokes `build_aelithia_longform_narrative` or `build_moku_longform_narrative`, producing $\ge 2,800$ words.
2. **Curation & Alignment**: `CinematicScriptCuratorAgent` / `_dispatch_curate_script` validates `min_words >= 2600`.
3. **Audio Synthesis**: `generate_audio` yields master audio track with `duration_sec >= 600.0`.
4. **Scene Manifest Planning**: `ScenePlannerCompositorAgent` segments the 600s+ audio into 5–8 semantic scenes ($60\text{s} \le \text{dur} \le 150\text{s}$).
5. **Render Delegation**:
   - **Unit Tests**: `MultiSceneCompositor.composite_from_manifest` is mocked to emit placeholder MP4 instantly.
   - **E2E / Live**: `MultiSceneCompositor` streams raw RGBA frames to FFmpeg with BT.709 color space.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/templates/narratives.py` | Modify | Expand Aelithia and Moku longform templates to $\ge 2,800$ words across structured beats. |
| `src/curators/aelithia_drama.py` | Modify | Update `target_words = 2600` (from 1800) in `AelithiaDramaCurator`. |
| `src/pipeline.py` | Modify | Align duration validation gate for directed runs and ensure `is_loop_mode` supports `"beats"`. |
| `tests/unit/test_daemon.py` | Modify | Patch `MultiSceneCompositor.composite_from_manifest` in `test_run_pipeline_once_soy_el_malo_channel_and_youtube_url`. |
| `tests/unit/test_directed_story_safety.py` | Modify | Patch `MultiSceneCompositor.composite_from_manifest` in `test_non_short_pipeline_creates_srt_before_validation`. |

## Interfaces / Contracts

### Extended Narrative Template Signature
```python
def build_aelithia_longform_narrative(
    topic: str,
    channel: str = "aelithia",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Produces >=2800 words across 16-18 structured dramatic beats."""
```

### Unit Test Compositor Mock Interface
```python
def fake_multiscene_composite(manifest_path, output_path, **kwargs):
    out = Path(output_path)
    out.write_bytes(b"MP4-MULTISCENE-MOCK")
    return out
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| **Unit** | Word count $\ge 2800$ on narrative templates | Assert `len(script.split()) >= 2800` for Aelithia and Moku templates. |
| **Unit** | Fast daemon & safety pipeline orchestration | Run `test_daemon.py` and `test_directed_story_safety.py` with mocked compositor (<5s total). |
| **Integration** | Multi-scene manifest duration matching | Verify 5–8 scenes totaling $\ge 600\text{s}$ in `test_multiscene_dispatch.py`. |
| **E2E** | Full audio-video render | Existing `tests/e2e/` (110 passed) and `test_e2e_validation.py` (12 passed). |

## Threat Matrix
`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

## Migration / Rollout
No database migration or config schema change required. `config/lanes.json` already defines `duration: {min_sec: 600, target_sec: 600, max_sec: 1800}` and `words: {min: 2600}`.

## Open Questions
None.
