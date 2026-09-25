# Versiones Auditadas y Referencias Técnicas Oficiales

> **Estado:** OFICIAL | **Actualización:** 2026-09 | Versiones fijadas de runtime y fuentes primarias oficiales.

## 1. Versiones Fijadas de Runtime

| Componente | Versión | Ámbito de Uso |
|---|---|---|
| **Python** | `3.12.x` / `3.13` | Runtime principal del backend y pipeline. |
| **FFmpeg** | `6.1+` / `7.0+` | Motor de composición stream-copy, libass y EBU R128. |
| **SQLite** | `3.45+` | Persistencia atómica WAL (`shorts_queue.db`). |
| **Node.js / npm** | `20.x LTS` | Herramientas auxiliares y scripts de soporte. |
| **Antigravity CLI** | `agy v1.1.10+` | Arnés de ejecución para agentes nativos con streaming Gemini. |
| **Telegram Bot API** | `latest` | Servidor local para transferencias zero-copy hasta 2 GB. |

## 2. Fuentes Primarias Upstream
- **Gemini API & Modelos**: [ai.google.dev/gemini-api/docs](https://ai.google.dev/gemini-api/docs)
- **YouTube Data API v3**: [developers.google.com/youtube/v3/docs](https://developers.google.com/youtube/v3/docs)
- **Google Drive API v3**: [developers.google.com/drive/api/v3](https://developers.google.com/drive/api/v3)
- **Telegram Bot API**: [core.telegram.org/bots/api](https://core.telegram.org/bots/api)
- **FFmpeg & SQLite**: [ffmpeg.org/documentation.html](https://ffmpeg.org/documentation.html) · [sqlite.org/wal.html](https://www.sqlite.org/wal.html)
- **Edge-TTS**: [github.com/rany2/edge-tts](https://github.com/rany2/edge-tts)
