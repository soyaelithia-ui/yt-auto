# Archive Report: Longform Visual Quality and CPU Optimization (Hybrid Multi-Act Director)

**Change**: `2026-09-24-longform_visual_and_cpu_optimization`  
**Archived At**: `2026-09-24`  
**Mode**: `hybrid` (OpenSpec filesystem + Engram memory)  
**Status**: Closed / Complete  

---

## 1. Executive Summary

This archive report serves as the terminal record of the `2026-09-24-longform_visual_and_cpu_optimization` SDD cycle. All planned capabilities have been designed, specified, implemented via strict Test-Driven Development (RED-GREEN-VERIFY), verified through exhaustive unit and anti-regression suites, and promoted into canonical OpenSpec specifications.

The core deliverable of this change is the **Hybrid Multi-Act Director** architecture on 16:9 horizontal longform video channels (`horror-horror-long`, `drama-aita-long`, `scifi-singularity-long`). It eliminates runtime visual monotony and CPU-saturating transcoding by decomposing 10–30 minute narratives into 4–8 dramatic acts, resolving distinct thematic horizontal loops per act with progressive tension calibration (1–5), executing zero-transcode stream-copy concatenation (`-f concat -safe 0 -c:v copy`), injecting formatted YouTube interactive chapter markers into descriptions, and soft-muxing subtitles (`mov_text`) with `.srt` sidecars under strict $\le 2.0$ CPU Cores and $\le 2.0$ GiB RAM constraints.

Key Architectural Milestones Delivered:
1. **Dynamic 4–8 Act Narrative Partitioning & Duration Scaling** (`src/curators/curation_profiles.py`, `src/curators/text_splitter.py`): Replaced rigid 4-act templates with dynamic 4–8 act structures across horror and drama profiles; implemented proportional duration scaling against synthesized audio timestamps with strict zero temporal drift and semantic paragraph break fallback.
2. **Thematic Multi-Loop Catalog Resolution & Engine Routing** (`src/media/loop/rotation.py`, `src/pipeline/stages/stage_04_mood.py`, `src/pipeline/utils.py`, `src/pipeline/executor.py`): Eliminated runtime coercion of longform director lanes to single continuous loop mode; implemented dramatic role and tension-aware catalog loop matching with seeded modulo rotation fallback and `FORCE_SINGLE_LOOP` operational killswitch.
3. **Zero-Transcode Stream-Copy Concat Assembly & Soft Subtitle Muxing** (`src/media/loop/stream_copy.py`, `src/pipeline/stages/stage_08_loop.py`, `src/pipeline/stages/stage_09_render.py`): Deployed sequential multi-act concat manifest compilation for FFmpeg concat demuxer (`-f concat -safe 0 -c:v copy`), slashing 30-minute render turnaround to $\le 45\text{ seconds}$ (target 25–35s); soft-muxed subtitles as container timed text (`-c:s mov_text`) with `.srt` sidecar export; established Resource Work Refusal guardrail prohibiting `libass` burning and full-pixel Ken Burns re-encoding on horizontal longform.
4. **Interactive YouTube Chapters & Sidecar Metadata** (`src/pipeline/stages/stage_11_metadata.py`): Formatted compliant YouTube chapter markers in video descriptions satisfying platform constraints (starting at `00:00`, $\ge 3$ chapters, each $\ge 10\text{ seconds}$), automatically coalescing short trailing segments, and registering sidecar `.srt` artifacts.
5. **Anti-Regression & Guardrail Compliance**: 100% pass across REG-01 through REG-14, zero network/browser activity, and verified compliance with `AGENTS.md` Section 5 hard resource ceiling ($\le 2$ CPU Cores, $\le 2.0$ GiB RAM).

---

## 2. Implementation Record

- **Total Tasks**: 22 / 22 completed (100%)
- **Phases Executed**:
  - **Phase 1: Foundation & Act Narrative Contracts** (Tasks 1.1 – 1.4): Expanded narrative curation profiles for `horror-horror-long` and `drama-aita-long` in `curation_profiles.py` to support 4–8 acts with dramatic roles and tension progression (1–5); implemented dynamic act builder and zero-drift proportional duration scaling in `text_splitter.py`; verified 4/4 unit tests.
  - **Phase 2: Stage 04 Thematic Loop Resolution & Engine Routing** (Tasks 2.1 – 2.5): Refactored `_resolve_engine_mode` in `utils.py` and `executor.py` to preserve `director` mode on horizontal longform lanes; implemented `resolve_multi_act_loops` in `rotation.py` with tension mapping and modulo fallback; wired multi-act planning into `stage_04_mood.py` with `FORCE_SINGLE_LOOP` killswitch; verified 5/5 unit tests.
  - **Phase 3: Stage 08 & Stage 09 Concat Assembly & Subtitle Muxing** (Tasks 3.1 – 3.5): Deployed multi-scene concat manifest routing in `stage_08_loop.py`; implemented stream-copy concat and soft subtitle muxing (`mov_text`) in `stage_09_render.py` and `stream_copy.py`; enforced Resource Work Refusal against longform `libass` burning; verified 4/4 unit tests.
  - **Phase 4: Stage 11 YouTube Chapters Metadata & Sidecar** (Tasks 4.1 – 4.4): Implemented `YouTubeChapterSpec` in `stage_11_metadata.py`; injected interactive chapter markers into descriptions; registered `.srt` sidecar artifacts; verified 4/4 unit tests.
  - **Phase 5: Anti-Regression Verification, Guardrails & Offline Checks** (Tasks 5.1 – 5.4): Expanded REG-13 and REG-14 assertions in `test_anti_regression_guardrails.py`; ran complete unit and anti-regression suites (49 passed); confirmed offline network isolation; validated repository integrity SLA (`verify_integrity.sh`).

