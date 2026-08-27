# Diagnóstico Rápido y Resolución de Errores (Troubleshooting)

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Matriz de diagnóstico operativo para rápida resolución de incidentes.

---

| Síntoma / Error | Causa Probable | Diagnóstico / Verificación | Solución Recomendada |
|---|---|---|---|
| **HTTP 429 / `WAITING_LLM_QUOTA`** | Límite de cuota diaria o RPM en Google Gemini API. | `python3 main.py status` | Mantener el trabajo en cola; el planificador reintenta automáticamente tras el periodo de enfriamiento. |
| **`NotFoundError` en llamada IA** | Modelo de Gemini retirado o nombre inválido. | Revisar modelo en `src/config.py` | Configurar el modelo canónico `gemini-3.6-flash` o secundario `gemini-2.5-flash`. |
| **Token OAuth de YouTube Expirado** | Refresh token revocado o desactualizado. | `python3 main.py status --apis` | Ejecutar `python3 main.py auth url -c <canal>` y canjear con `auth exchange <code>`. |
| **Error 403 en Google Drive** | Token sin permisos en carpetas de destino. | `python3 main.py run --preflight` | Verificar que la cuenta o Service Account tenga permisos de edición sobre `DRIVE_ROOT_FOLDER_ID`. |
| **SQLite `database is locked`** | Bloqueo por escrituras simultáneas sin modo WAL. | `python3 main.py status` | Verificar modo WAL y timeout configurado (`busy_timeout=15000`). No eliminar archivos `-wal` con la app activa. |
| **Error de Render / Pantalla Negra** | Fallo en resolución de loop o asset corrupto. | `src/visual_validator.py` | El validador rechaza el render automáticamente. Reintentar con catálogo de loops (`assets/loops/`). |
| **Fallo en Telegram Bot (:8081)** | Contenedor local no disponible o permisos. | `curl -I http://localhost:8081` | Asegurar que el contenedor `telegram-bot-api` esté en ejecución (`docker compose up -d telegram-bot-api`). |
| **FFmpeg saturando CPU al 100%** | Concurrencia de hilos no limitada en VPS. | `ps aux | grep ffmpeg` | Asegurar límites de hilos (`-threads 2` a `4`) y prioridad reducida con `nice`. |
