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
| **`run`** | Ejecuta iteración puntual del pipeline por carril. | `--lane <lane_id>`, `-c` (canal), `-s` (historia), `-t` (test sintético), `-d` (dry-run), `--preflight`, `--generate-only` | `python3 main.py run --lane moku-scp-shorts` |
| **`daemon`** | Bucle planificador continuo multi-carril. | `-i`, `--interval` (intervalo en seg, default 60), `--sequential` | `python3 main.py daemon --interval 60` |
| **`status`** | Diagnóstico y salud del sistema. | `-j` (JSON), `--apis` (auditar credenciales), `--errors` (triage de errores), `-l` (límite) | `python3 main.py status --apis` |
| **`queue`** | Administración de colas de producción. | `list`, `pause <canal>`, `resume <canal>`, `activate <canal>`, `sweep` (barrido `AUTO_PUBLISH_TIMEOUT_HOURS`, default 24h), `-j` | `python3 main.py queue list` |
| **`clean`** | Limpieza de temporales y caché. | `-d` (dry-run), `--cache` (trabajos expirados), `--sessions` | `python3 main.py clean --cache -d` |
| **`auth`** | Gestión y diagnóstico de tokens OAuth2 oficiales de Google (YouTube Data API v3 y Drive). | `login`, `check`, `url`, `exchange <code>`, `standardize`, `-c` (canal), `--port` | `python3 main.py auth login -c moku`<br>`python3 main.py auth check -c moku` |
| **`backup`** | Respaldo atómico de SQLite con verificación. | `-o` (directorio destino), `-j` (salida JSON) | `python3 main.py backup` |
| **`migrate`** | Migraciones de esquema SQLite. | `-d` (dry-run), `-j` (salida JSON) | `python3 main.py migrate -d` |
| **`service`** | Control de servicios Systemd y logs. | `build`, `start`, `stop`, `restart`, `logs` | `python3 main.py service logs` |
| **`loop`** | Administración y síntesis de bucles de video web (Three.js/Canvas/CSS). | `list`, `generate`, `preview`, `audit`, `daemon`, `-c` (categoría), `-o` (orientación), `-n` (cantidad), `-j` (JSON) | `python3 main.py loop list`<br>`python3 main.py loop generate -c cosmic_horror -o vertical`<br>`python3 main.py loop audit` |


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

- **Límites de Recursos (low-RAM primero)**: el techo del compose base es `mem_limit: 6g` / `cpus: 4.0` / `shm_size: 1g` (path pesado / reencode). **Camino recomendado de despliegue**: overlay small — `docker compose -f docker-compose.yml -f docker-compose.small.yml up -d` → `2g` / `2` CPU / `shm 256m` / tmpfs `/tmp` 512m. Smoke live (etapas 8–9) ≈ 84–88 MB RSS. Presupuesto CI (`src/core/rss_budgets.py`): ΔRSS 8/9 ≤16 MB, peak ≤512 MB — cabe holgado bajo `mem_limit: 2g` del overlay small. No bajar el techo del compose base (6g) hasta full-render RSS.
- **Aislamiento y Seguridad**: Rootfs de solo lectura (`read_only: true`), tmpfs `/tmp` (2 GB en base; 512m con small), `cap_drop: ALL`, usuario no-root `appuser:10001`, named volumes (no bind del workdir). Secretos solo en `./secrets:/run/secrets:ro`.
- **Servidor Telegram Local**: Puerto `127.0.0.1:8081`, hasta 2 GB, zero-copy `file:///`.
- **Antigravity**: AppData en el volumen `yt_agy_home` (`/home/appuser/.gemini`). El token OAuth se copia desde `secrets/antigravity-oauth-token` (login `agy` en una máquina con navegador; el contenedor no abre OAuth interactivo).

### Checklist deploy (pasos 0→8)

| Paso | Acción | Criterio de OK |
|---|---|---|
| **0** | Árbol vacío / clone limpio; `cp .env.example .env` y editar (sin secretos en git). | `.env` local `chmod 600`; no commitear. |
| **1** | Layout `secrets/`: `drive_key.json`, `youtube_token.json`, `youtube_token_aelithia.json`, `cookies_moku.json`, `cookies_aelithia.json`, opcional `antigravity-oauth-token`. | Archivos presentes; montaje compose `ro`. |
| **2** | Completar `.env`: Telegram (`TELEGRAM_*` + `TELEGRAM_ALLOWED_CHAT_ID`), Drive IDs (`DRIVE_FOLDER_ID`, `DRIVE_APPROVED_VIDEO_FOLDER_ID`, …), channel IDs; `TELEGRAM_API_ID`/`HASH` para sidecar. | Placeholders secretos no vacíos en runtime. |
| **3** | `./scripts/stage_agy.sh` | `build/agy` existe (gitignored). |
| **4** | Preflight: `python3 main.py run --preflight` | `Production preflight: PASS` (ver [CONFIGURACION_SECRETOS.md](CONFIGURACION_SECRETOS.md) §3). |
| **5** | Preferir path low-RAM: `docker compose -f docker-compose.yml -f docker-compose.small.yml build` | Build OK. |
| **6** | `docker compose -f docker-compose.yml -f docker-compose.small.yml up -d` | Contenedores creados. |
| **7** | `docker compose -f docker-compose.yml -f docker-compose.small.yml ps` | `yt-automation` + `telegram-bot-api` healthy/up. |
| **8** | Logs: `… logs --follow yt-automation` | Sin FAIL de preflight; daemon en intervalo. |

Path pesado (6g/4 CPU) solo si hace falta reencode: `docker compose build && docker compose up -d`. Overlay small → `2g` / `2` CPU / `shm 256m` / tmpfs `/tmp` 512m. Defaults compose: `AUTO_APPROVE: "0"`, `ENABLE_AUTO_PUBLISH_SWEEP: "0"` (**no flippear** en el YAML).

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

No editar a mano el unit copiado: usar drop-in para mantener `WorkingDirectory`, `ExecStart`, `EnvironmentFile` y `YT_AUTO_ROOT` alineados.

```bash
sudo systemctl edit yt-lanes-daemon.service
# [Service]
# EnvironmentFile=-/opt/yt-auto/.env
# Environment=YT_AUTO_ROOT=/opt/yt-auto
# WorkingDirectory=/opt/yt-auto
# Environment=YOUTUBE_AUTOMATION_DB=/opt/yt-auto/data/shorts_queue.db
# Environment=VIDEO_REVIEW_DB_PATH=/opt/yt-auto/data/review_state.db
# ExecStart=/opt/yt-auto/.venv/bin/python main.py daemon --interval 60

sudo systemctl edit yt-review-bot.service
# [Service]
# EnvironmentFile=-/opt/yt-auto/.env
# Environment=YT_AUTO_ROOT=/opt/yt-auto
# WorkingDirectory=/opt/yt-auto
# ExecStart=/opt/yt-auto/.venv/bin/python deploy/tmux_review_bot.py
```

Catálogo CI vs prod (seed test / sin inventar media): [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md).