---

## 3. Specs Synced to Source of Truth

All specifications were synced mechanically to canonical storage in `openspec/specs/`:

| Domain | Action | Requirements Summary |
|---|---|---|
| `longform-multi-act-director` | Created | New canonical spec created at `openspec/specs/longform-multi-act-director/spec.md` via mechanical shell copy with byte-for-byte empty `diff -r` readback. (Req 1: Script Act Partitioning & Tension Curve; Req 2: Thematic Multi-Loop Catalog Resolution; Req 3: Zero-Transcode Stream-Copy Concatenation Assembly; Req 4: Soft Subtitle Container Muxing & SRT Sidecar Export; Req 5: YouTube Interactive Chapter Formatting & Metadata Injection). |
| `media-processing-performance-policy` | Updated | Composed canonical spec with delta via `gentle-ai sdd-archive-compose`. Updated `Stream-Copy Priority and Soft Subtitle Muxing` -> `Stream-Copy Priority, Multi-Act Longform Concatenation, and Soft Subtitle Muxing` (mandating stream-copy concat turnaround $\le 45\text{s}$, aggregate CPU $\le 120\%$, peak RAM $< 200\text{ MiB}$, prohibiting full-pixel Ken Burns and libass subtitle burning on 16:9 horizontal longform). Updated `libass Subtitle Rendering and Safe Area` (prohibiting libass burning on 16:9 horizontal longform, restricting burning exclusively to 9:16 vertical animation lanes). |
| `multi-channel-lanes-and-smoke-test` | Updated | Composed canonical spec with delta via `gentle-ai sdd-archive-compose`. Updated `Canonical Thematic Six-Lane Configuration Parity and Declarative Visual Pipelines` (preserving `director` mode on horizontal longform lanes `horror-horror-long` and `drama-aita-long` without runtime coercion to single loop). Updated `End-to-End Generate-Only Smoke Test Across Dual Paradigms` -> `End-to-End Generate-Only Smoke Test Across Dual Paradigms and Multi-Act Director` (verifying multi-act stream-copy, chapter metadata, and `.srt` sidecars). |

---

## 4. Verification and Integrity Evidence

Per the final-state authority hierarchy, terminal verification facts superseding all intermediate snapshots:

- **Unit & Integration Tests**: 49 / 49 tests passed in 13.02s (17 multi-act tests + 32 anti-regression guardrail tests).
- **Anti-Regression Guardrails**: 14 / 14 guardrails passed (REG-01 through REG-14, 32 assertions green).
- **Repository Integrity SLA**: `./scripts/verify_integrity.sh` passed 100% clean (exit code 0, 3748ms, commit #357).
- **Turnaround Performance**: Multi-act stream-copy concatenation turnaround verified $\le 45\text{s}$ (target 25–35s).
- **Resource Target Ceiling SLA**: Strict compliance with `REG-14` & `AGENTS.md` Section 5 ($\le 2.0$ CPU Cores, $\le 2.0$ GiB RAM, zero steady-state idle footprint).

---

## 5. Traceability and Engram Observation Citations

All cycle artifacts were recorded and tracked across Engram memory (`youtubechannels` project) and OpenSpec storage:

- **Proposal**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/proposal.md`
- **Exploration**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/exploration.md`
- **Design**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/design.md`
- **Tasks**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/tasks.md`
- **Verification Report**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/verify-report.md`
- **Archive Report (File)**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization/archive-report.md`
- **Engram Archive Report**: Topic `sdd/longform_visual_and_cpu_optimization/archive-report` (type: `architecture`)

---

## 6. Mechanical Archival Audit

- **Source Path**: `openspec/changes/longform_visual_and_cpu_optimization` (verified removed)
- **Archive Path**: `openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization` (verified present)
- **Mechanical Move Command**: Shell move using `git mv` with `mv` fallback.
- **Readback Verification**: Mandatory pre-move snapshot readback `diff -r /tmp/change_pre_move_snapshot openspec/changes/archive/2026-09-24-longform_visual_and_cpu_optimization` yielded **0 byte difference** (exit code 0).
- **Specs Sync Method**: Mechanical `cp -R` for new capability `longform-multi-act-director`; `gentle-ai sdd-archive-compose` for modified capabilities `media-processing-performance-policy` and `multi-channel-lanes-and-smoke-test`.
