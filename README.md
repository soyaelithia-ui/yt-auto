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

---

## 🌟 Canales y Carriles de Producción (Lanes)

| Canal | Carril (`--lane`) | Enfoque Narrativo | Orientación y Formato | Plantilla Visual | Perfil de Voz TTS |
|---|---|---|---|---|---|
| **MOKU** (`moku`, `config/channels/moku.json`) | `moku-scp-shorts` | Anomalías SCP Foundation | Vertical 9:16 (`1080x1920`, 60–180s) | `shorts_creepypasta` | `es-ES-AlvaroNeural` |
| **MOKU** (`moku`, `config/channels/moku.json`) | `moku-horror-long` | Terror / Creepypastas | Horizontal 16:9 (`1920x1080`, ≥600s) | `creepypasta` | `es-ES-AlvaroNeural` |
| **AELITHIA** (`aelithia`, `config/channels/aelithia.json`) | `aelithia-aita-long` | Drama / Relatos AITA | Horizontal 16:9 (`1920x1080`, ≥600s) | `aita` | `es-MX-DaliaNeural` |

- **Shorts Verticales (9:16)**: Resolución `1080x1920` @30fps, subtítulos ASS Karaoke (libass) en franja segura inferior (`MarginV 240-250`).
- **Longform Horizontal (16:9)**: Resolución `1920x1080` @30fps, duración ≥600s auto-expandible por compilación multihistoria y carrusel dinámico director.

---

## 🚀 Inicio Rápido con CLI Unificado

```bash
# 1. Verificación de entorno y credenciales (Preflight)
python3 main.py run --preflight

# 2. Listar carriles configurados y estado de planificación
python3 main.py lanes

# 3. Prueba sintética ultrarrápida (~2s render, sin consumo de cuotas)
python3 main.py run --lane moku-scp-shorts -t

# 4. Ejecución puntual de pipeline en producción por carril
python3 main.py run --lane moku-scp-shorts
python3 main.py run --lane moku-horror-long
python3 main.py run --lane aelithia-aita-long

# 5. Estado de salud general y colas
python3 main.py status
python3 main.py queue list

# 6. Catálogo y síntesis de bucles de video (native procedural / FFmpeg)
python3 main.py loop list
python3 main.py loop generate -c cosmic_horror -o vertical -n 2
python3 main.py loop audit

# 7. Autenticación y diagnóstico oficial de Google (YouTube Data API v3 & Drive)
python3 main.py auth check --channel moku
python3 main.py auth login --channel moku

# 8. Daemon continuo multi-carril autónomo (cadencia por config/lanes.json)
python3 main.py daemon --interval 60
```

---

## 🎨 Motor Visual FFmpeg (SSOT Teología v2.4.0) y Catálogo Local de Bucles

El stack visual de **producción** es **FFmpeg-first y determinista** (sin navegador headless, sin WebGPU en el hot path):
- **Modo beats / loop** (`LoopVideoEngine`): concat demuxer + **`-c:v copy`** (stream-copy, casi cero reencode) cuando la orientación es horizontal y no se queman subtítulos.
- **Modo director / multi-escena** (`MultiSceneCompositor` + `HybridVideoEngine`): Ken Burns vía FFmpeg **`zoompan`** en escenas hybrid; ensamble master FFmpeg (libass + EBU R128). Con `DIRECTOR_SINGLE_PASS=1` (default) y escenas procedurales con bucles de catálogo compatibles, **omite N re-encodes** y arma con stream-copy trim + concat demuxer (`-c:v copy`). `DIRECTOR_XFADE=1` activa `xfade` real (acorta timeline; off por defecto para sync con narración). `MultiActVideoRenderer` sí usa `xfade` en un solo `filter_complex`. `ENABLE_NATIVE_PROCEDURAL` default **off**.
- **Catálogo de bucles** (SQLite `video_loops` + `loop_worker.py`): micro-bucles **6–10 s** (~2–5 MB) sintetizados con FFmpeg lavfi (`technology=ffmpeg_lavfi`), expandidos con `-stream_loop -1`.
- **Temáticas**: `cosmic_horror`, `dark_forest`, `monsters`, `space_abyss`, `scp`, `drama_aita` (y `dark_ambient` en el worker). Cero Canvas/Three.js/WebGL en el camino activo.
- **Agentes vs píxeles**: los agentes emiten texto/JSON; el código de media es dueño de los píxeles (ASS + **libass** cuando hay subtítulos).
- **Quarantined (no prod)**: `src/media/_legacy/native_procedural.py` + WGSL shaders (`wgpu`/Lavapipe). SSOT = FFmpeg + Pillow thumbs. Opt-in only via `ENABLE_NATIVE_PROCEDURAL=1`; default off.
- **Low-CPU encode defaults**: `RENDER_PRESET=veryfast` + `RENDER_CRF=21` (see `src/media/encode_defaults.py` / docker-compose). Horizontal beats keep `-c:v copy`. Do not reintroduce `preset=slow` on the hot path or default Pillow/`rawvideo` frame loops (opt-in via `FORCE_PILLOW_*` only).

