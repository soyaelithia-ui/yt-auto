# yt-auto Project Specification & Feature Traceability

Sistema modular de automatización de producción audiovisual para YouTube (Shorts 9:16 y Longform 16:9) con arquitectura desacoplada por agentes, motor procedural Three.js/WebGL y persistencia SQLite WAL.

## 📋 Matriz de Características (F-01 a F-24)

| ID | Módulo | Descripción Técnica |
|---|---|---|
| **F-01** | Multi-Lane Architecture | Canales independientes con perfiles aislados (`lanes.json`). |
| **F-02** | SQLite WAL Persistence | Transacciones atómicas, colas y bloqueos en base de datos local. |
| **F-03** | 13-Stage State Machine | Ciclo de vida estricto desde el claim inicial hasta la publicación. |
| **F-04** | Edge-TTS Voice Synthesis | Generación neuronal de voz multilocutor con ajuste de pitch y rate. |
| **F-05** | EBU R128 Audio Mastering | Normalización (-14 LUFS shorts / -16 LUFS long) y ducking sidechain. |
| **F-06** | Real-Time Procedural Engine | Motor Three.js/WebGL multiescena con 5 entornos PBR y sincronización temporal. |
| **F-07** | Dual-Engine Compositor | Motor híbrido cinemático 2.5D y procedural puro por código. |
| **F-08** | Dynamic Safe Area ASS Subtitles | Subtítulos karaoke adaptados a zonas seguras en 9:16 y 16:9. |
| **F-09** | Agent 1: Script Curator | Estructura dramática en actos y gancho de retención inicial (0-3s). |
| **F-10** | Agent 2: Art Director | Matriz de color Rec.709, iluminación volumétrica y partículas. |
| **F-11** | Agent 3: Scene Planner | Construcción y validación del manifiesto canónico `SceneManifestV2`. |
| **F-12** | Agent 4: Forensic QA Auditor | Auditoría automatizada de luminancia, congelamiento y LUFS. |
| **F-13** | Agent 5: Image Auditor | Veeduría Anti-Filler descartando stock genérico y validando esquemas técnicos. |
| **F-14** | Agent 6: SEO Optimizer | Optimización algorítmica de títulos A/B, tags, hashtags y miniaturas. |
| **F-15** | Telegram Interactive Bot | Bot de revisión con menús inline, telemetría y entrega local rápida. |
| **F-16** | Drive Backup & Verification | Respaldo verificado en Google Drive previo a publicación. |
| **F-17** | YouTube Data API v3 Upload | Publicación automatizada con metadatos y comentarios fijados. |
| **F-18** | AutoPilot Autonomous Scheduler | Planificador desatendido con cadencias configurables por carril. |
| **F-19** | Scenic Loop Detector | Clasificador heurístico de atmósferas y transiciones visuales. |
| **F-20** | Playwright Headless Renderer | Renderizado cuadro a cuadro determinista vía Chromium headless pipe. |
| **F-21** | Zero-Quota Testing Framework | Suite estratificada de pruebas locales sin consumo de cuotas LLM. |
| **F-22** | Draft-07 JSON Schema Contracts | Validación normativa de esquemas para todos los intercambios de datos. |
| **F-23** | Unified CLI Interface | Entrada principal `main.py` con subcomandos preflight, daemon y reportes. |
| **F-24** | Self-Healing Recovery | Mecanismos de reintento automático y recuperación ante fallos transitorios. |
