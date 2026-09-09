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

## PR #69 feature acceptance (verify_vps_github_status)
- 6 lanes; stream-copy multi-scene loop composition; honest precomputed QA; CHANNEL_THEMES channel isolation.

## 2026-09-09T20:28:35Z

Implementar y certificar las optimizaciones de rendimiento de hardware para eliminar cuellos de botella de renderizado y control de calidad (activando Stream-Copy con los videos pre-renderizados del catálogo de assets y sellando métricas en QA manifest), realizar la poda y unificación de worktrees para coordinación limpia, eliminar procesos huérfanos del host, actualizar la documentación técnica oficial (`docs/`), validar la integridad y suite de pruebas del proyecto, y coordinar la publicación de cambios mediante commits atómicos y push en la rama `analyze_system_performance_benchmark` en GitHub.

> [!NOTE]
> **Aclaración sobre Gobernanza y Política Anti-Procedural:**
> Los "loops de código" (shaders WGSL, WebGPU, Three.js, Canvas y generadores matemáticos por código) **fueron eliminados definitivamente en el commit `7114ca7` y siguen terminantemente prohibidos** bajo el Invariante 6. Esta tarea **NO revive ningún renderizador por código**. Se refiere exclusivamente al enlace simbólico hacia los **archivos de video físicos pre-renderizados (`*.mp4`) del catálogo de assets** (`/home/moku/projects/yt-auto/assets/loops/`) que no viajan en Git por estar en `.gitignore`.

Working directory: /home/moku/.gemini/antigravity-cli/worktrees/yt-auto/analyze_system_performance_benchmark
Integrity mode: development

## Requirements

### R1. Poda, Unificación y Gobernanza de Worktrees para Coordinación Limpia
Ejecutar y estandarizar la poda completa de worktrees derivados obsoletos mediante `scripts/agent_worktree.sh`, garantizando que únicamente persistan el checkout principal (`/home/moku/projects/yt-auto`) y el worktree activo de trabajo. Prunear los metadatos de Git (`git worktree prune`) para que cualquier nuevo agente opere sobre ramas frescas y coordinadas sin colisiones de ramas stale.

### R2. Enlace Idempotente del Catálogo de Videos Pre-renderizados en Worktrees
Actualizar `scripts/setup_worktree_env.sh` para enlazar de forma idempotente la carpeta de videos pre-renderizados del catálogo (`assets/loops`) y la base de datos de catálogo SQLite (`data/loop_catalog.db`) desde el repositorio principal (`$PRIMARY_ROOT`) hacia los worktrees derivados. Si en el worktree de destino ya existen carpetas esqueleto (`horizontal/`, `vertical/`), resolver de forma robusta la vinculación para que el motor de composición encuentre los archivos MP4 físicos de 1080p y active la ruta de stream-copy instantáneo (`-c:v copy`), sin re-renderizar fotogramas con CPU.

### R3. Certificación y Sellado de Métricas Visuales en el Manifiesto de Activos
Calcular y registrar de forma persistente en `assets/loops/bank_manifest.json` las métricas de calidad precalculadas (`longest_black_seconds` y `perceptual_luminance`) para cada uno de los videos maestros del catálogo, de modo que el motor de prepublicación (`validate_prepublication`) omita la decodificación redundante en vivo en `10_qa_gating`.

### R4. Protección de Hilos en Control de Calidad en Vivo
Establecer un límite de concurrencia (`-threads 2`) en los procesos FFmpeg de decodificación en vivo para detección de cuadros negros y análisis de luminancia en `src/core/quality.py`, evitando saturación del 100% de CPU en el host cuando se evalúen medios no certificados.

### R5. Limpieza de Procesos Huérfanos del Proyecto y del Host
Terminar de forma exhaustiva los procesos zombi y huérfanos del sistema host relacionados con el proyecto: instancias residuales de Chromium/Playwright (`ms-playwright`), procesos zombi de Python (runners de prueba y kernels huérfanos), procesos residuales de FFmpeg y workers descolgados, recuperando la memoria RAM física disponible del sistema.

