# Architecture and Technical Design: Visual Diversity & QA Guardrails

## 1. Overview and Architectural Flow

This design rectifies visual monotony and QA blindspots by introducing decoupled pacing logic and two deterministic quality gates:

```text
[Story Audio / Duration]
           │
           ▼
[src/media/pacing.py: compute_dynamic_shot_pacing()] ──► Dynamic Shots (15-45s longform)
           │
           ▼
[src/agents/scene_planner.py & loop_engine.py] ────────► Diverse Multi-Asset Manifest
           │
           ▼
[FFmpeg Multi-Asset Composition] ──────────────────────► Master Video MP4
           │
           ▼
[QA Gatekeeper Evaluation]
   ├── SceneDiversityGate (>= 6 scenes for longform, max 25% single asset)
   └── LuminanceContrastGate (perceived luminance floor Y >= 22.0)
```

## 2. File and Module Map

1. **`src/media/pacing.py` [NEW]**:
   - `compute_dynamic_shot_pacing(total_duration_sec: float, orientation: str) -> list[float]`
   - Pure, zero-dependency calculation for shot durations adhering to format pacing constraints.
2. **`lib/qa/diversity_gate.py` [NEW]**:
   - `SceneDiversityGate(BaseGate)`: Evaluates manifest scene count and asset dominance ratio.
   - `LuminanceContrastGate(BaseGate)`: Evaluates sampled frame mean luminance ($Y_{\text{mean}} \ge 22.0$) and shadow distribution.
3. **`src/pipeline.py` [MODIFY]**:
   - Integrate `compute_dynamic_shot_pacing()` in loop/director scene planning, replacing lines 907-911 (`min(4, ...)`).
   - Ensure multi-scene asset list is fed into composition.
4. **`src/core/verdict.py` [MODIFY]**:
   - Wire `SceneDiversityGate` and `LuminanceContrastGate` into the deterministic `evaluate_video()` pipeline.

## 3. Architecture Decisions & Trade-off Analysis

### Decision 1: Pure Functional Module for Pacing (`src/media/pacing.py`)
- **Rationale**: Isolating shot math from `src/pipeline.py` ensures 100% unit-testability without needing database fixtures or mock pipeline states.
- **Alternatives Considered**: Inlining the math inside `src/pipeline.py`. Rejected due to high risk of regression and poor modularity.

### Decision 2: Photometric Luminance Floor vs AI Computer Vision Model
- **Rationale**: Computing ITU-R BT.709 relative luminance ($Y = 0.2126R + 0.7152G + 0.0722B$) across existing sampled frames executes in $< 10\text{ms}$ with zero memory overhead and zero external API dependencies.
- **Alternatives Considered**: Using a deep-learning vision model. Rejected due to latency, non-determinism, and external quota consumption.

### Decision 3: Deterministic Quality Invariant in `BaseGate` Interface
- **Rationale**: Integrating directly into `lib/qa/` ensures both CLI pre-publication gates and Telegram review submissions enforce the exact same standard.
