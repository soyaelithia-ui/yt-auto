# Configuración, Variables de Entorno y Secretos

> **Repositorio Oficial:** [https://github.com/Ade-ia2005/yt-auto.git](https://github.com/Ade-ia2005/yt-auto.git) | **Gobernanza:** Repositorio privado con resolución dinámica de identidades y secretos desacoplados.  
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

### B. Inteligencia Artificial (Google Gemini)
| Variable | Descripción | Uso |
|---|---|---|
| `GEMINI_API_KEY` | Clave de API de Google Gemini para proveedores REST de respaldo. | Requerida si no se utiliza sesión OAuth Pro activa en el arnés `agy`. |

### C. Google Drive API v3 (Respaldo)
| Variable | Descripción | Valor Predeterminado / Requisito |
|---|---|---|
| `DRIVE_ROOT_FOLDER_ID` | ID de carpeta raíz en Google Drive. | Requerido (formato alfanumérico). |
| `DRIVE_APPROVED_FOLDER_ID` | ID de carpeta para videos aprobados. | Requerido. |
| `DRIVE_USE_GCLOUD` | Utilizar credenciales activas de `gcloud auth`. | `0` (inactivo) / `1` (activo). |
| `DRIVE_KEY_PATH` | Ruta al archivo JSON de credenciales Service Account. | `/run/secrets/drive_key.json` |

### D. Canales de YouTube, Identidades y Publicación
| Variable | Descripción | Detalle / Dinámico |
|---|---|---|
| `CHANNEL_HANDLE` | Handle global dinámico del canal activo (`@Canal`). | Override genérico para el carril en ejecución. |
| `CHANNEL_URL` | URL de YouTube del canal activo. | Override genérico (`https://youtube.com/@Canal`). |
| `CHANNEL_NAME` | Nombre público del canal activo. | Override genérico. |
| `MOKU_HANDLE` | Handle específico para canal Moku. | Por defecto resuelto de `config/channels/moku.json`. |
| `MOKU_YOUTUBE_CHANNEL_ID` | ID de canal de YouTube para Moku. | Identificador `UC...` |
| `MOKU_YOUTUBE_TOKEN_PATH` | Ruta al token OAuth2 de Moku. | `/run/secrets/youtube_token.json` |
| `AELITHIA_HANDLE` | Handle específico para canal Aelithia. | Por defecto resuelto de `config/channels/aelithia.json`. |
| `AELITHIA_YOUTUBE_CHANNEL_ID`| ID de canal de YouTube para Aelithia. | Identificador `UC...` |
| `AELITHIA_YOUTUBE_TOKEN_PATH`| Ruta al token OAuth2 de Aelithia. | `/run/secrets/youtube_token_aelithia.json` |

### E. Telegram Bot API y Puerta de Revisión
| Variable | Descripción | Valor Predeterminado / Ejemplo |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token de BotFather para interacción. | Requerido (`id:secret`). |
| `TELEGRAM_CHAT_ID` | Chat principal para recepción de videos. | Requerido (entero). |
| `TELEGRAM_ALLOWED_USER_ID` | ID de usuario de Telegram autorizado para aprobar. | Requerido (entero). |
| `TELEGRAM_API_BASE_URL` | URL base del servidor de Telegram Bot API. | `http://telegram-bot-api:8081` |
| `TELEGRAM_LOCAL` | Habilitar soporte para servidor local (hasta 2 GB). | `true` |
| `TELEGRAM_USE_LOCAL_FILES` | Habilitar transporte zero-copy `file:///`. | `1` |
| `AUTO_APPROVE` | Aprueba revisión HITL sin botones de Telegram (camino Auto/autopilot). **No** omite preflight ni secretos de YouTube/Drive. | `0` (poner `1` para Auto). |
| `ENABLE_AUTO_PUBLISH_SWEEP` | Barrido del daemon tras `AUTO_PUBLISH_TIMEOUT_HOURS` para publicar pendientes aprobados/stale vía `ReviewJobManager`. | `0` (poner `1` con Auto). |
| `AUTO_PUBLISH_TIMEOUT_HOURS` | Ventana antes del sweep de auto-publicación. | `24` |

---

---

## 2. Autenticación Oficial de Google (YouTube Data API v3 & Google Drive API v3)

El sistema utiliza las bibliotecas oficiales de Google (`google-auth`, `google-auth-oauthlib`, `google-api-python-client`) y almacena credenciales autorizadas en formato canónico oficial (`token`, `refresh_token`, `scopes`, `token_uri`, `client_id`, `client_secret`, `expiry`).

### Comandos de Autenticación CLI:

1. **Login interactivo de 1-clic** (abre navegador local y guarda credenciales):
   ```bash
   python3 main.py auth login --channel moku
   python3 main.py auth login --channel aelithia
   ```

2. **Generar URL de autorización (manual / headless)**:
   ```bash
   python3 main.py auth url --channel moku
   ```

3. **Canjear código de autorización**:
   ```bash
   python3 main.py auth exchange <CODIGO_OAUTH> --channel moku
   ```

4. **Diagnóstico y verificación de credenciales/permisos**:
   ```bash
   python3 main.py auth check --channel moku
   python3 main.py auth check --channel aelithia
   ```

5. **Estandarizar tokens existentes al formato canónico oficial**:
   ```bash
   python3 main.py auth standardize --channel moku
   python3 main.py auth standardize --channel aelithia
   ```

---

## 3. Validación de Configuración (Preflight)

Para comprobar que todas las dependencias y secretos requeridos estén configurados correctamente antes de iniciar producción:

```bash
python3 main.py run --preflight
```
