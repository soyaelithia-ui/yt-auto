# Agentes Nativos de IA, Modelos y Política AI-First

> **Estado:** OFICIAL / PRODUCCIÓN | **Actualización:** 2026-09 | Arquitectura en `src/agents/` y conmutación de cuotas.

## 1. Política AI-First y Conmutación por Cuota (Graceful Fallback)

Las tareas creativas y semánticas se ejecutan con IA vía Antigravity CLI (`gemini-3.8-flash-high`). Ante saturación (429, `RESOURCE_EXHAUSTED` o circuit breaker abierto), el sistema activa enfriamiento de 300s y conmuta a respaldos procedurales (`_procedural_fallback_story`, `_deterministic_seo`). El renderizado FFmpeg (`LoopVideoEngine`) y SQLite son 100% deterministas locales.

## 2. Modelo de IA Canónico

| Identificador | Rol en el Sistema | Estado |
|---|---|---|
| **`gemini-3.8-flash-high`** | Modelo canónico exclusivo para todos los agentes nativos en `src/agents/` bajo arnés `agy`. | Activo / Oficial |

## 3. Módulos Canónicos de Agentes (`src/agents/`)

```text
src/agents/
├── base_agent.py           # ProgrammaticAgent, CircuitBreaker, AgyStreamClient y AgentSaturationError
├── story_director.py       # StoryDirectorAgent (curación narrativa) y StoryInvestigatorAgent (fuentes)
├── atmospheric_director.py # AtmosphericDirectorAgent (atmósfera visual y categorías de loop)
├── seo_optimizer.py        # SeoOptimizerAgent (packaging YouTube, tags, descripciones y CTR)
├── video_qa.py             # VideoQAAgent (auditoría automatizada de luminancia y black frames)
└── translator.py           # TranslatorAgent (adaptación cultural y traducción multi-idioma)
```

### Funciones e Interfaces Programáticas
- **`base_agent.py` (`ProgrammaticAgent`)**: Arnés persistente NDJSON (`stream-json`) del CLI oficial `agy`, fallback a SDK (`USE_ANTIGRAVITY_SDK=1`), volumen `yt_agy_home` y aislamiento `CircuitBreaker.get(instance_id)`.
- **`story_director.py` (`StoryDirectorAgent`, `StoryInvestigatorAgent`)**: Curación en 4–8 actos, tension-curve pacing, extracción Reddit/SCP y adaptación de longitud al carril.
- **`atmospheric_director.py` (`AtmosphericDirectorAgent`)**: Mapeo de tono temático a categorías canónicas (`dark_ambient`, `cosmic_horror`) y resolución de arquetipos visuales.
- **`seo_optimizer.py` (`SeoOptimizerAgent`)**: Fórmulas de retención algorítmica, 3 títulos virales A/B, descripción estructurada con timestamps, tags y prompts de miniatura.
- **`video_qa.py` (`VideoQAAgent`)**: Inspección automatizada de luminancia, detección de fotogramas negros, integridad de audio EBU R128 y verificación perceptual.
- **`translator.py` (`TranslatorAgent`)**: Traducción y adaptación cultural de fuentes manteniendo el tono y la sincronización de ritmo.

## 4. Política Anti-Filler y Cláusula de Negativa

- **Anti-Filler SSOT**: Fondos de video exclusivamente de loops offline o scenery limpio (Ken Burns `zoompan`). Prohibido stock genérico o title cards con HUD horneado ([visual-assets-policy.md](visual-assets-policy.md), [ARQUITECTURA.md](ARQUITECTURA.md)). Emblemas institucionales en SVG vectorial.
- **Cláusula de Negativa (Kill Switch)**: Cada 25 commits o antes de producción, ejecutar `./scripts/verify_integrity.sh`. Si se violan invariantes, el agente DEBE NEGARSE A TRABAJAR ([POLITICA_GOBERNANZA_ANTI_REGRESION.md](POLITICA_GOBERNANZA_ANTI_REGRESION.md)).
