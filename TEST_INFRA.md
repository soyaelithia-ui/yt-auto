# yt-auto Test Infrastructure & Zero-Quota Framework

Especificación de la infraestructura de pruebas automatizadas y diagnóstico para el sistema `yt-auto`.

## 🧪 Estrategia de Pruebas Zero-Quota

La infraestructura de pruebas está estratificada en niveles para validar el sistema de forma determinista y sin consumo de cuotas LLM ni APIs externas:

- **F-01**: Multi-Lane Architecture isolation tests.
- **F-02**: SQLite WAL Persistence and transactional rollback tests.
- **F-03**: 13-Stage State Machine workflow progression tests.
- **F-04**: Edge-TTS Voice Synthesis duration and frequency tests.
- **F-05**: EBU R128 Audio Mastering and sidechain ducking tests.
- **F-06**: Real-Time Procedural Engine Three.js multiscene render tests.
- **F-07**: Dual-Engine Compositor seamless assembly tests.
- **F-08**: Dynamic Safe Area ASS Subtitles karaoke alignment tests.
- **F-09**: Agent 1: Script Curator schema and retention hook tests.
- **F-10**: Agent 2: Art Director Rec.709 color matrix tests.
- **F-11**: Agent 3: Scene Planner canonical manifest builder tests.
- **F-12**: Agent 4: Forensic QA Auditor audiovisual gatekeeper tests.
- **F-13**: Agent 5: Image Auditor Anti-Filler policy enforcement tests.
- **F-14**: Agent 6: SEO Optimizer viral title and hashtag tests.
- **F-15**: Telegram Interactive Bot callback and delivery tests.
- **F-16**: Drive Backup & Verification preflight tests.
- **F-17**: YouTube Data API v3 Upload payload contract tests.
- **F-18**: AutoPilot Autonomous Scheduler interval timing tests.
- **F-19**: Scenic Loop Detector classification heuristics tests.
- **F-20**: Playwright Headless Renderer deterministic capture tests.
- **F-21**: Zero-Quota Testing Framework local fixture tests.
- **F-22**: Draft-07 JSON Schema Contracts strict validation tests.
- **F-23**: Unified CLI Interface parameter parsing tests.
- **F-24**: Self-Healing Recovery retryable failure handling tests.
