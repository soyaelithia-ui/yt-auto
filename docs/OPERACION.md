# Manual de Operación, CLI Unificado y Despliegue

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-09  

Guía completa para la administración, ejecución en terminal, despliegue con Docker y Systemd, y mantenimiento de bases de datos bajo la arquitectura multi-carril (`config/lanes.json`).

---

## 1. Referencia del CLI Unificado (`main.py` / `manage.py`)

El sistema cuenta con subcomandos principales y banderas estandarizadas:

### Subcomandos Principales

| Subcomando | Propósito | Opciones Clave | Ejemplo de Invocación |
|---|---|---|---|
| **`lanes`** | Lista carriles configurados y su estado de planificación. | `-j` (salida JSON), `--db-path` | `python3 main.py lanes` |
| **`run`** | Ejecuta iteración puntual del pipeline por carril. | `--lane <lane_id>`, `-c` (canal), `-s` (historia), `-t` (tema), `-d, --dry-run` (simulación), `--preflight`, `--generate-only` | `python3 main.py run --lane horror-scp-shorts --dry-run` |
| **`daemon`** | Bucle planificador continuo multi-carril. | `-i`, `--interval` (intervalo en seg, default 60), `--sequential` | `python3 main.py daemon --interval 60` |
| **`status`** | Diagnóstico y salud del sistema. | `-j` (JSON), `--apis` (auditar credenciales), `--errors` (triage de errores), `-l` (límite) | `python3 main.py status --apis` |
| **`queue`** | Administración de colas de producción. | `list`, `pause <canal>`, `resume <canal>`, `activate <canal>`, `sweep` (barrido `AUTO_PUBLISH_TIMEOUT_HOURS`, default 24h), `-j` | `python3 main.py queue list` |
| **`clean`** | Limpieza de temporales y caché. | `-d, --dry-run` (simulación), `--cache` (trabajos expirados), `--sessions` | `python3 main.py clean --cache --dry-run` |
| **`auth`** | Gestión y diagnóstico de tokens OAuth2 oficiales de Google (YouTube Data API v3 y Drive). | `login`, `check`, `url`, `exchange <code>`, `standardize`, `-c` (canal), `--port` | `python3 main.py auth login -c horror`<br>`python3 main.py auth check -c horror` |
| **`backup`** | Respaldo atómico de SQLite con verificación. | `-o` (directorio destino), `-j` (salida JSON) | `python3 main.py backup` |
| **`migrate`** | Migraciones de esquema SQLite. | `-d, --dry-run` (simulación), `-j` (salida JSON) | `python3 main.py migrate --dry-run` |
| **`service`** | Control de servicios Systemd y logs. | `build`, `start`, `stop`, `restart`, `logs` | `python3 main.py service logs` |
| **`loop`** | Administración e indexación de bucles de video (catálogo de videos pre-renderizados MP4 y stream-copy). | `list`, `generate`, `preview`, `audit`, `daemon`, `-c` (categoría), `-o` (orientación), `-n` (cantidad), `-j` (JSON) | `python3 main.py loop list`<br>`python3 main.py loop generate -c cosmic_horror -o vertical`<br>`python3 main.py loop audit` |
| **`mcp`** | Servidor Model Context Protocol oficial (stdio / SSE) para orquestación e inspección por IA. | `--transport {stdio,sse}`, `--port` | `python3 main.py mcp`<br>`python3 -m src.mcp` |


### Opciones Globales (heredables antes o después del subcomando)
- `-p`, `--profile {prod,cli,test}`: Perfil de ejecución (por defecto: `cli` en terminal local, `prod` en daemon).
- `--db-path <ruta>`: Ruta personalizada a la base de datos SQLite.
- `-y`, `--yes`: Confirmación automática de operaciones críticas sobre perfiles de producción.

---

## Auto-approve / Autopilot (HITL)

Defaults de producción: `AUTO_APPROVE=0` y `ENABLE_AUTO_PUBLISH_SWEEP=0` (`.env.example` y `docker-compose.yml`). Opt-in explícito:

1. Completar preflight (`python3 main.py run --preflight`) — Telegram + YouTube/Drive siguen obligatorios; el opt-in **no** omite la validación.
2. En `.env` (no en el YAML base): `AUTO_APPROVE=1` y, si aplica, `ENABLE_AUTO_PUBLISH_SWEEP=1`.
3. `AUTO_APPROVE` solo aprueba la puerta HITL; YouTube sigue gated por cookies/token del canal.
4. `TEST_MODE=1` sigue **prohibido** en producción.

```bash
# Ejemplo (no publica sin credenciales de canal)
AUTO_APPROVE=1 ENABLE_AUTO_PUBLISH_SWEEP=1 python3 main.py daemon --interval 60
```


## 2. Despliegue con Docker Compose (`docker-compose.yml`)

Camino feliz **sin sudo**. Contenedor autocontenido (FFmpeg, Chromium, `agy` en `/usr/local/bin/agy`). Secretos solo en `./secrets:/run/secrets:ro`.

