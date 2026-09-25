# Manual de Operación, CLI Unificado y Despliegue

> **Estado:** REPOSITORIO / OFICIAL | **Actualización:** 2026-09 | CLI unificado, despliegue Docker/Systemd y mantenimiento (`config/lanes.json`).

## 1. Referencia del CLI Unificado (`main.py`)

| Subcomando | Propósito | Opciones y Ejemplo |
|---|---|---|
| **`lanes`** | Lista carriles y estado. | `python3 main.py lanes [-j]` |
| **`run`** | Ejecuta iteración de pipeline. | `python3 main.py run --lane horror-scp-shorts [--dry-run] [--preflight]` |
| **`daemon`** | Bucle continuo multi-carril. | `python3 main.py daemon --interval 60 [--sequential]` |
| **`status`** | Diagnóstico y salud del sistema. | `python3 main.py status [--apis] [--errors] [-j]` |
| **`queue`** | Administración de colas SQLite. | `python3 main.py queue {list,pause,resume,sweep} [-j]` |
| **`clean`** | Limpieza de temporales y caché. | `python3 main.py clean --cache [--dry-run]` |
| **`auth`** | Gestión OAuth2 Google (YouTube/Drive). | `python3 main.py auth {login,check,url} -c horror` |
| **`backup`** | Respaldo atómico SQLite. | `python3 main.py backup [-o <dir>]` |
| **`migrate`** | Migraciones de esquema SQLite. | `python3 main.py migrate [--dry-run]` |
| **`loop`** | Catálogo de loops y stream-copy. | `python3 main.py loop {list,generate,audit} -c cosmic_horror -o vertical` |
| **`mcp`** | Servidor Model Context Protocol. | `python3 main.py mcp [--transport {stdio,sse}]` |

**Opciones Globales**: `-p, --profile {prod,cli,test}`, `--db-path <ruta>`, `-y, --yes`.

### Auto-approve / Autopilot (HITL)
Por defecto `AUTO_APPROVE=0` y `ENABLE_AUTO_PUBLISH_SWEEP=0`. Opt-in explícito en `.env`:
```bash
# Requiere preflight previo: python3 main.py run --preflight
AUTO_APPROVE=1 ENABLE_AUTO_PUBLISH_SWEEP=1 python3 main.py daemon --interval 60
```

## 2. Despliegue con Docker Compose (`docker-compose.yml`)

Contenedor autocontenido (FFmpeg, CLI `agy` en `/usr/local/bin/agy`, Chromium). Presupuesto estricto: $\le 2$ Cores CPU, $\le 2.0$ GiB RAM (techo compose: `cpus: 4.0`, `mem_limit: 6g` para picos). Rootfs read-only, secrets en `./secrets:/run/secrets:ro`, usuario `appuser:10001`.

```bash
# 1. Preflight local y build con overlay low-RAM (2g RAM / 2 Cores)
python3 main.py run --preflight
docker compose -f docker-compose.yml -f docker-compose.small.yml build

# 2. Iniciar servicios y monitorear logs independientes por canal
docker compose -f docker-compose.yml -f docker-compose.small.yml up -d
docker compose logs -f yt-moku       # Canal Horror
docker compose logs -f yt-aelithia   # Canal Drama
```

- **Operación granular**: `docker compose up -d yt-moku` (inicia solo Horror) o `docker compose stop yt-moku` (sin afectar Drama).

## 3. Unidades Systemd (`deploy/systemd/`) y Supervisor VPS

Canónico en VPS con root (`/srv/projects/yt-auto`):
- `yt-lanes-daemon.service`: Daemon autónomo (`main.py daemon --interval 60`, `MemoryMax=2G` con drop-in low-ram).
- `yt-review-bot.service`: Bot interactivo Telegram (`deploy/tmux_review_bot.py`, `MemoryMax=1G`).

```bash
# Instalación Systemd con drop-in low-RAM
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp -r deploy/systemd/yt-lanes-daemon.service.d /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now yt-lanes-daemon.service yt-review-bot.service

# Operación sin Systemd (supervisión Tmux alternativa)
./deploy/ctl.sh status && ./deploy/ctl.sh start all
```

## 4. Servidor MCP Oficial (`main.py mcp`)

Inicia el servidor Model Context Protocol sobre transporte stdio o SSE:
```bash
python3 main.py mcp                     # stdio (Antigravity / Claude Desktop)
python3 main.py mcp --transport sse     # SSE (HTTP en puerto 8000)
```
Manual técnico completo y catálogo de herramientas en [MCP.md](MCP.md).

## 5. Gestión de Worktrees Concurrentes y Aprovisionamiento de Assets

Flujos multi-agente concurrentes y aislamiento de ramas de desarrollo sin colisiones:
- **`scripts/agent_worktree.sh`**: Gestiona worktrees aislados fuera de `<repo_root>` (`create`, `remove`, `list`).
- **`scripts/setup_worktree_env.sh`**: Configura entorno enlazando `.venv`, `.env` y el catálogo de loops (`assets/loops/`) con la DB (`data/loop_catalog.db`) desde `$PRIMARY_ROOT` mediante symlinks relativos para habilitar stream-copy instantáneo.
- Política CI vs prod del catálogo: [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md).
