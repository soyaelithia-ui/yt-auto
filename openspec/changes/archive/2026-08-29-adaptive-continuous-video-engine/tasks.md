# Tasks: Adaptive Continuous Multi-Scene Video Engine

## Review Workload Forecast
- **400-line budget risk**: High (~1,100 lines added/modified across 16 modules, ~180 lines refactored).
- **Chained PRs recommended**: Yes (split into 3 sequential PRs to maintain review velocity and component isolation).
- **Chain strategy**:
  - **PR 1 (Foundations & Narrative)**: Phases 1 & 2 (Test suites + Narrative schemas, 5-phase tension curve & curation layer).
  - **PR 2 (Visuals & Subtitles)**: Phase 3 (Procedural WebGL visual compositing, 2.5D camera drift & ASS safe-zone subtitles).
  - **PR 3 (Audio, Daemon & E2E)**: Phases 4 & 5 (Tension audio mastering, subprocess watchdog, continuous daemon lifecycle & E2E verification).
- **Decision needed before apply**: None (all interfaces, schemas, and mathematical bounds are strictly typed and backwards-compatible behind `CONTINUOUS_ENGINE_V2`).

## Suggested Work Units
| Unit | Phase | Description | Target Files | Est. Diff |
| :--- | :--- | :--- | :--- | :--- |
| **U1** | 1 | Author RED unit tests for narrative tension scoring, WPM segmentation, and Rec.709 palette mapping | `tests/unit/test_narrative_tension_rec709.py` | +180 / -0 |
| **U2** | 1 | Author RED unit tests for 2.5D camera drift, fallback shaders, `xfade` transitions, and ASS subtitle safe-zones | `tests/unit/test_procedural_compositor_subtitles.py` | +190 / -0 |
| **U3** | 1 | Author RED unit tests for -18 dB sidechain ducking, EBU R128 mastering, tension drone, and subprocess watchdog | `tests/unit/test_audio_master_watchdog.py` | +210 / -0 |
| **U4** | 1 | Author RED unit tests for 64-bit SimHash dedup, semaphore concurrency, and 5 GB disk guard | `tests/unit/test_continuous_daemon_guard.py` | +200 / -0 |
| **U5** | 2 | Implement narrative schemas, 5-phase tension engine, and topic-agnostic curation agents | `src/narrative/schema.py`<br>`src/narrative/archetypes.py`<br>`src/narrative/engine.py`<br>`src/agents/script_curator.py`<br>`src/agents/art_director.py`<br>`src/agents/scene_planner.py` | +320 / -40 |
| **U6** | 3 | Implement 2.5D camera drift, dynamic GLSL uniforms, stream isolation, and dynamic ASS safe-zone subtitles | `src/rendering/camera_controller.py`<br>`src/rendering/renderer.py`<br>`src/media/proc_engine.py`<br>`src/media/web_renderer.py`<br>`src/media/compositor.py`<br>`src/media/multi_act_renderer.py`<br>`src/media/subtitles.py`<br>`lib/subtitles.py`<br>`src/compositing/subtitles.py` | +380 / -70 |
| **U7** | 4 | Implement tension drone modulation, SFX cues, -18 dB sidechain ducking, EBU R128 loudnorm & watchdog | `src/audio/procedural_drone.py`<br>`src/audio/sfx_library.py`<br>`src/audio/mixer.py`<br>`src/audio_processor.py`<br>`src/media/procedural_audio.py`<br>`lib/ffmpeg.py` | +280 / -50 |
| **U8** | 5 | Implement `CONTINUOUS_ENGINE_V2` config, 64-bit SimHash dedup, bounded semaphore, and post-render disk guard | `src/daemon.py`<br>`src/cleaner.py`<br>`src/config.py` | +240 / -30 |
| **U9** | 5 | Implement end-to-end pipeline verification test harness and validate full test suite | `tests/e2e/test_continuous_engine_e2e.py`<br>full test harness | +150 / -0 |

---

## Phase 1: Test Infrastructure & RED Test Suites

