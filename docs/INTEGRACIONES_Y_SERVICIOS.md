# Integraciones de Servicios y Contratos de API

> **Estado:** REPOSITORIO / OFICIAL | **Actualización:** 2026-09 | Contratos externos: Telegram, YouTube, Drive y Edge-TTS.

## 1. Telegram Bot API (Servidor Local 2 GB & Cloud Fallback)

Expone una fachada en `src/telegram` (`TelegramNotifier`, `TelegramReviewBot`, `InteractiveTelegramBot`):
- **Endpoints Clave**: `POST /sendVideo` (soporte `file:///` zero-copy hasta 2000 MB), `POST /sendPhoto`, `POST /sendMessage`, `GET /getUpdates` (long-polling con offset pre-despacho), `POST /answerCallbackQuery`.
- **Comandos Principales**: `/start`, `/help`, `/status` (salud y cola), `/health` (diagnóstico cuotas), `/autopilot` (conmutación 24/7), `/shorts`, `/long`, `/seo`, `/latest`, `/stats`, `/priv`, `/pub`, `/del`.
- **Transporte Zero-Copy**: Con `TELEGRAM_USE_LOCAL_FILES=1`, transfiere `file:///` con latencia <0.05s y 0 MB de memoria de red. Si es Cloud API (>50 MB), transcodifica proxy liviano 720p sin tocar el máster.

## 2. Publicación en YouTube: Sesión Directa & Data API v3

- **Subida por Sesión Persistente (`src/youtube/session_uploader.py`)**: Método primario para eludir el techo de cuota de API v3 (10,000 pts/día) usando cookies autenticadas (`LOGIN_INFO`, `SAPISID`).
- **Validador de Salud (`SessionHealthValidator`)**: Detección preventiva de cookies expiradas o próximas a caducar (`EXPIRING_SOON` < 48h).
- **YouTube Data API v3 (`google-api-python-client`)**: Canal OAuth2 oficial para sincronización de metadatos, tags y control de visibilidad.

## 3. Google Drive API v3 (Respaldo en Nube)

- **SDK Oficial**: Factoría `build("drive", "v3", ...)` compatible con OAuth de usuario y Service Account (`secrets/drive_key.json`).
- **Idempotencia (`DriveProof`)**: Asocia `yt_backup_key` en `appProperties` para prevenir subidas duplicadas y certificar la integridad del respaldo.

## 4. Microsoft Edge-TTS y Motor de Audio FFmpeg

- **Síntesis Neural Edge-TTS**: Locución neutra de alta fidelidad:
  - Canal Horror: `es-MX-JorgeNeural` o `es-ES-AlvaroNeural` (graves cinematográficos).
  - Canal Drama: `es-MX-DaliaNeural` (expresividad dinámica para relatos AITA).
- **Masterización FFmpeg**: Filtro `loudnorm` calibrado a EBU R128 (-14.0 LUFS, TP ≤ -1.5 dBTP) y sidechain ducking de música de fondo a -18 dB.
