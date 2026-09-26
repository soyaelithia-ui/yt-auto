# Design: Streamlined Defect Remediation and Test Restoration

## Architectural Invariants
- Zero Browser in media/pipeline.
- Resource envelope strictly bounded: ≤ 2 CPU cores, ≤ 2.0 GiB RAM.
- No new third-party dependencies or bloated helper wrappers.

## Fix Architecture
1. **Concurrency Detection (`deploy/ctl.sh`)**:
   Use `docker ps --filter "name=yt-automation" --format '{{.Names}}' | grep -E -q '(^|[-_])yt-automation([-_]|$)'`.
2. **Failure Screenshot Path (`src/youtube/uploader/session.py`)**:
   Check `if screenshot_dir: os.makedirs(screenshot_dir, exist_ok=True)` and construct `os.path.join(screenshot_dir, ...)`.
3. **Ownership Verification (`src/youtube/control.py`)**:
   Export `_verify_ownership` in `__all__`, provide explicit type signature, and add tests in `tests/unit/test_youtube_control.py`.
4. **Channel Alias & Persona Alignment (`src/llm.py`)**:
   Map `is_drama = resolve_channel_key(channel) in ("aelithia", "drama")`.
   Include `"horror"`, `"drama"`, `"moku"`, `"aelithia"` keys in `_ADAPTATION_PERSONAS`.
5. **Anti-Regression Guardrails & Documentation (`tests/unit/test_anti_regression_guardrails.py`, `docs/FFMPEG_LOW_CPU.md`)**:
   - Align REG-03, REG-08, REG-09 with loop-only composition and `story_v1.json`.
   - Update `docs/FFMPEG_LOW_CPU.md` to document the 2 Cores/2 GB RAM resource target and 45s turnaround ceiling.
6. **Obsolete Test Quarantine**:
   - Retire or remove obsolete test modules asserting removed graphics files (`test_chunked_xfade.py`, legacy compositor tests).
   - Update test fixtures from legacy names (`moku`, `aelithia`) to canonical ones (`horror`, `drama`).
