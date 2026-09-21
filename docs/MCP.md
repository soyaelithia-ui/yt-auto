# Manual Operativo y Especificación del Servidor MCP — yt-auto

> **Estado:** OFICIAL / REPOSITORIO  
> **Versión MCP:** 2.2.0 (`mcp.server.mcpserver.MCPServer`)  
> **Última actualización:** 2026-09  
> **Transporte Primario:** stdio (con soporte modular SSE para HTTP)

El servidor Model Context Protocol (MCP) de `yt-auto` expone las capacidades operativas, de consulta, auditoría y despacho de la factoría de videos sobre el protocolo estándar JSON-RPC, permitiendo a asistentes de IA (Antigravity, Claude Desktop, CLI de inspección) interactuar de forma determinista y segura con la infraestructura de producción.

---

## 1. Arquitectura y Principios de Diseño

1. **Framework Oficial**: Construido con el SDK oficial de Python `mcp` v2.2.0 utilizando `from mcp.server.mcpserver import MCPServer`.
2. **Cero Duplicación de Lógica**: Cada herramienta, recurso y prompt delega directamente en los módulos probados del repositorio (`src/core/`, `src/config.py`, `src/cli/handlers/`, `review/db.py`, `healthcheck.py`, `scripts/verify_integrity.sh`).
3. **Presupuesto de Recursos Estricto (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)**:
   - Baseline de memoria del servidor MCP: < 60 MiB RSS en reposo.
   - Procesamiento de video estrictamente basado en Stream-Copy (`-c:v copy`) vía FFmpeg concat demuxer.
   - Sondas e inspecciones limitadas a 2 hilos (`-threads 2`) y sin decodificación de video (`-vn`).
4. **Política Zero-Browser (Invariante 3)**:
   - Absolutamente cero dependencias o imports de `playwright` o `chromium` en `src/mcp/`.
5. **Gobernanza de Credenciales y Memoria (Zero Secrets, Invariante 2)**:
   - Sanitización recursiva de salidas JSON-RPC (`[REDACTED]`).
   - El recurso `channels://{channel_name}/config` utiliza `ChannelConfig.public_dict()` exponiendo solo banderas booleanas (`cookies_available`, `youtube_token_available`), sin revelar rutas físicas ni secretos.
6. **Desvío de Descriptores de Archivo (OS fd diversion)**:
   - En transporte stdio, stdout queda reservado exclusivamente para la trama JSON-RPC. Todos los logs internos y salidas de subprocesos se redirigen a `stderr`.

---

## 2. Invocación y Modos de Transporte

### 2.1. Invocación CLI Directa (`main.py mcp`)
```bash
# Iniciar servidor sobre transporte stdio (por defecto)
python3 main.py mcp

# Iniciar servidor sobre transporte SSE (escuchando HTTP)
python3 main.py mcp --transport sse --port 8000
```

### 2.2. Invocación como Módulo Python
```bash
# Invocación directa como módulo
python3 -m src.mcp
```

### 2.3. Modo de Prueba con MCP Inspector
```bash
npx @modelcontextprotocol/inspector .venv/bin/python3 -m src.mcp
```

---

## 3. Catálogo Canónico de Herramientas (Tools)

El servidor registra 9 herramientas operativas:

