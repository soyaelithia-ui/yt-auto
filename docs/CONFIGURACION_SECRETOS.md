# Configuración, Variables de Entorno y Secretos

> **Estado:** OFICIAL | **Actualización:** 2026-09 | Variables de entorno, seguridad y preflight para `yt-auto`.

## 1. Reglas de Seguridad (Cero Hardcoding)
1. Cero credenciales reales en Git. Secretos exclusivamente en `.env` (`chmod 600`) o montados en `/run/secrets` (ro).
2. `.env` y `secrets/` ignorados en `.gitignore`. Versionar únicamente `.env.example` con secretos vacíos (`VARIABLE=`).
3. Logs públicos nunca exponen rutas a secretos ni valores de cookies/tokens.
4. Sesiones de navegador/Playwright deben purgar cookies en memoria (`context.clear_cookies()`).

## 2. Inventario Consolidado de Variables de Entorno

| Dominio | Variable | Descripción y Ejemplo |
|---|---|---|
| **Persistencia** | `YOUTUBE_AUTOMATION_DB` | Ruta base de datos principal (`data/shorts_queue.db`). |
| | `VIDEO_REVIEW_DB_PATH` | Base de datos de Telegram (`data/review_state.db`). |
| | `WORK_ROOT` / `ARTIFACT_ROOT` | Temporales de trabajo (`work/`) y artefactos persistentes (`artifacts/`). |
| | `SECRETS_DIR` | Montaje de credenciales (`/run/secrets` o `secrets/`). |
| | `ANTIGRAVITY_AGENTS_APP_DATA_DIR` | Directorio de sesión para agentes de IA (`.bot_home/.gemini/antigravity-cli`). |
| **Inteligencia** | `GEMINI_API_KEY` | Clave API Google Gemini para fallback REST si no hay sesión CLI `agy`. |
| **YouTube & Drive** | `YOUTUBE_CLIENT_SECRETS_FILE` | Archivo client secrets OAuth2 Google (`secrets/client_secret.json`). |
| | `CHANNEL_KEY` | Canal activo por defecto (`horror`, `drama`, `scifi`). |
| | `CHANNEL_YOUTUBE_CHANNEL_ID` | ID público de canal YouTube (`UC...`). |
| | `CHANNEL_YOUTUBE_TOKEN_PATH` | Ruta al token OAuth2 (`secrets/tokens/<canal>.json`). |
| | `CHANNEL_COOKIES_PATH` | Ruta a cookies de sesión (`secrets/cookies/<canal>.json`). |
| | `DRIVE_FOLDER_ID` / `DRIVE_KEY_PATH` | Carpeta operativa en Drive y Service Account (`secrets/drive_key.json`). |
| **Telegram Review**| `TELEGRAM_BOT_TOKEN` | Token oficial de BotFather (preflight requerido). |
| | `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_ID` | Identificadores de chat y usuario autorizado para aprobación HITL. |
| | `TELEGRAM_API_BASE_URL` | Endpoint local o cloud (`http://telegram-bot-api:8081`). |
| | `AUTO_APPROVE` / `ENABLE_AUTO_PUBLISH_SWEEP` | Opt-in para aprobación automática (`0`/`1`) y barrido de cola (`24h`). |

## 3. Autenticación Oficial Google CLI (`main.py auth`)

Gestión y diagnóstico OAuth2 oficial (`google-auth`, `google-api-python-client`):
```bash
python3 main.py auth login -c horror       # Login interactivo 1-clic
python3 main.py auth url -c horror         # Generar URL de autorización headless
python3 main.py auth exchange <CODE> -c horror  # Canjear código OAuth2
python3 main.py auth check -c horror       # Verificación de credenciales y permisos
python3 main.py auth standardize -c horror # Estandarizar tokens a formato canónico
```

## 4. Validación Preflight (`main.py run --preflight`)

Comprueba en caliente la coherencia de credenciales antes de iniciar daemons:
- **`require_drive`**: Verifica `DRIVE_FOLDER_ID`, `DRIVE_APPROVED_VIDEO_FOLDER_ID` y clave `DRIVE_KEY_PATH` o token con scope Drive.
- **`require_publish`**: Verifica cookies, token OAuth2 y `CHANNEL_YOUTUBE_CHANNEL_ID` por cada canal activo.
- **`require_review`**: Verifica `TELEGRAM_BOT_TOKEN`, IDs numéricos de chat/usuario y que `TEST_MODE != 1`.
- **Salida**: `Production preflight: PASS` (código 0) o `Production preflight: FAIL: <razón>` (código 1).
