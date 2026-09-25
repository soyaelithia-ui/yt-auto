# Base de Conocimiento Técnica — yt-auto

> **Estado:** OFICIAL (Índice Central) | **Actualización:** 2026-09 | Catálogo consolidado de los 19 documentos técnicos en `docs/`.

## Catálogo de Documentación Técnica

| Dominio | Documento | Ámbito y Contenido Clave |
|---|---|---|
| **Pipeline & Media** | [ARQUITECTURA](ARQUITECTURA.md) | Arquitectura multiformato (9:16 y 16:9), persistencia SQLite WAL y leases. |
| | [FLUJO_VIDEOS](FLUJO_VIDEOS.md) | 13 etapas canónicas secuenciales (01 a 13) desde el lease a la publicación. |
| | [MULTICHANNEL_PIPELINE](MULTICHANNEL_PIPELINE.md) | Pipeline multi-canal, Multi-Act Director horizontal y stream-copy $\le 45$s. |
| | [DIRECTOR_SINGLE_PASS](DIRECTOR_SINGLE_PASS.md) | Ensamble FFmpeg en un solo paso, matriz de codificación y stream-copy. |
| | [FFMPEG_LOW_CPU](FFMPEG_LOW_CPU.md) | Presupuesto estricto ($\le 2$ Cores, $\le 2.0$ GiB RAM) y Resource Work Refusal. |
| | [CANALES](CANALES.md) | Perfiles modulares (`config/channels/`), taxonomía y variables genéricas. |
| **Operación e Infra** | [OPERACION](OPERACION.md) | Manual operativo: CLI unificado (`main.py`), Systemd daemons y Docker. |
| | [CONFIGURACION_SECRETOS](CONFIGURACION_SECRETOS.md) | Inventario de variables de entorno, perfiles y preflight checks. |
| | [INTEGRACIONES_Y_SERVICIOS](INTEGRACIONES_Y_SERVICIOS.md) | Contratos de API: Telegram Bot local, YouTube API v3, Drive y FFmpeg. |
| | [MCP](MCP.md) | Servidor Model Context Protocol: 9 herramientas, 3 recursos y 3 prompts. |
| **Agentes e IA** | [AGENTES_IA_Y_POLITICA](AGENTES_IA_Y_POLITICA.md) | Política AI-First, modelo canónico Gemini y 6 módulos activos en `src/agents/`. |
| **Evolución Visual** | [PLAN_MAESTRO_PIPELINE_VISUAL](PLAN_MAESTRO_PIPELINE_VISUAL.md) | Plan maestro visual, matriz de componentes e hitos de transición. |
| | [PROPUESTA_EVOLUCION_PIPELINE_VISUAL](PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md) | Hoja de ruta visual, arquetipos y narrativa de 4 a 8 actos. |
| **Gobernanza Calidad** | [POLITICA_GOBERNANZA_ANTI_REGRESION](POLITICA_GOBERNANZA_ANTI_REGRESION.md) | 6 invariantes de calidad, suite REG-01 a REG-14 y work refusal. |
| | [POLITICA_CATALOGO_CI](POLITICA_CATALOGO_CI.md) | Política de assets en CI vs producción y contención de seeds sintéticos. |
| | [visual-assets-policy](visual-assets-policy.md) | Estándares de loops limpios, cuarentena y filtros de elegibilidad. |
| **Diagnóstico & Ref** | [TROUBLESHOOTING](TROUBLESHOOTING.md) | Diagnóstico rápido de fallos, causas raíz y comandos de mitigación. |
| | [REFERENCIAS_Y_VERSIONES](REFERENCIAS_Y_VERSIONES.md) | Versiones fijadas (Python 3.12+, FFmpeg 6.1+, SQLite) y enlaces upstream. |
| | [README](README.md) | Índice central y mapa de navegación del sistema documental. |

## Navegación por Rol
- **Desarrollo**: [ARQUITECTURA](ARQUITECTURA.md) · [FLUJO_VIDEOS](FLUJO_VIDEOS.md) · [MULTICHANNEL_PIPELINE](MULTICHANNEL_PIPELINE.md) · [DIRECTOR_SINGLE_PASS](DIRECTOR_SINGLE_PASS.md) · [CANALES](CANALES.md)
- **Operaciones**: [OPERACION](OPERACION.md) · [CONFIGURACION_SECRETOS](CONFIGURACION_SECRETOS.md) · [INTEGRACIONES_Y_SERVICIOS](INTEGRACIONES_Y_SERVICIOS.md) · [TROUBLESHOOTING](TROUBLESHOOTING.md)
- **IA & Calidad**: [AGENTES_IA_Y_POLITICA](AGENTES_IA_Y_POLITICA.md) · [MCP](MCP.md) · [POLITICA_GOBERNANZA_ANTI_REGRESION](POLITICA_GOBERNANZA_ANTI_REGRESION.md) · [FFMPEG_LOW_CPU](FFMPEG_LOW_CPU.md)