- [x] 1.1 [TDD-RED] Create `tests/unit/test_narrative_tension_rec709.py` covering:
  - 5-Phase tension curve scoring ($T \in [1, 5]$: baseline 1–2, anomaly 2–3, escalation 3–4, climax 5, loop hook 2–3).
  - Monotonic tension smoothing and clamping for erratic/inverted input scores.
  - Semantic scene duration bounds ($8.0\text{s} \le t \le 15.0\text{s}$ at 150–175 WPM) and orphan clause merging.
  - Rec.709 color palette generation, Kelvin temperature calibration ($3000\text{K} \le K \le 7000\text{K}$), and `schemas/art_director.schema.json` compliance.
- [x] 1.2 [TDD-RED] Create `tests/unit/test_procedural_compositor_subtitles.py` covering:
  - 2.5D camera drift transform calculations ($dx, dy \le 8\%$, roll $\le 1.5^\circ$, zoom $[1.00, 1.15]$) with canvas boundary clamping.
  - Fallback procedural shader activation (`"MONOLITHS_RAYMARCHING"`) upon GLSL compilation error.
  - Seamless `xfade` filtergraph generation, transition duration clamping ($\le 30\%$ adjacent act duration), and zero dropped frames.
  - ASS subtitle vertical margin positioning ($MarginV \ge 480\text{px}$ portrait, $\ge 130\text{px}$ landscape, scaled $\ge 510\text{px}$ with downward camera drift).
  - Dynamic Rec.709 color grade text and karaoke highlight (`\k`) burning with dark high-contrast outline ($Outline \ge 3$).
- [x] 1.3 [TDD-RED] Create `tests/unit/test_audio_master_watchdog.py` covering:
  - Dynamic sidechain ducking filter string generation ($-18\text{ dB}$ vocal attenuation, ratio $\ge 5:1$, attack $10\text{–}20\text{ms}$, release $250\text{–}400\text{ms}$).
  - Broadcast EBU R128 loudness normalization ($I = -14.0 \pm 0.5\text{ LUFS}$, $TP \le -1.5\text{ dBTP}$, $LRA \le 11.0\text{ LU}$).
  - Tension-coupled procedural drone frequency modulation ($28\text{Hz} \le f_0 \le 65\text{Hz}$) and click-free crossfade transitions.
  - Millisecond-accurate SFX insertion (`adelay`, `amix`) with procedural synthesis fallback for unknown cues.
  - `SubprocessWatchdog` process group monitoring, RSS memory limit enforcement ($\le 4.0\text{ GB}$), and 180s timeout `SIGKILL`.
- [x] 1.4 [TDD-RED] Create `tests/unit/test_continuous_daemon_guard.py` covering:
  - 64-bit token/bigram SimHash calculation and duplicate rejection ($Hamming < 4$ rejected against rolling history $\ge 100$).
  - Bounded concurrency semaphore ($N = 1$ heavy render, $N \le 2$ light synthesis).
  - Immediate post-render scratch sweep in `finally` blocks for `work/` artifacts.
  - Free disk space watermark guard ($5.0\text{ GB}$) pausing queue processing.
  - Continuous daemon autonomous heartbeat loop, exponential backoff with jitter on transient failures, and graceful `SIGINT`/`SIGTERM` shutdown.

---

## Phase 2: Narrative & Semantic Curation Layer (GREEN)

- [x] 2.1 [TDD-GREEN] Extend `src/narrative/schema.py` with `TensionLevel` (1–5), `Rec709Palette` (primary, secondary, accent, shadow, highlight, kelvin, lut_profile), `CameraTransform`, and `SceneContractV2`.
- [x] 2.2 [TDD-GREEN] Update `src/narrative/archetypes.py` to add open-domain archetype mappings, tension progression presets, and Rec.709 palette tables.
- [x] 2.3 [TDD-GREEN] Implement 5-phase tension scoring, monotonic smoothing, and WPM scene segmentation ($8.0\text{s} \le t \le 15.0\text{s}$) with orphan merging in `src/narrative/engine.py`.
- [x] 2.4 [TDD-GREEN] Refactor `src/agents/script_curator.py` to support topic-agnostic curation, dynamic archetype routing, and fallback to canonical archetypes on empty/malformed inputs.
- [x] 2.5 [TDD-GREEN] Update `src/agents/art_director.py` and `src/agents/scene_planner.py` to generate compliant Rec.709 visual specifications and scene layout manifests against `schemas/art_director.schema.json`.
- [x] 2.6 Run `pytest tests/unit/test_narrative_tension_rec709.py` and confirm all tests turn GREEN.

