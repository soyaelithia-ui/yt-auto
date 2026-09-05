# Delta Specification: Media Processing and Performance Policy

## MODIFIED Requirements

### Requirement: libass Subtitle Rendering and Safe Area
(Previously: Subtitles MUST enforce bottom UI Safe Area MarginV >= 240px, canonical 260px)
Subtitles generated for 9:16 vertical Shorts MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles generated for 9:16 vertical Shorts MUST enforce bottom UI Safe Area $MarginV \ge 480\text{px}$ (canonical $\ge 25\%$ of canvas height) and $MarginV \ge 130\text{px}$ for 16:9 horizontal video, scaled with procedural 2.5D camera drift offsets to ensure clearance above player UI controls. Subtitles MUST enforce word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

#### Scenario: Native libass subtitle burn for 9:16 vertical Shorts (Happy Path)
- **Given** word-level narration timestamps for a 9:16 vertical Short ($1080\times 1920$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 480\text{px}$ (scaling to $\ge 510\text{px}$ under downward camera drift)
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Native libass subtitle burn for 16:9 horizontal video (Happy Path)
- **Given** word-level narration timestamps for a 16:9 horizontal canvas ($1920\times 1080$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 130\text{px}$
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Downward camera drift compensation (Edge Case)
- **Given** a 9:16 video scene with active downward procedural camera drift ($\Delta y = +30\text{px}$)
- **When** subtitle margin calculation executes
- **Then** $MarginV$ MUST be boosted dynamically to $\ge 510\text{px}$
- **And** rendered text MUST remain strictly above the 450px bottom UI danger threshold.

## ADDED Requirements

### Requirement: Stream-Copy Preservation When Subtitles Inactive
Video generation engines (`LoopVideoEngine`, `MultiSceneCompositor`, `MultiActVideoRenderer`) MUST omit the subtitle filter and preserve `-c:v copy` stream-copy eligibility whenever `burn_subtitles` (or equivalent subtitle burn flag) is `False` or `has_active_subtitles(path)` evaluates to `False`. Video generation engines MUST NOT inject inactive or empty subtitle filters into FFmpeg filtergraphs, avoiding unnecessary video re-encoding passes and preserving lossless source video streams. When subtitles are active and burning is enabled, subtitle file paths MUST be escaped properly for FFmpeg filter syntax.

#### Scenario: Stream-copy preserved when subtitle burning is inactive or disabled (Happy Path)
- **Given** a media generation pipeline where subtitle burning is disabled or `has_active_subtitles(path)` returns `False`
- **When** `LoopVideoEngine`, `MultiSceneCompositor`, or `MultiActVideoRenderer` prepares FFmpeg arguments
- **Then** the engine MUST omit any `subtitles=` filter from the FFmpeg command
- **And** the engine MUST retain `-c:v copy` for video output muxing when source codecs and parameters permit stream copy.

#### Scenario: Active subtitle dialogue triggers libass filter injection (Happy Path)
- **Given** a valid ASS file with at least one active dialogue event and subtitle burning enabled
- **When** video engine constructs the FFmpeg filtergraph
- **Then** `has_active_subtitles(path)` MUST evaluate to `True`
- **And** the engine MUST include the escaped subtitle filter and perform video transcoding with `libass`.

#### Scenario: None or empty subtitle path provided to engine (Edge Case)
- **Given** a subtitle path parameter that is `None`, empty string, or points to a non-existent file
- **When** video engine evaluates subtitle eligibility
- **Then** `has_active_subtitles(path)` MUST return `False` without raising an exception
- **And** the engine MUST omit subtitle filters and maintain stream-copy eligibility.
