# Diagnóstico Rápido y Resolución de Errores (Troubleshooting)

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Matriz de diagnóstico operativo para rápida resolución de incidentes.

---

| Síntoma / Error | Causa Probable | Diagnóstico / Verificación | Solución Recomendada |
|---|---|---|---|
| **HTTP 429 / `WAITING_LLM_QUOTA`** | Límite de cuota diaria o RPM en Google Gemini API. | `python3 main.py status` | Mantener el trabajo en cola; el planificador reintenta automáticamente tras el periodo de enfriamiento. |
| **`NotFoundError` en llamada IA** | Modelo de Gemini retirado o nombre inválido. | Revisar modelo en `src/agents/base_agent.py` | Configurar el modelo canónico `gemini-3.7-flash` o secundario `gemini-3.6-flash`. |
| **Cookies de Sesión Expiradas / `EXPIRING_SOON`** | Vencimiento de tokens `LOGIN_INFO` o `SAPISID`. | Bot Telegram `/health` o `SessionHealthValidator` | Extraer cookies Netscape actualizadas del navegador y guardarlas en `secrets/cookies_<canal>.txt`. |
| **Token OAuth de YouTube Expirado** | Refresh token revocado o desactualizado. | `python3 main.py status --apis` | Ejecutar `python3 main.py auth url -c <canal>` y canjear con `auth exchange <code>`. |
| **Lease de Carril Bloqueado tras Crash (OOM/SIGKILL)** | Worker interrumpido sin liberar lock de carril. | `LeaseReaper` / `shorts_queue.db` | El demonio `lease_reaper.py` libera el lease automáticamente en < 35s. Para liberar manual: `python3 main.py cleanup-leases`. |
| **Error 403 en Google Drive** | Token sin permisos en carpetas de destino. | `python3 main.py run --preflight` | Verificar que la cuenta o Service Account tenga permisos de edición sobre `DRIVE_ROOT_FOLDER_ID`. |
| **SQLite `database is locked`** | Bloqueo por escrituras simultáneas sin modo WAL. | `python3 main.py status` | Verificar modo WAL y timeout configurado (`busy_timeout=15000`). No eliminar archivos `-wal` con la app activa. |
| **Error de Render / Pantalla Negra** | Fallo en resolución de loop o asset corrupto. | `src/visual_validator.py` | El validador rechaza el render automáticamente. Reintentar con catálogo de loops (`assets/loops/`). |
| **Fallo en Telegram Bot (:8081)** | Contenedor local no disponible o permisos. | `curl -I http://localhost:8081` | Asegurar que el contenedor `telegram-bot-api` esté en ejecución (`docker compose up -d telegram-bot-api`). |
| **FFmpeg saturando CPU al 100%** | Concurrencia de hilos no limitada en VPS. | `ps aux | grep ffmpeg` | Asegurar límites de hilos (`-threads 2` a `4`) y prioridad reducida con `nice`. |
| **`docker compose build`: `build/agy: not found`** | No se stageó el CLI Antigravity. | `ls -l build/agy` | `./scripts/stage_agy.sh` (requiere `agy` en PATH o `AGY_BIN`) y volver a construir. No commitear el ELF. |
| **`Antigravity CLI missing at /usr/local/bin/agy`** | Imagen construida sin el binario. | `docker compose exec yt-automation ls -l /usr/local/bin/agy` | Rebuild tras `stage_agy.sh`. El compose ya no monta `agy` del host. |
| **Directorio no escribible uid 10001** | Named volume con ownership de root o de otro UID. | `docker compose exec yt-automation id` | `docker compose down -v` y `up` de nuevo (borra estado). No usar bind de `~/.gemini`. |
| **Agentes tocan el Antigravity del IDE** | AppData del host filtrada por env/symlink. | `pytest tests/unit/test_antigravity_host_isolation.py` | El arnés deniega `~/.gemini/antigravity-cli`. Sembrar token en `secrets/antigravity-oauth-token`, no en el home del usuario. |

---

## Procedimiento de Recuperación de Sesión y Rotación de Cookies

1. **Detección Temprana**: El bot de Telegram emitirá una alerta preventiva si restan menos de 48 horas de vigencia en las cookies de sesión del canal (`LOGIN_INFO`, `SAPISID`).
2. **Exportación de Cookies**: Desde una sesión autenticada en YouTube Studio, exportar las cookies en formato Netscape o JSON mediante la extensión oficial del navegador.
3. **Actualización Segura**: Guardar el archivo en `secrets/cookies_<canal>.txt` o `secrets/cookies_<canal>.json`.
4. **Verificación de Salud**: Ejecutar `/health` en Telegram o invocar `SessionHealthValidator.validate_channel("<canal>")` para confirmar estado `HEALTHY`.

