# Agentes Nativos de IA, Modelos y Política AI-First

> **Estado:** OFICIAL / PRODUCCIÓN  
> **Última actualización:** 2026-09  

Directivas de inteligencia artificial generativa, arquitectura de agentes en `src/agents/` y políticas de failover.

---

## 1. Política AI-First y Falla Cerrada (Fail-Closed)

> [!IMPORTANT]
> **Principio Fundamental**: Las tareas creativas y semánticas (curación y estructuración de guiones, traducción adaptativa y optimización SEO) DEBEN ser ejecutadas exclusivamente por modelos de IA. Si la cadena de proveedores se agota por cuotas o saturación, el sistema **falla cerrado** elevando `AIProviderChainExhausted` para reintentar tras enfriamiento.

El renderizado FFmpeg con `LoopVideoEngine`, subtítulos ASS, miniaturas y operaciones de base de datos son **100% código determinista local**.

---

## 2. Modelo de IA Oficial

| Identificador | Rol en el Sistema | Estado |
|---|---|---|
| **`gemini-3.8-flash-high`** | **Modelo Canónico Exclusivo** para todos los agentes nativos en `src/agents/` bajo arnés CLI `agy`. | Activo / Oficial |

---

## 3. Agentes Especializados por Rol (`src/agents/`)

```text
src/agents/
├── base_agent.py          # ProgrammaticAgent (Arnés base Antigravity CLI agy, circuit breaker y control de cuotas)
├── script_curator.py      # CinematicScriptCuratorAgent (Agent 1: Guion de retención, beats narrativos y safe area)
├── art_director.py        # ArtDirectorMoodAgent (Agent 2: Paleta Rec.709, iluminación volumétrica y partículas)
├── scene_planner.py       # ScenePlannerCompositorAgent (Agent 3: Manifiesto canónico SceneManifestV2)
├── qa_auditor.py          # VisualAudioQAAuditorAgent (Agent 4: Auditoría forense EBU R128 LUFS y luminancia)
├── image_auditor.py       # ImageAuditorAgent (Agent 5: Veedor forense anti-filler y validación de insignias)
├── seo_optimizer.py       # SeoOptimizerAgent (Agent 6: Títulos virales A/B, tags, comentarios y miniaturas)
├── investigator.py        # StoryInvestigatorAgent (Investigación y curación profunda de historias)
└── translator.py          # TranslatorAgent (Traducción adaptativa de fuentes extranjeras)
```

### Funciones de los Agentes

1. **`ProgrammaticAgent` (`base_agent.py`)**:
   - Gestiona el arnés de ejecución nativo con cliente de streaming persistente NDJSON (`stream-json`) y SDK oficial `google-antigravity`.
   - Autenticación 100% nativa con cuota Pro mediante sesión OAuth (`antigravity-oauth-token`) sin necesidad de API keys.
   - Aislamiento Multi-Instancia: directorio AppData (`.bot_home_{instance_id}/.gemini/antigravity-cli`) y `CircuitBreaker.get(instance_id)` independientes por instancia para evitar colisiones y saturación cruzada.
   - Soporte de modulación de esfuerzo de razonamiento (`--effort low|medium|high`) y poda automática de trayectorias efímeras (`cleanup_ephemeral_sessions`).
2. **`CinematicScriptCuratorAgent` (`script_curator.py`)**:
   - Estructura guiones en 4 actos con gancho inicial (0-3s), sincronización de pausas dramáticas y franja segura de subtitulado.
   - Opera en `instance_id="pipeline_creative"` con esfuerzo `high` para máxima profundidad narrativa.
3. **`ArtDirectorMoodAgent` (`art_director.py`)**:
   - Define el tratamiento estético cinemático, matrices de color y comportamientos de cámara procedural.
4. **`ScenePlannerCompositorAgent` (`scene_planner.py`)**:
   - Ensambla el manifiesto canónico `SceneManifestV2` (arquetipos FFmpeg/híbrido, overlays, pacing, audio y subtítulos ASS). Los agentes emiten JSON; el motor de media decide píxeles.
5. **`VisualAudioQAAuditorAgent` (`qa_auditor.py`)**:
   - Aplica filtros de control de calidad EBU R128, correlación estéreo, moov atom y ratios de negro antes de la publicación.
6. **`ImageAuditorAgent` (`image_auditor.py`)**:
   - **Política Anti-Filler**: fondos de video = loops/catálogo FFmpeg o scenery limpio (Ken Burns `zoompan`); **no** hot path WebGPU/WebGL/Canvas. Prohíbe stock genérico y title cards pre-horneadas (`DISCARDED_GENERIC_FILLER`). Ver [visual-assets-policy.md](visual-assets-policy.md).
   - Autoriza exclusivamente logotipos de marca o emblemas institucionales oficiales (`APPROVED_REFERENCE`) como overlays vectoriales no invasivos (SVG / `resvg-py`).
7. **`SeoOptimizerAgent` (`seo_optimizer.py`)**:
   - Fórmulas algorítmicas de retención: 3 títulos virales para A/B testing, descripción con marcas de tiempo formateadas, tags optimizados, hashtags virales, comentario fijado para disparar interacción comunitaria y blueprints de miniaturas.

---

## 4. Política Anti-Filler (alineada al SSOT FFmpeg)

> [!IMPORTANT]
> **Directiva de Calidad Visual** (no contradice [ARQUITECTURA.md](ARQUITECTURA.md)):
> - Fondos de video: loops/catálogo FFmpeg o scenery limpio — **no** WebGL/Three.js/Canvas ni WebGPU en el hot path.
> - Prohibido rellenar con stock genérico o title cards con texto/HUD horneado. Clasificación: [visual-assets-policy.md](visual-assets-policy.md).
> - Marcas oficiales (SCP, NASA, etc.): badges/emblemas vectoriales (SVG), no scrapes de UI.

---

## 5. Cadencia de Verificación y Cláusula de Negativa (Kill Switch)

> [!CAUTION]
> **Obligación Profesional de Negativa**:
> Cada **25 commits** o antes de iniciar sesiones mayores y pipelines de producción, es mandatario ejecutar `./scripts/verify_integrity.sh`. Si se detecta cualquier worktree huérfano, import de navegador en renderizado o plano obsoleto, el agente **DEBE NEGARSE A TRABAJAR**, abortar la ejecución y alertar al operador.
>
> Ver especificación completa en [POLITICA_GOBERNANZA_ANTI_REGRESION.md](POLITICA_GOBERNANZA_ANTI_REGRESION.md).
