# Spec: Longform Multi-Act Director

## Purpose
Defines the architectural and runtime contracts for the Hybrid Multi-Act Director pipeline on 16:9 horizontal longform video channels (10–30 minutes / 600–1800 seconds). Decomposes longform scripts into 4–8 narrative acts with progressive tension scoring, resolves distinct thematic horizontal loops per act from the catalog, executes zero-transcode stream-copy concatenation (`-c:v copy`), injects automated YouTube interactive chapter markers into descriptions, and soft-muxes subtitles (`mov_text`) with `.srt` sidecar export under strict $\le 2$ CPU Cores and $\le 2.0$ GiB RAM constraints.

## Requirements

### Requirement: Script Act Partitioning & Tension Curve
The narrative curation engine (`CinematicScriptCuratorAgent`, `TextSegmentationEngine`) SHALL systematically partition 10–30 minute longform scripts (600–1800 seconds narration, approximately 2,600 to 4,800 words) into 4 to 8 structured dramatic narrative acts based on semantic boundaries and pacing rules in `src/curators/curation_profiles.py`.

Each narrative act MUST specify:
1. `act_index`: 1-based sequential integer ($1 \le \text{act\_index} \le N$, where $4 \le N \le 8$).
2. `title`: Public dramatic act title suitable for display in YouTube chapters (e.g., "Acto I: Incepción Sensorial y Aislamiento", "Acto II: Tensión Creciente y Advertencias", "Acto III: Punto de Ruptura y Crisis", "Acto IV: Secuela Psicológica y Trauma").
3. `role`: Structural dramatic function (`exposition_inception`, `rising_action_dread`, `confrontation_crisis`, `climax_breaking_point`, `aftermath_revelation`).
4. `tension`: Integer tension rating from 1 (lowest / ambient exposition) to 5 (highest / peak climax).
5. `text`: The assigned segment dialogue and narrative text.
6. `target_duration`: Calculated proportional duration in seconds scaled to match the total voiceover synthesis duration (`ctx.audio_duration`), satisfying:
   $$\sum_{i=1}^{N} \text{target\_duration}_i = \text{ctx.audio\_duration}$$
   with each individual act duration strictly enforcing $\text{target\_duration}_i \ge 30.0\text{ seconds}$.

#### Scenario: Script partitioning into 4-8 acts with progressive tension curve (Happy Path)
- **Given** a curated longform script with a target narration duration of 1,200 seconds (20 minutes)
- **When** `TextSegmentationEngine.curate_acts()` or `CinematicScriptCuratorAgent` processes the script
- **Then** the script payload MUST contain between 4 and 8 structured acts ($4 \le N \le 8$)
- **And** every act MUST include a non-empty `title`, an assigned `role`, and a `tension` rating between 1 and 5
- **And** the tension ratings MUST exhibit narrative progression culminating in a peak tension act ($\text{tension} \ge 4$)
- **And** the sum of calculated act durations MUST equal the total narration duration within a tolerance of $\pm 0.1\text{ seconds}$.

#### Scenario: Proportional duration clamping to total audio duration with zero drift (Happy Path)
- **Given** an Edge-TTS synthesized voiceover file `speech.wav` with measured duration $T = 845.60\text{ seconds}$
- **When** act boundaries are aligned with audio word timestamps
- **Then** each act's duration MUST be scaled proportionally to its word allocation
- **And** the final act boundary MUST be clamped precisely to $T$ so cumulative drift across acts is $0.0\text{ seconds}$.

#### Scenario: Short narrative script boundary handling (Edge Case)
- **Given** a shorter longform narrative script yielding only 3 raw thematic sections
- **When** act decomposition executes
- **Then** the engine MUST subdivide the longest narrative section at a semantic paragraph break
- **And** emit at least 4 valid acts each satisfying the minimum duration of $\ge 30.0\text{ seconds}$.

---

### Requirement: Thematic Loop Resolution per Act
In Stage 04 (`src/pipeline/stages/stage_04_mood.py`), for all horizontal longform lanes configured with `"visual_pipeline": "director"` (such as `horror-horror-long` and `drama-aita-long`), the engine MUST resolve a distinct horizontal video loop from `LoopCatalogRepository` for each of the $N$ narrative acts. Repeating a single 6-second video loop across an entire 600–1800s narrative is STRICTLY PROHIBITED.

