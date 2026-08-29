# Proposal: Adaptive Continuous Multi-Scene Video Engine

## Problem Statement
The current pipeline relies on hardcoded thematic templates and manual scheduling, limiting cross-lane video synthesis. Audio mastering lacks dynamic narrative tension coupling, and continuous 24/7 background rendering risks duplicate generation, GPU memory exhaustion, and disk overflow.

## Capabilities

### New Capabilities
- `adaptive-narrative-curation`: Open-domain topic orchestration with dynamic tension-curve scoring (levels 1–5), 8–15s semantic scene segmentation, and Rec.709 color-palette mapping.
- `procedural-scene-compositor`: Multi-scene WebGL/shader compositor featuring dynamic uniforms, particle systems, 2.5D camera drift, styled ASS subtitles in safe zones, and seamless crossfades.
- `tension-aware-audio-master`: Dynamic sidechain ducking (-18 dB on speech), EBU R128 loudness normalization (-14 LUFS, -1.5 dBTP), and inter-act transition SFX.
- `continuous-daemon-scheduler`: 24/7 continuous autonomous lifecycle with 64-bit SimHash deduplication, bounded concurrency semaphore, and post-render disk sweep.

### Modified Capabilities
- `media-pipeline-hardening`: Adds multi-scene rendering fault-tolerance, pipe stream isolation, and non-blocking sub-process watchdog.
- `subtitles-safe-zone`: Binds scene-level ASS subtitle positioning ($MarginV \ge 480\text{px}$) to dynamic camera drift and resolution boundaries.

## Affected Areas

| Component | Target Files | Changes |
| :--- | :--- | :--- |
| **Narrative & Art** | `src/agents/art_director.py`<br>`src/agents/script_curator.py`<br>`src/narrative/archetypes.py`<br>`src/narrative/engine.py` | Topic-agnostic archetype mapping, tension-curve scoring (1–5), dynamic Rec.709 palette injection. |
| **Compositing & Video** | `src/media/compositor.py`<br>`src/media/multi_act_renderer.py`<br>`src/rendering/camera_controller.py`<br>`src/rendering/renderer.py` | 2.5D camera drift, particle shaders, seamless `xfade` transitions, dynamic multi-scene compilation. |
| **Audio Processing** | `src/audio/mixer.py`<br>`src/audio/procedural_drone.py`<br>`src/audio/sfx_library.py` | Sidechain ducking (-18 dB), EBU R128 compliance (-14 LUFS, -1.5 dBTP), act-transition SFX triggers. |
| **Subtitles** | `src/compositing/subtitles.py` | Dynamic safe-area styling ($MarginV \ge 480\text{px}$) and per-scene subtitle burning. |
| **Daemon & Lifecycle** | `src/daemon.py`<br>`src/core/scheduler.py`<br>`src/cleaner.py` | 64-bit SimHash dedup, bounded parallel render workers, post-render temp artifact sweeping. |

## Success Criteria
- [ ] 100% topic-agnostic scene generation without hardcoded niche templates.
- [ ] Video renders achieve target frame rates with 0 dropped frames during xfade transitions.
- [ ] Integrated audio loudness meets EBU R128 (-14.0 ± 0.5 LUFS, True Peak ≤ -1.5 dBTP).
- [ ] Subtitle text strictly contained above $MarginV = 480\text{px}$.
- [ ] 24-hour continuous daemon run without memory leaks, duplicate scripts (SimHash distance < 4 rejected), or disk accumulation.

## Rollback Plan
All components operate behind feature flags in `src/config.py`. Setting `CONTINUOUS_ENGINE_V2=False` restores legacy single-scene pipeline. Reversion requires no database schema migration.