| # | Herramienta | Propósito Principal | Módulo Backing |
|---|---|---|---|
| 1 | `system_preflight` | Validación integral de entorno, dependencias, tokens y cuotas sin efectos colaterales. | `src.config`, `src.api_health`, `healthcheck` |
| 2 | `list_lanes` | Lista carriles configurados con estado del scheduler y voz resuelta. | `src.core.lanes`, `shorts_queue.db` |
| 3 | `get_lane_info` | Especificación editorial, visual, de audio y QA de un carril. | `src.core.lanes`, `config/lanes.json` |
| 4 | `query_loop_catalog` | Consulta y filtrado de loops maestros por categoría, orientación y canal. | `src.core.catalog`, `data/loop_catalog.db` |
| 5 | `audit_loop_catalog` | Auditoría de assets físicos MP4 vs SQLite y validación de `bank_manifest.json`. | `src.core.catalog`, `src.media.loop_engine` |
| 6 | `run_pipeline_dry_run` | Ejecución sintética de prueba (`--lane <id> -t`) con consumo cero de cuotas. | `src.orchestrator.pipeline`, `src.pipeline` |
| 7 | `get_system_status` | Diagnóstico de salud, conteos de cola, bloqueos y logs de errores recientes. | `src.cli.handlers.status`, `healthcheck` |
| 8 | `manage_queue` | Inspección de cola, revisión de pendientes, pausa/reanudación y barrido de publicación. | `src.cli.handlers.queue`, `review.db`, `src.telegram.approval` |
| 9 | `verify_integrity` | Ejecución del script oficial de integridad y suite anti-regresión (REG-01 a REG-14). | `scripts/verify_integrity.sh` |

### 3.1. `system_preflight`
- **Parámetros**:
  - `channel` (string opcional): Canal a auditar (`"horror"`, `"drama"`, `"scifi"` o `"all"`, por defecto `"all"`).
  - `require_drive` (boolean, default `False`): Requiere validación estricta de credenciales de Google Drive.
  - `require_publish` (boolean, default `False`): Requiere validación de tokens/cookies de publicación en YouTube.
  - `require_review` (boolean, default `False`): Requiere validación de conectividad con Telegram Bot API.
- **Respuesta**:
```json
{
  "status": "OK",
  "checks": [
    { "name": "disk", "status": "ok", "free_gb": 42.5 },
    { "name": "binaries", "status": "ok", "binaries": { "ffmpeg": true, "ffprobe": true } }
  ],
  "channels": {
    "horror": { "youtube_ok": true, "drive_ok": true, "cookies_ok": true }
  },
  "errors": []
}
```

### 3.2. `list_lanes`
- **Parámetros**:
  - `channel` (string opcional): Filtrar por canal (`"horror"`, `"drama"`).
  - `include_disabled` (boolean, default `False`): Incluir carriles desactivados.
- **Respuesta**:
```json
{
  "lanes": [
    {
      "lane_id": "moku-scp-shorts",
      "channel": "moku",
      "story_type": "scp",
      "orientation": "vertical",
      "resolution": [1080, 1920],
      "duration": { "min_sec": 60, "target_sec": 90, "max_sec": 180 },
      "voice_profile": "scp_documentary_es",
      "resolved_voice": "es-ES-AlvaroNeural",
      "enabled": true,
      "paused": false
    }
  ],
  "count": 1
}
```

### 3.3. `get_lane_info`
- **Parámetros**:
  - `lane_id` (string requerido): Identificador canónico del carril (ej. `"moku-scp-shorts"`).
- **Respuesta**: Retorna la especificación editorial completa, fuentes de Reddit, configuración visual, parámetros de audio y estado dinámico del scheduler.

### 3.4. `query_loop_catalog`
- **Parámetros**:
  - `category` (string opcional): Categoría temática (`"cosmic_horror"`, `"dark_forest"`, `"drama"`, etc.).
  - `orientation` (string opcional): `"vertical"` o `"horizontal"`.
  - `channel` (string opcional): `"horror"`, `"drama"` o `"scifi"`.
  - `limit` (integer, default `50`): Límite de registros.
- **Respuesta**: Lista de loops maestros registrados con metadatos de resolución, duración, FPS, ruta física y estadísticas de uso.

### 3.5. `audit_loop_catalog`
- **Parámetros**:
  - `cleanup` (boolean, default `False`): Si es `True`, elimina de la base de datos registros cuyos archivos físicos no existan en disco.
- **Respuesta**: Conteo de archivos verificados, activos válidos, faltantes, estado del sellado en `bank_manifest.json` y lista de los 6 loops maestros certificados.

### 3.6. `run_pipeline_dry_run`
- **Parámetros**:
  - `lane_id` (string requerido): Carril de producción.
  - `topic` (string opcional): Tema sintético de prueba.
  - `channel` (string opcional): Canal asignado.
