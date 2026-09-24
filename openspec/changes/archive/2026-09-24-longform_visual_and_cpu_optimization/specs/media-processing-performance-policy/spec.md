# Media Processing and Performance Policy Specification (Delta)

## Purpose
Codifies the operational and performance policy for longform horizontal media composition: mandates zero-transcode stream-copy (`-c:v copy`) concatenation for multi-act longform videos (turnaround $\le 45\text{s}$, aggregate CPU $\le 120\%$, peak RAM $< 200\text{ MiB}$), strictly prohibiting full-pixel Ken Burns re-encoding (`zoompan`) and `libass` subtitle pixel burning on 16:9 horizontal longform videos, while enforcing container soft subtitle muxing (`mov_text`) and `.srt` sidecar export.

## MODIFIED Requirements

### Requirement: Stream-Copy Priority, Multi-Act Longform Concatenation, and Soft Subtitle Muxing
(Previously: Prioritized stream-copy `-c:v copy` composition across single video-loop and ambient pathways with `mov_text` soft subtitles when active, but lacked explicit mandates for multi-act longform stream-copy concatenation turnaround $\le 45\text{s}$, aggregate CPU $\le 120\%$, peak RAM $< 200\text{ MiB}$, and did not explicitly prohibit 60–90 minute full-pixel Ken Burns re-encoding or `libass` subtitle burning on 16:9 horizontal longform videos)

The system MUST prioritize stream-copy (`-c:v copy`) composition across all video-loop and longform horizontal rendering pathways (`horror-horror-long`, `drama-aita-long`, `scifi-singularity-long`) to maintain near-zero CPU consumption ($\approx 0.10\text{ Cores}$ idle/copy, $\le 1.20\text{ Cores}$ during audio ducking/normalizing) and ultra-high throughput.

For multi-act longform horizontal (16:9) narratives (10–30 minutes / 600–1800 seconds):
1. **Mandatory Stream-Copy Concatenation**: Video composition MUST assemble $N$ distinct narrative act loops sequentially using the FFmpeg concat demuxer (`-f concat -safe 0 -c:v copy`). Video packets MUST be demuxed and remuxed directly from disk without decoding or re-encoding video frames.
2. **Turnaround Performance Contract**: Rendering turnaround for an entire 10–30 minute video MUST complete in $\le 45\text{ seconds}$ from invocation to container finalization.
3. **CPU Utilization Ceiling**: Aggregate CPU utilization across all active subprocesses during composition MUST NOT exceed $120\%$ (1.2 CPU Cores), with CPU cycles restricted exclusively to audio highpass/lowpass filtering, sidechain ducking, and EBU R128 loudness normalization (`amix`, `loudnorm` bounded by `-threads 2`).
4. **RAM Footprint Bounding**: Peak resident memory (RSS) MUST remain strictly $< 200\text{ MiB}$ (canonical $< 150\text{ MiB}$) throughout multi-act composition, streaming concat manifests (`ffconcat`) and audio tracks directly from disk or `/dev/shm`.
5. **Transcoding & Subtitle Burning Prohibition**: Full-pixel Ken Burns re-encoding (`libx264` with `zoompan` or procedural transitions) and pixel-rasterized subtitle burning via `libass` are STRICTLY PROHIBITED on 16:9 horizontal longform videos. Any attempt to invoke pixel re-encoding on horizontal longform narratives MUST trigger the Resource Work Refusal policy and immediately abort.
6. **Soft Subtitle Muxing & Sidecar**: Subtitles for horizontal longform videos MUST be soft-muxed into the MP4 container as a timed text track (`-c:s mov_text`) via `subtitle_mux_ffmpeg_parts` and exported as an `.srt` sidecar file for YouTube Captions API upload.
7. **Animation Lanes Exemption**: When video re-encoding is explicitly required (strictly reserved for 9:16 vertical Shorts on `image_animation` lanes), subtitles SHALL be burned natively via `libass` in a single pass with safe-area compliance ($MarginV \ge 480\text{px}$).

