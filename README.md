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

## 🎨 Motor de Video Procedural Nativo y Base de Datos Local de Bucles

El stack visual activo es **nativo y determinista** (sin navegador headless): `src/media/native_procedural.py` (`wgpu-py` + shaders WGSL, con fallback CPU Mesa Lavapipe) y composición/expansión vía **FFmpeg** (`src/media/loop_engine.py`, `loop_worker.py`, `unified_encoder.py`), con catálogo local en SQLite (`video_loops`):
- **Cero videos pesados**: Genera y almacena micro-bucles de **6 a 10 segundos** (~2 a 5 MB c/u). FFmpeg los expande sin costuras (`-stream_loop -1`) a la duración total del audio (Shorts o videos de 10 min).
- **Temáticas de catálogo**: `cosmic_horror`, `dark_forest`, `monsters`, `space_abyss`, `scp`, `drama_aita` (y `dark_ambient` en el worker). La síntesis marca `technology=native_procedural`; no hay motor Canvas/Three.js/WebGL en el camino activo.
- **Rotación Inteligente**: La base de datos local rota automáticamente los bucles menos usados para garantizar variedad visual entre publicaciones consecutivas.
- **Modo Activo**: El worker en segundo plano mantiene nutrido el buffer de bucles por temática sin intervención manual.
- **Agentes vs píxeles**: Los agentes del arnés producen texto/JSON creativo (guion, mood, manifiesto, SEO, veredictos). El código de media determinista es dueño de los píxeles; con subtítulos activos, ASS + **libass** en la cadena FFmpeg.

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
3. **Política AI-First**: Tareas creativas emplean agentes bajo arnés Antigravity (`gemini-3.7-flash`) con failover a Gemini REST y política fail-closed. Los agentes emiten texto/JSON; el renderizado procedural nativo (`wgpu`/WGSL), bucles FFmpeg, subtítulos ASS/libass y persistencia son 100% código determinista local (dueño de los píxeles).