- **Límites de Recursos y Presupuesto Objetivo (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)**: El sistema está diseñado para que todas las operaciones normales (renderizado Stream-Copy, QA Gatekeeper, síntesis TTS y despachador reactivo) se mantengan bajo una **meta objetivo estricta de ≤ 2 Cores de CPU y ≤ 2.0 GiB de RAM**. El archivo `docker-compose.yml` base define un techo de emergencia de `mem_limit: 6g` y `cpus: 4.0` exclusivamente como red de seguridad para evitar terminaciones OOM bruscas ante picos transitorios, pero el software y los agentes deben optimizar y mantenerse dentro de la envolvente de 2 Cores / 2 GB RAM.
- **Aislamiento y Seguridad**: Rootfs de solo lectura (`read_only: true`), tmpfs `/tmp` (2 GB en base; 512m con small), `cap_drop: ALL`, usuario no-root `appuser:10001`, named volumes (no bind del workdir). Secretos solo en `./secrets:/run/secrets:ro`.
- **Servidor Telegram Local**: Puerto `127.0.0.1:8081`, hasta 2 GB, zero-copy `file:///`.
- **Antigravity**: AppData en el volumen `yt_agy_home` (`/home/appuser/.gemini`). El token OAuth se copia desde `secrets/antigravity-oauth-token` (login `agy` en una máquina con navegador; el contenedor no abre OAuth interactivo).

### Checklist deploy (pasos 0→8)

| Paso | Acción | Criterio de OK |
|---|---|---|
| **0** | Árbol vacío / clone limpio; `cp .env.example .env` y editar (sin secretos en git). | `.env` local `chmod 600`; no commitear. |
| **1** | Layout `secrets/`: `drive_key.json`, `tokens/<canal>.json` (`tokens/horror.json`, `tokens/drama.json`), `cookies.json`, `cookies_aelithia.json`, opcional `antigravity-oauth-token`. | Archivos presentes; montaje compose `ro`. |
| **2** | Completar `.env`: Telegram (`TELEGRAM_*` + `TELEGRAM_ALLOWED_CHAT_ID`), Drive IDs (`DRIVE_FOLDER_ID`, `DRIVE_APPROVED_VIDEO_FOLDER_ID`, …), channel IDs; `TELEGRAM_API_ID`/`HASH` para sidecar. | Placeholders secretos no vacíos en runtime. |
| **3** | `./scripts/stage_agy.sh` | `build/agy` existe (gitignored). |
| **4** | Preflight: `python3 main.py run --preflight` | `Production preflight: PASS` (ver [CONFIGURACION_SECRETOS.md](CONFIGURACION_SECRETOS.md) §3). |
| **5** | Preferir path low-RAM: `docker compose -f docker-compose.yml -f docker-compose.small.yml build` | Build OK (`yt-automation:local`). |
| **6** | `docker compose -f docker-compose.yml -f docker-compose.small.yml up -d` | Contenedores creados e iniciados (`yt-moku` + `yt-aelithia`). |
| **7** | `docker compose -f docker-compose.yml -f docker-compose.small.yml ps` | `yt-moku` + `yt-aelithia` (+ opcional sidecar) healthy/up. |
| **8** | Logs por canal: `… logs --follow yt-moku` / `… logs --follow yt-aelithia` | Daemons autónomos desacoplados en intervalo. |

Preferir overlay low-RAM (`2g` / `2` CPU, `shm 256m`, tmpfs `/tmp` 512m): `docker compose -f docker-compose.yml -f docker-compose.small.yml up -d`. Defaults: `AUTO_APPROVE: "0"`, `ENABLE_AUTO_PUBLISH_SWEEP: "0"`.

**Gestión Independiente de Canales:**
- Levantar un solo canal: `docker compose up -d yt-moku` (o `docker compose up -d yt-aelithia`)
- Detener un canal sin afectar al otro: `docker compose stop yt-moku` (`yt-aelithia` continúa procesando)
- Monitorear logs individuales: `docker compose logs -f yt-moku`
- Modo monolítico clásico: `docker compose --profile all-in-one up -d yt-automation`
- Failover de Telegram Poller: Si el contenedor que sostiene el poller se detiene, el segundo canal asume automáticamente la escucha de callbacks.

Si `build/agy: not found` → paso 3. Si uid 10001 no escribe → `docker compose down -v` y `up` de nuevo.

---

## 3. Unidades Systemd (`deploy/systemd/`) y Mantenimiento SQLite

Solo para VPS **con root**. El despliegue Docker de la sección 2 no usa systemd.

**Root de despliegue canónico (VPS):** `/srv/projects/yt-auto`.

Los unit files fijan ese path en `WorkingDirectory=` y `ExecStart=` (systemd exige rutas absolutas ahí; no expande `Environment=` en esos campos). También exportan `EnvironmentFile=-/srv/projects/yt-auto/.env` para carga de credenciales, `Environment=YT_AUTO_ROOT=/srv/projects/yt-auto` (default documentado) y derivan rutas de DB con `${YT_AUTO_ROOT}` donde sí hay sustitución.

