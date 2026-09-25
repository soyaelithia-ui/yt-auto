# Diagnóstico Rápido y Resolución de Errores (Troubleshooting)

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-09  

Matriz de diagnóstico operativo para rápida resolución de incidentes.

---

| Síntoma / Error | Causa Probable | Diagnóstico / Verificación | Solución Recomendada |
|---|---|---|---|
| **`Production preflight: FAIL` (Drive)** | Faltan `DRIVE_FOLDER_ID` / `DRIVE_APPROVED_VIDEO_FOLDER_ID` o credencial Drive. | `python3 main.py run --preflight` | Completar IDs y `DRIVE_KEY_PATH` (o OAuth con scope Drive). Ver [CONFIGURACION_SECRETOS.md](CONFIGURACION_SECRETOS.md) §3 y checklist [OPERACION.md](OPERACION.md) pasos 1–4. |
| **`Production preflight: FAIL` (YouTube publish)** | Cookies/token o channel ID ausentes por canal. | Mismo preflight; `auth check -c <canal>` | Colocar tokens/cookies en `secrets/`; IDs `UC…` en `.env`. §3 CONFIG + pasos 1–4 OPERACION. |
| **`Production preflight: FAIL` (Telegram / TEST_MODE)** | `TELEGRAM_*` incompletos o `TEST_MODE=1`. | Mismo preflight | Rellenar token/chat/user/`TELEGRAM_ALLOWED_CHAT_ID`; `TEST_MODE=0`. §3 CONFIG. |
| **`AUTO_APPROVE=1` pero preflight falla** | Opt-in HITL no omite validación ni puerta YouTube. | Preflight + compose defaults `"0"` | Completar secretos; no esperar bypass. §3 CONFIG; Auto-approve en OPERACION. |
| **HTTP 429 / `WAITING_LLM_QUOTA`** | Límite de cuota diaria o RPM en Google Gemini API. | `python3 main.py status` | Mantener el trabajo en cola; el planificador reintenta automáticamente tras el periodo de enfriamiento. |
| **`NotFoundError` en llamada IA** | Modelo de Gemini retirado o nombre inválido. | Revisar modelo en `src/agents/base_agent.py` | Configurar el modelo canónico exclusivo `gemini-3.8-flash-high`. |
| **Cookies de Sesión Expiradas / `EXPIRING_SOON`** | Vencimiento de tokens `LOGIN_INFO` o `SAPISID`. | Bot Telegram `/health` o `SessionHealthValidator` | Extraer cookies Netscape actualizadas del navegador y guardarlas en `secrets/cookies_<canal>.txt`. |
| **Token OAuth de YouTube Expirado** | Refresh token revocado o desactualizado. | `python3 main.py status --apis` | Ejecutar `python3 main.py auth url -c <canal>` y canjear con `auth exchange <code>`. |
| **Lease de Carril Bloqueado tras Crash (OOM/SIGKILL)** | Worker interrumpido sin liberar lock de carril. | `LeaseReaper` / `shorts_queue.db` | El demonio `lease_reaper.py` libera el lease automáticamente en < 35s. Para liberar manual: `python3 main.py cleanup-leases`. |
| **Error 403 en Google Drive** | Token sin permisos en carpetas de destino. | `python3 main.py run --preflight` | Verificar que la cuenta o Service Account tenga permisos de edición sobre `DRIVE_ROOT_FOLDER_ID`. |
| **SQLite `database is locked`** | Bloqueo por escrituras simultáneas sin modo WAL. | `python3 main.py status` | Verificar modo WAL y timeout configurado (`busy_timeout=15000`). No eliminar archivos `-wal` con la app activa. |
| **Error de Render / Pantalla Negra** | Fallo en resolución de loop o asset corrupto. | `src/visual_validator.py` | El validador rechaza el render automáticamente. Reintentar con catálogo de loops (`assets/loops/`). |
| **Fallo en Telegram Bot (:8081)** | Contenedor local no disponible o permisos. | `curl -I http://localhost:8081` | Asegurar que el contenedor `telegram-bot-api` esté en ejecución (`docker compose up -d telegram-bot-api`). |
| **FFmpeg saturando CPU al 100%** | Concurrencia de hilos no limitada en VPS. | `ps aux | grep ffmpeg` | Asegurar límites de hilos (`-threads 2` a `4`) y prioridad reducida con `nice`. |
| **Saturación de Cuota Pro / HTTP 429 en Agentes** | Cuota de tokens o límites de velocidad alcanzados en Antigravity. | Logs del demonio `CircuitBreaker` o estado `saturated` | El sistema activa automáticamente el `CircuitBreaker` (enfriamiento de 300s) y conmuta a narrativa procedural y SEO determinístico sin detener el demonio. |
| **`Antigravity CLI missing at /usr/local/bin/agy`** | Error de red durante `curl` en construcción de imagen. | `docker compose exec yt-moku ls -l /usr/local/bin/agy` | Reconstruir la imagen sin caché: `docker compose build --no-cache`. |
| **Directorio no escribible uid 10001** | Named volume con ownership de root o de otro UID. | `docker compose exec yt-moku id` | `docker compose down -v` y `up` de nuevo (borra estado). No usar bind de `~/.gemini`. |
| **Agentes tocan el Antigravity del IDE** | AppData del host filtrada por env/symlink. | `pytest tests/unit/test_antigravity_host_isolation.py` | El arnés deniega `~/.gemini/antigravity-cli`. Sembrar token en `secrets/antigravity-oauth-token`, no en el home del usuario. |

---

## Procedimiento de Recuperación de Sesión y Rotación de Cookies

1. **Detección Temprana**: El bot de Telegram emitirá una alerta preventiva si restan menos de 48 horas de vigencia en las cookies de sesión del canal (`LOGIN_INFO`, `SAPISID`).
2. **Exportación de Cookies**: Desde una sesión autenticada en YouTube Studio, exportar las cookies en formato Netscape o JSON mediante la extensión oficial del navegador.
3. **Actualización Segura**: Guardar el archivo en `secrets/cookies_<canal>.txt` o `secrets/cookies_<canal>.json`.
4. **Verificación de Salud**: Ejecutar `/health` en Telegram o invocar `SessionHealthValidator.validate_channel("<canal>")` para confirmar estado `HEALTHY`.

