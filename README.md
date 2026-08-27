# Sistema Unificado de Automatización de YouTube — yt-auto

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
| **MOKU** (`moku`, `@MokuRedit`) | `moku-scp-shorts` | Anomalías SCP Foundation | Vertical 9:16 (`1080x1920`, 60–180s) | `shorts_creepypasta` | `es-ES-AlvaroNeural` |
| **MOKU** (`moku`, `@MokuRedit`) | `moku-horror-long` | Terror / Creepypastas | Horizontal 16:9 (`1920x1080`, ≥600s) | `creepypasta` | `es-ES-AlvaroNeural` |
| **AELITHIA** (`aelithia`, `@Aelithia-c1f`) | `aelithia-aita-long` | Drama / Relatos AITA | Horizontal 16:9 (`1920x1080`, ≥600s) | `aita` | `es-MX-DaliaNeural` |

- **Shorts Verticales (9:16)**: Canvas `1080x1920` @30fps, subtítulos ASS Karaoke en franja segura inferior (`MarginV 240-250`).
- **Longform Horizontal (16:9)**: Canvas `1920x1080` @30fps, duración ≥600s auto-expandible por compilación multihistoria y carrusel dinámico director.

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

# 6. Catálogo y síntesis de bucles de video por código web (Three.js/Canvas/CSS)
python3 main.py loop list
python3 main.py loop generate -c cosmic_horror -o vertical -n 2
python3 main.py loop audit

# 7. Daemon continuo multi-carril autónomo (cadencia por config/lanes.json)
python3 main.py daemon --interval 60
```

---

## 🎨 Motor de Video Procedural Web y Base de Datos Local de Bucles

El sistema implementa un motor de composición visual por código y tecnologías web (**HTML5 Canvas, WebGL, Three.js y animaciones CSS**) con un catálogo local en SQLite (`video_loops`):
- **Cero videos pesados**: Genera y almacena micro-bucles periódicos matemáticos de **6 a 10 segundos** (~2 a 5 MB c/u). FFmpeg los expande sin costuras (`-stream_loop -1`) a la duración total del audio (Shorts o videos de 10 min).
- **Temáticas Adaptables**: `cosmic_horror` (vórtices y agujeros negros en Three.js/WebGL), `dark_forest` (niebla y esporas orgánicas en Canvas 2D), `monsters` (sombras y ojos parpadeantes), `space_abyss` (abismo estelar 3D), `scp` (terminal CRT de fósforo verde y wireframe 3D) y `drama_aita` (ondas fluidas).
- **Rotación Inteligente**: La base de datos local rota automáticamente los bucles menos usados para garantizar variedad visual entre publicaciones consecutivas.
- **Modo Activo**: El worker en segundo plano mantiene nutrido el buffer de bucles por temática sin intervención manual.

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
3. **Política AI-First**: Tareas creativas emplean agentes bajo arnés Antigravity (`gemini-3.7-flash`) con failover a Gemini REST y política fail-closed. El renderizado procedural, subtítulos y persistencia son 100% código determinista local.
