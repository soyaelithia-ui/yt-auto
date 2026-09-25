# Diagnóstico Rápido y Resolución de Errores (Troubleshooting)

> **Estado:** REPOSITORIO / OFICIAL | **Actualización:** 2026-09 | Matriz de diagnóstico y recuperación de incidentes.

| Síntoma / Error | Causa Probable | Diagnóstico / Verificación | Solución Recomendada |
|---|---|---|---|
| **`preflight: FAIL (Drive)`** | Faltan `DRIVE_*` o credencial Drive. | `python3 main.py run --preflight` | Rellenar IDs y `DRIVE_KEY_PATH` ([CONFIGURACION_SECRETOS.md](CONFIGURACION_SECRETOS.md)). |
| **`preflight: FAIL (YouTube)`** | Cookies/token o IDs ausentes. | Mismo preflight; `auth check -c <canal>` | Colocar tokens/cookies en `secrets/`; IDs `UC…` en `.env`. |
| **`preflight: FAIL (Telegram)`** | `TELEGRAM_*` incompletos o `TEST_MODE=1`. | Mismo preflight | Rellenar token/chat/user en `.env`; fijar `TEST_MODE=0`. |
| **HTTP 429 / Cuota Gemini** | Límite RPM en Google Gemini API. | `python3 main.py status` | Enfriamiento automático 300s; conmuta a respaldos procedurales. |
| **Cookies Expiradas (`EXPIRING`)**| Vencimiento de cookies `LOGIN_INFO`. | Telegram `/health` o `SessionHealthValidator` | Exportar cookies Netscape/JSON a `secrets/cookies_<canal>.json`. |
| **Token OAuth Revocado** | Refresh token de YouTube expirado. | `python3 main.py status --apis` | Ejecutar `auth url -c <canal>` y `auth exchange <code>`. |
| **Lease de Carril Bloqueado** | Crash previo sin liberar lock SQLite. | `LeaseReaper` / `shorts_queue.db` | Auto-liberado en <35s o manual con `python3 main.py cleanup-leases`. |
| **SQLite `database is locked`** | Escrituras simultáneas sin modo WAL. | `python3 main.py status` | Asegurar `journal_mode=WAL` y `PRAGMA busy_timeout=15000`. |
| **Pantalla Negra en Render** | Loop de catálogo corrupto o ausente. | `src/visual_validator.py` | Validar archivos físicos en `assets/loops/` y manifiesto. |
| **Telegram Bot (:8081) Down** | Contenedor local no disponible. | `curl -I http://localhost:8081` | Levantar sidecar: `docker compose up -d telegram-bot-api`. |
| **Saturación CPU FFmpeg** | Hilos no acotados en host limitado. | `ps aux \| grep ffmpeg` | Restringir concurrencia (`-threads 2`) bajo política $\le 2$ Cores. |
| **Directorio no escribible uid 10001**| Permisos root en named volume Docker. | `docker compose exec yt-moku id` | Ejecutar `docker compose down -v && docker compose up -d`. |
| **Fuga a AppData del Host** | Symlink indebido a `~/.gemini`. | `test_antigravity_host_isolation.py` | Sembrar token en `secrets/antigravity-oauth-token`, no en home host. |

## Rotación de Cookies de Sesión
1. Detección preventiva vía `/health` (<48h restantes).
2. Exportar cookies desde YouTube Studio en formato Netscape/JSON.
3. Guardar en `secrets/cookies_<canal>.json` y validar con `/health` (debe reportar `HEALTHY`).
