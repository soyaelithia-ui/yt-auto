# Zero-Quota Testing Framework & Architectural Verification Suite (M5)

**Document ID:** `ARCH-M5-ZERO-QUOTA-TESTING-2026`  
**Milestone:** M5 (Zero-Quota Testing Framework & Architectural Verification Suite)  
**System Target:** `yt-auto` (Premium Multi-Lane Dual-Engine Video Production Platform)  
**Assurance Level:** High-Assurance / Deterministic / Zero-Quota-Cost  

---

## 1. Executive Summary & The Zero-Quota Testing Philosophy

The automated audiovisual pipeline in `yt-auto` integrates multiple sophisticated subsystems: multi-agent LLM reasoning, neural speech synthesis (TTS), AI generative background mattes, monocular depth estimation, procedural WebGL/Three.js raymarching shaders, HTML5 Canvas dynamics, and broadcast-grade FFmpeg filtergraphs.

In conventional systems, end-to-end integration testing frequently leaks external network calls to third-party APIs (e.g., Google Gemini, Anthropic Claude, ElevenLabs, Midjourney, YouTube Data API v3, Google Drive API). This introduces five fatal anti-patterns:
1. **Quota Depletion & Financial Cost:** Running automated test suites on every pull request rapidly burns paid API quotas and developer credits.
2. **Test Flakiness & Non-Determinism:** Third-party API rate-limiting (HTTP 429), network latency, server downtime, and generative model temperature variance cause false test failures.
3. **CI/CD Latency:** Real-time generation of multi-minute audio/video and waiting for remote inference creates 15–30 minute CI runtimes.
4. **Credential Exposure Risk:** CI test runners require live production API keys and OAuth tokens in test environments.
5. **Masked Regression Bugs:** Imprecise generative outputs mask structural regressions in JSON schemas, timeline synchronization, and mathematical audio/video invariants.

### The Zero-Quota Mandate
The `yt-auto` test infrastructure is built upon the **Zero-Quota-Waste Guarantee**:
> **100% of pipeline behaviors, agent contracts, dual-engine rendering paths, FFmpeg filtergraphs, audio mastering, and forensic QA gates must be fully verifiable in a strictly offline, deterministic test harness with zero network requests, zero API token consumption, and zero external costs.**

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          ZERO-QUOTA TEST ARCHITECTURE TOPOLOGY                         │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────┐  ┌───────────────────────────┐  ┌──────────────────────┐ │
│ │  SYNTHETIC FIXTURES       │  │  HEADLESS MOCK RUNNERS    │  │ DRAFT-07 VALIDATORS  │ │
│ │ - Tone WAV Generator      │  │ - Virtual-Time Playwright │  │ - Script Curator     │ │
│ │ - High-Contrast PNG Mattes│  │ - Canvas2D Mock Rasterizer│  │ - Art Director       │ │
│ │ - Monocular Depth Slices  │  │ - Neural TTS Mock Engine  │  │ - Scene Planner      │ │
│ │ - Word-Timing Subtitles   │  │ - Deterministic LLM Mock  │  │ - Scene Manifest     │ │
│ │ - Ephemeral SQLite WAL DB │  │ - WebGL Shader Dry-Runner │  │ - Forensic Video QA  │ │
│ └─────────────┬─────────────┘  └─────────────┬─────────────┘  └──────────┬───────────┘ │
│               │                              │                           │             │
│               └──────────────────────────────┼───────────────────────────┘             │
│                                              ▼                                         │
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │                      5-TIER STRATIFIED VERIFICATION HARNESS                        │ │
│ ├───────────────────────┬───────────────────────┬────────────────────────────────────┤ │
│ │ Tier 1: Unit & Schema │ Tier 2: Boundary/Edge │ Tier 3: Cross-Feature Interactions │ │
│ │ - 24 Feature Units    │ - Duration bounds     │ - 4-Agent DAG Pipeline Flow        │ │
│ │ - Schema Validation   │ - Luminance limits    │ - Dual-Engine Manifest Generation  │ │
│ │ - Pure Math Invariants│ - Audio NaN avoidance │ - Channel Matrix Pairwise Tests    │ │
│ ├───────────────────────┴───────────────────────┴────────────────────────────────────┤ │
│ │ Tier 4: Real-World Application Scenarios (Cosmic Horror, SCP Shorts, AITA Drama)   │ │
│ ├────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ Tier 5: Adversarial Hardening (Circuit Breakers, Corrupt Containers, Chaos Fuzz)   │ │
│ └────────────────────────────────────────────┬───────────────────────────────────────┘ │
│                                              ▼                                         │
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │               FORENSIC INVARIANT ASSERTIONS (Pass / Fail-Closed Gate)              │ │
│ │ - Audio: EBU R128 (-14.0 ± 1.5 LUFS, True Peak <= -1.5 dBTP, Ducking -18 dB)       │ │
│ │ - Video: 1080p, Rec.709 Matrix, Avg Lum >= 22.0, CRF 18-20, Lanczos Rescaling      │ │
│ │ - Container: ISO/IEC 14496-14, moov atom before mdat (+faststart)                  │ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 5-Tier Stratified Test Architecture

