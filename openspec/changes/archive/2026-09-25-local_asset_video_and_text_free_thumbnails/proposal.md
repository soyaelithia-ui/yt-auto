# Proposal: local-asset video pipeline and text-free AI thumbnails

## Problem

The repository still carried multiple runtime graphics renderers, generated HUD/overlay paths, and agents that designed baked thumbnail headlines. These paths increase CPU/RAM cost, duplicate visual policy, and conflict with the desired local-resource workflow.

## Decision

Make local video assets the only production visual source. Keep `director` as an editorial act selector, but route every lane through `LoopVideoEngine` and stream-copy assembly. Remove runtime graphics modules and their direct production contracts. Delegate cover creation to a local AI thumbnail bank; SEO may request an asset but never designs or renders cover text.

Add bounded Antigravity recovery: explicit retry/correction decisions, strict attempt budgets, and structured failure evidence in every task result.

## Non-goals

- No remote image generation or API billing.
- No deletion of local video assets, catalog rows, or story data.
- No changes to subtitle authoring; soft subtitle muxing remains supported.