#### Scenario: Multi-act longform stream-copy concatenation turnaround and CPU bounding (Happy Path)
- **Given** an 1,800-second (30-minute) horizontal narrative with 6 act loops and mastered audio
- **When** `_render_video_loop` in `stage_09_render.py` executes media composition via `stream_copy.py`
- **Then** the FFmpeg command MUST contain `-f concat -safe 0` and `-c:v copy`
- **And** total video composition turnaround MUST NOT exceed 45 seconds (target 25–35 seconds)
- **And** aggregate CPU utilization across all subprocess threads MUST NOT exceed 120% (1.2 Cores)
- **And** peak resident memory (RSS) MUST remain below 200 MiB.

#### Scenario: Container soft subtitle muxing without video re-encode on longform horizontal video (Happy Path)
- **Given** a multi-act longform horizontal video with narration subtitles
- **When** video composition and container packaging execute
- **Then** subtitles MUST be soft-muxed via `-c:s mov_text`
- **And** an `.srt` sidecar file MUST be generated in the run artifacts directory
- **And** video stream-copy `-c:v copy` MUST be preserved without pixel decoding.

#### Scenario: Subtitle burn enabled exclusively on re-encode animation lane (Happy Path)
- **Given** an `image_animation` lane requiring Ken Burns camera motion and subtitle display
- **When** `UnifiedEncoder` constructs the FFmpeg filtergraph
- **Then** the filtergraph MUST incorporate `libass` subtitle burning into the atomic single-pass filterchain
- **And** enforce $MarginV \ge 480\text{px}$ to preserve mobile UI safe zones.

#### Scenario: Work refusal on full-pixel Ken Burns or libass burning on longform horizontal lane (Edge Case)
- **Given** a 16:9 horizontal longform lane configuration attempting to execute full-pixel `zoompan` re-encode or `libass` subtitle burning
- **When** engine validation or render stage initiates
- **Then** the system MUST trigger Resource Work Refusal and abort execution
- **And** execution MUST NOT proceed with CPU-saturating re-encoding.

#### Scenario: Inactive or missing subtitles preserve stream-copy (Edge Case)
- **Given** a multi-act longform scene configuration where subtitles are absent, empty, or disabled
- **When** the composition engine constructs the concat command
- **Then** subtitle inputs and filter clauses MUST be omitted completely
- **And** stream-copy `-c:v copy` MUST be preserved.

---

### Requirement: libass Subtitle Rendering and Safe Area
(Previously: Mandated native `libass` subtitle burning for both 9:16 vertical Shorts and 16:9 horizontal videos without explicit prohibition of `libass` subtitle burning on 16:9 horizontal longform videos)

Subtitles generated for 9:16 vertical Shorts (`image_animation` or vertical re-encode lanes) MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles generated for 9:16 vertical Shorts MUST enforce bottom UI Safe Area $MarginV \ge 480\text{px}$ (canonical $\ge 25\%$ of canvas height), scaled with procedural 2.5D camera drift offsets to ensure clearance above player UI controls. Subtitles MUST enforce word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

For 16:9 horizontal longform videos (600–1800s), burning subtitles into video frames via `libass` is STRICTLY PROHIBITED; subtitles MUST be soft-muxed into the container via `mov_text` and exported as an `.srt` sidecar.

#### Scenario: Native libass subtitle burn for 9:16 vertical Shorts (Happy Path)
- **Given** word-level narration timestamps for a 9:16 vertical Short ($1080\times 1920$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 480\text{px}$ (scaling to $\ge 510\text{px}$ under downward camera drift)
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Downward camera drift compensation (Edge Case)
- **Given** a 9:16 video scene with active downward procedural camera drift ($\Delta y = +30\text{px}$)
- **When** subtitle margin calculation executes
- **Then** $MarginV$ MUST be boosted dynamically to $\ge 510\text{px}$
- **And** rendered text MUST remain strictly above the 450px bottom UI danger threshold.

#### Scenario: Prohibition of libass subtitle burn on 16:9 horizontal longform lanes (Edge Case)
- **Given** a 16:9 horizontal longform production lane
- **When** subtitles are processed for video composition
- **Then** the pipeline MUST NOT invoke `libass` or add subtitle filtergraphs to the video stream
- **And** the pipeline MUST route subtitles to container soft muxing (`-c:s mov_text`) and `.srt` sidecar export.
