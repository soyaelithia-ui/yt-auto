# Original User Request

## 2026-09-02T08:42:17Z

This is a single self-contained fix; keep it small and focused.

Reconcile and consolidate recent codebase changes: unify contracts and duplicate constants into a single source of truth (SSOT), align function signatures, remove dead code and temporary files, and ensure 100% of the test suite passes green without introducing new features.

Working directory: /home/moku/projects/yt-auto
Integrity mode: development

## Requirements

### R1. Single Source of Truth (SSOT) Consolidation
Unify overlapping contracts, schemas, and duplicate constants across modules into canonical definitions without changing external public interfaces required by the system.

### R2. Function Signature Alignment & Dead Code Removal
Align mismatched function and method signatures across updated modules, remove orphaned functions, deleted template references, dead code, and temporary build/test artifacts.

### R3. Test Suite Integrity & 100% Green Verification
Ensure all active unit, integration, and E2E tests in the test suite pass with zero regressions or skipped failures, strictly without adding new business features or changing expected behavior.

## Acceptance Criteria

### Test Verification
- [ ] `.venv/bin/pytest` passes 100% with 0 failures and 0 errors across all active test suites.

### Codebase Cleanliness
- [ ] No duplicate constant definitions or duplicate schema contracts remaining in `src/` and `schemas/`.
- [ ] All deleted/deprecated media templates or temporary scratch scripts are properly unlinked and pruned from active imports.
- [ ] No new functional feature or breaking behavioral change introduced.

## 2026-09-02T15:39:16Z

This is a single self-contained fix; keep it small and focused. Refactor hardcoded legacy channel handles, references to obsolete '@Moku' branding, and update repository configuration and project policies to use standard environment-driven variables.

Working directory: /home/moku/projects/yt-auto
Integrity mode: development

## Requirements

### R1. Dynamic Channel Identifiers & Metadata Resolution
Replace all hardcoded '@Moku' and '@MokuRedit' references across runtime configuration (`src/branding.py`, `src/config.py`, prompt templates, dev scripts) with dynamic resolution backed by channel configuration (`config/channels/{channel}.json`) and standard environment variables (`CHANNEL_HANDLE`, `CHANNEL_URL`, `CHANNEL_NAME`). No channel identity should be hardcoded as global constants or default fallbacks.

### R2. Repository Settings & Project Policies Alignment
Synchronize project documentation, operational guides, and policy references with the current repository (`https://github.com/Ade-ia2005/yt-auto.git`), removing stale public/external handles and clarifying private repo governance.

### R3. Codebase Anti-Pattern & Hardcoding Audit
Audit and eliminate similar anti-patterns across `src/` and `review/`, ensuring URLs, branding tags, and channel-specific paths are parameterized rather than hardcoded.

## Acceptance Criteria

### Automated Codebase Audit
- [ ] A recursive case-insensitive search for `@Moku` or `@MokuRedit` in `src/` returns zero hardcoded runtime occurrences (excluding explicit channel config files in `config/channels/`).
- [ ] `src/branding.py` and `src/config.py` resolve channel handles, URLs, and watermarks dynamically from environment variables or channel config without hardcoded defaults to '@MokuRedit'.
- [ ] All documentation files (`README.md`, `docs/`) and policy guides reference `https://github.com/Ade-ia2005/yt-auto.git` and generic channel variables rather than obsolete handles.
- [ ] The full test suite passes with zero regressions:
  `.venv/bin/pytest tests/unit/ tests/integration/ -q`

## 2026-09-03T07:30:33Z

Reconciliar y alinear el repositorio yt-auto con GitHub `origin/main` (commit `acc279f`), purgar de raíz cualquier dependencia de navegadores headless (Playwright/Chromium) en el pipeline de video, eliminar documentación obsoleta resucitada y certificar que la suite de pruebas ejecute al 100% de forma determinista y sin consumo de cuota externa.

Working directory: /home/moku/projects/yt-auto
Integrity mode: development

## Requirements

### R1. Sincronización y Reconciliación con GitHub SSOT
- Alinear la rama principal local con `origin/main` (`acc279f`), integrando de forma limpia las modificaciones no confirmadas de shaders nativos WGSL (`src/media/native_procedural.py`, `src/media/shaders/maritime_lighthouse.wgsl`) y perfiles de Aelithia.
- Purgar de forma permanente los 5 documentos de arquitectura obsoletos resucitados en `docs/architecture/` (`01_DUAL_RENDERING_ENGINES.md` a `05_ZERO_QUOTA_TESTING_FRAMEWORK.md`).
- Limpiar y descartar el worktree desfasado `implement_grill_test_suite`.

### R2. Erradicación de Navegadores en Renderizado de Medios
- Garantizar que ningún comando del pipeline (`main.py loop`, `main.py run`, `LoopSynthesizerWorker`, `LoopVideoEngine`) importe o invoque `playwright` o `chromium` para la generación o ensamblado de video.
- Ratificar en `openspec/specs/media-processing-performance-policy/spec.md` la prohibición explícita del renderizado por navegador web en favor de FFmpeg nativo y shaders WGSL por GPU.

### R3. Certificación de la Suite de Pruebas y Cero Regresiones
- Ejecutar la suite completa de pruebas unitarias, de integración y E2E mediante `pytest`.
- Verificar que el 100% de las pruebas aprueben con 0 errores, 0 procesos residuales de Chromium y 0 consumo de cuotas de APIs externas.

