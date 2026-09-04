# Design: VPS FFmpeg Hot-Path Smoke

## Technical Approach

Parse **live** FFmpeg evidence (spec `ffmpeg-hot-path-smoke`) without touching encode engines. Beats argv is already logged (`LoopVideoEngine`: `Executing Stream-Copy ... command:`). `ffmpeg_compose.log` is stderr only (no argv). Checker is a pure parser + pytest fixtures; optional CLI wraps it. Fail-closed is process: non-zero exit blocks look PRs. No compositor / proc_engine / pipeline edits. DSP/EBU unchanged.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|----------|--------|----------|-----------|
| Language | Python parser + thin CLI | Bash-only grep | Tokenize argv; offline pytest; avoid `-c:v copy` false positives in filenames |
| Evidence | Prefer logged argv; stderr is fallback | Treat unit tests as smoke | Spec forbids source/pytest as evidence |
| Beats-only | Copy pass without director | Force a director job | Prod `lanes.json` is all `beats` |
| Re-encode | If libx264 present: require `-preset veryfast` and `-crf 21`; else `no re-encode observed` | Fail when veryfast missing | Spec edge case |
| Hot path | Read-only | Patch `lib/video.py` to dump argv | Out of scope unless evidence impossible |

## Data Flow

```
capture (docker logs | work/*/ffmpeg_compose.log | operator file)
        │
        ▼
parse_ffmpeg_evidence(text)
        │  argv lines  → tokens (-c:v, -preset, -crf)
        │  else stderr → x264 [veryfast] / crf=  (weaker)
        ▼
verdict JSON: copy|reencode|missing_argv + pass/fail
        │
        ├── pytest fixtures (offline)
        └── CLI exit 0/1 (VPS / CI)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/media/ffmpeg_hot_path_smoke.py` | Create | Parse evidence; verdict dataclass; no subprocess ffmpeg |
| `tests/unit/test_ffmpeg_hot_path_smoke.py` | Create | RED/GREEN on fixture argv/stderr |
| `scripts/smoke_ffmpeg_hot_path.sh` | Create | `python -m` wrapper; stdin or file path; exit codes |
| `compositor.py` / `proc_engine.py` / `pipeline.py` | None | Forbidden |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class HotPathVerdict:
    copy_observed: bool
    reencode_observed: bool
    reencode_preset: str | None  # must be "veryfast" if reencode
    reencode_crf: int | None     # must be 21 if reencode
    argv_recovered: bool
    passed: bool
    note: str  # e.g. "no re-encode observed"
```

CLI: `scripts/smoke_ffmpeg_hot_path.sh [log_path|-]` reads UTF-8 text. Input is **data**, never executed. Exit 1 if `not passed`.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Missing argv → fail | Fixture empty log |
| Unit | Beats argv `-c:v copy` → pass | Fixture `Executing Stream-Copy ... -c:v copy` |
| Unit | Beats-only, no director → pass | Same; no libx264 |
| Unit | libx264 + veryfast + crf 21 → pass | Fixture argv |
| Unit | libx264 + slow/ultrafast or crf≠21 → fail | Fixture argv |
| Unit | Path named `README.sh` is read as text | Classification RED |
| Integration/E2E | VPS capture | Operator-run CLI; not default pytest (`not live`) |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|----------|---------------|-----------------|-------------------|
| Documentation-like paths | Applicable | Log path is read-only bytes; never exec/chmod/source | `README.sh` / `requirements.txt` fixtures parsed as text |
| Git repository selection | N/A: no git | — | — |
| Commit state | N/A: no commits | — | — |
| Push state | N/A: no push | — | — |
| PR commands | N/A: no gh/git | — | — |

Safe: open file/stdin, parse, print JSON, exit. Failure: missing file → argv not recovered → fail (no exception swallow).

## Migration / Rollout

No migration. Run against a VPS log after deploy. Follow-up SDD changes stay closed until exit 0.

## Open Questions

- [ ] Exact VPS log path (docker journal vs `work/**/ffmpeg_compose.log`) — CLI takes a path, so non-blocking.
