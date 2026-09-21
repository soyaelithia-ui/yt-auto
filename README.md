# Sistema Unificado de Automatización de YouTube — yt-auto

> **Repositorio Oficial:** [https://github.com/Ade-ia2005/yt-auto.git](https://github.com/Ade-ia2005/yt-auto.git)  
> **Gobernanza:** Repositorio privado para infraestructura, producción y publicación automatizada multi-canal.

Sistema de producción y publicación automatizada para **YouTube Shorts verticales (9:16)** y **Videos Largos (16:9, 10+ min)** en español, con revisión interactiva en Telegram (`review`), respaldo verificado en Google Drive y control atómico en SQLite WAL.

---

## 📚 Base de Conocimiento

Índice completo y navegación por rol: [`docs/README.md`](docs/README.md).

| Documento | Contenido Principal |
|---|---|
| [ARQUITECTURA](docs/ARQUITECTURA.md) | Diseño multi-carril, persistencia SQLite WAL y máquina de estados. |
| [FLUJO_VIDEOS](docs/FLUJO_VIDEOS.md) | Las 13 etapas canónicas de producción, del claim a la publicación. |
| [MULTICHANNEL_PIPELINE](docs/MULTICHANNEL_PIPELINE.md) | Especificaciones visuales, perfiles de canal y entrega zero-copy. |
| [OPERACION](docs/OPERACION.md) | Manual operativo: CLI unificado (`main.py`), Systemd, Docker y respaldos. |
| [CONFIGURACION_SECRETOS](docs/CONFIGURACION_SECRETOS.md) | Inventario de variables de entorno `.env` y validación preflight. |
| [INTEGRACIONES_Y_SERVICIOS](docs/INTEGRACIONES_Y_SERVICIOS.md) | Contratos de APIs: Telegram Bot API (2 GB local), YouTube v3, Drive y FFmpeg. |
| [AGENTES_IA_Y_POLITICA](docs/AGENTES_IA_Y_POLITICA.md) | Política AI-First fail-closed, arnés `agy` y agentes por rol. |
| [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | Matriz de diagnóstico rápido de errores operativos. |
| [REFERENCIAS_Y_VERSIONES](docs/REFERENCIAS_Y_VERSIONES.md) | Versiones fijadas de paquetes, binarios y referencias oficiales. |
| [MCP](docs/MCP.md) | Manual oficial del servidor MCP: tools, resources, prompts y SSOT. |

---

## 🌟 Canales y Carriles de Producción (Lanes)

| Canal | Carril (`--lane`) | Enfoque Narrativo | Orientación y Formato | Plantilla Visual | Perfil de Voz TTS | Cadencia |
|---|---|---|---|---|---|---|
| **TERROR / HORROR** (`horror`, `config/channels/horror.json`) | `horror-scp-shorts` | Anomalías SCP Foundation | Vertical 9:16 (`1080x1920`, 60–180s) | `shorts_creepypasta` | `es-ES-AlvaroNeural` | 1 c/10m (offset 0s, 6/h) |
| **DRAMA / RELACIONES** (`drama`, `config/channels/drama.json`) | `drama-shorts` | Dilemas Morales / AITA | Vertical 9:16 (`1080x1920`, 60–180s) | `shorts_drama` | `es-MX-DaliaNeural` | 1 c/10m (offset 300s, 6/h) |
| **TERROR / HORROR** (`horror`, `config/channels/horror.json`) | `horror-long` | Terror / Creepypastas | Horizontal 16:9 (`1920x1080`, ≥600s) | `creepypasta` | `es-ES-AlvaroNeural` | 1 c/60m (offset 0s, 1/h) |
| **DRAMA / RELACIONES** (`drama`, `config/channels/drama.json`) | `drama-aita-long` | Drama / Relatos AITA | Horizontal 16:9 (`1920x1080`, ≥600s) | `aita` | `es-MX-DaliaNeural` | 1 c/60m (offset 1800s, 1/h) |

- **Cadencia Intercalada**: 12 Shorts/h (1 c/5m) y 2 Videos Largos/h (1 c/30m) alternando los canales de Terror y Drama.
- **Rendimiento y Narrativa**: Stream-copy (`-c:v copy`) en <5s; narración en primera persona sin handles ni CTAs.

---

## 🚀 Inicio Rápido con CLI Unificado

```bash
# 1. Verificación de entorno y credenciales (Preflight)
python3 main.py run --preflight

# 2. Listar carriles configurados y estado de planificación
python3 main.py lanes

# 3. Prueba sintética ultrarrápida (simulación dry-run sin consumo de cuotas)
python3 main.py run --lane horror-scp-shorts --dry-run

# 4. Ejecución puntual de pipeline en producción por carril
python3 main.py run --lane horror-scp-shorts  # o horror-long / drama-aita-long

# 5. Estado de salud general y colas
python3 main.py status
python3 main.py queue list

# 6. Catálogo de bucles de video (FFmpeg stream-copy)
python3 main.py loop list
python3 main.py loop audit

# 7. Autenticación y diagnóstico de Google (YouTube v3 & Drive)
python3 main.py auth check --channel horror

# 8. Daemon continuo multi-carril autónomo
python3 main.py daemon --interval 60

# 9. Servidor MCP oficial (Model Context Protocol stdio / SSE)
python3 main.py mcp
```

---

## 🎨 Motor Visual FFmpeg y Catálogo Local de Bucles

El stack visual de producción es **100% basado en assets y FFmpeg nativo** (cero navegadores, cero procedural):
- **Modo beats / loop** (`LoopVideoEngine`): concat demuxer + **`-c:v copy`** sobre loops maestros pre-renderizados.
- **Modo director / multi-escena** (`MultiSceneCompositor`): Ken Burns fotográfico (`zoompan`) con stream-copy trim + concat demuxer (`-c:v copy`).
- **Catálogo de bucles y assets** (`LoopCatalogRepository` + `data/loop_catalog.db`): loops maestros (`assets/loops/`) y overlays pre-renderizados. Fail-closed con `CatalogAssetNotFoundError`.
- **Temáticas canónicas**: `cosmic_horror`, `dark_forest`, `dark_ambient`, `tactical_chamber`, `monsters`, `space_abyss`, `classified_terminal`, `drama`.
- **Zero Procedural**: Shaders WGSL, canvas y navegadores erradicados. Codificación fallback: `RENDER_PRESET=veryfast`.

> [!NOTE]
> `python3 manage.py` reenvía de forma transparente al CLI unificado. Ver [docs/OPERACION.md](docs/OPERACION.md).

---

## 🤖 Arnés Antigravity Multi-Agente (6 Agentes Especializados)

Pipeline de 6 agentes desacoplados bajo contratos JSON Schema y CLI local `agy` (`gemini-3.8-flash-high`):
- **Producción Narrativa y Visual**: Script Curator (retención/gancho), Art Director (Rec.709) y Scene Planner (`SceneManifestV2`).
- **Control de Calidad y SEO**: Forensic QA (EBU R128), Image Auditor (anti-filler) y SEO Optimizer (títulos virales y tags).

---

## 🛠️ Herramientas de Desarrollo y Diagnóstico (`dev/`)

- `python3 dev/test_pipeline_harness.py`: Diagnóstico integral Zero-Quota del arnés y contratos JSON.
- `python3 dev/produce_batch.py --count 3`: Producción en lote multi-canal (`horror`, `drama`).
- `python3 dev/run_telegram_bot.py --autopilot`: Bot interactivo en segundo plano con AutoPilot 24/7.
- `python3 dev/audit_assets.py --topic "SCP-2000"`: Veeduría independiente de activos contra la política anti-filler.

---

## 🔒 Seguridad, Revisión y Política AI-First

1. **Revisión & Despacho**: Veredicto determinista (`CodeReviewVerdict`), compuertas QA y Telegram local (`:8081`, hasta 2 GB zero-copy).
2. **Auto-Publicación**: Ventana configurable vía `AUTO_PUBLISH_TIMEOUT_HOURS` (default 24h); barrido con `main.py queue sweep`.
3. **Política AI-First**: Agentes bajo arnés Antigravity (`gemini-3.8-flash-high`); renderizado de producción FFmpeg stream-copy y persistencia determinista local. Cero navegadores y cero generadores procedurales.

---

## 🔌 Servidor MCP Oficial (Model Context Protocol)

Servidor MCP (`src/mcp/`, SDK v2.2.0) para orquestación e inspección asistida por IA sobre transporte stdio / SSE:
- **Tools (9)**: `system_preflight`, `list_lanes`, `get_lane_info`, `query_loop_catalog`, `audit_loop_catalog`, `run_pipeline_dry_run`, `get_system_status`, `manage_queue`, `verify_integrity`.
- **Resources (3)**: `channels://{channel_name}/config`, `lanes://catalog`, `system://health`.
- **Prompts (3)**: `preflight_diagnostics`, `channel_incident_analysis`, `video_qa_review`.
- **Ejecución y Configuración**: `python3 main.py mcp` o `python3 -m src.mcp`. Plantillas en `mcp_config.json` y [docs/MCP.md](docs/MCP.md).
