# Configuración, Variables de Entorno y Secretos

> **Estado:** REPOSITORIO / OFICIAL  
> **Última actualización:** 2026-08  

Inventario estructurado de variables de entorno y directivas de seguridad para `yt-auto`.

> [!CAUTION]
> **REGLA ABSOLUTA DE SEGURIDAD**: Ningún valor real de claves API, tokens OAuth, cookies o contraseñas debe incluirse en el repositorio. Los secretos deben residir en `.env` (local con `chmod 600`) o montarse en `/run/secrets` (Docker/VPS).

---

## 1. Inventario de Variables de Entorno

### A. Directorios y Persistencia
| Variable | Descripción | Valor Predeterminado / Ejemplo |
|---|---|---|
| `YOUTUBE_AUTOMATION_DB` | Ruta a la base de datos principal de cola SQLite. | `data/shorts_queue.db` |
| `VIDEO_REVIEW_DB_PATH` | Ruta a la base de datos de revisión de Telegram. | `data/review_state.db` |
| `WORK_ROOT` | Directorio temporal de trabajo y renders. | `work/` |
| `ARTIFACT_ROOT` | Directorio persistente de artefactos generados. | `artifacts/` |
| `SECRETS_DIR` | Directorio de montaje de secretos del sistema. | `/run/secrets` |
| `ANTIGRAVITY_AGENTS_APP_DATA_DIR` | Directorio aislado de sesión para agentes de IA. | `.bot_home/.gemini/antigravity-cli` |

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

### D. Canales de YouTube y Publicación
| Variable | Descripción | Detalle |
|---|---|---|
| `MOKU_YOUTUBE_CHANNEL_ID` | ID de canal de YouTube para Moku. | Identificador `UC...` |
| `MOKU_YOUTUBE_TOKEN_PATH` | Ruta al token OAuth2 de Moku. | `/run/secrets/youtube_token.json` |
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
| `ENABLE_AUTO_PUBLISH_SWEEP` | Habilitar barrido automático tras ventana de 6h. | `0` (requiere activación explícita). |

---

## 2. Validación de Configuración (Preflight)

Para comprobar que todas las dependencias y secretos requeridos estén configurados correctamente antes de iniciar producción:

```bash
python3 main.py run --preflight
```