The verification suite partitions testing into five rigorous tiers, spanning from isolated feature contracts to full-scale simulated production runs:

| Tier | Focus | Verification Methodology | Execution Cost | Target Count |
|---|---|---|:---:|:---:|
| **Tier 1** | **Feature Coverage & Unit Contracts** | Equivalence partition representatives, individual function contracts, JSON schema conformance, color math validation. | < 50ms / test | $\ge 120$ tests ($\ge 5$ / feature) |
| **Tier 2** | **Boundary Value & Corner Analysis** | Extreme duration boundaries ($45.0$s, $90.0$s, $8.0$s, $15.0$s), tension levels ($1$ and $5$), luminance floors ($22.0$), silence vs full-scale audio, aspect ratio edges. | < 100ms / test | $\ge 120$ tests ($\ge 5$ / feature) |
| **Tier 3** | **Cross-Feature Interactions** | Pairwise integration testing across 4 agents, dual engines (Hybrid AI + Procedural Three.js), 3 channel lanes, and audio-video compositing. | 100–500ms / test | $\ge 24$ pairwise tests |
| **Tier 4** | **Real-World Application Scenarios** | Full multi-minute pipeline runs simulating complete production scenarios: Cosmic Horror 12-min longform, SCP Foundation 9:16 Shorts, and AITA Relationship Drama. | 1–5s / test | $\ge 5$ comprehensive scenarios |
| **Tier 5** | **Adversarial Hardening & Fuzzing** | White-box chaos injection, corrupt container headers, broken audio waveforms, non-monotonic timestamps, network timeout simulations, fail-closed quarantine gates. | 50–300ms / test | Exhaustive stress suite |

---

## 3. Offline Synthetic Fixtures & Generators

To eliminate external file downloads and network dependencies, the framework provides high-fidelity in-memory and local file generators that create mathematically compliant media assets on demand.

### 3.1 Synthetic Audio Fixtures (`_tone_frames` & `create_synthetic_wav`)
Pure digital silence (zero-amplitude samples) causes FFmpeg's `loudnorm` filter to compute invalid infinite negative dynamic ranges, emitting `NaN` floats that trigger catastrophic encoder failures (`Input contains (near) NaN/+-Inf`). 

The test harness uses deterministic harmonic tone synthesis to generate valid PCM audio buffers:
```python
import math
import struct
import subprocess
import wave
from pathlib import Path

def create_synthetic_wav(
    path: Path | str,
    duration_sec: float = 5.0,
    sample_rate: int = 44100,
    freq_hz: float = 440.0,
) -> str:
    """Generate a clean sinusoidal WAV audio file without external assets."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_sec * sample_rate)
    with wave.open(str(p), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit PCM
        wav.setframerate(sample_rate)
        frames = b"".join(
            struct.pack("<h", int(1200 * math.sin(2 * math.pi * freq_hz * i / sample_rate)))
            for i in range(n_samples)
        )
        wav.writeframes(frames)
    return str(p)
```

