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

## 2. YouTube Data API v3 & Subida Híbrida

1. **Subida Primaria (API v3)**: Utiliza `google-api-python-client` con el endpoint `videos.insert` y tokens OAuth2 específicos por canal.
2. **Subida Secundaria (Playwright TS)**: En caso de agotamiento de cuota diaria de API (HTTP 403 `quotaExceeded`), el sistema conmuta a subida automatizada vía navegador con sesiones seguras.

---

## 3. Google Drive API v3 (Respaldo en la Nube)

- Respalda videos aprobados, miniaturas y metadatos estructurados en carpetas organizadas por canal.
- Calcula y valida la huella criptográfica SHA-256 (`DriveProof`) para confirmar la integridad del archivo transferido.

---

## 4. Microsoft Edge-TTS (Síntesis Neural de Voz)

- Genera locución con calidad neural humana y acento neutro:
  * Canal **MOKU**: `es-MX-JorgeNeural` (tono profundo y misterioso para relatos de terror).
  * Canal **AELITHIA**: `es-MX-DaliaNeural` (tono empático y dinámico para drama/AITA).
- Latencia típica: ~2 segundos por relato completo con costo cero de infraestructura.
