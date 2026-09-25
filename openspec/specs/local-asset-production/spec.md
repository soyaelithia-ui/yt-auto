# Local asset production

## Requirements

### Requirement: local video only
Production lanes MUST accept only `director` or `video_loop`. Both MUST resolve local video assets and compose through `LoopVideoEngine`.

#### Scenario: retired pipeline rejected
- Given a lane with `visual_pipeline: image_animation`
- When the lane is parsed
- Then validation fails before execution.

#### Scenario: director remains editorial
- Given a horizontal director lane with several local act videos
- When stages 8 and 9 run
- Then the manifest uses `catalog_loop` and the output is assembled by the loop engine without runtime graphics.

### Requirement: no runtime graphics
The production source tree MUST NOT import or expose Ken Burns, hybrid frame generation, SVG/in-memory overlays, HUD drawtext/drawbox, or procedural video renderers.

### Requirement: text-free thumbnail bank
Thumbnail generation MUST resolve a local AI-bank image or deterministic local fallback and MUST never draw title text, badges, watermarks, or captions.

#### Scenario: declared text asset rejected
- Given a bank image whose sidecar has `text_free: false`
- When the bank resolves candidates
- Then that image is excluded.

### Requirement: bounded agent recovery
Agent execution MUST record every failure decision and MUST not exceed configured attempt/correction budgets.

#### Scenario: transient failure
- Given a transient provider error on attempt one
- When the recovery policy has remaining attempts
- Then it retries and records `action: retry`.

#### Scenario: contract failure
- Given a response validation failure and one correction budget
- When the agent retries
- Then it sends one correction prompt and records `action: correct`.

#### Scenario: saturation
- Given a quota/rate-limit error
- When the agent handles it
- Then it stops immediately, records `provider_saturation`, and trips the instance circuit breaker.