### 3.2 High-Contrast Synthetic Image & Matte Generator
Video quality gates enforce edge density ($\ge 2.0$) and root-mean-square contrast ($\ge 5.0$) to detect blank or black-frame rendering bugs. Synthetic image generators render deterministic geometric grids with Rec.709 color compliance:
```python
from PIL import Image, ImageDraw

def create_synthetic_image(
    path: Path | str,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple[int, int, int] = (15, 20, 30),
) -> str:
    """Generate a high-contrast Rec.709 test pattern for visual QA gates."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Render high-contrast structural grid and geometric shapes
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=(40, 60, 80), width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=(40, 60, 80), width=1)
        
    draw.rectangle([width//4, height//4, 3*width//4, 3*height//4], fill=(74, 124, 89), outline=(100, 180, 120))
    img.save(str(p), format="PNG")
    return str(p)
```

### 3.3 Synthetic Monocular Depth Maps
Generates 8-bit single-channel grayscale images with linear and radial depth gradients representing foreground ($Z=0$), midground ($Z=128$), and background ($Z=255$) planes to verify 2.5D parallax slicing and Ken Burns camera projections.

### 3.4 Ephemeral SQLite WAL Repositories
Every test instantiates an isolated `QueueRepository` backed by a temporary SQLite file using Write-Ahead Logging (`WAL`), strict foreign keys (`PRAGMA foreign_keys = ON;`), and immediate transactions. All states are torn down completely upon fixture exit, guaranteeing zero state leakage across tests.

---

## 4. Headless Mock Runners & Virtual-Time Execution

### 4.1 Headless Chromium / Playwright Virtual-Time Shader Renderer
For procedural Three.js, WebGL raymarching, and HTML5 Canvas templates, real-time rendering is both slow and non-deterministic. The framework employs virtual-time frame stepping:
- The browser animation clock is overridden via `window.__virtual_time = frame_index / fps`.
- `requestAnimationFrame` is mocked to advance monotonically without waiting for wall-clock time.
- Playwright captures canvas frames directly into memory buffers via `page.evaluate("canvas.toDataURL()")` or headless WebGL screencast.

### 4.2 Mock LLM Agent Adapters
The 4-agent DAG pipeline (`ScriptCurator`, `ArtDirector`, `ScenePlanner`, `VisualAudioQAAuditor`) uses mock client adapters that produce deterministic JSON responses strictly validated against the canonical schemas:
```python
class MockLLMClient:
    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.call_history = []

    def generate_json(self, prompt: str, schema_name: str) -> dict:
        self.call_history.append({"prompt": prompt, "schema": schema_name})
        if schema_name in self.responses:
            return self.responses[schema_name]
        raise ValueError(f"No mock response configured for schema: {schema_name}")
```

### 4.3 Mock Neural TTS Synthesis Adapter
Simulates neural speech synthesis by computing word durations from character length and generating synchronized word-level timestamps (`[{"word": w, "start": t0, "end": t1}, ...]`) along with matching synthetic WAV buffers, verifying subtitle alignments without invoking Microsoft Edge-TTS or ElevenLabs APIs.

---

## 5. Schema Validation & Contract Enforcement

All agent interfaces and intermediate data artifacts are validated against **Draft-07 JSON Schemas** stored in `schemas/`. The test framework enforces `additionalProperties: false` to detect payload drift, undocumented fields, and schema regressions.

### Schema Inventory & Validation Matrix

