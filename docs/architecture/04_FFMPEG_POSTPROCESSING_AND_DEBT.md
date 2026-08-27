# Master FFmpeg Postprocessing, Broadcast Audio Mastering & Technical Debt Inventory

**Document ID:** `ARCH-M4-FFMPEG-AUDIO-DEBT-2026`  
**Milestone:** M4 (Master FFmpeg Postprocessing Pipeline & Technical Debt Inventory)  
**System Target:** `yt-auto` (Premium Multi-Lane Dual-Engine Video Production Platform)  
**Assurance Level:** High-Assurance / Deterministic / Broadcast-Grade  

---

## 1. Executive Summary & Encoding Architecture

The master postprocessing pipeline serves as the final rendering and mastering stage of `yt-auto`. Its primary architectural goal is to synthesize multi-scene video buffers (from both the Hybrid Cinematic and Procedural WebGL engines) and multi-track audio streams (narration, ambient music, SFX) into a broadcast-standard Full HD (1080p) MP4 master file with zero visible compression artifacts, zero color banding in deep dark gradients, and perfect vocal clarity governed by EBU R128 broadcast loudness standards.

```
                               MASTER FFMPEG PIPELINE TOPOLOGY
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ INPUT VIDEO STREAMS (SCENE BUFFERS)                                                    │
 │ Scene 01 (Hybrid AI) ──┐                                                               │
 │ Scene 02 (Procedural) ─┼──► [xfade filters] ──► [deband] ──► [scale:lanczos] ──► [v_out] │
 │ Scene 03 (Hybrid AI) ──┘                                                               │
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ INPUT AUDIO STREAMS (MULTI-TRACK PCM)                                                  │
 │ Voice Narration (Edge-TTS) ──┬────────────────────────────────────────────────────────┤
 │ Ambient Horror Music ────────┴──► [sidechaincompress] ──► [amix] ──► [loudnorm] ──► [a_out]
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ MASTER COMPOSITION & BROADCAST CONTAINER ENCODING                                      │
 │ - Video: libx264 / libx265, CRF 18-20, preset slow, Rec.709 color matrix, yuv420p     │
 │ - Audio: AAC Stereo 384 kbps, 48000 Hz, EBU R128 (-14 LUFS, -1.5 dBTP, LRA 11)         │
 │ - Muxing: MP4 container with +faststart (moov atom placed before mdat)                 │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Visually Lossless CRF 18–20 Master Encoding Pipeline

### 2.1 Video Compression & Rate Control Standards
To guarantee pristine visual quality on modern high-DPI and OLED displays, the encoder configuration replaces legacy `ultrafast`/`veryfast` CRF 24 presets with a mathematically optimized multi-pass / slow single-pass rate control graph:

- **Target Container:** ISO/IEC 14496-14 (MP4) with `-movflags +faststart` for zero-buffering web playback.
- **Primary Codec:** `libx264` (Advanced Video Coding, High Profile, Level 4.2).
- **Secondary / Archival Codec:** `libx265` (High Efficiency Video Coding, Main 10 Profile, 10-bit color depth).
- **Rate Control Mode:** Constant Rate Factor (`CRF`):
  * **Longform (16:9 Landscape - 1920x1080):** `CRF 18` (Visually lossless baseline).
  * **Shortform (9:16 Vertical - 1080x1920):** `CRF 19` (Optimal balance of mobile bandwidth and visual sharpness).
- **Encoding Preset:** `slow` (Activates multi-frame motion estimation `hex`/`umh`, subpixel refinement `subme=8`, and adaptive B-frame placement `b-adapt=2`).
- **GOP Structure:** Fixed closed GOP of 2 seconds (`g=60` at 30 fps, `g=120` at 60 fps) with `keyint_min=30` and `sc_threshold=0` for deterministic seeking.

### 2.2 Studio Rec.709 Color Matrix Configuration
Color representation must strictly adhere to ITU-R Recommendation BT.709-6 standards to prevent color space conversion shifts between browser decoders and native video players:

```bash
-color_primaries bt709 \
-color_trc bt709 \
-colorspace bt709 \
-color_range tv \
-pix_fmt yuv420p
```

---

## 3. High-Precision 36-Tap Lanczos Geometry & Chroma Rescaling

### 3.1 Scaling Algorithm Selection
When scaling procedural HTML5 Canvas buffers, WebGL framebuffer outputs, or AI-generated mattes to canonical resolutions (1920x1080 or 1080x1920), simple bilinear or nearest-neighbor filtering introduces aliasing, texture blurring, or jagged diagonal edges. The platform mandates **36-Tap Lanczos Resampling** (`flags=lanczos` with sinc kernel windowing):

$$\text{Lanczos}(x) = \begin{cases} \text{sinc}(x) \cdot \text{sinc}(x / a) & \text{for } -a \le x \le a \\ 0 & \text{otherwise} \end{cases} \quad \text{where } a = 3$$

### 3.2 Chroma Subsampling & Color Plane Alignment
Chrominance components ($U, V$) are resampled with full phase accuracy to prevent color bleeding on red/amber alarm strobes in SCP or Creepypasta scenes:

```bash
# Longform (16:9):
-vf "scale=1920:1080:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p"