> [!NOTE]
> Para compatibilidad con despliegues previos, `python3 manage.py` reenvía de forma transparente todos los comandos al CLI unificado. Consulta [docs/OPERACION.md](docs/OPERACION.md) para la referencia completa de subcomandos y alias.


---

## 🤖 Arnés Antigravity Multi-Agente (6 Agentes Especializados)

El sistema integra un pipeline desacoplado de 6 agentes regidos por contratos JSON Schema Draft-07 bajo el CLI local `agy` (`gemini-3.7-flash`):
1. **Agent 1: Script Curator** (`src/agents/script_curator.py`): Guión optimizado para retención con gancho en los primeros 3 segundos.
2. **Agent 2: Art Director** (`src/agents/art_director.py`): Graduación de color Rec.709, dinámica de iluminación y partículas.
3. **Agent 3: Scene Planner** (`src/agents/scene_planner.py`): Construcción del manifiesto canónico `SceneManifestV2`.
4. **Agent 4: Forensic QA Auditor** (`src/agents/qa_auditor.py`): Verificación EBU R128 (-14 LUFS para shorts), luminancia y desincronización.
5. **Agent 5: Image Auditor (Anti-Filler)** (`src/agents/image_auditor.py`): Veeduría forense estricta. Descarta toda foto de stock estática y aprueba únicamente insignias vectoriales oficiales y esquemas técnicos.
6. **Agent 6: SEO Optimizer** (`src/agents/seo_optimizer.py`): Generador de 3 títulos virales para A/B testing, descripción estructurada con marcas de tiempo, etiquetas y conceptos de miniatura.

---

## 🛠️ Herramientas de Desarrollo y Diagnóstico (`dev/`)

Centralizadas en `dev/` para ejecución local y pruebas desatendidas:
- `python3 dev/generate_scp_short.py --topic "SCP-2000"`: Genera un Short vertical completo (9:16) con los 6 agentes.
- `python3 dev/test_pipeline_harness.py`: Diagnóstico integral Zero-Quota del arnés y contratos JSON.
- `python3 dev/produce_batch.py --count 3`: Producción en lote multi-canal (`moku`, `aelithia`).
- `python3 dev/run_telegram_bot.py --autopilot`: Bot interactivo en segundo plano con AutoPilot 24/7.
- `python3 dev/audit_assets.py --topic "SCP-2000"`: Veeduría independiente de activos contra la política anti-filler.

---

## 🔒 Seguridad, Revisión y Política AI-First

1. **Revisión por Código & Despacho**: Veredicto determinista de código (`CodeReviewVerdict`) evaluando integridad, compuertas QA (LUFS/freeze/drift) y auto-aprobación con fallback a Telegram local `telegram-bot-api:8081` (hasta 2 GB zero-copy `file:///`).
2. **Auto-Publicación Segura**: Ventana de revisión de 6h configurable. Barrido de aprobación ejecutable vía `python3 main.py queue sweep`.
3. **Política AI-First**: Tareas creativas emplean agentes bajo arnés Antigravity (`gemini-3.7-flash`) con failover a Gemini REST y política fail-closed. Los agentes emiten texto/JSON; el renderizado de producción es FFmpeg (beats stream-copy / director zoompan), subtítulos ASS/libass y persistencia 100% determinista local (dueño de los píxeles). `native_procedural`/wgpu está **quarantined** bajo `src/media/_legacy` (`ENABLE_NATIVE_PROCEDURAL=0` por defecto; no forma parte del SSOT de producción).
