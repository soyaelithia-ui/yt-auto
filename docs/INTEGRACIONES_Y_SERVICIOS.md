# Integraciones de Servicios y Contratos de API

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Contratos de integración con servicios externos, endpoints y protocolos de comunicación.

---

## 1. Telegram Bot API (Servidor Local 2 GB)

Para permitir el envío de videos master sin compresión destructiva (hasta 2000 MB), el sistema utiliza un servidor local `telegram-bot-api` (`aiogram/telegram-bot-api:latest`) en el puerto 8081.

### Endpoints Principales (`review/telegram_bot.py`)

| Endpoint | Parámetros Clave | Uso en el Sistema |
|---|---|---|
| `POST /sendVideo` | `chat_id`, `video` (URI `file:///` o multipart), `supports_streaming=true`, `reply_markup` | Despacho de video master al operador para revisión con botones inline. |
| `POST /sendPhoto` | `chat_id`, `photo`, `caption` | Envío de miniaturas y portadas de alta resolución. |
| `POST /sendMessage` | `chat_id`, `text`, `parse_mode` | Alertas de estado, reportes de cola y logs operativos. |
| `GET /getUpdates` | `offset`, `timeout=25`, `allowed_updates=["callback_query"]` | Long-polling para captura de respuestas del operador (`approve`, `redo`, `reject`). |
| `POST /answerCallbackQuery` | `callback_query_id`, `text`, `show_alert` | Confirmación instantánea tras interacción con botones. |
| `POST /editMessageText` | `chat_id`, `message_id`, `text` | Actualización del estado del mensaje tras la acción de revisión. |

### Transporte Zero-Copy (`file:///`)
Cuando `TELEGRAM_USE_LOCAL_FILES=1`, el bot no sube el archivo por red; envía la ruta montada local (`file:///app/work/<run_id>/master.mp4`). El servidor local lee directamente el archivo en disco (<0.05s de latencia y 0 MB de uso de memoria de red).

---

## 2. YouTube Data API v3 & Autenticación Oficial
- **SDK Oficial**: Utiliza `google-auth`, `google-auth-oauthlib` (`InstalledAppFlow`) y `google-api-python-client` (`build("youtube", "v3", ...)`).
- **Subida Primaria (API v3)**: Endpoint `videos.insert` con soporte de subida reanudable (`MediaFileUpload(resumable=True)`).
- **Control y Mutaciones (`src/youtube/control.py`)**: Endpoints `videos.delete`, `videos.update` (privacidad) y estadísticas `videos.list`, verificando la propiedad del canal (`expected_youtube_channel_id`) antes de cualquier mutación.
- **Subida Secundaria (Playwright)**: En caso de agotamiento de cuota diaria de API (HTTP 403 `quotaExceeded`), el sistema conmuta a subida automatizada vía navegador con cookies descifradas de sesión.

---

## 3. Google Drive API v3 (Respaldo en la Nube y Verificación)
- **SDK Oficial**: Factoría `build("drive", "v3", ...)` con soporte unificado para tokens de usuario OAuth (`Credentials`), Service Accounts (`drive_key.json`) o credenciales en memoria de `gcloud auth`.
- **Idempotencia y Respaldo Verificado**: Asocia la propiedad `yt_backup_key` en `appProperties` para evitar duplicados en la nube y valida la huella (`DriveProof`) antes de dar por completado el respaldo.

---

## 4. Microsoft Edge-TTS (Síntesis Neural de Voz)

- Genera locución con calidad neural humana y acento neutro:
  * Canal **MOKU**: `es-MX-JorgeNeural` (tono profundo y misterioso para relatos de terror).
  * Canal **AELITHIA**: `es-MX-DaliaNeural` (tono empático y dinámico para drama/AITA).
- Latencia típica: ~2 segundos por relato completo con costo cero de infraestructura.
