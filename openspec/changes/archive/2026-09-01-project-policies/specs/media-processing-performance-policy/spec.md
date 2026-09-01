# Spec: Media Processing and Performance Policy

## Requirement: Volatile RAM-Based Audio Temp Storage (`/dev/shm`)
Intermediate audio files, silence chunks, and dramatic pause concatenation buffers MUST be allocated in `/dev/shm` (or OS temp directory fallback) to prevent unnecessary SSD I/O wear and reduce latency during TTS processing.

### Scenario: RAM Temp Directory Resolution
- **Given** a Linux host with a writable `/dev/shm` filesystem
- **When** `_get_ram_temp_dir()` is invoked during audio generation
- **Then** the returned directory path MUST reside inside `/dev/shm/yt_auto_audio`
- **And** all intermediate chunk files MUST be deleted from RAM immediately after concatenation.

## Requirement: Single-Pass FFmpeg Audio Mastering
Audio mastering MUST execute in a single consolidated FFmpeg `filter_complex` pass combining voice highpass/lowpass equalization, sidechain ducking under background music, and EBU R128 loudness normalization (Integrated Loudness $I=-14.0\text{ LUFS}$, True Peak $TP=-1.5\text{ dBTP}$, Loudness Range $LRA=11.0$). Double-pass disk renders are strictly prohibited.

### Scenario: Single-Pass Mastering Execution
- **Given** narration speech WAV and background music MP3 inputs
- **When** `master_audio_track` runs
- **Then** FFmpeg MUST emit a stereo 48 kHz master audio file in a single execution pass.

## Requirement: Dynamic Pillow Subtitle Geometry and Safe Area
Subtitles generated for 9:16 vertical Shorts MUST respect the bottom UI Safe Area ($MarginV \ge 260\text{px}$) and utilize dynamic Pillow font metrics (`font.getlength`) to split and wrap text with `\N` whenever rendered cue width exceeds 960 pixels on a 1080x1920 canvas.

### Scenario: Long Spanish Text Auto-Wrapping
- **Given** a subtitle cue with long Spanish phrasing
- **When** `create_ass_subtitles` renders ASS event lines
- **Then** Pillow bounding box measurement MUST detect width exceeding 960px
- **And** insert `\N` linebreaks so text remains centered and completely within safe viewing boundaries.
