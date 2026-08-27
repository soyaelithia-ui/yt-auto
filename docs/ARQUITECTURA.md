# Arquitectura del Sistema — yt-auto

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Arquitectura modular, persistencia atómica en SQLite WAL, catálogo de assets offline y política de ejecución del sistema basada en carriles editoriales (`config/lanes.json`).

---

## 1. Diagrama de Arquitectura General

```mermaid
graph TD
    subgraph Dominio y Configuración
        Lanes[config/lanes.json: Perfiles LaneProfile]
        Config[src/config.py: Canales moku & aelithia]
        Domain[src/core/domain.py: Estados JobStatus]
    end
    subgraph Persistencia, Cola y Catálogo de Loops
        DB[(data/shorts_queue.db: SQLite WAL)]
        Repo[src/core/repository.py: QueueRepository & Lane Leases]
        LoopDB[(data/shorts_queue.db: tabla video_loops)]
        LoopCat[src/core/loop_catalog.py: LoopCatalogRepository]
    end
    subgraph Generación Visual por Código Web
        WebRenderer[src/media/web_video_renderer.py: Playwright Chromium]
        WebTemplates[src/media/web_templates/: Three.js, Canvas, WebGL, CSS]
        LoopWorker[src/media/loop_synthesizer_worker.py: Buffer Activo]
    end
    subgraph Pipeline de Producción (13 Etapas)
        Pipe[src/pipeline.py: Orquestador Canónico]
        Agents[src/agents/: Agentes Gemini Direct REST]
        TTS[lib/tts.py: Edge-TTS & Masterización EBU R128]
        Subs[src/subtitles.py: ASS Karaoke Franja Segura]
        Video[src/media/loop_video_engine.py: LoopVideoEngine FFmpeg]
    end
    subgraph Puerta de Revisión y Veredicto
        CodeQA[src/core/code_review_verdict.py: CodeReviewVerdict]
        ReviewDB[(data/review_state.db)]
        Adapter[src/review_publication_adapter.py]
        TelegramBot[review: Bot Client]
        LocalAPI[telegram-bot-api :8081: Servidor Local 2 GB]
    end
    subgraph Destinos Remotos Verificados
        Drive[src/drive.py: Google Drive API v3 Backup]
        YouTube[src/youtube_uploader.py: YouTube API v3 / Playwright]
    end

    Lanes --> Pipe
    Config --> Pipe
    Repo <--> DB
    LoopCat <--> LoopDB
    WebRenderer --> WebTemplates
    LoopWorker --> WebRenderer --> LoopCat
    Pipe --> LoopCat
    Pipe --> Repo & Agents & TTS & Subs & Video & CodeQA
    CodeQA -- Code PASS --> Drive & YouTube
    CodeQA -- Manual/Fallback --> Adapter
    Adapter <--> ReviewDB & TelegramBot
    TelegramBot -->|Transporte Dual: file:/// 0-Copy & Multipart| LocalAPI
    TelegramBot -- APPROVED --> Drive & YouTube
```

---

## 2. Carriles Editoriales de Producción (Lanes & `config/lanes.json`)

El sistema sustituye las banderas de formato manuales por **carriles de producción (`LaneProfile`)** autodirigidos por cadencia y configuración:

1. **`moku-scp-shorts` (Shorts Verticales 9:16)**:
   - Formato vertical `1080x1920` @30fps con `LoopVideoEngine`.
   - Subtítulos ASS Karaoke en franja segura inferior (`MarginV 240-250` sobre `1080x1920`).
   - Duración adaptativa 60–180s (objetivo canónico 150s con re-condensación de guion si excede).
   - Ingestión multi-fuente: subreddits SCP (`r/SCP`, `r/SCPDeclassified`) y SCP Wiki scraper (`src/scraper_scp.py`) con atribución CC BY-SA 3.0.
2. **`moku-horror-long` (Horizontal 16:9)**:
   - Formato apaisado `1920x1080` @30fps con video loop continuo.
   - Compilación multihistoria automática hasta superar presupuesto de palabras (≥2600 palabras) y duración mínima de ≥600s.
3. **`aelithia-aita-long` (Horizontal 16:9)**:
   - Formato apaisado `1920x1080` @30fps con compilación multihistoria de relatos AITA / relaciones.
   - Filtrado temático estricto vía `src/core/topic_filter.py` para garantizar relevancia editorial.

---

## 3. Persistencia Atómica y Concurrencia (SQLite WAL & Lane Leases)

Gestionada en `src/core/repository.py` y `src/db.py`:
- **Modo WAL (`journal_mode=WAL`)**: Permite lecturas simultáneas concurrentes sin bloquear escrituras.
- **Configuración de Bloqueos**: `PRAGMA busy_timeout=15000`, claves foráneas activadas y leases transaccionales con `BEGIN IMMEDIATE`.
- **Leases por Carril (`lane_leases`)**: Permite la ejecución concurrente no conflictiva de múltiples carriles sobre el mismo canal (ej. `moku-scp-shorts` y `moku-horror-long` en paralelo).
- **Deduplicación Aislada**: Huellas SHA-256 y SimHash 64-bit por canal en la tabla `content_fingerprints`. Lo encolado o publicado en un canal no afecta a otros.

---

## 4. Catálogo de Assets Offline

1. **Catálogo de Loops Atmosféricos**: `assets/loops/{cosmic_horror,dark_ambient,dark_forest,monsters,space_abyss}/`.
2. **Banco Temático de Canal**: `assets/visual_bank/{moku,aelithia}/{scenery,ambient_gifs,overlays}`.
3. **Identidad Visual y Marcas de Agua**: `assets/branding/`.
4. **Música y Efectos**: `assets/music/` por género narrativo (terror, drama, suspenso).
5. **Tipografías**: `assets/fonts/Montserrat-Black.ttf` para renderizado ASS y portadas.
