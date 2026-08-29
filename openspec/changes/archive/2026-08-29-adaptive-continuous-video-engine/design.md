# Technical Design: Adaptive Continuous Multi-Scene Video Engine

## Technical Approach
Transforms synthesis into an autonomous multi-scene pipeline. Combines 5-phase tension scoring (1–5), Rec.709 palette mapping, WebGL/GLSL compositing with 2.5D Perlin drift, EBU R128 audio with -18 dB voice sidechain ducking, and a 24/7 daemon guarded by 64-bit SimHash dedup ($Hamming < 4$ reject), bounded concurrency ($N=1$), and post-render scratch sweepers under `CONTINUOUS_ENGINE_V2`.

## Architecture Decisions

| Area | Options | Tradeoffs | Decision |
| :--- | :--- | :--- | :--- |
| **Narrative** | (A) Static templates<br>(B) 5-phase curve (1–5) + WPM pacing | B enables topic-agnostic scripts with monotonic pacing and 8–15s acts. | **B**: Dynamic script curation. |
| **Compositing** | (A) Loop MP4s<br>(B) GLSL shaders + 2.5D drift + `xfade` | B runs procedural WebGL with dynamic uniforms and fallback shaders. | **B**: Code-driven, zero-drop transitions. |
| **Audio Master** | (A) Static mix<br>(B) Sidechain (-18 dB) + EBU R128 + tension drone | B ducks drone/SFX during speech and enforces $-14\text{ LUFS} \pm 0.5$ / $-1.5\text{ dBTP}$. | **B**: Broadcast vocal clarity and tension drone. |
| **Daemon** | (A) Unchecked cron<br>(B) 64-bit SimHash + semaphore + 5 GB guard | B rejects duplicates ($Hamming < 4$), throttles ($N=1$), and purges scratch. | **B**: Prevents duplicates, VRAM leaks, disk full. |
| **Isolation** | (A) Raw pipes<br>(B) Watchdog (RSS $\le 4\text{ GB}$, 180s) + stream isolation | B isolates act pipes and kills runaway FFmpeg groups via `SIGKILL`. | **B**: Prevents deadlocks, stalls, zombies. |

## Data Flow

```text
[ Topic Prompt ] -> [ Narrative Engine ] (5-phase tension 1-5, Rec.709 palette, 8-15s acts)
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
 [ Audio Mastering ]             [ Procedural Visuals ]
 - Tension drone (28-65 Hz)      - GLSL uniforms & 2.5D drift
 - Sidechain ducking (-18 dB)    - Subtitles (MarginV >= 480px)
 - EBU R128 (-14 LUFS)           - Pipe stream isolation
          │                               │
          └───────────────┬───────────────┘
                          ▼
   [ FFmpeg xfade + Watchdog (RSS <= 4 GB, t <= 180s) ] -> Master MP4
                          │
                          ▼
   [ Daemon: 64-bit SimHash (Hamming >= 4) + 5 GB Disk Guard Sweep ]
```

## File Changes

| File | Action | Description |
| :--- | :--- | :--- |
| `src/narrative/schema.py` | Modify | Add `TensionLevel` (1–5), Rec.709 palette, camera drift configs. |
| `src/narrative/archetypes.py` | Modify | Open-domain archetype mappings, tension presets, Rec.709 maps. |
| `src/narrative/engine.py` | Modify | 5-Phase tension scoring, monotonic smoothing, WPM segmentation. |
| `src/agents/script_curator.py` | Modify | Topic-agnostic curation, 8–15s Short acts, orphan clause merging. |
| `src/agents/art_director.py` | Modify | Rec.709 schemas, Kelvin temperature scaling, LUT profiles. |
| `src/rendering/camera_controller.py` | Modify | 2.5D Perlin drift ($dx, dy \le 8\%$, roll $\le 1.5^\circ$, zoom $[1.00, 1.15]$). |
| `src/rendering/renderer.py` | Modify | Dynamic GLSL uniforms (`u_tension`, `u_palette_*`) & fallback shader. |
| `src/media/multi_act_renderer.py` | Modify | Pipe stream isolation, dynamic `xfade`, duration clamping. |
| `src/media/compositor.py` | Modify | Route multi-scene rendering through watchdog-guarded rawvideo pipes. |
| `src/audio/procedural_drone.py` | Modify | Modulate frequencies ($28\text{–}65\text{ Hz}$) and harmonics by tension. |
| `src/audio/sfx_library.py` | Modify | Inter-act transition cues (risers, sub-drops) with fallback synthesis. |
| `src/audio/mixer.py` | Modify | -18 dB sidechain ducking and EBU R128 `loudnorm` (-14 LUFS, -1.5 dBTP). |
| `src/compositing/subtitles.py` | Modify | ASS $MarginV \ge 480\text{px}$ bound to camera drift ($\ge 510\text{px}$) and palette. |
| `lib/ffmpeg.py` | Modify | Non-blocking watchdog monitoring RSS ($\le 4\text{ GB}$) and 180s timeout. |
| `src/daemon.py` | Modify | 64-bit SimHash dedup ($Hamming < 4$ reject), semaphore ($N=1$), 5 GB disk guard. |
| `src/config.py` | Modify | Add `CONTINUOUS_ENGINE_V2` feature flag and engine settings. |
| `tests/unit/test_continuous_engine.py` | New | Unit tests for tension curve, SimHash, ASS margin, ducking. |