# Shortform (9:16):
-vf "scale=1080:1920:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p"
```

---

## 4. De-Banding & Gradient Smoothing Filter Graph

### 4.1 Root Cause of Color Banding in Dark Horror Gradients
In deep atmospheric horror visuals, pixel luminance frequently hovers between $Y=16$ (studio black) and $Y=45$ (shadow floor). In standard 8-bit color spaces ($2^8 = 256$ levels per channel), subtle atmospheric fog and volumetric light rays suffer from discrete quantization steps ("banding rings" or posterization).

### 4.2 FFmpeg De-Band Pre-Conditioning Filter Graph
The postprocessing pipeline applies an adaptive pre-conditioning `deband` filter before encoder quantization. This algorithm samples neighboring pixels in a 16-pixel radius, detects planar stepping, and injects micro-dithering that blends seamlessly under H.264 entropy coding:

```bash
# Adaptive Deband Filter Configuration:
deband=1:range=16:direction=0:blur=true:threshold=0.03
```

- **`range=16`:** Samples up to 16 pixels away to resolve wide, gradual gradient transitions.
- **`threshold=0.03`:** Limits debanding to subtle gradient steps while preserving hard object boundaries, silhouettes, and text contours.
- **`blur=true`:** Applies smooth bilinear interpolation across detected banding zones.

---

## 5. EBU R128 Broadcast Audio Mastering & Dynamic Sidechain Ducking

### 5.1 EBU R128 / ITU-R BS.1770 Broadcast Standards
Audio tracks must strictly comply with international broadcast loudness regulations:

| Acoustic Parameter | Standard Value | Strict Acceptance Window | Downstream Gate Action |
|---|---|---|---|
| **Integrated Loudness ($I$)** | **$-14.0\text{ LUFS}$** | $[-15.5, -12.5]\text{ LUFS}$ | Rejects master if $|I - (-14.0)| > 1.5$ |
| **True Peak Ceiling ($\text{TP}$)** | **$-1.5\text{ dBTP}$** | $\le -1.0\text{ dBTP}$ | Rejects master if $\text{TP} > -1.0\text{ dBTP}$ |
| **Loudness Range ($\text{LRA}$)** | **$11.0\text{ LU}$** | $[6.0, 14.0]\text{ LU}$ | Flags warning if $\text{LRA} > 14.0$ |
| **Maximum Short-Term ($S_{\text{max}}$)** | **$-10.0\text{ LUFS}$** | $\le -8.0\text{ LUFS}$ | Rejects if ear-fatiguing blast occurs |
| **Stereo Phase Correlation ($\rho$)** | **$\ge +0.20$** | $[+0.20, +1.00]$ | Rejects if destructive mono cancellation |

### 5.2 Dynamic Sidechain Compression Ducking
To ensure 100% vocal intelligibility while preserving the terrifying atmospheric presence of background music and ambient drones, the pipeline implements real-time **Sidechain Compression Ducking**:

$$\text{Gain Reduction (dB)} = -18.0\text{ dB during active speech}$$

- **Threshold:** `0.08` (Detects vocal presence immediately above the ambient noise floor).
- **Ratio:** `6:1` (Deep gain attenuation for ambient bed).
- **Attack Time:** `20ms` (Rapid response to first consonant onset; zero audible pumping).
- **Release Time:** `350ms` (Smooth, imperceptible swell back to ambient baseline during pauses).

### 5.3 Complete Audio Mastering Filter Graph

```
 [Narration Voice] ─────┬─────────────────────────────────────────────────────────────┐
                        │ Control Signal                                              │
                        ▼                                                             │
 [Ambient Music]   ──► [sidechaincompress (duck -18dB)] ──► [Ducked Music] ─────────┐ │
                                                                                     ▼ ▼
                                                                             [amix (inputs=2)]
                                                                                     │
                                                                                     ▼
                                                                     [loudnorm (I=-14, TP=-1.5, LRA=11)]
                                                                                     │
                                                                                     ▼
                                                                             [Master Audio AAC]