The resolution engine (`LoopRotationEngine` / `resolve_multi_act_loops`):
1. MUST match candidate horizontal loop assets based on lane thematic category (`horror`, `dark_forest`, `facility`, `drama`, `aita`, `courtroom`, `nocturne_city`), the act's dramatic `role`, and its `tension` level (e.g. tension 1–2 maps to atmospheric wide/interior shots; tension 4–5 maps to intense lighting, claustrophobic framing, or emergency states).
2. MUST populate `ctx.scene_bg_list` with a list of $N$ distinct loop video file paths:
   $$\text{ctx.scene\_bg\_list} = [\text{loop}_1, \text{loop}_2, \dots, \text{loop}_N]$$
   and `ctx.shot_durations` with the corresponding act durations $[\text{dur}_1, \text{dur}_2, \dots, \text{dur}_N]$.
3. MUST employ deterministic seeded modulo rotation (`seed = act_index`) and semantic alias mapping (e.g., `dark_forest` $\to$ `horror`) when the local catalog contains fewer unique video loops than the number of narrative acts, guaranteeing resolution without runtime failure.
4. MUST provide an environment killswitch: if `FORCE_SINGLE_LOOP=1` is explicitly set, the stage SHALL bypass multi-act rotation and resolve a single continuous loop.

#### Scenario: Resolving distinct thematic horizontal loops per act based on mood and tension (Happy Path)
- **Given** a 5-act narrative for lane `horror-horror-long` with act tension scores $[1, 2, 3, 5, 2]$
- **When** `stage_04_mood.py` executes loop resolution
- **Then** `ctx.scene_bg_list` MUST contain 5 horizontal video loop file paths
- **And** at least 3 distinct video assets MUST be assigned across the 5 acts
- **And** the asset assigned to Act 4 (tension 5) MUST correspond to a high-intensity catalog tag
- **And** `ctx.shot_durations` MUST contain 5 duration values matching the act timing.

#### Scenario: Catalog loop shortage fallback via deterministic modulo rotation (Edge Case)
- **Given** a 6-act narrative and a local loop catalog containing only 3 matching horizontal loops for the lane category
- **When** `resolve_multi_act_loops` executes
- **Then** the engine MUST NOT fail or raise `AssetNotFoundError`
- **And** it MUST deterministically cycle through the available assets using modulo indexing
- **And** consecutive acts MUST NOT share identical loop assets unless the catalog pool has fewer than 2 assets.

#### Scenario: Environment killswitch activates single continuous loop fallback (Edge Case)
- **Given** a longform director lane execution with environment variable `FORCE_SINGLE_LOOP=1`
- **When** `stage_04_mood.py` executes
- **Then** the stage MUST resolve exactly one continuous loop video
- **And** `ctx.scene_bg_list` MUST contain a single loop file path
- **And** `ctx.shot_durations` MUST contain a single element equal to the total narrative duration.

---

### Requirement: Automated YouTube Interactive Chapters Generation
In Stage 11 (`src/pipeline/stages/stage_11_metadata.py`), the metadata generator MUST automatically extract narrative act time boundaries from `ctx.shot_durations` and format clickable YouTube Chapter markers in `ctx.youtube_description` and `ctx.story_record.chapters`.

Chapter formatting MUST adhere strictly to official YouTube interactive chapter constraints:
1. **Timestamp Origin**: The first chapter timestamp MUST start strictly at `00:00` (or `0:00`).
2. **Minimum Chapter Count**: The description MUST contain at least 3 distinct chapter timestamps.
3. **Minimum Chapter Duration**: Each chapter MUST be at least 10 seconds in duration ($t_{i+1} - t_i \ge 10\text{ seconds}$).
4. **Chronological Ordering**: Timestamps MUST be formatted in strictly ascending chronological order (`MM:SS` for durations $< 3600\text{s}$, `HH:MM:SS` for durations $\ge 3600\text{s}$).
5. **Act Title Sanitization**: Chapter titles MUST be stripped of non-printable characters, backticks, and markdown links, formatted cleanly as:
   ```text
   Capítulos:
   00:00 - Acto I: Incepción Sensorial y Aislamiento
   04:12 - Acto II: Advertencias Ignoradas y Señales
   09:45 - Acto III: Confrontación Inexplicable y Ruptura
   17:20 - Acto IV: Secuela Psicológica y Trauma
   ```
6. **Rejection Safeguard**: If act curation produces fewer than 3 chapters or if validation fails, the chapter block MUST be omitted cleanly from `ctx.youtube_description` without aborting the publication pipeline.

