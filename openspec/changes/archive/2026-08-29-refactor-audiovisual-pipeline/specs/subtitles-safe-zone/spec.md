# Delta Specification: Subtitles Safe Zone

## Capability Overview
The `subtitles-safe-zone` capability specifies Advanced SubStation Alpha (.ass) subtitle generation, safe-zone positioning rules, and karaoke timing chunking to guarantee visibility without overlapping YouTube Shorts bottom interactive UI controls.

## Modified Requirements

### Requirement 1: Vertical Safe-Zone Boundary Floor for Shorts
For 9:16 portrait video formats ($1080\times 1920$), subtitle styling headers MUST configure bottom vertical margin $MarginV \ge 480\text{px}$ (at least $25\%$ of canvas height) to completely clear the 450px bottom UI danger zone of mobile video players.

#### Scenario: Generation of portrait ASS subtitles with safe vertical margin (Happy Path)
- **Given** a video canvas with dimensions $width=1080$ and $height=1920$
- **When** `TerminalKaraokeSubtitleGenerator.generate_ass` builds the style header
- **Then** the `Style` definition MUST set $MarginV \ge 480$
- **And** subtitle lines MUST render vertically above the 450px mobile UI overlay zone.

#### Scenario: Subtitle generation for landscape aspect ratio (Edge Case)
- **Given** a horizontal video canvas with dimensions $width=1920$ and $height=1080$
- **When** subtitle header generation is invoked
- **Then** $MarginV$ MUST scale proportionally to landscape standard ($\approx 12\%$ of height, minimum 130px)
- **And** font size MUST scale according to horizontal resolution.

### Requirement 2: High-Impact Word-Level Karaoke Cue Grouping
Subtitle generators MUST group word timestamps into short, high-impact cues containing between 2 and 4 words (default 3 words), synchronizing word highlights via ASS `\k` centisecond tags.

#### Scenario: Grouping sentence words into 3-word karaoke cues (Happy Path)
- **Given** a sequence of 9 timestamped words spanning 4.5 seconds
- **When** cue grouping executes with `max_words=3`
- **Then** the generator MUST produce exactly 3 distinct subtitle event dialogue lines
- **And** each dialogue line MUST format each constituent word with `{\k<centiseconds>}` highlighting tags.

#### Scenario: Single trailing word or minimal duration cue (Edge Case)
- **Given** a final remaining word with duration 0.05 seconds
- **When** cue grouping executes
- **Then** the cue end time MUST be padded to ensure a minimum display duration of at least 0.10 seconds
- **And** centisecond tag `\k` MUST be set to at least 1 centisecond.

## Added Requirements

### Requirement 3: Horizontal Margin and Collision Prevention
Subtitle generators MUST maintain horizontal boundaries ($MarginL \ge 40\text{px}$ and $MarginR \ge 40\text{px}$) and ensure sequential cues do not exhibit overlapping temporal intervals.

#### Scenario: Sequential cues with adjacent timestamps (Happy Path)
- **Given** two sequential subtitle cues where cue 1 ends at $t=3.20\text{s}$ and cue 2 starts at $t=3.20\text{s}$
- **When** ASS dialogue events are written
- **Then** start and end timestamps MUST be non-overlapping ($end_1 \le start_2$).

#### Scenario: Inverted or overlapping input timestamps from whisper/STT (Edge Case)
- **Given** raw input word timestamps where word 2 start time is earlier than word 1 start time
- **When** cue normalization executes
- **Then** the generator MUST sanitize start and end values such that $end \ge start + 0.05\text{s}$
- **And** all timestamp strings MUST format to valid ASS timestamp format `H:MM:SS.cs`.