```

---

## 6. End-to-End Master FFmpeg Execution Command

The complete, canonical FFmpeg command line synthesized by the pipeline for a multi-scene longform production is formulated as follows:

```bash
ffmpeg -y \
  -i scene_001.mp4 \
  -i scene_002.mp4 \
  -i scene_003.mp4 \
  -i narration.wav \
  -i horror_ambient.mp3 \
  -filter_complex "\
    [0:v][1:v] xfade=transition=fade:duration=1.5:offset=58.5 [v_xfade1]; \
    [v_xfade1][2:v] xfade=transition=fade:duration=1.5:offset=118.5 [v_xfade2]; \
    [v_xfade2] deband=1:range=16:threshold=0.03:blur=true, \
               scale=1920:1080:flags=lanczos+accurate_rnd+full_chroma_int, \
               format=yuv420p [v_master]; \
    [4:a][3:a] sidechaincompress=threshold=0.08:ratio=6:attack=20:release=350 [a_ducked_music]; \
    [3:a][a_ducked_music] amix=inputs=2:duration=first:dropout_transition=2 [a_mixed]; \
    [a_mixed] loudnorm=I=-14.0:TP=-1.5:LRA=11.0:measured_I=-14.2:measured_TP=-1.6:measured_LRA=10.8:measured_thresh=-24.5:offset=0.2:print_format=json [a_master] \
  " \
  -map "[v_master]" \
  -map "[a_master]" \
  -c:v libx264 \
  -preset slow \
  -crf 18 \
  -color_primaries bt709 \
  -color_trc bt709 \
  -colorspace bt709 \
  -color_range tv \
  -c:a aac \
  -b:a 384k \
  -ar 48000 \
  -ac 2 \
  -movflags +faststart \
  output/master_render.mp4
