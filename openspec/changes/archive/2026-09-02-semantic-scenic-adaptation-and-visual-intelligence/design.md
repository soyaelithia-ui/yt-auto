# Design: Layered Atmospheric Visual Intelligence & Maritime Lighthouse Engine

## Technical Approach
Enrich procedural background shaders and thumbnail generation with layered environmental elements (celestial bodies like moons, volumetric beacon sweeps, ocean waves, cloud strata, and architectural landmarks) to eliminate visual emptiness. Introduce the `maritime_lighthouse` procedural archetype and update `scenic_detector.py`, `native_procedural.py`, and `subject_extractor.py` to support dynamic maritime, coastal, and lighthouse horror/mystery narratives.

## Architecture Decisions

| Option | Tradeoff | Decision |
| :--- | :--- | :--- |
| **Procedural Ocean & Volumetric Light Beam in WGSL** | Adds mathematical shader computations but produces infinite seamless 60fps loops with zero external asset dependencies. | **Chosen**: Implement analytic raymarching for lighthouse light beam, sine-fBm water waves, and cratered moon in WGSL. |
| **Multi-Element Composition in Thumbnail Compositor** | Requires layered PIL vector drawing (moon, cloud wisps, waves, tower body, beacon rays) with separate alpha masks. | **Chosen**: Extend `AdaptiveSubjectCompositor` with 4x supersampled layered scenic props (celestial moon, clouds, ocean, lighthouse). |
| **Expanded Scenic Semantic Dictionaries** | Minimal runtime cost (regex/dict lookup <1ms). | **Chosen**: Register `maritime_lighthouse` in `CANONICAL_ARCHETYPES` with coastal, nautical, and lighthouse keywords. |

## Data Flow

```
Story Text / Title ──→ ScenicDetector.detect_adaptive_theme()
                              │ (e.g. 'maritime_lighthouse', 'dark_forest', etc.)
                              ▼
                       LoopVideoEngine
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
       NativeProceduralEngine        ThumbnailEngine
   (maritime_lighthouse.wgsl)      (AdaptiveSubjectCompositor)
   - Raymarched Beacon Beam        - Crescent / Full Moon with Halo
   - Specular Ocean Waves          - Drifting Cloud Ribbons
   - Rocky Headland & Tower        - Silhouette of Lighthouse Tower
   - Nocturnal Moon & Clouds       - Wave Crests & Sea Foam
```

## File Changes

| File | Action | Description |
| :--- | :--- | :--- |
| `src/media/shaders/maritime_lighthouse.wgsl` | Create | Native WGSL procedural shader with rotating volumetric lighthouse beam, ocean wave simulation, rocky cliffs, and glowing nocturnal moon with drifting cloud layers. |
| `src/media/native_procedural.py` | Modify | Register `maritime_lighthouse` in `VALID_ARCHETYPES` and define canonical cyan-amber palette `#00E5FF` / `#FFB300`. |
| `src/core/scenic_detector.py` | Modify | Add `maritime_lighthouse` keywords (faro, mar, océano, costa, acantilado, olas, isla, muelle, puerto, etc.) to canonical classifier. |
| `src/media/thumbnails/subject_extractor.py` | Modify | Add rich scenic composition for `maritime_lighthouse` (tower, rotating beam, moon, cloud ribbons, and sea waves) and enrich other archetypes. |
| `config/channels/moku.json` | Modify | Add maritime/coastal genre mappings to archetype table. |

## Interfaces / Contracts

```python
# Canonical archetype list in src/core/scenic_detector.py and native_procedural.py
CANONICAL_ARCHETYPES: tuple[str, ...] = (
    "tactical_chamber",
    "dark_forest",
    "arctic_desolation",
    "cosmic_singularity",
    "arcade_vector_flight",
    "parkour_runner",
    "cozy_hearth",
    "synaptic_network",
    "maritime_lighthouse",
)
```

## Testing Strategy

| Layer | What to Test | Approach |
| :--- | :--- | :--- |
| Unit | `test_maritime_scenic_detection` | Test story texts containing "faro", "acantilado", "mar embravecido" resolve to `maritime_lighthouse`. |
| Integration | `test_maritime_lighthouse_render` | Render a test frame of `maritime_lighthouse.wgsl` at 1080x1920 via `NativeProceduralEngine` and verify RGBA buffer integrity. |
| Integration | `test_thumbnail_lighthouse_composition` | Generate thumbnail for a maritime story and verify moon, cloud, wave, and tower layers render smoothly. |

## Threat Matrix
`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

## Migration / Rollout
No migration required. The new shader compiles automatically on first run via Mesa Lavapipe and registers in SQLite `video_loops`.

## Open Questions
- None.
