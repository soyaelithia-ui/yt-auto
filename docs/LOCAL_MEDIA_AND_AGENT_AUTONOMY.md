# Local media and bounded agent autonomy

## Video boundary

Production lanes accept only `director` and `video_loop`. Both resolve local videos through `LoopVideoEngine`; `director` only chooses an ordered act sequence. The renderer does not create frames or add graphics at runtime.

Retired paths include image animation/Ken Burns, hybrid scene rendering, SVG/in-memory overlays, HUD `drawtext`/`drawbox`, and generated thumbnail typography. Their modules and direct production imports are removed.

## Thumbnail boundary

`LocalAIThumbnailBank` reads `assets/thumbnails/ai_bank/` (or `AI_THUMBNAIL_BANK_DIR`) and selects deterministically by channel, archetype, and title metadata. A generated image may carry a sidecar with `text_free: true`; invalid, corrupt, or text-declared files are rejected. The fallback is a clean local scenery/template asset; if no valid local asset exists, generation fails closed instead of synthesizing an image.

`ThumbnailEngine` resizes and grades the selected image only. It does not render a title, badge, watermark, caption, or logo. SEO returns `thumbnail_asset_request` with `bank: local_ai` and `text_free: true`; it does not design cover layouts or headlines.

## Agent recovery boundary

`ProgrammaticAgent` applies `AgentRecoveryPolicy` to both the SDK and CLI paths:

- `AGY_MAX_ATTEMPTS` is bounded to 1–4 (default 2).
- `AGY_MAX_SELF_CORRECTIONS` is bounded to 0–2 (default 1).
- A transient failure may retry within budget.
- A declared response-contract failure may receive one correction prompt.
- Saturation/quota failures stop immediately and trip the instance circuit breaker.
- Every attempt records the error, selected action, reason, correction count, and policy in `failure_evidence` inside `task_result.json`.

No agent may invent an unavailable model identifier; runtime model selection remains validated against `agy models`.