- `yt-lanes-daemon.service`: Daemon autónomo multi-carril (`main.py daemon --interval 60`). Default `MemoryMax=6G`; low-RAM: drop-in `deploy/systemd/yt-lanes-daemon.service.d/low-ram.conf` → `MemoryMax=2G`. Anti-doble-polling: `ENABLE_TELEGRAM_CALLBACK_POLLING=0`.
- `yt-review-bot.service`: Bot interactivo Telegram (`deploy/tmux_review_bot.py`). Único poller autorizado: `ENABLE_TELEGRAM_CALLBACK_POLLING=1`. Default `MemoryMax=1G`.

```bash
# Systemd setup (requiere sudo; checkout en /srv/projects/yt-auto)
sudo cp deploy/systemd/*.service /etc/systemd/system/
# Opcional (recomendado para hosts con <=4GB RAM): instalar drop-in low-ram
sudo cp -r deploy/systemd/yt-lanes-daemon.service.d /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yt-lanes-daemon.service yt-review-bot.service

# Respaldo SQLite verificado y barrido de cola
python3 main.py backup && python3 main.py queue sweep
```

### Checklist de Despliegue VPS (Systemd / Tmux)

| Paso | Control / Tarea | Comando de Verificación / Acción | Criterio de Aceptación |
|---|---|---|---|
| **1. Usuario y Grupo** | Verificar pertenencia al grupo `developers` y usuario `moku`. | `id -Gn \| grep -w developers` (si falta: `sudo groupadd -f developers && sudo usermod -aG developers $USER`) | El usuario de ejecución pertenece a `developers`. |
| **2. Permisos y Entorno** | Permisos estrictos de secrets/env y script de control ejecutable. | `chmod 600 .env`<br>`chmod +x deploy/ctl.sh` | `.env` protegido; `./deploy/ctl.sh` ejecutable (`100755`). |
| **3. Virtualenv y Deps** | Python 3.12 y dependencias instaladas en canonical path. | `/srv/projects/yt-auto/.venv/bin/python --version`<br>`ffmpeg -version` | `.venv` y FFmpeg funcionales. |
| **4. Preflight Check** | Validación de APIs, tokens y carpetas de Drive. | `python3 main.py run --preflight` | `Production preflight: PASS`. |
| **5. Instalación Systemd** | Copia de units y drop-in low-RAM si aplica. | `sudo cp deploy/systemd/*.service /etc/systemd/system/`<br>`sudo cp -r deploy/systemd/yt-lanes-daemon.service.d /etc/systemd/system/`<br>`sudo systemctl daemon-reload` | Unidades registradas sin sintaxis rota. |
| **6. Inicio de Servicios** | Arranque atómico de bot de review y daemon productor. | `sudo systemctl enable --now yt-review-bot.service yt-lanes-daemon.service` | Ambos servicios `active (running)`. |
| **7. Operación sin Systemd (Tmux)** | Alternativa en hosts sin root mediante script supervisor. | `./deploy/ctl.sh status`<br>`./deploy/ctl.sh start all` | Sesiones `ytauto-sched` y `ytauto-bot` activas. |
| **8. Verificación Operacional** | Diagnóstico en vivo de logs y base de datos. | `systemctl status yt-lanes-daemon.service yt-review-bot.service`<br>`python3 main.py status --apis` | Sin colisiones de polling ni fallas de memoria. |

### Instalar fuera de `/srv/projects/yt-auto`

Usar drop-in de systemd (`sudo systemctl edit yt-lanes-daemon.service`) para ajustar `WorkingDirectory`, `ExecStart`, `EnvironmentFile` y `YT_AUTO_ROOT` a la ruta destino personalizada sin alterar los units oficiales.

---

## 4. Servidor MCP Oficial (`main.py mcp`)

Inicia el servidor Model Context Protocol sobre transporte stdio (por defecto) o SSE:
```bash
python3 main.py mcp                     # stdio (Antigravity / Claude Desktop)
python3 main.py mcp --transport sse     # SSE (HTTP en puerto 8000)
```
Manual técnico completo, catálogo de herramientas y configuración de clientes en [docs/MCP.md](MCP.md).

---

## 5. Gestión de Worktrees Concurrentes y Aprovisionamiento de Assets

Flujos multi-agente concurrentes y aislamiento de ramas de desarrollo sin colisiones:

- **`scripts/agent_worktree.sh`**: Gestiona worktrees aislados fuera del checkout primario (`/home/moku/projects/yt-auto`).
  - `create <name> [branch]`: Crea worktree y rama de trabajo aislada.
  - `remove <name>`: Desmonta el worktree de forma segura y ejecuta `git worktree prune`.
  - `list`: Inspecciona worktrees activos garantizando higiene sin ramas huérfanas.
- **`scripts/setup_worktree_env.sh`**: Configura de forma idempotente el entorno del worktree derivado:
  - Enlaza `.venv`, `.agents` y `.env` usando rutas relativas seguras sin exponer secretos.
  - Enlaza el catálogo de videos pre-renderizados (`assets/loops/`) y la base de datos SQLite (`data/loop_catalog.db`) desde `$PRIMARY_ROOT`, garantizando stream-copy (`-c:v copy`) instantáneo sin duplicar gigabytes ni desalinear Git tracking.

Catálogo CI vs prod (seed test / sin inventar media): [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md).