```

---

## 7. Taxative Legacy Technical Debt Inventory

This section establishes the definitive, binding classification of codebase modules, configuration parameters, and asset banks into **Deprecated / Discarded Legacy Debt** vs. **Core Architectural Modules to Preserve & Modernize**.

### 7.1 Deprecated / Discarded Legacy Components (To Be Removed / Replaced)

| # | File / Component | Specific Location | Nature of Technical Debt | Remediation / Modernized Replacement |
|---|---|---|---|---|
| **D-1** | **Monolithic Single-Loop Path** | `src/pipeline.py` (lines 703–786) | Hard-forces a single repeating background loop for entire video; raises `RuntimeError` if multi-image path requested. Causes severe visual monotony in 10+ min videos. | Replaced by `ScenePlanner` and `MultiSceneOrchestrator` segmenting videos into 45–90s dynamic environments. |
| **D-2** | **Obsolete 768p Asset Metadata** | `assets/visual_bank/index.json` | Contains legacy prototype resolution tags `[768, 1360]` and low-quality static JPEG tags. Scaling 768p to 1080p introduces blurriness. | Deprecate 768p entries; upgrade visual bank to native 1080p/4K cinematic assets indexed by theme lane and lighting Kelvin. |
| **D-3** | **Broken SceneAssetTracker Stub** | `src/visuals/scene_asset_tracker.py` | Stubbed out to a dummy class returning `0`, causing import errors in `tests/unit/test_scene_asset_tracker.py`. | Implement type-safe scene tracking in `src/visuals/` integrated directly with `scene_manifest.json`. |
| **D-4** | **Static 2D Pillow Overlay Baker** | `lib/video.py` | Bakes static 2D vignette/grain PNGs (`dark_vignette.png`, `film_grain.png`) via Pillow with simple bicubic fit, causing color banding in dark gradients. | Replace with real-time FFmpeg / GLSL post-processing shaders with Rec.709 color profiles and adaptive deband filters. |
| **D-5** | **Scattered Heuristic Sanitizers** | `src/llm.py`, `src/sanitizer.py`, `src/script_repair.py` | Multiple ad-hoc regex passes and prompt leak filters spread across disparate modules without unified schema validation. | Consolidate into strict, contract-driven Pydantic and JSON schemas within the `CinematicScriptCurator` interface. |
| **D-6** | **Low-Quality Encoder Presets** | `lib/video.py`, `src/media/loop_video_engine.py` | Defaults to `preset="veryfast"` or `preset="ultrafast"` with `crf=23` or `crf=24`, introducing macroblocking in dark scenes. | Upgrade all encoding pipelines to `preset="slow"`, `crf=18-20`, and Rec.709 color matrix. |
| **D-7** | **Superfluous Scratch Scripts** | `scripts/render_cosmic_lighthouse.py`, `docs/archive/` | Unmaintained one-off scripts and obsolete architecture notes that cause developer confusion. | Relocate one-off scripts to test harnesses and archive legacy documentation. |

---

### 7.2 Core Architectural Modules to Preserve & Modernize

| # | Module / Subsystem | Current File Paths | Architectural Value & Capabilities | Modernization & Upgrade Plan |
|---|---|---|---|---|
| **P-1** | **Transactional SQLite Queue & Repository** | `src/core/repository.py`, `src/db.py` | SQLite WAL mode, atomic `lane_leases`, foreign key integrity, 64-bit SimHash deduplication, checkpoint resumption. | Add multi-scene asset lineage tracking (`scene_assets` table), per-act tension indexing, and dual-engine telemetry logs. |
| **P-2** | **Multi-Lane Channel Resolver** | `src/core/lanes.py`, `config/lanes.json` | Resolves lane profiles (`moku-horror-long`, `moku-scp-shorts`, `aelithia-aita-long`) and cadence schedules. | Extend schema to include dynamic scene transition cadences (45–90s targets) and visual mood profile tags. |
| **P-3** | **Procedural Web Video Renderer** | `src/media/web_video_renderer.py`, `src/media/web_templates/` | Playwright Headless Chromium frame capture piping WebGL/Three.js/Canvas generative templates into FFmpeg. | Enhance virtual-time synchronization for 1080p/4K 60fps rendering and expand template shaders. |
| **P-4** | **SQLite Procedural Loop Catalog** | `src/core/loop_catalog.py`, `src/media/loop_synthesizer_worker.py` | Autonomous buffer maintainer, usage count tracking, and background pre-rendering of procedural loops. | Upgrade to support multi-seed procedural generation at native 1080p/4K tagged with strict color matrices. |
| **P-5** | **Single-Pass 9-Gate Quality Engine** | `lib/qa/` (`engine.py`, `gates.py`, `models.py`) | Modular 9-gate verification (Container, Audio LUFS/TP, Visual Resolution/FPS, Subtitles, ROI). | Update `SceneCadenceGate` to enforce 45–90s dynamic scene shifts and integrate with Agent 4 (`VisualAudioQAAuditor`). |
| **P-6** | **Neural TTS & Audio Post-Processing** | `lib/tts.py`, `src/tts.py`, `config/voice_profiles.json` | Edge-TTS synthesis, multi-voice rotation profiles, EBU R128 master voice pre-conditioning. | Expose fine-grained emotion/pacing markers corresponding to narrative tension levels (1–5). |
| **P-7** | **Karaoke Subtitle Generator** | `src/subtitles.py`, `lib/subtitles.py`, `assets/fonts/` | ASS / SRT generation with safe area compliance (`MarginV 240-250`), font vendoring (`Montserrat-Black.ttf`). | Support adaptive dynamic styling for dramatic beats and multi-speaker dialogues (e.g. in AITA drama lane). |
| **P-8** | **Crom API & Reddit Scrapers** | `src/scraper_scp.py`, `src/scraper.py` | SCP Foundation Wiki / Crom API scraper with CC BY-SA 3.0 attribution; Reddit multi-source scraper with category rotation. | Preserve CC BY-SA 3.0 legal attribution; capture incident logs and dialogue segments for multi-act pacing. |
| **P-9** | **Automated Code Review & Telegram Gate** | `src/core/code_review_verdict.py`, `review/` | Dual review paths: deterministic automated `CodeReviewVerdict` + Telegram interactive approval fallback. | Add multi-scene keyframe preview grids and contact sheet inspection to review payloads. |
| **P-10** | **Cloud & Platform Uploaders** | `src/drive.py`, `src/youtube_uploader.py` | Google Drive v3 verified upload with SHA-256 proofs and YouTube Data API v3 uploader with OAuth token refresh. | Maintain idempotent upload proofs and retry safety. |