```
┌───────────────────────────────┬───────────────────────────────┬────────────────────────────────────────┐
│ Schema File                   │ Agent Interface Contract      │ Key Validations & Invariants           │
├───────────────────────────────┼───────────────────────────────┼────────────────────────────────────────┤
│ `script_curator.schema.json`  │ ScriptCurator -> ArtDirector  │ - 4 Acts (Exposition to Aftermath)     │
│                               │                               │ - Scene durations: 45.0..90.0s (Long)  │
│                               │                               │ - Scene durations: 8.0..15.0s (Shorts) │
│                               │                               │ - Tension levels: integer 1..5         │
│                               │                               │ - Lane IDs: moku/aelithia enum         │
├───────────────────────────────┼───────────────────────────────┼────────────────────────────────────────┤
│ `art_director.schema.json`    │ ArtDirector -> ScenePlanner   │ - 5-Color Rec.709 Hex Palette          │
│                               │                               │ - Volumetric lighting direction/type   │
│                               │                               │ - Negative prompt ban list             │
│                               │                               │ - Weather FX: fog/embers/spores/etc.   │
├───────────────────────────────┼───────────────────────────────┼────────────────────────────────────────┤
│ `scene_planner.schema.json` / │ ScenePlanner -> DualCompositor│ - Engine: hybrid_ai / procedural_webgl │
│ `scene_manifest.schema.json`  │                               │ - 3D Ken Burns Cubic Bezier curves     │
│                               │                               │ - Particle systems (density, speed)    │
│                               │                               │ - Sidechain ducking (-18 dB, 20/350ms) │
│                               │                               │ - Safe Area protection (bottom 330px)  │
├───────────────────────────────┼───────────────────────────────┼────────────────────────────────────────┤
│ `video_qa.schema.json`        │ DualCompositor -> QA Auditor  │ - L1 Audio physics (-14 LUFS, dBTP)    │
│                               │                               │ - L2 Container (1080p, Rec.709, moov)  │
│                               │                               │ - L3 Vision QA keyframe score (>=0.85) │
└───────────────────────────────┴───────────────────────────────┴────────────────────────────────────────┘
```

---

## 6. Invariant Assertions & Forensic Quality Gates

The test harness asserts strict mathematical invariants on all rendered media artifacts before certifying them:

### 6.1 Audio Physics Invariants (EBU R128 Standard)
- **Integrated Loudness ($I$):** $-14.0 \pm 1.5$ LUFS.
- **Maximum True Peak ($\text{TP}$):** $\le -1.5$ dBTP (prevents inter-sample clipping on mobile DACs).
- **Loudness Range ($\text{LRA}$):** $\le 11.0$ LU (guarantees dynamic consistency across scene changes).
- **Dynamic Sidechain Ducking:** Narration triggers $-18.0$ dB attenuation on background music channels with a $20$ms attack and $350$ms release curve.
- **Stereo Phase Correlation:** Mean phase coefficient $\ge +0.2$ (verifies mono-compatibility and eliminates destructive phase cancellation).

### 6.2 Video Color & Luminance Invariants
- **Color Space Matrix:** Strict ITU-R BT.709-6 primaries (`bt709`), transfer characteristics (`bt709`), and color matrix (`bt709`).
- **Minimum Average Luminance:** Scene average pixel luminance $\ge 22.0$ / $255.0$ (ensures visibility on mobile OLED screens and bans pitch-black frames).
- **Resolution & Aspect Ratio:**
  * Longform: $1920 \times 1080$ ($16:9$, tolerance $\pm 0$ px).
  * Shorts: $1080 \times 1920$ ($9:16$, tolerance $\pm 0$ px).
- **Encoding Profile:** Constant Rate Factor $\text{CRF} \in [18, 20]$, `preset=slow`, `pix_fmt=yuv420p`.
- **Max Freeze-Frame Duration:** No static unmoving frames exceeding $1.0$s duration.

### 6.3 Container & Web Streaming Invariants
- **Faststart MOOV Atom Placement:** The `moov` atom must precede the `mdat` atom (`-movflags +faststart`) to allow immediate playback streaming without downloading the complete file.
- **Fail-Closed Gatekeeper:** If any forensic check fails, the video is immediately quarantined in SQLite with `overall_pass = false` and upload procedures are aborted.

---

## 7. Continuous Integration & Local Verification Strategy

### 7.1 Local & CI Test Runner Command
The entire verification suite is executed through standard `pytest` in the local Python 3.12 virtual environment:
```bash
./.venv/bin/pytest -v
```

