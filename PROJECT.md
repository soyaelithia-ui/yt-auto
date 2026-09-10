# Project: 16:9 Long-Form Video Pipeline Optimization & Thematic Loop Rotation

## Architecture
- **Pipeline & Composition Engine (`src/pipeline.py`, `src/media/loop_engine.py`)**:
  - Single continuous loop composition: single clip (10s vertical 9:16 for shorts from `assets/videos/shorts/`, 30s horizontal 16:9 for longs from `assets/videos/longs/`) repeated seamlessly across narration duration.
  - Zero-reencode stream-copy (`-c:v copy`) via concat demuxer (<2s execution, near-zero CPU/RAM).
  - Multichannel neutrality: round-robin rotation across available `.mp4` files without channel coupling.
  - Fail-Fast safeguard: raises `CatalogAssetNotFoundError` if video directories are empty.
  - Prompt-driven real-time thumbnails: Chiaroscuro high-CTR style with 3-5 word viral hooks.
- **Locking & Concurrency (`src/core/lock.py`, `src/orchestrator/pipeline.py`)**:
  - Non-blocking/timed `ChannelLock` with polling timeout and reentrancy registration in `_active_locks`.
- **Review Delivery & Telegram Bot (`review/telegram_bot.py`, `src/telegram/approval.py`)**:
  - Size preflight check against 50 MB Telegram cloud limit.
  - Mandatory 2-hour rejection window for human veto/approval (`AUTO_PUBLISH_TIMEOUT_HOURS = 2`).
  - Automatic publish sweep after 2 hours without human action (fail-open programmed).
  - Post-publication local cleanup (`delete_local_post_publication`): unlinks local `.mp4` and TTS audios, archiving permanently to Google Drive.
- **Governance & CI (`./scripts/verify_integrity.sh`, `.githooks/pre-commit`)**:
  - Zero-Browser policy in media/pipeline.
  - Zero-Secrets policy across git and memory.
  - 100% HEALTHY state verified via `./scripts/verify_integrity.sh`.

## Feature Inventory
| # | Feature ID | Feature | Description | Milestone | Source |
|---|------------|---------|-------------|-----------|--------|
| 1 | F01 | Stream-Copy Concat Slicing | `ffconcat version 1.0` with `duration <shot_dur>` per entry in `LoopVideoEngine.compose()` | M1 | Survey (Explorer 1) |
| 2 | F02 | Elimination of Re-encoding Bottlenecks | Use `-c:v copy` for all 1080p Main master loops; eliminate redundant `libx264` re-encoding | M1 | Survey (Explorer 1) |
| 3 | F03 | Lock Hardening & Anti-Deadlock | Add polling timeout and `_active_locks` registration to `ChannelLock` to eliminate self-collisions | M1 | Survey (Explorer 1) |
| 4 | F04 | Catalog Candidate Pool Fallback | Allow seeded rotation across distinct channel-compatible loops when subcategory count == 1 | M2 | Survey (Explorer 3) |
| 5 | F05 | Thematic Loop Rotation & Channel Isolation | Alternating scene background rotation per channel theme (dark/horror for Moku, cosmos/tech for SciFi) | M2 | Survey (Explorer 2) |
| 6 | F06 | 16:9 Aspect Ratio Preservation | Preserve exact 1920x1080 dimensions without distortion across all master loop transitions | M2 | Survey (Explorer 2) |
| 7 | F07 | Long-Form Test Generation (Moku & SciFi) | Generate test 16:9 longform videos for `moku-horror-long` and `scifi-singularity-long` | M3 | User Request (R3) |
| 8 | F08 | Telegram Proxy Generation (<= 50MB) | Ensure longform videos are adaptively compressed to <= 50MB for Telegram review delivery | M3 | Survey (Explorer 3) |
| 9 | F09 | Telegram Delivery Verification | Send test video review to chat `8266399903`, verifying HTTP 200 and `ok: true` | M3 | User Request (R3) |
| 10 | F10 | Secret Hygiene Remediation | Redact plain-text Telegram token in `ORIGINAL_REQUEST.md` to pass `.githooks/pre-commit` | M4 | Survey (Explorer 3) |
| 11 | F11 | Invariant & Governance Verification | Verify `./scripts/verify_integrity.sh` 100% HEALTHY, zero-browser, and zero-secrets | M4 | User Request (R4) |
| 12 | F12 | Git Branch Integration & Push | Pull/rebase remote commits, create semantic commits, and push to `origin/verify_vps_github_status` | M4 | User Request (R4) |
| 13 | F13 | E2E Test Suite Creation | Requirements-driven opaque-box test suite (Tiers 1-4) published via `TEST_READY.md` | E2E Track | Project Pattern |
| 14 | F14 | Live Director Shot Mix | Majority settled background reuse with minority designed in-moment grades | Pipeline | PR #69 |
| 15 | F15 | Precomputed QA Metrics Gate | `bank_manifest.json` visual metrics avoid double full-file decode in prepublication QA | Pipeline | PR #69 |
| 16 | F16 | Multi-Channel Lane Parity | Six production lanes across Moku, Aelithia, and SciFi (Shorts + Longform) | Pipeline | PR #69 |
| 17 | F17 | Permanent 6 Master Loops Catalog | Purge 66 unbranded atomic clips & Sci-Fi loops; exactly 6 certified brand master loops | Pipeline | v3.2 Restructure |
| 18 | F18 | Production Cadence Calibration | 12 shorts/h (1 short c/5m: 6 Moku + 6 Aelithia) and 2 longs/h (1 long c/30m: 1 Moku + 1 Aelithia); interleaved initial offsets | Pipeline | Cadence Sync |
| 19 | F19 | Telegram 2h Rejection Window | All generated videos sent to Telegram in PENDING_REVIEW; 2h operator veto window before auto-publish | Review | v3.2 Restructure |
| 20 | F20 | Post-Publish Local Reclamation | Unlink local .mp4 and TTS audio files post-publish, retaining 100% video archive on Google Drive | Storage | v3.2 Restructure |
| 21 | F21 | Dynamic Procedural Narrative Synthesis | Eradication of 44s shortcuts and static hardcoded stories; procedural synthesis calibrated to 180-320 words (Shorts) and >=2,600 words (Longform) | Narrative | Cadence Sync |
| 22 | F22 | Narration Channel-Sanitization | Complete removal of spoken channel names, `@` handles, and self-referential promos; 100% immersive narration | Narrative | Audio Purity |
| 23 | F23 | Low-Resource Fast Composition & Zero Artificial Duration Cap | Concat demuxer stream-copy (`-c:v copy`) sub-second assembly, enabling 5m cadence with zero CPU saturation and natural narrative duration | Media | Pipeline SLA |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Stream-Copy Concat & Lock Hardening | `src/media/loop_engine.py`, `src/core/lock.py`, `src/pipeline.py` | none | DONE |
| M2 | Catalog Candidate Pool & Thematic Rotation | `src/core/catalog.py`, `tests/unit/test_loop_catalog.py` | none | DONE |
| M3 | Long-Form Generation & Telegram Delivery | `src/orchestrator/pipeline.py`, `review/telegram_bot.py`, generation CLI | M1, M2 | DONE |
| M4 | E2E Validation & Governance | E2E test pass, secret redaction, `./scripts/verify_integrity.sh`, git push | M3, E2E Track | DONE |
| M5 | 6 Loops Catalog, Cadence, 2h Telegram Window & Post-Publish Clean | `assets/loops/`, `config/lanes.json`, `src/pipeline.py`, `src/telegram/approval.py`, `src/cleaner.py` | M1-M4 | DONE |
| M6 | Cadence Synchronization, Dynamic Narratives & Narration Sanitization | `config/lanes.json`, `src/core/lanes.py`, `src/core/repository.py`, `src/templates/narratives.py`, `src/curators/`, `src/agents/` | M1-M5 | DONE |

