# Tasks: Grok Master Loops Bank and Classified Asset Repository

## Phase 1: Automation Script & Concatenation
- [x] 1.1 Implement `scripts/build_loops_bank.py` to parse `assets/background_scenes/catalog.json`.
- [x] 1.2 Define thematic groupings for Moku Horror, Aelithia Drama, and Singularidad Sci-Fi.
- [x] 1.3 Concatenate atomic clips using FFmpeg concat demuxer into $\ge 30-60\text{s}$ continuous sequences.
- [x] 1.4 Encode all outputs to H.264 `Main` Profile (`yuv420p`, 24fps) with faststart flags.

## Phase 2: Classification & SQLite Registration
- [x] 2.1 Populate `assets/loops/horizontal/` and `assets/loops/vertical/` directory structure.
- [x] 2.2 Create hardlinks/symlinks for channel alias categories (`dark_forest`, `dark_ambient`, `space_abyss`).
- [x] 2.3 Link 55 atomic 6-second clips into `atomic/` subfolders for micro-cutting.
- [x] 2.4 Register all 8 master loops and alias references into `data/loop_catalog.db` via `LoopCatalogRepository`.
- [x] 2.5 Generate `assets/loops/bank_manifest.json` inventory summary.

## Phase 3: Testing & Engine Resolution
- [x] 3.1 Write unit test suite `tests/unit/test_loops_bank.py`.
- [x] 3.2 Verify manifest integrity and file size constraints.
- [x] 3.3 Verify SQLite catalog records and category queries.
- [x] 3.4 Verify `LoopVideoEngine.resolve_loop_video` returns valid paths for all supported channels and orientations.
- [x] 3.5 Execute full test suite and anti-regression verification.
