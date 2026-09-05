# Delta Specification: Subtitles Safe Zone

## MODIFIED Requirements

### Requirement: Multi-Scene Resolution Boundary and Horizontal Safe Margin Binding
(Previously: MarginL >= 40px and MarginR >= 40px static across all resolutions)
Subtitle generators MUST maintain horizontal boundaries based on canvas aspect ratio: in 9:16 portrait ($1080\times 1920$), MarginR MUST be $\ge 130\text{px}$ (or $\ge 12\%$ canvas width) to clear the right mobile UI interaction rail, and MarginL MUST be $\ge 64\text{px}$ (or $\ge 6\%$ canvas width). In 16:9 landscape ($1920\times 1080$), MarginL and MarginR MUST both be $\ge 40\text{px}$. Generators MUST enforce non-overlapping temporal intervals across sequential cues and bind text wrapping to active scene resolution boundaries across multi-act scene transitions.

#### Scenario: Portrait subtitle horizontal safe margins (Happy Path)
- **Given** a 9:16 portrait canvas ($1080\times 1920$) with sequential subtitle cues across scenes
- **When** ASS dialogue events and style headers are compiled
- **Then** start and end timestamps MUST be non-overlapping ($end_1 \le start_2$)
- **And** the style definition MUST set $MarginR \ge 130\text{px}$ and $MarginL \ge 64\text{px}$ to clear right UI action buttons.

#### Scenario: Landscape subtitle horizontal safe margins (Happy Path)
- **Given** a 16:9 landscape canvas ($1920\times 1080$)
- **When** ASS subtitle style header is generated
- **Then** $MarginL$ and $MarginR$ MUST both be $\ge 40\text{px}$
- **And** text alignment and margin constraints MUST remain consistent across scene transitions.

#### Scenario: Inverted or overlapping input timestamps (Edge Case)
- **Given** raw input word timestamps where word 2 start time is earlier than word 1 start time
- **When** cue normalization executes
- **Then** the generator MUST sanitize start and end values such that $end \ge start + 0.05\text{s}$
- **And** all timestamp strings MUST format to valid ASS timestamp format `H:MM:SS.cs`.

## ADDED Requirements

### Requirement: Adaptive Font Sizing and Word Chunking
Subtitle font size MUST scale adaptively with canvas height: setting a base of $52\text{px}$ for $1920\text{px}$ vertical height and a base of $38\text{px}$ for $1080\text{px}$ horizontal height, proportional to canvas dimensions without causing horizontal overflow. Cues SHOULD chunk sequential narration words into groups of $\le 3$ words.

#### Scenario: Adaptive font sizing across orientations (Happy Path)
- **Given** narration transcript words for subtitle generation
- **When** `ASSSubtitleGenerator` computes style metrics for $1080\times 1920$ portrait or $1920\times 1080$ landscape
- **Then** `Fontsize` MUST scale to $52\text{px}$ at $1920\text{px}$ vertical height and $38\text{px}$ at $1080\text{px}$ horizontal height
- **And** cues SHOULD chunk words into $\le 3$ words per event.

#### Scenario: Boundary containment with long cue words (Edge Case)
- **Given** a subtitle cue with long phrasing in a 9:16 portrait canvas
- **When** cue layout is computed
- **Then** chunking MUST limit the cue to $\le 3$ words
- **And** rendered text width MUST not exceed printable width ($1080 - 130 - 64 = 886\text{px}$).

### Requirement: Subtitle File Dialogue Validation Sentinel
A validation function `has_active_subtitles(path)` MUST return `True` ONLY if the path exists, is a regular file, has size $> 0$ bytes, and contains $\ge 1$ valid non-whitespace `Dialogue:` event. Otherwise, it MUST return `False`.

#### Scenario: Subtitle file with active dialogue events (Happy Path)
- **Given** an ASS file on disk with valid headers and $\ge 1$ non-whitespace `Dialogue:` event
- **When** `has_active_subtitles(path)` is evaluated
- **Then** the function MUST return `True`.

#### Scenario: Missing, empty, or dialogue-free subtitle file (Edge Case)
- **Given** a path that is `None`, non-existent, 0 bytes, or containing only headers without `Dialogue:` lines
- **When** `has_active_subtitles(path)` is evaluated
- **Then** the function MUST return `False` without raising exceptions.