- **Respuesta**:
```json
{
  "status": "SUCCESS",
  "run_id": "dryrun_moku-scp-shorts_20260919_003300",
  "lane_id": "moku-scp-shorts",
  "channel": "moku",
  "duration_sec": 84.5,
  "video_path": "output/dryrun_moku-scp-shorts.mp4",
  "zero_quota_verified": true,
  "facts": { "composition_mode": "stream-copy", "cpu_time_sec": 1.4 }
}
```

### 3.7. `get_system_status`
- **Parámetros**:
  - `include_recent_errors` (boolean, default `True`): Incluye los últimos logs de fallas.
  - `error_limit` (integer, default `10`): Cantidad máxima de errores a retornar.
- **Respuesta**: Estado del daemon autónomo, latido, estado de colas (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`), espacio en disco, bloqueos activos de canal y procesos workers en ejecución.

### 3.8. `manage_queue`
- **Parámetros**:
  - `action` (string requerido): Una de `"list"`, `"list_review_pending"`, `"pause"`, `"resume"`, `"sweep"`.
  - `channel` (string opcional): Canal objeto de la acción.
  - `limit` (integer, default `50`): Límite de elementos a retornar.
  - `reason` (string opcional): Motivo de la pausa (cuando `action="pause"`).
- **Respuesta**: Estructura de resultados según la acción ejecutada.

### 3.9. `verify_integrity`
- **Parámetros**:
  - `fast` (boolean, default `False`): Omite suites lentas de integración.
- **Respuesta**:
```json
{
  "healthy": true,
  "exit_code": 0,
  "checks_passed": [
    "git_worktrees",
    "no_legacy_docs",
    "zero_playwright_in_media",
    "zero_procedural_shaders",
    "anti_regression_tests",
    "mcp_sync_parity"
  ],
  "checks_failed": [],
  "commit_count": 87,
  "output": "100% HEALTHY - All checks passed"
}
```

---

## 4. Recursos Canónicos (Resources) y Esquemas de URI

El servidor expone 3 recursos estandarizados:

```
resources/
├── channels://{channel_name}/config   # Configuración pública y sanitizada del canal
├── lanes://catalog                    # Catálogo de especificaciones de carriles
└── system://health                    # Métricas de salud en tiempo real
```

### 4.1. `channels://{channel_name}/config`
- **URI Template**: `channels://{channel_name}/config` (`channel_name` ∈ `{"horror", "drama", "scifi"}`)
- **MIME Type**: `application/json`
- **Seguridad**: Rutas locales a cookies y tokens se eliminan y sustituyen por banderas booleanas:
```json
{
  "id": "horror",
  "enabled": true,
  "editorial": {
    "public_name": "Expedientes de Terror",
    "handle": "@expedientesdeterror",
    "topic": "terror psicológico, historias de la Fundación SCP",
    "tone": "oscuro, inmersivo, solemne",
    "channel_url": "https://www.youtube.com"
  },
  "visual": {
    "style_id": "cosmic_chiaroscuro",
    "watermark_text": "CLASIFICADO"
  },
  "audio": {
    "default_voice_profile": "scp_documentary_es",
    "default_tts_provider": "edge-tts"
  },
  "auth_status": {
    "cookies_available": true,
    "youtube_token_available": true
  }
}
```

### 4.2. `lanes://catalog`
- **URI**: `lanes://catalog`
- **MIME Type**: `application/json`
- **Origen**: `config/lanes.json` cargado con validación de esquema.

### 4.3. `system://health`
- **URI**: `system://health`
- **MIME Type**: `application/json`
- **Origen**: Reporte diagnóstico en vivo (`healthcheck.py` + `shorts_queue.db`).

---

## 5. Flujos Guiados de Operación (Prompts)

El servidor proporciona 3 prompts estructurados:

### 5.1. `preflight_diagnostics`
- **Argumentos**: `channel` (opcional, default `"all"`).
- **Flujo Operativo**:
  1. Invoca la herramienta `system_preflight(channel=channel, require_publish=True)`.
  2. Lee el recurso `system://health` evaluando margen de disco y dependencias FFmpeg.
  3. Verifica la vigencia de credenciales sin revelar tokens.
  4. Emite un dictamen formal **GO / NO-GO** previo al lanzamiento del daemon o lotes.

### 5.2. `channel_incident_analysis`
- **Argumentos**: `channel_name` (requerido), `incident_description` (opcional).
- **Flujo Operativo**:
  1. Lee `channels://{channel_name}/config` para verificar el estado de configuración.
  2. Invoca `get_system_status` filtrando errores del canal y bloqueos huérfanos.
  3. Invoca `list_lanes(channel=channel_name)` para diagnosticar si un carril está en `PAUSED`.
  4. Analiza fallas comunes (`heartbeat_timeout`, `CatalogAssetNotFoundError`, `TokenExpiredError`).
  5. Formula un Plan de Mitigación y comandos de remediación.

### 5.3. `video_qa_review`
- **Argumentos**: `story_id` (requerido), `channel_name` (opcional).
- **Flujo Operativo**:
  1. Consulta el elemento en revisión mediante `manage_queue(action="list_review_pending")`.
  2. Audita contra las compuertas QA del pipeline:
     - **Video**: Resolución canónica (1080x1920 9:16 o 1920x1080 16:9), 30 fps, luminancia > 22.0, cuadros negros = 0.
     - **Audio**: EBU R128 (-14.0 LUFS ±1.5 dB), True Peak ≤ -1.5 dBFS, LRA ≤ 11.0 LU.
     - **Subtítulos**: Contraste alto, área segura MarginV ≥ 240px.
     - **Editorial**: Guión en español neutro, sin prompt leaks y sin duplicidad.
  3. Emite veredicto: `APROBADO`, `RECHAZADO_PARA_REGEN` o `REQUIERE_EDICION_MANUAL`.

---

## 6. Configuración de Clientes MCP

### 6.1. Antigravity Agent (`~/.gemini/antigravity-cli/` o `.mcp.json`)
```json
{
  "mcpServers": {
    "yt-auto": {
      "command": ".venv/bin/python3",
      "args": ["-m", "src.mcp"],
      "env": {
        "PYTHONPATH": ".",
        "YT_PROFILE": "cli"
      }
    }
  }
}
```

### 6.2. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "yt-auto": {
      "command": "/srv/projects/yt-auto/.venv/bin/python3",
      "args": ["-m", "src.mcp"],
      "env": {
        "PYTHONPATH": "/srv/projects/yt-auto",
        "YT_PROFILE": "cli"
      }
    }
  }
}
```

---

## 7. Gobernanza de Cambios y Sincronización SSOT

Para mantener la sincronización absoluta entre código, políticas y documentación:

1. **Paridad Bidireccional Obligatoria**:
   - Cada herramienta, recurso o prompt añadido o modificado en `src/mcp/` DEBE documentarse en este archivo (`docs/MCP.md`).
   - La suite automatizada `scripts/verify_mcp_sync.py` verifica la paridad 1-a-1 entre el registro en runtime y esta documentación.
2. **Integración en CI y Puertas de Integridad**:
   - `scripts/verify_integrity.sh` incluye la verificación MCP como Check #9. Si la documentación y el código divergen, la verificación falla con código 1.
3. **Presupuesto de Líneas de Documentación**:
   - Este manual (`docs/MCP.md`) es una especificación especializada no indexada en `ACTIVE_DOCS` de `tests/unit/test_docs_integrity.py` (al igual que `docs/FFMPEG_LOW_CPU.md` o `docs/POLITICA_CATALOGO_CI.md`).
   - **PROHIBICIÓN**: `docs/MCP.md` **NUNCA** debe agregarse a la lista `ACTIVE_DOCS` para preservar el límite estricto de 1000 líneas de la documentación básica.
4. **Etiquetas de Sintaxis en Bloques de Código**:
   - Todo bloque de código en documentación debe declarar explícitamente su lenguaje (` ```bash `, ` ```json `, ` ```python `).
