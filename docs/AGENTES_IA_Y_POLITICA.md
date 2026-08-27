# Agentes Nativos de IA, Modelos y Política AI-First

> **Estado:** OFICIAL / PRODUCCIÓN  
> **Última actualización:** 2026-08  

Directivas de inteligencia artificial generativa, arquitectura de agentes en `src/agents/` y políticas de failover.

---

## 1. Política AI-First y Falla Cerrada (Fail-Closed)

> [!IMPORTANT]
> **Principio Fundamental**: Las tareas creativas y semánticas (curación y estructuración de guiones, traducción adaptativa y optimización SEO) DEBEN ser ejecutadas exclusivamente por modelos de IA. Si la cadena de proveedores se agota por cuotas o saturación, el sistema **falla cerrado** elevando `AIProviderChainExhausted` para reintentar tras enfriamiento.

El renderizado FFmpeg con `LoopVideoEngine`, subtítulos ASS, miniaturas y operaciones de base de datos son **100% código determinista local**.

---

## 2. Catálogo de Modelos de Gemini

| Identificador | Rol en el Sistema | Estado |
|---|---|---|
| **`gemini-3.7-flash`** | **Modelo Canónico Primario** para agentes nativos en `src/agents/` y arnés CLI `agy`. | Activo / Predeterminado |
| **`gemini-3.6-flash`** | Modelo secundario de alta velocidad y compatibilidad en arnés CLI. | Activo / Compatible |
| **`gemini-2.5-flash`** | Proveedor secundario de contingencia vía API REST. | Activo / Failover |
| **`gemini-1.5-flash`** | Fallback terciario en contingencias. | Legacy / Activo |
| **`gemini-2.0-flash`** | Descomisionado por Google. | **Retirado / Prohibido** |

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
   - Gestiona el arnés del CLI `agy` y SDK de Antigravity.
   - Aplica aislamiento de sesión en `.bot_home/.gemini/antigravity-cli` mediante `ANTIGRAVITY_AGENTS_APP_DATA_DIR`.
   - Circuit breaker integrado para suspender llamadas ante saturación (`AgentSaturationError`).
2. **`CinematicScriptCuratorAgent` (`script_curator.py`)**:
   - Estructura guiones en 4 actos con gancho inicial (0-3s), sincronización de pausas dramáticas y franja segura de subtitulado.
3. **`ArtDirectorMoodAgent` (`art_director.py`)**:
   - Define el tratamiento estético cinemático, matrices de color y comportamientos de cámara procedural.
4. **`ScenePlannerCompositorAgent` (`scene_planner.py`)**:
   - Ensambla el manifiesto canónico `SceneManifestV2` integrando capas de Three.js, audio y subtítulos ASS.
5. **`VisualAudioQAAuditorAgent` (`qa_auditor.py`)**:
   - Aplica filtros de control de calidad EBU R128, correlación estéreo, moov atom y ratios de negro antes de la publicación.
6. **`ImageAuditorAgent` (`image_auditor.py`)**:
   - **Política Anti-Filler**: 100% de fondos y sujetos animados deben ser generados proceduralmente (código WebGL/Canvas). Prohíbe terminantemente fotos de stock estáticas (`DISCARDED_GENERIC_FILLER`).
   - Autoriza exclusivamente logotipos de marca o emblemas institucionales oficiales (`APPROVED_REFERENCE`) para proyección en insignias overlay no invasivas (SVG o Canvas).
7. **`SeoOptimizerAgent` (`seo_optimizer.py`)**:
   - Fórmulas algorítmicas de retención: 3 títulos virales para A/B testing, descripción con marcas de tiempo formateadas, tags optimizados, hashtags virales, comentario fijado para disparar interacción comunitaria y blueprints de miniaturas.

---

## 4. Política Anti-Filler y Pureza Procedural

> [!IMPORTANT]
> **Directiva Estricta de Calidad Visual**:
> - Todo el contenido animado de fondo debe originarse en motores procedurales WebGL/Canvas (código puro).
> - Se prohíbe el uso de imágenes fijas de stock para 'rellenar' el video.
> - Si se requiere presentar entidades reales o marcas oficiales (ej. Fundación SCP, NASA, MIT, OpenAI), deben proyectarse como **badges vectoriales o emblemas en canvas** respetando márgenes seguros y opacidad calibrada.
