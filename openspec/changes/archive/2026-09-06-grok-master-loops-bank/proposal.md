# Proposal: Grok Master Loops Bank and Classified Asset Repository

## 1. Context & Motivation

In previous iterations of `yt-auto`, background visuals relied on real-time procedural 2D rendering via PIL (`NativeProceduralEngine` / `scripts/generate_master_loops.py`), which caused massive operational bottlenecks on VPS environments:
- 8.5 minutes to render a single 60s background on 4 vCPUs (3.5 fps).
- Visually primitive/flat aesthetic contrary to channel identity and analog horror reference (`swrBqnV6bNM`).

To achieve instant, production-grade video publishing, an offline library of 72 scenes and 55 native AI video loops (6s, 24fps) was generated via Grok CLI (`image_to_video`). However, atomic 6-second clips alone are insufficient for full 45-60s Shorts or 2-3 minute longform videos without repetitive looping.

This change unifies, concatenates, and classifies these assets into permanent production-ready master loops of 60 seconds, pre-encoded in H.264 Main Profile (`yuv420p`, 24fps) with SQLite catalog indexing, enabling sub-5-second stream-copy (`-c:v copy`) video composition.

---

## 2. Proposed Changes

1. **Master Sequence Concatenation (`scripts/build_loops_bank.py`)**:
   - Assemble atomic 6s clips into coherent, thematic 60s continuous sequences using FFmpeg concat demuxer.
   - Encode master loops into H.264 `Main` profile at CRF 19 with `-movflags +faststart`.
   - Prevent runtime transcoding in `LoopVideoEngine.ensure_h264_main_profile` by pre-satisfying the YouTube profile gate.

2. **Categorized Asset Bank Population (`assets/loops/`)**:
   - Organize into orientation-first hierarchy:
     - `assets/loops/horizontal/{horror,dark_forest,drama,scifi,space_abyss}/`
     - `assets/loops/vertical/{horror,drama,scifi}/`
   - Store both 60s master loops and linked atomic 6s clips (`atomic/` subfolder) for rhythmic beat cutting.

3. **Catalog & Database Registration (`data/loop_catalog.db`)**:
   - Register all master loops and channel aliases in `LoopCatalogRepository` SQLite database.
   - Generate `assets/loops/bank_manifest.json` tracking checksums, durations, and scene lineage.

4. **Engine Resolution & Verification**:
   - Ensure `LoopVideoEngine.resolve_loop_video` resolves horizontally and vertically across all channels without falling back to live synthesis.
   - Comprehensive test suite in `tests/unit/test_loops_bank.py`.

---

## 3. Rollback Plan

- If the concatenated master loops cause any pipeline regression, `assets/loops/bank_manifest.json` and `data/loop_catalog.db` can be cleared.
- `LoopVideoEngine` retains fallback filesystem traversal and optional on-demand synthesis flags.
- All 55 raw clips remain untouched in `assets/background_scenes/`.