### R6. Actualización de Documentación Oficial del Proyecto
Actualizar los documentos técnicos y manuales operativos en `docs/`:
1. `docs/OPERACION.md`: Documentar la gestión y poda de worktrees (`scripts/agent_worktree.sh`), la vinculación del catálogo en entornos derivados (`scripts/setup_worktree_env.sh`), y purgar cualquier referencia obsoleta legacy (p.ej. menciones a Three.js/Canvas/CSS en subcomandos de bucles).
2. `docs/FFMPEG_LOW_CPU.md`: Incorporar el contrato de limitación de hilos (`-threads 2`) en pasadas de validación y control de calidad visual (QA Gating) y la garantía de stream-copy para activos de catálogo certificados.
3. `docs/POLITICA_CATALOGO_CI.md`: Registrar el requisito de persistencia de métricas (`longest_black_seconds`, `perceptual_luminance`) en `bank_manifest.json` y el aprovisionamiento de assets en worktrees concurrentes.

### R7. Auditoría de Integridad y Suite Anti-Regresión
Ejecutar `./scripts/verify_integrity.sh` y la suite de pruebas unitarias (`pytest`), garantizando el cumplimiento estricto del Invariante 6 (cero generadores procedurales matemáticos/shaders), Invariante 4 (cero resurrección de docs de arquitectura obsoletos en `docs/architecture/0*.md`) y todas las directivas de seguridad y aislamiento de `AGENTS.md`.

### R8. Publicación y Coordinación en GitHub
Crear commits convencionales y atómicos (`fix: ...`, `perf: ...`, `docs: ...`) respetando los githooks (`.githooks/pre-commit`) y sincronizar los cambios mediante `git push` a la rama remota `origin/analyze_system_performance_benchmark` en GitHub.

## Acceptance Criteria

### Rendimiento y Gestión del Entorno
- [ ] Stale worktrees podados y eliminados; `scripts/agent_worktree.sh list` reporta únicamente el checkout primario y el worktree actual.
- [ ] Procesos huérfanos de Chromium/Playwright y runners de Python/FFmpeg eliminados del host, con memoria RAM recuperada.
- [ ] `scripts/setup_worktree_env.sh` vincula exitosamente los assets físicos de `assets/loops` y `data/loop_catalog.db`.
- [ ] Cero código procedural matemático, shaders WGSL o canvas introducidos (respeto estricto a Invariant 6).
- [ ] `LoopVideoEngine.get_loop_quality_metrics` devuelve un diccionario con `longest_black_seconds` y `perceptual_luminance` para los videos maestros de `bank_manifest.json`.
- [ ] `validate_prepublication` utiliza `report.facts["black_source"] == "precomputed_visual"` y no invoca `detect_long_black_frames` cuando el activo está certificado.
- [ ] Las llamadas de fallback de FFmpeg en `src/core/quality.py` incluyen explícitamente el argumento `-threads 2`.

### Documentación y Calidad
- [ ] `docs/OPERACION.md`, `docs/FFMPEG_LOW_CPU.md` y `docs/POLITICA_CATALOGO_CI.md` actualizados y alineados con la arquitectura actual.
- [ ] Ninguna documentación legacy resucitada en `docs/architecture/0*.md`.
- [ ] `./scripts/verify_integrity.sh` retorna código 0 (`HEALTHY`).
- [ ] La suite de pruebas unitarias relevantes (`test_zero_procedural_math_video_policy.py`, `test_catalog_asset_only_composition.py`, `test_ffmpeg_low_cpu_defaults.py`, etc.) pasa al 100%.
- [ ] Ningún archivo binario de video, audio temporal o archivo de clave/secreto se agrega al índice de Git.

### Git & GitHub
- [ ] Los commits locales pasan la verificación estricta de `.githooks/pre-commit`.
- [ ] La rama `analyze_system_performance_benchmark` queda sincronizada y actualizada en el repositorio remoto de GitHub (`origin`).
