# Delta Specification: Subtitles Safe Zone

## Capability Overview
The `subtitles-safe-zone` capability specifies Advanced SubStation Alpha (.ass) subtitle generation, safe-zone positioning rules, and karaoke timing chunking. This delta binds scene-level ASS subtitle positioning ($MarginV \ge 480\text{px}$) dynamically to 2.5D camera drift transformations, multi-scene resolution boundaries, and dynamic Rec.709 color grade burning.

## Modified Requirements

### Requirement 1: Dynamic Camera Drift Bound Vertical Safe-Zone for Shorts
For 9:16 portrait video formats ($1080\times 1920$), subtitle styling headers MUST configure bottom vertical margin $MarginV \ge 480\text{px}$ (at least $25\%$ of canvas height) to completely clear the 450px bottom UI danger zone of mobile video players. When procedural 2.5D camera drift or vertical tilt is active, the generator MUST compensate margin offsets such that subtitle text lines remain strictly contained above the 450px UI overlay floor regardless of camera translation.

#### Scenario: Generation of portrait ASS subtitles with safe vertical margin under camera drift (Happy Path)
- **Given** a 9:16 video canvas ($1080\times 1920$) with active 2.5D downward camera drift ($\Delta y = +30\text{px}$)
- **When** `ASSSubtitleGenerator` (`src/media/subtitles_ass.py`) builds the style header
- **Then** the `Style` definition MUST set $MarginV \ge 480$ (scaled to $\ge 510\text{px}$ with camera drift compensation)
- **And** rendered subtitle lines MUST remain fully visible strictly above the 450px mobile UI danger zone.

#### Scenario: Subtitle generation for landscape aspect ratio with camera zoom (Edge Case)
- **Given** a horizontal video canvas ($1920\times 1080$) with dynamic camera zoom ramp ($s = 1.15$)
- **When** subtitle header generation is invoked
- **Then** $MarginV$ MUST scale proportionally to landscape standard ($\approx 12\%$ of height, minimum 130px)
- **And** font scaling MUST maintain readability without exceeding canvas boundaries.

### Requirement 3: Multi-Scene Resolution Boundary and Horizontal Safe Margin Binding
Subtitle generators MUST maintain horizontal boundaries ($MarginL \ge 40\text{px}$ and $MarginR \ge 40\text{px}$), enforce non-overlapping temporal intervals across sequential cues, and bind text wrapping to active scene resolution boundaries across multi-act scene transitions.

#### Scenario: Sequential cues with adjacent timestamps across scene transitions (Happy Path)
- **Given** two sequential subtitle cues where cue 1 ends at $t = 8.50\text{s}$ (Scene 1 end) and cue 2 starts at $t = 8.50\text{s}$ (Scene 2 start)
- **When** ASS dialogue events are compiled across scene boundaries
- **Then** start and end timestamps MUST be non-overlapping ($end_1 \le start_2$)
- **And** text alignment and margin constraints MUST remain consistent across the scene transition.

#### Scenario: Inverted or overlapping input timestamps from STT/alignment models (Edge Case)
- **Given** raw input word timestamps where word 2 start time is earlier than word 1 start time
- **When** cue normalization executes
- **Then** the generator MUST sanitize start and end values such that $end \ge start + 0.05\text{s}$
- **And** all timestamp strings MUST format to valid ASS timestamp format `H:MM:SS.cs`.

## Added Requirements

### Requirement 4: Per-Scene Dynamic Color Palette Subtitle Burning
Subtitle generators MUST accept dynamic color palette configurations from the narrative Rec.709 color grade, setting primary text color, high-contrast dark outline (`BorderStyle=1`, `Outline=3`, `OutlineColour=&H00000000`), and accent highlight colors on active karaoke words (`\k` tags) to ensure readability across dark, glowing, or high-luminance procedural shader backgrounds.

#### Scenario: Subtitles styled with theme-aligned Rec.709 highlight palette (Happy Path)
- **Given** a scene with a green terminal aesthetic (theme `"scp_foundation"`, accent color `#00FF66`)
- **When** the subtitle generator renders ASS styles for the scene
- **Then** the primary text and karaoke highlight tags MUST incorporate the `#00FF66` color code in ASS hex format (`&H0066FF00`)
- **And** the outline MUST provide high contrast against the background shader.

#### Scenario: High-luminance or noisy background shader overlay (Edge Case)
- **Given** a scene containing bright explosion flashes or high-luminance particle shaders
- **When** subtitle styling is compiled
- **Then** the generator MUST enforce an opaque bounding shadow or high-density outline ($Outline \ge 3$)
- **And** the subtitle text MUST retain a minimum contrast ratio $\ge 4.5:1$ against the background.
