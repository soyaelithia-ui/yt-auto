# Manual de Operación, CLI Unificado y Despliegue

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

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
| **`queue`** | Administración de colas de producción. | `list`, `pause <canal>`, `resume <canal>`, `activate <canal>`, `sweep` (barrido 6h), `-j` | `python3 main.py queue list` |
| **`clean`** | Limpieza de temporales y caché. | `-d` (dry-run), `--cache` (trabajos expirados), `--sessions` | `python3 main.py clean --cache -d` |
| **`auth`** | Gestión de tokens OAuth2 de YouTube. | `url`, `exchange <code>`, `-c` (canal) | `python3 main.py auth url -c moku` |
| **`backup`** | Respaldo atómico de SQLite con verificación. | `-o` (directorio destino), `-j` (salida JSON) | `python3 main.py backup` |
| **`migrate`** | Migraciones de esquema SQLite. | `-d` (dry-run), `-j` (salida JSON) | `python3 main.py migrate -d` |
| **`service`** | Control de servicios Systemd y logs. | `build`, `start`, `stop`, `restart`, `logs` | `python3 main.py service logs` |
| **`loop`** | Administración y síntesis de bucles de video web (Three.js/Canvas/CSS). | `list`, `generate`, `preview`, `audit`, `daemon`, `-c` (categoría), `-o` (orientación), `-n` (cantidad), `-j` (JSON) | `python3 main.py loop list`<br>`python3 main.py loop generate -c cosmic_horror -o vertical`<br>`python3 main.py loop audit` |


### Opciones Globales (heredables antes o después del subcomando)
- `-p`, `--profile {prod,cli,test}`: Perfil de ejecución (por defecto: `cli` en terminal local, `prod` en daemon).
- `--db-path <ruta>`: Ruta personalizada a la base de datos SQLite.
- `-y`, `--yes`: Confirmación automática de operaciones críticas sobre perfiles de producción.

---

## 2. Despliegue con Docker Compose (`docker-compose.yml`)

Entorno de producción supervisado:
- **Límites de Recursos**: `mem_limit: 6g`, `cpus: 4.0`, `pids_limit: 512`, `shm_size: 1g`.
- **Aislamiento y Seguridad**: Rootfs de solo lectura (`read_only: true`), tmpfs `/tmp` de 2 GB, `cap_drop: ALL`, usuario no-root `appuser:10001`.
- **Servidor Telegram Local**: Integrado en el puerto `8081` con soporte para cargas de hasta 2 GB y transporte zero-copy `file:///`.

```bash
# Iniciar servicios en segundo plano
docker compose up -d

# Ver logs en tiempo real
docker compose logs --follow yt-automation

# Verificar estado de los contenedores
docker compose ps
```

---

## 3. Unidades Systemd (`deploy/systemd/`)

Para despliegues nativos en VPS:

| Unidad Systemd | Función | Comando Ejecutado |
|---|---|---|
| `yt-lanes-daemon.service` | Daemon autónomo de producción multi-carril. | `python3 main.py daemon --interval 60` |
| `yt-review-bot.service` | Bot de revisión interactiva Telegram. | `python3 review/review_bot_daemon.py` |

```bash
# Instalación y habilitación
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yt-lanes-daemon.service yt-review-bot.service

# Monitoreo
systemctl status yt-lanes-daemon.service
journalctl -u yt-lanes-daemon.service --follow
```

---

## 4. Mantenimiento, Respaldo y Recuperación de SQLite

```bash
# 1. Respaldo verificado con PRAGMA quick_check
python3 main.py backup

# 2. Simular migraciones de esquema
python3 main.py migrate -d

# 3. Aplicar migraciones
python3 main.py migrate

# 4. Barrido de auto-publicación de revisiones pendientes (6 horas)
python3 main.py queue sweep
```
