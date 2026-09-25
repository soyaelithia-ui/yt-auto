# Sistema Unificado de Automatización de YouTube — yt-auto

> **Repositorio:** [github.com/soyaelithia-ui/yt-auto](https://github.com/soyaelithia-ui/yt-auto) | Producción y publicación automatizada multi-canal.

Automatización de **YouTube Shorts (9:16)** y **Videos Largos (16:9, 10+ min)** en español, revisión interactiva en Telegram (`review`), respaldo Google Drive y control en SQLite WAL.

## 📚 Base de Conocimiento Central
Índice completo y navegación: [`docs/README.md`](docs/README.md).
[ARQUITECTURA](docs/ARQUITECTURA.md) · [FLUJO_VIDEOS](docs/FLUJO_VIDEOS.md) · [MULTICHANNEL_PIPELINE](docs/MULTICHANNEL_PIPELINE.md) · [OPERACION](docs/OPERACION.md) · [CONFIGURACION_SECRETOS](docs/CONFIGURACION_SECRETOS.md) · [INTEGRACIONES_Y_SERVICIOS](docs/INTEGRACIONES_Y_SERVICIOS.md) · [AGENTES_IA_Y_POLITICA](docs/AGENTES_IA_Y_POLITICA.md) · [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) · [REFERENCIAS_Y_VERSIONES](docs/REFERENCIAS_Y_VERSIONES.md) · [MCP](docs/MCP.md)

## 🌟 Canales y Carriles de Producción (`config/lanes.json`)

| Canal | Carril (`--lane`) | Formato | Tipo Historia | Estado | Cadencia |
|---|---|---|---|---|---|
| **Horror** | `horror-scp-shorts` | 9:16 (`1080x1920`) | `scp` | Activo | 1 c/10m (offset 0s, 6/h) |
| **Horror** | `horror-horror-long` | 16:9 (`1920x1080`) | `horror` | Activo | 1 c/60m (offset 0s, 1/h) |
| **Drama** | `drama-drama-shorts` | 9:16 (`1080x1920`) | `reddit_aita` | Activo | 1 c/10m (offset 300s, 6/h) |
| **Drama** | `drama-aita-long` | 16:9 (`1920x1080`) | `reddit_aita` | Activo | 1 c/60m (offset 1800s, 1/h) |
| **SciFi** | `scifi-singularity-shorts` | 9:16 (`1080x1920`) | `scifi` | Preconfigurado | Intercalado según demanda |
| **SciFi** | `scifi-singularity-long` | 16:9 (`1920x1080`) | `scifi` | Preconfigurado | Intercalado según demanda |

- **Cadencia Agregada**: 12 Shorts/h (1 c/5m alternando) y 2 Videos Largos/h (1 c/30m alternando).
- **Rendimiento**: Stream-copy (`-c:v copy`) en <5s (Shorts) y $\le 45$s (Longs) bajo $\le 2$ Cores y $\le 2.0$ GiB RAM.

## 🚀 Inicio Rápido con CLI Unificado

```bash
# Preflight y listado de carriles
python3 main.py run --preflight && python3 main.py lanes

# Simulación dry-run puntual o ejecución real
python3 main.py run --lane horror-scp-shorts --dry-run
python3 main.py run --lane horror-scp-shorts

# Diagnóstico, colas y catálogo de loops
python3 main.py status && python3 main.py queue list
python3 main.py loop list && python3 main.py loop audit

# Daemons de producción y servidor MCP
python3 main.py daemon --interval 60
python3 main.py mcp
```

## 🎨 Motor Visual FFmpeg (100% Asset-Based)
- **Loops & Stream-Copy (`LoopVideoEngine`)**: Concat demuxer + `-c:v copy` sobre loops maestros H.264 (`assets/loops/`).
- **Multi-Act Director (`director_assembly.py`)**: 4 a 8 actos narrativos con soft muxing `mov_text`.
- **Cero Procedural**: Cero WebGL, shaders WGSL o canvas2d. Fail-closed temprano con `CatalogAssetNotFoundError`.

## 🤖 Arnés Multi-Agente (`src/agents/`)
Arquitectura de 6 módulos canónicos respaldados por `gemini-3.8-flash-high`:
- `base_agent.py` (`ProgrammaticAgent`, circuit breaker) · `story_director.py` (curación y pacing) · `atmospheric_director.py` (atmósfera y arquetipos) · `seo_optimizer.py` (packaging algorítmico) · `video_qa.py` (auditoría visual/audio) · `translator.py` (traducción adaptativa).

## 🔌 Servidor MCP Oficial (Model Context Protocol)
Servidor MCP (`src/mcp/`) para orquestación e inspección por IA (`python3 main.py mcp`):
- **9 Tools**: `system_preflight`, `list_lanes`, `get_lane_info`, `query_loop_catalog`, `audit_loop_catalog`, `run_pipeline_dry_run`, `get_system_status`, `manage_queue`, `verify_integrity`.
- **3 Resources**: `channels://{channel_name}/config`, `lanes://catalog`, `system://health`.
- **3 Prompts**: `preflight_diagnostics`, `channel_incident_analysis`, `video_qa_review`.
