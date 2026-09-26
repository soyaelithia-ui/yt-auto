# Configuración, Variables de Entorno y Secretos
> **Repositorio Oficial:** [https://github.com/soyaelithia-ui/yt-auto.git](https://github.com/soyaelithia-ui/yt-auto.git) | **Gobernanza:** Repositorio privado con resolución dinámica de identidades y secretos desacoplados.  
> **Última actualización:** 2026-09  
Inventario estructurado de variables de entorno, directivas de seguridad y políticas contra hardcoding para `yt-auto`.
> [!CAUTION]
> **REGLAS ABSOLUTAS DE SEGURIDAD (POLÍTICA DE CERO HARDCODING)**:
> 1. Ningún valor real de claves API, tokens OAuth, cookies o contraseñas debe incluirse en el repositorio ni escribirse como constante hardcodeada en el código fuente.
> 2. Los secretos deben residir exclusivamente en `.env` (local con `chmod 600`) o montarse en `/run/secrets` (Docker/VPS en modo lectura `ro`).
> 3. El archivo `.env` y el directorio `secrets/` NUNCA deben commitearse (deben permanecer en `.gitignore`).
> 4. Solo el archivo plantilla `.env.example` debe versionarse. **Secretos** (API keys, tokens OAuth, cookies, contraseñas, client secrets) DEBEN ir siempre vacíos (`VARIABLE=`). **Defaults no secretos sí están permitidos** y son intencionales: flags (`0`/`1`/`true`), timeouts, presets de encode, rutas relativas genéricas de plantilla (`*_PATH` / `*_FILE` / `*_DIR` bajo `secrets/` u otros roots relativos, p. ej. `secrets/youtube_token.json`, `SECRETS_DIR=secrets`), y knobs operativos. Nunca valores reales de producción ni credenciales. Lo refuerza `tests/unit/test_security_policies.py::test_env_example_contains_no_real_secrets`.
> 5. Los diccionarios y logs públicos (como `ChannelSettings.public_dict()`) NUNCA deben exponer rutas de disco a secretos ni valores de cookies/tokens; solo indicadores booleanos de disponibilidad.
> 6. Las sesiones automatizadas de Playwright deben purgar sus cookies de memoria (`context.clear_cookies()`) antes del cierre para evitar residuos en memoria.
> 7. Tests, fixtures, mocks y scripts de auditoría NUNCA pueden incrustar credenciales reales ni usarlas como agujas de regex. Solo firmas de formato genéricas o tokens sintéticos construidos en runtime.
> 8. Homes de agentes (`.codex/`, `.claude/`, `.gemini/`, `.agents/`, `.opencode/`) son locales y no se versionan.
> 9. Si hay una filtración: no abrir issue público; hacer el repositorio privado; rotar todas las credenciales; invalidar el proyecto/API de Google afectado.
> 10. Residual risk: rotated literals MAY remain in git objects and stale refs. History rewrite is not required.
---

## 1. Inventario de Variables de Entorno

### A. Directorios y Persistencia
| Variable | Descripción | Valor Predeterminado / Ejemplo |
|---|---|---|
| `YOUTUBE_AUTOMATION_DB` | Ruta a la base de datos principal de cola SQLite. | `data/shorts_queue.db` |
| `VIDEO_REVIEW_DB_PATH` | Ruta a la base de datos de revisión de Telegram. | `data/review_state.db` |
| `WORK_ROOT` | Directorio temporal de trabajo y renders. | `work/` |
| `ARTIFACT_ROOT` | Directorio persistente de artefactos generados. | `artifacts/` |
| `SECRETS_DIR` | Directorio de montaje de secretos. Semilla `antigravity-oauth-token` / `settings.json` hacia AppData (copia `0600`, nunca symlink al host). | `/run/secrets` o `secrets/` |
| `ANTIGRAVITY_AGENTS_APP_DATA_DIR` | Directorio aislado de sesión para agentes de IA (instancia predeterminada). | `.bot_home/.gemini/antigravity-cli` (host) / `/home/appuser/.gemini/antigravity-cli` (Docker) |
| `ANTIGRAVITY_AGENTS_APP_DATA_DIR_<ID>` | Directorio aislado para una instancia específica (ej. `PIPELINE_CREATIVE`). | `.bot_home_<id>/.gemini/antigravity-cli` |
| `AGY_BIN` | Ruta al CLI Antigravity. En Docker vive **dentro** de la imagen. | `/usr/local/bin/agy` |

### B. Inteligencia Artificial (Antigravity local y Google Gemini)
| Variable | Descripción | Uso |
|---|---|---|
| `AGY_MODEL` | Override opcional de un modelo concreto (por defecto `gemini-3.8-flash-high`); se valida contra `agy models` antes de ejecutar. | `gemini-3.8-flash-high` |
| `AGY_MODEL_PREFERENCES` | Lista ordenada de preferencias separadas por coma. | `gemini-3.8-flash-high,gemini-3.8-flash-medium,gemini-3.8-flash-low` |
| `AGY_FREE_FALLBACK_MODEL` | Fallback permitido para el plan gratuito; debe aparecer en el catálogo de `agy`. | `gemini-3.8-flash-low` |
| `AGY_ACCOUNT_TIER` | Etiqueta operativa para observabilidad; no concede cuota ni permisos. | `pro` |
| `AGY_MODEL_DISCOVERY_TIMEOUT_SECONDS` | Timeout de la consulta local `agy models`. | `20` |
| `GEMINI_API_KEY` | Clave opcional para el proveedor REST de respaldo. | Vacía; no es necesaria para el arnés CLI con sesión. |

El arnés consulta el catálogo oficial de `agy models`; si una preferencia no está disponible, selecciona el siguiente modelo compatible en la cadena de preferencias o el fallback oficial.

### C. Google Drive API v3 (Respaldo)
| Variable | Descripción | Valor Predeterminado / Requisito |
|---|---|---|
| `DRIVE_FOLDER_ID` | Carpeta raíz operativa (preflight `require_drive`). | Obligatorio para respaldar. |
| `DRIVE_APPROVED_VIDEO_FOLDER_ID` | Carpeta de videos aprobados (preflight). | Obligatorio para respaldar. |
| `DRIVE_ROOT_FOLDER_ID` | Alias/carpeta raíz en Drive (compose). | Opcional si `DRIVE_FOLDER_ID` cubre. |
| `DRIVE_APPROVED_FOLDER_ID` | Carpeta aprobados (legado/compose). | Opcional. |
| `DRIVE_APPROVED_COVER_FOLDER_ID` / `DRIVE_METADATA_FOLDER_ID` / `DRIVE_PUBLISHED_FOLDER_ID` / `DRIVE_REJECTED_FOLDER_ID` / `DRIVE_ARCHIVE_FOLDER_ID` | Carpetas de ciclo de vida (compose). | IDs vacíos en plantilla. |
| `DRIVE_USE_GCLOUD` | Credenciales activas de `gcloud auth`. | `0` / `1`. |
| `DRIVE_KEY_PATH` | JSON Service Account (si no hay OAuth Drive en token de canal). | `secrets/drive_key.json` → `/run/secrets/drive_key.json` |

### D. Canales de YouTube, Identidades y Publicación
| Variable | Descripción | Detalle / Dinámico |
|---|---|---|
| `CHANNEL_KEY` | Identificador del canal activo a procesar por defecto. | `horror`, `drama`, `scifi` (resuelto en `config/channels/<id>.json`). |
| `CHANNEL_HANDLE` | Handle global dinámico del canal activo (`@Canal`). | Override genérico para el canal en ejecución. |
| `CHANNEL_URL` | URL de YouTube del canal activo. | Override genérico (`https://youtube.com/@Canal`). |
| `CHANNEL_NAME` | Nombre público del canal activo. | Override genérico. |
| `CHANNEL_TITLE` | Título / Nombre visible del canal. | Override genérico. |
| `CHANNEL_TOPIC` | Temática / Nicho del canal. | Override genérico. |
| `CHANNEL_TARGET_AUDIENCE` | Audiencia objetivo del canal. | Override genérico. |
| `CHANNEL_YOUTUBE_CHANNEL_ID` | ID de canal de YouTube (`UC...`). | Override genérico para subida y preflight. |
| `CHANNEL_YOUTUBE_TOKEN_PATH` | Ruta al token OAuth2 de YouTube del canal. | `secrets/tokens/<channel_id>.json` |
| `CHANNEL_COOKIES_PATH` | Ruta a cookies de Playwright del canal. | `secrets/cookies/<channel_id>.json` |

### E. Telegram Bot API y Puerta de Revisión
| Variable | Descripción | Valor Predeterminado / Ejemplo |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token de BotFather. | Requerido (preflight). |
| `TELEGRAM_CHAT_ID` | Chat de entrega de videos. | Requerido (numérico). |
| `TELEGRAM_ALLOWED_USER_ID` | Usuario autorizado a aprobar. | Requerido (numérico). |
| `TELEGRAM_ALLOWED_CHAT_ID` | Chat autorizado (preflight). | Requerido (numérico). |
| `TELEGRAM_API_BASE_URL` | Bot API local o cloud. | `http://telegram-bot-api:8081` |
| `TELEGRAM_LOCAL` / `TELEGRAM_USE_LOCAL_FILES` | API local + zero-copy `file:///`. | `true` / `1` |
| `TELEGRAM_REQUEST_TIMEOUT_SECONDS` / `TELEGRAM_MEDIA_TIMEOUT_SECONDS` / `TELEGRAM_MAX_FILE_SIZE_MB` | Timeouts y techo de archivo. | `60` / `1800` / `2000` |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Credenciales del sidecar `telegram-bot-api`. | Vacías en plantilla. |
| `AUTO_APPROVE` | Aprueba HITL sin botones. **No** omite preflight ni puerta YouTube. | `0` (compose `"0"`). |
| `ENABLE_AUTO_PUBLISH_SWEEP` | Sweep tras `AUTO_PUBLISH_TIMEOUT_HOURS` vía `ReviewJobManager`. | `0` (compose `"0"`). |
| `AUTO_PUBLISH_TIMEOUT_HOURS` | Ventana del sweep. | `24` |

---

## 2. Autenticación Oficial de Google (YouTube Data API v3 & Google Drive API v3)

El sistema utiliza las bibliotecas oficiales de Google (`google-auth`, `google-auth-oauthlib`, `google-api-python-client`) y almacena credenciales autorizadas en formato canónico oficial (`token`, `refresh_token`, `scopes`, `token_uri`, `client_id`, `client_secret`, `expiry`).

### Comandos de Autenticación CLI:

1. **Login interactivo de 1-clic** (abre navegador local y guarda credenciales):
   ```bash
   python3 main.py auth login --channel horror
   python3 main.py auth login --channel drama
   ```

2. **Generar URL de autorización (manual / headless)**:
   ```bash
   python3 main.py auth url --channel horror
   ```

3. **Canjear código de autorización**:
   ```bash
   python3 main.py auth exchange <CODIGO_OAUTH> --channel horror
   ```

4. **Diagnóstico y verificación de credenciales/permisos**:
   ```bash
   python3 main.py auth check --channel horror
   python3 main.py auth check --channel drama
   ```

5. **Estandarizar tokens existentes al formato canónico oficial**:
   ```bash
   python3 main.py auth standardize --channel horror
   python3 main.py auth standardize --channel drama
   ```

---

## 3. Validación de Configuración (Preflight)

`python3 main.py run --preflight` invoca `validate_runtime_config(require_drive=True, require_publish=True, require_review=True)`.
Salida OK: `Production preflight: PASS`. Fallo: `Production preflight: FAIL: …` (exit 1).

| Modo | Comprueba | Mensajes FAIL típicos | Corrección |
|---|---|---|---|
| `require_drive` | `DRIVE_FOLDER_ID`, `DRIVE_APPROVED_VIDEO_FOLDER_ID`; credencial Drive (`DRIVE_KEY_PATH` o OAuth canal con scope Drive o `DRIVE_USE_GCLOUD=1`) | `DRIVE_FOLDER_ID es obligatorio…`; `DRIVE_APPROVED_VIDEO_FOLDER_ID…`; `Falta DRIVE_KEY_PATH y no hay un token OAuth…` | Completar IDs en `.env`; colocar `secrets/drive_key.json` o token con scope Drive. |
| `require_publish` | Por canal: cookies + token OAuth + `*_YOUTUBE_CHANNEL_ID` | `{canal}: faltan cookies o token de YouTube`; `{canal}: falta el channel ID…` | Layout `secrets/` + IDs UC…; `auth login` / `auth check`. |
| `require_review` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_ALLOWED_CHAT_ID`; dir escribible de `VIDEO_REVIEW_DB_PATH`; `TEST_MODE≠1` | `TELEGRAM_* obligatorio/debe ser numérico`; `TEST_MODE=1 no está permitido…`; directorio de revisión | Rellenar Telegram; `TEST_MODE=0`; crear dir de review. |

**Nota:** `AUTO_APPROVE=1` / `ENABLE_AUTO_PUBLISH_SWEEP=1` son opt-in HITL; **no** omiten este preflight ni la puerta de cookies/token de YouTube.
