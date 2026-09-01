# Integraciones de Servicios y Contratos de API

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Contratos de integración con servicios externos, endpoints y protocolos de comunicación.

---

## 1. Telegram Bot API (Servidor Local 2 GB & Integración Nativa)

Para permitir el envío de videos máster sin compresión destructiva (hasta **2000 MB / 2 GB**), el sistema integra nativamente el servidor local `telegram-bot-api` (`aiogram/telegram-bot-api:latest`) en el puerto `8081`, con fallback automático a la API Cloud estándar (**50 MB** con transcodificación proxy 720p).

### Arquitectura y Fachada Canónica (`src/telegram`)
La integración expone una fachada unificada en `src/telegram`:
- **`TelegramReviewBot`**: Cliente de bajo nivel con pool de conexiones (`TelegramHttpClient`), reintentos exponenciales para errores 5xx/429 y soporte para transporte local `file://`.
- **`TelegramNotifier`**: Notificador de alto nivel con firmas normalizadas (`send_message`, `send_status_update`, `send_render_notification`, `send_video_preview`, `send_video`, `send_photo`, `send_document`).
- **`InteractiveTelegramBot`**: Motor de polling interactivo y enrutamiento con soporte completo para comandos y botones.
- **`poll_callbacks`**: Bucle de long-polling blindado contra actualizaciones venenosas (avance de offset pre-despacho y tolerancia a fallos).

### Endpoints y Métodos Principales (`review/telegram_bot.py`)

| Endpoint | Parámetros Clave | Uso en el Sistema |
|---|---|---|
| `POST /sendVideo` | `chat_id`, `video` (URI `file:///` o multipart), `supports_streaming=true`, `reply_markup` | Despacho de video máster (hasta 2000 MB) al operador con teclado inline 2x2. |
| `POST /sendPhoto` | `chat_id`, `photo`, `caption` | Envío de miniaturas y portadas de alta resolución. |
| `POST /sendDocument` | `chat_id`, `document`, `caption` | Envío de paquetes de datos y archivos de respaldo. |
| `POST /sendMessage` | `chat_id`, `text`, `parse_mode`, `reply_markup` | Alertas de estado, menús interactivos y reportes de producción. |
| `GET /getUpdates` | `offset`, `timeout=25` | Long-polling continuo para captura de mensajes y callbacks. |
| `POST /answerCallbackQuery` | `callback_query_id`, `text`, `show_alert` | Confirmación visual e instantánea tras interacción con botones. |
| `POST /editMessageText` | `chat_id`, `message_id`, `text`, `reply_markup` | Actualización de estado en el mensaje original tras la acción de revisión. |

### Suite de Comandos Unificados

| Comando | Descripción |
|---|---|
| `/start`, `/help`, `/ayuda` | Despliega el menú principal interactivo con estado del servidor (2000 MB vs 50 MB) y botones de acción rápida. |
| `/menu` | Abre el panel inline de control de videos de YouTube. |
| `/status` | Muestra estado de AutoPilot 24/7, trabajos en caché, revisiones pendientes y modo de servidor Telegram. |
| `/health [canal]` | Diagnóstico en vivo de cuotas y estado de YouTube Data API, Google Drive y cookies de sesión. |
| `/autopilot` | Conmuta la ejecución autónoma de producción desatendida 24/7. |
| `/shorts <tema>` | Genera un YouTube Short procedural vertical (9:16). |
| `/long <tema>` | Genera un documental procedural horizontal (16:9, 10+ minutos). |
| `/seo <tema>` | Optimización algorítmica de metadatos (A/B testing de títulos, tags y comentario fijado). |
| `/latest`, `/ver` | Inspecciona el último entregable generado o la última revisión pendiente en cola. |
| `/stats <video_id> [canal]` | Estadísticas en vivo de reproducciones, likes y comentarios de YouTube. |
| `/priv`, `/pub`, `/unlist <video_id>` | Gestión directa de la visibilidad de videos en YouTube. |
| `/del`, `/delsi <video_id>` | Previsualización y borrado seguro de videos de YouTube. |

### Transporte Zero-Copy (`file:///`) vs Fallback Cloud
1. **Servidor Local (`is_local_bot_api() == True`)**:
   - Cuando `TELEGRAM_USE_LOCAL_FILES=1` (por defecto en local), el bot envía la URI directa `file:///app/work/.../video.mp4` o la ruta absoluta en disco. El servidor `telegram-bot-api` transmite el archivo directamente sin transferencias HTTP intermedias (**<0.05s de latencia y 0 MB de memoria de red**). Límite de **2000 MB**.
2. **Cloud Fallback (`is_local_bot_api() == False`)**:
   - Para archivos que exceden el límite de 50 MB de la API Cloud de Telegram, `_build_review_proxy` codifica determinísticamente un proxy ligero en 720p (<45 MB) para previsualización, manteniendo intacto el máster original en disco y Google Drive para publicación en YouTube.

---

## 2. Publicación en YouTube: Sesión Directa / Cookies & Data API v3

- **Subida Primaria por Sesión Persistente (`src/youtube/session_uploader.py`)**: Para evitar el agotamiento de la cuota diaria de YouTube Data API v3 (10,000 unidades = ~6 videos máx), el método primario de publicación de producción masiva opera mediante **sesiones autenticadas persistentes** inyectando cookies Netscape/JSON (`LOGIN_INFO`, `SAPISID`, `__Secure-3PSID`).
- **Validador de Salud de Sesión (`SessionHealthValidator`)**: Inspección profunda previa a cualquier renderizado. Si las cookies están en estado `EXPIRING_SOON` (< 48 horas restantes), emite una advertencia al operador y notifica por Telegram vía `/health`. Si están `EXPIRED` o `INVALID`, aborta preventivamente para evitar fallos a mitad de camino.
- **Control y Metadatos (`src/youtube/control.py`)**: Mutaciones de privacidad, borrado y consulta de estadísticas a través de endpoints protegidos por verificación estricta de propiedad de canal.
- **Canal de Respaldo API v3**: Disponible para sincronización de metadatos o subidas aisladas mediante OAuth (`google-api-python-client`).

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