## Interfaces / Contracts

```python
# src/narrative/schema.py
@dataclass
class Rec709Palette:
    primary: str; secondary: str; accent: str; shadow: str; highlight: str
    kelvin: int = 6500; lut_profile: str = "cosmic_rec709"

@dataclass
class SceneContractV2:
    start_sec: float; end_sec: float; tension_level: int
    shader_id: str; palette: Rec709Palette; camera_drift: Dict[str, float]

# src/rendering/camera_controller.py
@dataclass
class CameraTransform:
    offset_x: float; offset_y: float; rotation_deg: float; zoom_scale: float

# lib/ffmpeg.py
class SubprocessWatchdog:
    def __init__(self, max_rss_mb: float = 4096.0, timeout_sec: float = 180.0): ...
    def monitor_process(self, proc: subprocess.Popen) -> None: ...

# src/daemon.py
def evaluate_script_simhash(candidate_text: str, repository: QueueRepository, min_hamming_distance: int = 4) -> bool: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
| :--- | :--- | :--- |
| **Unit** | 5-Phase tension scoring, SimHash Hamming check ($< 4$), ASS $MarginV \ge 480\text{px}$, ducking filter strings. | Parameterized `pytest` testing bounds, regex, and clamping. |
| **Integration** | Procedural rendering with fallback shader, pipe stream isolation, multi-track audio mix. | Synthetic rendering verifying pipe flushes and audio sync. |
| **E2E** | Multi-act Short under `CONTINUOUS_ENGINE_V2=True` producing valid MP4 with 0 freeze frames and EBU R128 norm. | Video QA inspection via `visual_inspect.py` and `probe_media`. |
| **Zero-Quota Mocks** | Complete pipeline run in disconnected CI without network, GPU, or keys. | Mocked GLSL, synthetic PCM audio (`tests/helpers/audio.py`), SQLite. |

## Threat Matrix

| Threat / Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| **FFmpeg Deadlock / Zombie Leak** | Medium | High | Process groups (`start_new_session=True`) + `SubprocessWatchdog` `SIGKILL` at $t > 180\text{s}$. |
| **Memory / File Descriptor Leak** | Medium | Critical | Concurrency semaphore ($N=1$), pipe closing in `finally`, RSS limit $\le 4.0\text{ GB}$. |
| **SimHash Collisions / Duplicates** | Low | Medium | 64-bit weighted token & bigram SimHash rejecting Hamming $< 4$ on window $\ge 100$. |
| **Scratch Disk Accumulation** | Medium | High | Post-render sweep in `finally` and $5.0\text{ GB}$ minimum free disk watermark guard. |

## Migration / Rollout
1. Implement feature flag `CONTINUOUS_ENGINE_V2: bool = os.getenv("CONTINUOUS_ENGINE_V2", "1") == "1"` in `src/config.py`.
2. Enhance `src/narrative/engine.py` and `src/agents/script_curator.py` with 5-phase tension and Rec.709 palettes.
3. Update `src/audio/mixer.py` (-18 dB sidechain, EBU R128) and procedural drone/SFX generators.
4. Update `src/rendering/camera_controller.py`, `src/rendering/renderer.py`, `src/media/multi_act_renderer.py` with 2.5D drift and pipe isolation.
5. Integrate 64-bit SimHash dedup and watchdog into `src/daemon.py` and `lib/ffmpeg.py`.
6. Verify test suite and confirm rollback when `CONTINUOUS_ENGINE_V2=False`.

## Open Questions
- None. All interfaces, mathematical constraints, and operational bounds are fully specified.
