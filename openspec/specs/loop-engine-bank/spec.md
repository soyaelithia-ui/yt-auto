# Delta Spec: Loop Engine Bank

## MODIFIED Requirements

### Requirement: Pre-baked 60s Master Loop Resolution
The `LoopVideoEngine` SHALL default its catalog database connection to `data/loop_catalog.db` when present, ensuring LRU rotation and tag-scoring without falling back to unpopulated queue tables. The engine SHALL strictly default `enable_live_synth=False` and interpret `ENABLE_LIVE_LOOP_SYNTH="0"` by default, guaranteeing that production pipeline runs resolve pre-baked 60s master loops from `assets/loops/` without invoking runtime procedural synthesis.
(Previously: Resolved master loops via LoopCatalogRepository or filesystem traversal without explicitly defaulting to data/loop_catalog.db or specifying default inactive live synthesis flags)

#### Scenario: Catalog database default path selection
- GIVEN an initialized `LoopVideoEngine` without an explicit `db_path` override
- WHEN the engine instantiates `LoopCatalogRepository`
- THEN it SHALL connect to `data/loop_catalog.db` when the file exists on disk
- AND it SHALL leverage LRU rotation and tag-scoring across cataloged master loops.

#### Scenario: Production live synthesis deactivation
- GIVEN the production execution environment without `ENABLE_LIVE_LOOP_SYNTH` set to "1"
- WHEN `resolve_loop_video` executes for any channel or category
- THEN the engine SHALL NOT invoke `LoopSynthesizerWorker` or FFmpeg `lavfi` procedural filters
- AND it SHALL resolve an existing pre-baked master loop file from `assets/loops/`.

#### Scenario: Horizontal master loop query
- GIVEN an engine initialized with default loops directory `assets/loops/` and category `horror`, `drama`, or `scifi`
- WHEN `resolve_loop_video` is invoked with `orientation="horizontal"`
- THEN the engine SHALL return an existing master loop with duration >= 30.0 seconds and H.264 Main profile.

#### Scenario: Vertical master loop query for Shorts
- GIVEN an engine initialized with default loops directory `assets/loops/`
- WHEN `resolve_loop_video` is invoked with `orientation="vertical"` for `horror`, `drama`, or `scifi`
- THEN the engine SHALL return an existing 9:16 vertical master loop with duration >= 30.0 seconds without raising `LoopVideoAssetError`.

## ADDED Requirements

### Requirement: Retained On-Demand Procedural Synthesis
The system SHALL retain procedural synthesis logic (`LoopSynthesizerWorker`, native FFmpeg `lavfi` gradient generator) for explicit manual CLI commands and test invocations. The synthesizer worker SHALL only execute when explicitly enabled via `ENABLE_LIVE_LOOP_SYNTH=1`, constructor argument `enable_live_synth=True`, or the `main.py loop generate` command.

#### Scenario: Explicit environment variable activation
- GIVEN environment variable `ENABLE_LIVE_LOOP_SYNTH="1"` or `enable_live_synth=True`
- WHEN `resolve_loop_video` executes and no cached loop matches category filters
- THEN `LoopSynthesizerWorker` SHALL synthesize a procedural loop via FFmpeg `lavfi` into `assets/loops/procedural/`
- AND the resulting video path SHALL be returned.

#### Scenario: Manual CLI loop generation command
- GIVEN the operator executes `main.py loop generate --category cosmic_horror --duration 60`
- WHEN the command dispatches to the loop generation handler
- THEN the system SHALL run `LoopSynthesizerWorker.synthesize_on_demand` regardless of the default pipeline flag
- AND the synthesized asset SHALL be saved and indexed.
