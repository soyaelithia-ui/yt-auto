# Base de Conocimiento Técnica — yt-auto

> **Estado:** OFICIAL (Índice Central)  
> **Repositorio Oficial:** [https://github.com/Ade-ia2005/yt-auto.git](https://github.com/Ade-ia2005/yt-auto.git)  
> **Gobernanza:** Repositorio privado para infraestructura, producción y publicación automatizada multi-canal.  
> **Última actualización:** 2026-09  

Índice y mapa de navegación para el sistema de producción automatizada de videos de YouTube (`yt-auto` + `review`).

---

## 1. Convenciones de Estado

- **`OFICIAL`**: Confirmado en especificaciones y documentación de proveedores oficiales (Google, Telegram, FFmpeg, YouTube).
- **`REPOSITORIO`**: Confirmado mediante código fuente, esquemas SQLite o suites de pruebas automatizadas.
- **`RECOMENDACIÓN`**: Buenas prácticas operativas y de arquitectura.
- **`HISTÓRICO`**: Registros de auditorías previas y versiones archivadas (`docs/archive/2026-08/`).

---

## 2. Mapa de Documentación Activa

| Documento | Ámbito y Contenido Clave |
|---|---|
| [ARQUITECTURA](ARQUITECTURA.md) | Diseño multiformato (Shorts 9:16 y Longform 16:9), persistencia SQLite WAL y máquina de estados. |
| [PLAN_ARQUITECTURA_V3_1](PLAN_ARQUITECTURA_V3_1.md) | Plan maestro de arquitectura v3.1: Resiliencia de sesiones, reaper de PIDs, reconciliador 2PC y audio en RAM. |
| [FLUJO_VIDEOS](FLUJO_VIDEOS.md) | Las 13 etapas canónicas de producción, desde la extracción hasta la publicación. |
| [MULTICHANNEL_PIPELINE](MULTICHANNEL_PIPELINE.md) | Especificaciones visuales, perfiles de canal (`moku`, `aelithia`), márgenes y renderizado zero-copy. |
| [OPERACION](OPERACION.md) | Manual operativo: CLI unificado (`main.py`), Systemd, Docker Compose, respaldos y recuperación. |
| [CONFIGURACION_SECRETOS](CONFIGURACION_SECRETOS.md) | Inventario de variables de entorno `.env`, perfiles de ejecución (`prod`, `cli`, `test`) y preflight. |
| [INTEGRACIONES_Y_SERVICIOS](INTEGRACIONES_Y_SERVICIOS.md) | Contratos de APIs externas: Telegram Bot API (servidor local 2 GB), publicación por sesión/cookies, Drive y FFmpeg. |
| [AGENTES_IA_Y_POLITICA](AGENTES_IA_Y_POLITICA.md) | Política AI-First y fail-closed, arnés `agy` / SDK, modelos canónicos `gemini-3.8-flash-high` / `gemini-3.7-flash` y agentes por rol. |
| [TROUBLESHOOTING](TROUBLESHOOTING.md) | Matriz de diagnóstico rápido de errores, causas raíz, rotación de cookies y procedimientos de mitigación. |
| [REFERENCIAS_Y_VERSIONES](REFERENCIAS_Y_VERSIONES.md) | Versiones fijadas de binarios, dependencias de Python/Node y referencias primarias oficiales. |
| [POLITICA_CATALOGO_CI](POLITICA_CATALOGO_CI.md) | Política CI vs prod del catálogo: seed sintético solo en tests; sin inventar media en producción; `visual_bank` cruzado con disco. |
| [visual-assets-policy](visual-assets-policy.md) | Scenery/loops limpios vs title cards; quarantine; guards `is_eligible_background_asset` + tests. |

---

## 3. Consulta Rápida por Rol

- **Desarrollo y Pipeline**: [ARQUITECTURA.md](ARQUITECTURA.md) · [FLUJO_VIDEOS.md](FLUJO_VIDEOS.md) · [MULTICHANNEL_PIPELINE.md](MULTICHANNEL_PIPELINE.md) · [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md) · [visual-assets-policy.md](visual-assets-policy.md) · [INTEGRACIONES_Y_SERVICIOS.md](INTEGRACIONES_Y_SERVICIOS.md).
- **Operación y SysAdmin**: [OPERACION.md](OPERACION.md) · [CONFIGURACION_SECRETOS.md](CONFIGURACION_SECRETOS.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- **Inteligencia Artificial**: [AGENTES_IA_Y_POLITICA.md](AGENTES_IA_Y_POLITICA.md).
- **Auditoría y Dependencias**: [REFERENCIAS_Y_VERSIONES.md](REFERENCIAS_Y_VERSIONES.md).

---

## 4. Archivo Histórico

Documentos de auditorías pasadas, canarios y propuestas preliminares se encuentran consolidados en la documentación técnica oficial.