#### Scenario: YouTube chapter markers generated and injected into video description (Happy Path)
- **Given** a 4-act longform story with act durations $[255.0, 310.0, 480.0, 355.0]$ seconds
- **When** `stage_11_metadata.py` formats metadata and video description
- **Then** `ctx.youtube_description` MUST contain a formatted chapter block
- **And** the first chapter marker MUST be `00:00`
- **And** subsequent markers MUST be `04:15`, `09:25`, and `17:25`
- **And** the total count of chapter markers MUST be 4 ($\ge 3$).

#### Scenario: Short act duration (< 10s) merged to maintain YouTube chapter compliance (Edge Case)
- **Given** an act sequence where Act 2 has a duration of 8.0 seconds
- **When** chapter generation executes
- **Then** the chapter formatter MUST merge Act 2 into Act 1
- **And** every remaining chapter entry MUST have an interval of $\ge 10\text{ seconds}$ from its neighbor
- **And** the resulting chapter list MUST still satisfy the $\ge 3$ chapter minimum or be cleanly omitted.

#### Scenario: Insufficient chapters (< 3) suppresses chapter block cleanly (Edge Case)
- **Given** a video narrative with only 2 valid acts
- **When** chapter formatting executes
- **Then** the formatter MUST NOT emit a partial chapter block
- **And** `ctx.youtube_description` MUST omit the chapter header to prevent YouTube upload metadata rejection.

---

### Requirement: Container Soft Subtitle Muxing & SRT Sidecar Export
In Stages 08 and 09 (`stage_08_loop.py`, `stage_09_render.py`, `src/media/loop/stream_copy.py`), subtitle integration for 16:9 horizontal longform videos MUST be performed via MP4 container soft-muxing (`-c:s mov_text`) via `subtitle_mux_ffmpeg_parts` and an `.srt` sidecar file MUST be exported for YouTube Captions API upload during publication (`stage_13_publish.py`).

Composition rules:
1. **Zero Frame Re-Encoding**: Longform video composition MUST use FFmpeg stream-copy (`-c:v copy`). Rasterizing subtitles into video pixels via `libass` filtergraphs (`subtitles=...`) on longform horizontal videos is STRICTLY PROHIBITED, as burning subtitles into 600–1800s 1080p video saturates 2 CPU cores for 60–90 minutes and breaches the 900-second job lease timeout.
2. **Container Soft Subtitle Track**: Subtitles generated from narration timestamps MUST be muxed into the primary MP4 container as a `mov_text` timed text stream with Spanish language metadata (`-metadata:s:s:0 language=spa`).
3. **SRT Sidecar Export**: An `.srt` subtitle sidecar file matching the master video basename (`master_video.srt` or `subtitles.srt`) MUST be persisted in the run artifacts directory and registered in `ctx.artifacts["srt_path"]`.
4. **Performance Overhead**: Container subtitle soft-muxing MUST complete within $\le 3.0$ seconds of container packaging overhead, preserving the $\le 45$ second turnaround contract.

#### Scenario: Soft subtitle muxing via mov_text with .srt sidecar export under stream-copy (Happy Path)
- **Given** a 20-minute horizontal longform narrative with generated subtitle cues
- **When** `_render_video_loop` or `stream_copy.py` executes media composition
- **Then** the FFmpeg command MUST include `-c:v copy`
- **And** the FFmpeg command MUST include `-c:s mov_text`
- **And** the FFmpeg command MUST NOT contain `libass` or `subtitles=` filter clauses
- **And** a valid `.srt` file MUST exist in the run artifacts directory
- **And** video rendering MUST complete in $\le 45\text{ seconds}$.

#### Scenario: Missing or empty subtitle cues gracefully omitted without breaking stream-copy (Edge Case)
- **Given** a longform run where subtitle generation was disabled or emitted zero dialogue cues
- **When** media composition executes
- **Then** the engine MUST omit `-c:s mov_text` and subtitle inputs
- **And** stream-copy concatenation `-c:v copy` MUST proceed without error
- **And** the resulting MP4 container MUST contain valid video and master audio streams.

#### Scenario: Rejection of libass pixel burning on horizontal longform lanes (Edge Case)
- **Given** a media composition request for lane `horror-horror-long` or `drama-aita-long`
- **When** the composition parameters are checked
- **Then** the system MUST reject any request to apply `libass` video filter burning to 16:9 longform horizontal output
- **And** enforce container soft-muxing (`mov_text`) and `.srt` sidecar generation instead.
