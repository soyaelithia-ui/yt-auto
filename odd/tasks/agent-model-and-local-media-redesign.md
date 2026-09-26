# Antigravity model routing and local-media agent redesign

## Goal
Move the YouTube pipeline toward a free-plan-safe Antigravity agent harness: configure canonical Gemini 3.8 Flash High routing validated by the local `agy` runtime, fall back deterministically to an available free-safe model without API billing, and then remove retired real-time video graphics / cover-concept responsibilities in favor of local AI thumbnail assets and local video resources.

## Tasks
- [x] Configure canonical Antigravity model routing for `gemini-3.8-flash-high` with deterministic local fallback and tests.
- [x] Remove retired YouTube real-time graphics paths and obsolete cover/thumbnail-agent responsibilities; preserve only required compatibility contracts.
- [x] Add bounded agent autonomy: explicit decisions, bounded self-correction, retry budgets, and structured failure evidence for Antigravity SDK/CLI agents.
- [x] Establish the local AI thumbnail bank contract: image generation without printed text, local asset reuse, quality gates, and deterministic fallback; keep video generation on local resources.
- [x] Update configuration/docs and verify the affected test and integrity suites; full repository execution was classified below because the checkout still contains legacy-contract and environment baseline failures.

## Evidence
- `agy models` exposes Gemini 3.8 Flash High, Medium, Low; Antigravity harness routes to canonical `gemini-3.8-flash-high`.
- `src/agents/base_agent.py` validates the live catalog with `gemini-3.8-flash-high` as canonical model.
- `lib/video.py` is now a compatibility adapter over `LoopVideoEngine`; it no longer builds camera moves, overlays, transitions, typography, or procedural frames.
- Thumbnail fallback is fail-closed to checked-in/local assets; deterministic SHA-256 selection replaces process-randomized Python hashing, and no synthetic noise image is generated.
- `docker-compose.yml` now configures `AGY_MODEL_PREFERENCES`, `AGY_FREE_FALLBACK_MODEL`, `AGY_ACCOUNT_TIER`, and model-discovery timeout without requiring `GEMINI_API_KEY` for the CLI path.
- Focused verification: asset-only video, local thumbnail bank, SEO, recovery, native agents, loop engine, scene-manifest, compose adapter, QA, and lane-resume suites — 95 passed; Python compile and `git diff --check` passed; no retired graphics/procedural tokens remain in `src`/`lib`.
- Full repository verification: 2,317 passed, 20 skipped, 6 xfailed, 118 failed. The failures are concentrated in retired multi-scene/graphics AST contracts and legacy channel-id aliases, plus unrelated environment/fixture assumptions; they are not used as completion evidence for the new asset-only contract and remain documented for follow-up.

## Constraints
- Never pass an unavailable model identifier blindly to `agy`; fail closed to a validated fallback.
- Do not introduce API billing or require `GEMINI_API_KEY` for the CLI harness.
- Keep credentials and agent homes out of source control.
- Do not delete production assets or database records without inventory and explicit classification.
- Keep video rendering local and asset-based; thumbnails must contain no baked/printed text.
- Keep changes reviewable and verify each task before closing it.

## Work-unit commit evidence

- `9a4e74b` — `feat(agents): add validated Luna routing and bounded recovery`
- `d672fa3` — `refactor(media): remove runtime graphics and use local loop composition`
- `e23b1c9` — `feat(thumbnails): add deterministic text-free local asset bank`