## Interface Contracts
### LoopVideoEngine ↔ FFmpeg Concat Demuxer
- Input: `loop_concat_list.txt` formatted with `ffconcat version 1.0`, followed by alternating `file '<path>'` and `duration <dur_sec>` lines.
- FFmpeg Command: `ffmpeg -y -f concat -safe 0 -i loop_concat_list.txt -i speech.wav -i bgm.mp3 -filter_complex <ducking_filter> -c:v copy -c:a aac -movflags +faststart <output.mp4>`.
- Guarantees: Zero video re-encoding, sub-second composition, exact 1920x1080 16:9 output.

### LoopCatalogRepository ↔ Pipeline
- Signature: `get_best_loop(category: str, orientation: str = "horizontal", seed: Optional[int] = None, channel: Optional[str] = None) -> LoopMetadata`
- Semantics:
  - If `channel` is provided, candidate pool is filtered strictly by `CHANNEL_THEMES[channel]`.
  - If matching category has <= 1 record, fallback to all distinct channel records to allow seeded rotation.
  - Returns `LoopMetadata` with verified physical path in `assets/loops/horizontal/`.

### TelegramReviewBot ↔ Telegram Bot API
- Target: `https://api.telegram.org/bot[REDACTED]/sendVideo`
- Payload: multipart/form-data with `chat_id=8266399903`, `video=<proxy_file>`, `supports_streaming=true`.
- Output: `DeliveryResult(ok=True, message_id=<int>)` on HTTP 200.

## Code Layout
- `src/media/loop_engine.py`: Concat demuxer writing, stream-copy composition, audio filtergraph.
- `src/core/lock.py`: File locking mechanism (`ChannelLock`).
- `src/core/catalog.py`: Loop catalog repository, channel themes, seeded candidate rotation.
- `src/pipeline.py`: Main pipeline execution, shot planning, audio generation.
- `src/orchestrator/pipeline.py`: Channel orchestration, topic story creation, telegram review trigger.
- `review/telegram_bot.py`: Telegram review bot, preflight size check, proxy builder.
- `tests/e2e/`: E2E test suites covering loop stream-copy, rotation, locks, and delivery.