---

## Phase 3: Procedural Visuals, Subtitles & Compositor (GREEN)

- [x] 3.1 [TDD-GREEN] Enhance `src/rendering/camera_controller.py` with continuous 2.5D Perlin drift ($dx, dy \le 8\%$, $\text{roll} \le 1.5^\circ$, zoom $[1.00, 1.15]$) and canvas boundary clamping.
- [x] 3.2 [TDD-GREEN] Update `src/rendering/renderer.py`, `src/media/proc_engine.py`, and `src/media/web_renderer.py` to inject dynamic GLSL uniforms (`u_tension`, `u_resolution`, `u_palette_*`) and safe procedural fallback shaders (`"MONOLITHS_RAYMARCHING"`).
- [x] 3.3 [TDD-GREEN] Implement multi-act frame stream isolation, safe pipe flushing, and dynamic `xfade` composition with duration clamping in `src/media/multi_act_renderer.py` and `src/media/compositor.py`.
- [x] 3.4 [TDD-GREEN] Update subtitle generators in `src/compositing/subtitles.py`, `src/media/subtitles.py`, and `lib/subtitles.py` to enforce dynamic ASS vertical safe zones ($MarginV \ge 480\text{px}$, compensating for camera drift to $\ge 510\text{px}$), horizontal margins ($MarginL/R \ge 40\text{px}$), non-overlapping timestamps, and Rec.709 high-contrast karaoke styling ($Outline \ge 3$).
- [x] 3.5 Run `pytest tests/unit/test_procedural_compositor_subtitles.py` and confirm all tests turn GREEN.

---

## Phase 4: Audio Mastering & Subprocess Watchdog (GREEN)

- [x] 4.1 [TDD-GREEN] Implement tension-coupled oscillator frequency modulation ($28\text{–}65\text{Hz}$), overtone saturation, and pop-free crossfades in `src/audio/procedural_drone.py` and `src/media/procedural_audio.py`.
- [x] 4.2 [TDD-GREEN] Update `src/audio/sfx_library.py` to provide transition SFX cues (risers, sub-drops) with procedural synthetic sweep fallbacks for missing assets.
- [x] 4.3 [TDD-GREEN] Refactor `src/audio/mixer.py` and `src/audio_processor.py` to implement -18 dB voice sidechain ducking, sample-accurate SFX alignment (`adelay`), and broadcast EBU R128 loudness mastering (`loudnorm=I=-14:TP=-1.5:LRA=11`).
- [x] 4.4 [TDD-GREEN] Implement `SubprocessWatchdog` in `lib/ffmpeg.py` with process group isolation (`start_new_session=True`), RSS memory tracking ($\le 4.0\text{ GB}$), 180s timeout enforcement, and clean `SIGKILL` resource reaping.
- [x] 4.5 Run `pytest tests/unit/test_audio_master_watchdog.py` and confirm all tests turn GREEN.

---

## Phase 5: Continuous Daemon Lifecycle, Disk Guard & End-to-End Verification

- [x] 5.1 [TDD-GREEN] Add `CONTINUOUS_ENGINE_V2` feature flag and engine configuration parameters to `src/config.py`.
- [x] 5.2 [TDD-GREEN] Implement 64-bit token/bigram SimHash calculation and Hamming distance validation ($< 4$ bit rejection against rolling window $\ge 100$) in `src/daemon.py`.
- [x] 5.3 [TDD-GREEN] Implement bounded concurrency semaphore ($N=1$) and 5.0 GB minimum free disk watermark guard in `src/daemon.py` and `src/cleaner.py`.
- [x] 5.4 [TDD-GREEN] Wire automated post-render temporary scratch artifact purging in `src/cleaner.py` and `src/daemon.py` within `finally` blocks.
- [x] 5.5 Run `pytest tests/unit/test_continuous_daemon_guard.py` and confirm all tests turn GREEN.
- [x] 5.6 Create `tests/e2e/test_continuous_engine_e2e.py` verifying full end-to-end multi-act Short generation under `CONTINUOUS_ENGINE_V2=True` with zero-quota synthetic mocks, 0 dropped frames, and EBU R128 loudness verification.
- [x] 5.7 Execute full test suite (`pytest`) across all unit, integration, and e2e test suites to confirm 100% pass rate.