### 7.2 Coverage Governance & Gates
- **Total Test Count:** $\ge 1200$ automated tests across Unit, Integration, E2E, and Adversarial tracks.
- **Network Isolation:** Any test attempting an outbound socket connection to unmocked external hosts fails immediately with a network sandbox violation.
- **Zero Artifact Residue:** All temporary WAV, MP4, PNG, and SQLite files are created inside `tempfile.TemporaryDirectory()` or pytest `tmp_path` fixtures and deleted on completion.

---

## 8. Architectural Traceability Matrix

| Feature | Requirement | Implementation Module | Schema / Contract | Zero-Quota Verification Test |
|---|---|---|---|---|
| F-01 AI Background Matte Gen | R1 | `src/media/web_video_renderer.py` | `art_director.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/e2e/test_scenarios.py` |
| F-02 Depth Map & 2.5D Parallax | R1 | `src/media/web_video_renderer.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/integration/test_pipeline_e2e_mock.py` |
| F-03 Volumetric Light Shaders | R1 | `src/media/web_templates/` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py` |
| F-04 Atmospheric Particles | R1 | `src/media/web_templates/` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/e2e/test_scenarios.py` |
| F-05 WebGL / Three.js Procedural | R1 | `src/media/web_video_renderer.py` | `scene_manifest.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-06 Canvas2D Generator | R1 | `src/media/web_templates/` | `scene_manifest.schema.json` | `tests/e2e/test_scenarios.py` |
| F-07 Strict Color Enforcement | R1 | `src/core/quality.py` | `art_director.schema.json` | `tests/unit/test_architectural_specs.py` |
| F-08 Multi-Scene Pacing (45-90s) | R2 | `src/scene_manifest.py` | `script_curator.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/integration/test_pipeline_e2e_mock.py` |
| F-09 Tension Synchronizer (1-5) | R2 | `src/scene_manifest.py` | `script_curator.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-10 Multi-Channel Ambient Matrix | R2 | `src/scene_manifest.py` | `scene_manifest.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-11 Canonical `scene_manifest.json` | R1, R2 | `src/scene_manifest.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/integration/test_pipeline_e2e_mock.py` |
| F-12 Script Curator Agent | R3 | `src/llm.py` | `script_curator.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-13 Art Director Agent | R3 | `src/llm.py` | `art_director.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-14 Scene Planner Agent | R3 | `src/scene_manifest.py` | `scene_planner.schema.json` | `tests/integration/test_pipeline_e2e_mock.py`, `tests/e2e/test_scenarios.py` |
| F-15 Visual & Audio QA Auditor | R3 | `src/core/quality.py` | `video_qa.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/integration/test_pipeline_e2e_mock.py` |
| F-16 Fail-Closed Fallback | R3 | `src/pipeline.py` | `video_qa.schema.json` | `tests/e2e/test_scenarios.py` |
| F-17 Theme Lane Color Matrix | R3 | `src/media/web_templates/` | `art_director.schema.json` | `tests/unit/test_architectural_specs.py` |
| F-18 CRF 18-20 Master Encode | R4 | `lib/video.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/e2e/test_scenarios.py` |
| F-19 Lanczos Rescaling | R4 | `lib/video.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py` |
| F-20 De-banding Filter Graph | R4 | `lib/video.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py` |
| F-21 EBU R128 Audio & Ducking | R4 | `src/audio_processor.py` | `scene_manifest.schema.json` | `tests/unit/test_architectural_specs.py`, `tests/e2e/test_scenarios.py` |
| F-22 Legacy Debt Deprecation | R4 | `src/visuals/` | `scene_manifest.schema.json` | `tests/unit/test_scene_asset_tracker.py` |
| F-23 Zero-Quota Test Framework | R4 | `tests/` | `ALL SCHEMAS` | `tests/unit/test_architectural_specs.py`, `tests/integration/test_pipeline_e2e_mock.py` |
| F-24 E2E Acceptance & Hardening | R1-R4 | `tests/e2e/` | `ALL SCHEMAS` | `tests/e2e/test_scenarios.py` |
