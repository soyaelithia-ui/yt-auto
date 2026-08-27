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
| **`gemini-3.6-flash`** | **Modelo Canónico Primario** para agentes nativos en `src/agents/` y arnés CLI `agy`. | Activo / Obligatorio |
| **`gemini-2.5-flash`** | Proveedor secundario de contingencia vía API REST. | Activo / Failover |
| **`gemini-1.5-flash`** | Fallback terciario en contingencias. | Legacy / Activo |
| **`gemini-2.0-flash`** | Descomisionado por Google. | **Retirado / Prohibido** |

---

## 3. Agentes Especializados por Rol (`src/agents/`)

```text
src/agents/
├── base_agent.py          # ProgrammaticAgent (Arnés base, circuit breaker y control de cuotas)
├── story_investigator.py  # StoryInvestigatorAgent (Curación de guiones y estructura narrativa)
├── translator.py          # TranslatorAgent (Traducción adaptativa y optimización SEO)
└── video_qa_agent.py      # VideoQAAgent (Auditoría visual opcional vía Gemini Vision)
```

### Funciones de los Agentes

1. **`ProgrammaticAgent` (`base_agent.py`)**:
   - Gestiona el arnés del CLI `agy` y SDK de Antigravity.
   - Aplica aislamiento de sesión en `.bot_home/.gemini/antigravity-cli` mediante `ANTIGRAVITY_AGENTS_APP_DATA_DIR`.
   - Circuit breaker integrado para suspender llamadas ante saturación (`AgentSaturationError`).
2. **`StoryInvestigatorAgent` (`story_investigator.py`)**:
   - Adapta y estructura relatos crudos en guiones con división de beats y ganchos de retención.
3. **`TranslatorAgent` (`translator.py`)**:
   - Traduce contenido extranjero a español neutro profesional, generando títulos y descripciones optimizados.
4. **`VideoQAAgent` (`video_qa_agent.py`)**:
   - Auditoría de visión opcional (`CODE_REVIEW_VISION_QA=1`) para análisis de calidad diagnóstica.
