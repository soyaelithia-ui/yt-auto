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

Para decisiones rutinarias sin widget humano (bot **Auto** / Yon):

1. Completar preflight de secretos (`python3 main.py run --preflight`) — Telegram + YouTube/Drive siguen obligatorios según el modo.
2. En `.env` / compose: `AUTO_APPROVE=1` y, si se desea el barrido del daemon, `ENABLE_AUTO_PUBLISH_SWEEP=1`.
3. `AUTO_APPROVE` solo aprueba la puerta de revisión; la subida a YouTube sigue gated por cookies/token del canal.
4. `TEST_MODE=1` sigue **prohibido** en producción.

```bash
# Ejemplo (no publica sin credenciales de canal)
AUTO_APPROVE=1 ENABLE_AUTO_PUBLISH_SWEEP=1 python3 main.py daemon --interval 60
```


## 2. Despliegue con Docker Compose (`docker-compose.yml`)

Camino feliz **sin sudo en el host**. El contenedor es autocontenido (FFmpeg, Chromium, `agy` en `/usr/local/bin/agy`). No monta el CLI ni `~/.gemini` del usuario.

- **Límites de Recursos**: `mem_limit: 6g`, `cpus: 4.0`, `pids_limit: 512`, `shm_size: 1g`. Instancia pequeña: `docker compose -f docker-compose.yml -f docker-compose.small.yml up -d` (`2g` / `2` CPU).
- **Aislamiento y Seguridad**: Rootfs de solo lectura (`read_only: true`), tmpfs `/tmp` de 2 GB, `cap_drop: ALL`, usuario no-root `appuser:10001`, named volumes (no bind del workdir). Secretos solo en `./secrets:/run/secrets:ro`.
- **Servidor Telegram Local**: Puerto `127.0.0.1:8081`, hasta 2 GB, zero-copy `file:///`.
- **Antigravity**: AppData en el volumen `yt_agy_home` (`/home/appuser/.gemini`). El token OAuth se copia desde `secrets/antigravity-oauth-token` (login `agy` en una máquina con navegador; el contenedor no abre OAuth interactivo).

```bash
# 1. Stage del ELF agy (gitignored; build/agy no se commitea)
./scripts/stage_agy.sh

# 2. Construir e iniciar (hace falta Docker; no hace falta apt/sudo)
docker compose build
docker compose up -d

# Ver logs / estado
docker compose logs --follow yt-automation
docker compose ps
```

Si el build falla con `build/agy: not found`, falta el paso 1. Si el arranque falla por directorios no escribibles, recrear volúmenes: `docker compose down -v` (borra estado de data/work).

---

## 3. Unidades Systemd (`deploy/systemd/`) y Mantenimiento SQLite

Solo para VPS **con root**. El despliegue Docker de la sección 2 no usa systemd.

- `yt-lanes-daemon.service`: Daemon autónomo multi-carril (`python3 main.py daemon --interval 60`).
- `yt-review-bot.service`: Bot interactivo Telegram (`python3 review/review_bot_daemon.py`).

```bash
# Systemd setup (requiere sudo)
sudo cp deploy/systemd/*.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now yt-lanes-daemon.service yt-review-bot.service

# Respaldo SQLite verificado y barrido de cola
python3 main.py backup && python3 main.py queue sweep
```