## Verification Resources
- Suite de pruebas de shaders nativos: `tests/unit/test_native_procedural_uniforms.py`.
- Suite de dirección cinemática y storyboard: `tests/unit/test_cinematic_storyboard.py`.
- Suite de despacho multi-escena: `tests/integration/test_multiscene_dispatch.py`.
- Suite del motor de bucles FFmpeg: `tests/unit/test_loop_video_engine.py`.

## Acceptance Criteria

### Integridad de Código y Repositorio
- [ ] La rama `main` en `/home/moku/projects/yt-auto` coincide con `origin/main` (`acc279f`) más los commits de integración limpia.
- [ ] No existen archivos en `docs/architecture/0*.md`.
- [ ] `git status` en el repositorio principal queda limpio tras las confirmaciones de integración.

### Aislamiento de Medios y Rendimiento
- [ ] 0 archivos en `src/media/` o `src/cli/handlers/loop.py` invocan `playwright` para la composición de video.
- [ ] `main.py loop generate -c drama_aita -o horizontal --duration 3.0` sintetiza un bucle en menos de 2 segundos usando exclusivamente FFmpeg nativo sin lanzar Chromium.

### Suite de Pruebas y Certificación
- [ ] `pytest tests/unit/test_native_procedural_uniforms.py tests/unit/test_cinematic_storyboard.py tests/integration/test_multiscene_dispatch.py tests/unit/test_loop_video_engine.py` pasa al 100% (todos los tests en verde).
- [ ] La suite general del proyecto corre limpia sin bloqueos de base de datos (`database is locked`) ni excepciones de dependencias.

## 2026-09-07T19:33:24Z

Reparar y enriquecer integralmente la calidad visual y estética de los videos producidos en `yt-auto` (Shorts y Videos Largos), activando el catálogo existente de loops temáticos, restaurando subtítulos dinámicos estilizados y asegurando coherencia narrativa en los guiones con máxima eficiencia y bajo consumo de recursos.

Working directory: /home/moku/projects/yt-auto
Integrity mode: development

## Requirements

### R1. Activación e Indexación Exhaustiva del Catálogo de Loops Visuales
Indexar y verificar en la base de datos SQLite (`video_loops`) todos los bucles de video cinemáticos de alta calidad existentes en el repositorio (`assets/loops/horizontal/` y `assets/loops/vertical/`), organizados por canal (`moku`, `aelithia`) y categorías temáticas (`horror`, `dark_forest`, `cosmic_horror`, `drama`, `cozy_ambient`, etc.). Eliminar la dependencia exclusiva de los dos loops planos monocromáticos sintéticos (`loop_maritime_lighthouse_h` y `loop_arctic_desolation_v`), garantizando rotación automática y diversidad visual entre producciones.

### R2. Subtitulado Dinámico y Enriquecimiento Estético (Shorts y Longs)
Reactivar el flujo de subtitulado (`subtitles_active = True`) que fue desactivado arbitrariamente en `src/pipeline.py`. Implementar estilos tipográficos estéticos (fuente clara, stroke/sombra de alto contraste, ubicación equilibrada para 9:16 Shorts y 16:9 Longform). Añadir dinamismo visual ligero y eficiente (overlays cinemáticos sutiles, transiciones limpias entre escenas de 8-15s en videos largos según el `visual_plan.json` o gradación de color sin sobrecargar la CPU).

### R3. Coherencia Narrativa y Control de Calidad de Guiones
Auditar y afinar los generadores de historias y scrapers para garantizar coherencia temática estricta: progresión en 3 actos, coherencia psicológica de personajes, giros dramáticos convincentes y fluidez en español neutro (sin frases inconexas, rupturas tonales o muletillas repetitivas). Incorporar validación de coherencia narrativa previa a la síntesis TTS.

### R4. Eficiencia de Recursos, Estabilidad del Pipeline y Despliegue Bare-Metal
Todas las composiciones FFmpeg y procesos de generación deben ejecutarse con máxima eficiencia (preset rápido, multiplexación por stream-copy o filtros ligeros) garantizando tiempos de render contenidos (<5 min para shorts, <15 min para longs) sin fugas de memoria RSS, compatibilidad con la suite de pruebas unitarias existente (`pytest`) y preservando la operación bajo el supervisor Tmux (`./deploy/ctl.sh`).

## Acceptance Criteria

### [Catálogo y Variedad Visual]
- [ ] La tabla `video_loops` contiene indexados y verificados >50 bucles de video con categorización correcta para `moku` y `aelithia`.
- [ ] Los videos generados para `moku` y `aelithia` seleccionan loops contextuales diferentes por temática y rotan entre corridas sin reutilizar el mismo fondo plano.
- [ ] En videos largos (>10 min), el render cambia de fondo/escena periódicamente según el `visual_plan.json` en vez de mantener un único loop estático durante todo el metraje.

### [Estética y Subtítulos]
- [ ] Todos los Shorts generados muestran subtítulos legibles y estéticos sincronizados con el audio (`speech.wav`).
- [ ] Los videos no presentan pantallas vacías o monocromáticas sin elementos visuales o tipográficos.
- [ ] El tiempo de render por minuto de video no excede los límites presupuestados de CPU en bare-metal.

### [Coherencia de Guiones]
- [ ] Los guiones generados presentan estructura narrativa clara (inicio, desarrollo, clímax, desenlace) y superan la validación de coherencia sin incongruencias de trama.
- [ ] Vocabulario y tono adaptados al canal: terror/misterio inmersivo en Moku, dilemas morales y drama humano en Aelithia.

### [Integridad del Pipeline y Operación]
- [ ] La suite de pruebas de regresión (`pytest tests/unit/`) pasa al 100% (0 fallos).
- [ ] El demonio y el bot operan de manera ordenada en Tmux (`./deploy/ctl.sh status`).

