# Design: SCP Narrative Scripting & High-Retention Engine

## Technical Approach
Re-architect script compilation across `src/curators/moku_horror.py`, `src/agents/script_curator.py`, and `src/narrative/engine.py` to replace static wiki text generation with a 50-element dynamic retention pipeline. The engine supports dual narrative voices (Institutional Archivist vs. Conversational Incident Narrator), enforces 120-145 word limits with 7-10s scene bounds for Shorts, injects tension-mapped DSP audio cues, and guarantees seamless syntactic looping.

## Architecture Decisions

| Decision | Options Considered | Tradeoffs | Selected Rationale |
| :--- | :--- | :--- | :--- |
| **Dual Narrative Stances** | 1. Single generic voice<br>2. Dual: Institutional vs. Conversational | Single voice is rigid; dual voice increases variety across SCP incident types | **Dual Voice Engine**: Supports JOMOSU clinical horror and LaloBeRoth conversational incident storytelling dynamically based on topic type. |
| **Shorts Retention Boundaries** | 1. Unbounded text (40-60s)<br>2. Strict 120-145 words @ 165 WPM | Unbounded causes audio drag; strict word count ensures 45-50s sweet spot | **Strict 120-145 Words**: Guarantees optimal pacing and prevents video duration overflow (>58s). |
| **Outro & Loop Enforcement** | 1. Standard channel CTA<br>2. Seamless syntactic loop | CTA causes instant swipe drop-off; seamless loop increases AVD > 100% | **Seamless Syntactic Loop**: Prohibits channel plugs in Shorts; enforces conjunctive terminal clause matching 0s hook. |
| **DSP & Audio Cues** | 1. Single audio bed<br>2. Timestamped SFX cue contract | Single bed lacks impact; timestamped cues require timeline synchronization | **Timeline-Mapped SFX Cues**: Cues sub-drops (40Hz), radio static, and heartbeats aligned with tension levels (1-5). |

## Data Flow

```
Raw Topic / Lore ──→ Archetype & Voice Resolver ──→ Narrative Synthesizer (5-Phase / 3-Act)
                             │                                │
                             ▼                                ▼
                 Rec.709 Palette & DSP Cues        Scene Slicer (7-10s bounds)
                             │                                │
                             └──────→ SceneContractV2 ←───────┘
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/curators/moku_horror.py` | Modify | Replace static boilerplate with dynamic LaloBeRoth/JOMOSU hooks, 120-145 word limits, and loop connectors. |
| `src/agents/script_curator.py` | Modify | Integrate dual-voice lane configs, 3-stage D-Class experiment logs, and anti-cliché sanitization filters. |
| `src/narrative/archetypes.py` | Modify | Update archetype presets with refined tension progressions, voice presets, and sub-drone frequencies (34-48 Hz). |
| `src/narrative/engine.py` | Modify | Enforce 7-10s scene bounds, loop continuity validation, and tension-mapped SFX timeline generation. |
| `tests/unit/test_narrative_scripting.py` | Create | Unit tests for word count bounds, seamless loops, scene slicing, and schema validation. |

## Interfaces / Contracts

```python
class NarrativeVoiceStance(str, Enum):
    INSTITUTIONAL_ARCHIVIST = "institutional_archivist"  # JOMOSU style: clinical, ominous
    CONVERSATIONAL_INCIDENT = "conversational_incident"  # LaloBeRoth style: energetic, empathetic

@dataclass(frozen=True)
class RetentionScriptContract:
    title: str
    voice_stance: NarrativeVoiceStance
    target_format: str  # "short" | "longform"
    total_words: int
    estimated_duration_sec: float
    hook_text: str
    scenes: List[SceneContract]
    loop_connector: Optional[str] = None
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| **Unit** | Word count bounds (120-145 words for Shorts), loop syntax, anti-cliché filters | `pytest tests/unit/test_narrative_scripting.py` with deterministic inputs |
| **Integration** | End-to-end `CinematicScriptCuratorAgent.curate()` schema compliance | Validate generated output against `schemas/script_curator.schema.json` |
| **E2E** | Pipeline execution with synthetic horror topics | Offline mock test ensuring zero external quota consumption |

## Threat Matrix
`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

## Migration / Rollout
Zero breaking changes. `INarrativeCurator` and `CosmicNarrativeEngine` maintain existing method signatures (`build_short_narrative`, `generate_script`) while upgrading internal text synthesis templates and validation logic.

## Open Questions
None. Architecture decisions and retention blueprints are fully consolidated.
