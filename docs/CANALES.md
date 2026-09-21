# Guía de Configuración y Operación Modular de Canales

> **Estado:** OFICIAL / PRODUCCIÓN  
> **Última actualización:** 2026-09  

Esta guía documenta la arquitectura modular de canales en `yt-auto`, eliminando nombres propios o dependencias rígidas en el código fuente y permitiendo la adición y ejecución de canales temáticos mediante configuración declarativa.

---

## 1. Arquitectura Modular

En `yt-auto`, los canales no están definidos como clases o constantes hardcodeadas en el motor. Toda la identidad, directrices editoriales, parámetros visuales y flujos de audio se definen en perfiles JSON independientes:

```mermaid
flowchart TD
    Registry[config/channels.json] --> Channels[config/channels/*.json]
    Channels --> Horror[horror.json]
    Channels --> Drama[drama.json]
    Channels --> Scifi[scifi.json]
    Channels --> Custom[<canal_personalizado>.json]

    Env[.env (CHANNEL_KEY / CHANNEL_*)] --> ProfileLoader[src/core/channel_profile.py]
    Channels --> ProfileLoader
    ProfileLoader --> Pipeline[Pipeline de Producción / Curadores / Render]
```

### Ubicación de Archivos de Configuración:
- **Catálogo Central**: `config/channels.json` (lista canales activos y metadatos base).
- **Perfiles Específicos**: `config/channels/<channel_id>.json` (ejemplo: `horror.json`, `drama.json`, `scifi.json`).
- **Plantillas Narrativas**: `config/templates/narratives_<channel_id>.json` y `config/templates/longform_stories_<channel_id>.json`.

---

## 2. Estructura de un Perfil de Canal (`config/channels/<id>.json`)

Cada canal define una estructura fuertemente tipada validada por `src/core/channel_profile.py`:

```json
{
  "id": "horror",
  "name": "Canal de Terror & Misterio",
  "topic": "Historias de terror psicológico y misterios sin resolver",
  "target_audience": "Aficionados al suspenso, creepypastas y horror cósmico",
  "language": "es",
  "editorial": {
    "curator": "HorrorCurator",
    "tone": "oscuro, tenso, inmersivo",
    "target_retention_hook_seconds": 3,
    "forbidden_tropes": ["final feliz predecible", "jump scare gratuito"]
  },
  "visual": {
    "color_palette": {
      "primary": "#8A0303",
      "accent": "#FF4444",
      "background": "#0D0D0D"
    },
    "subtitles": {
      "font_name": "Montserrat ExtraBold",
      "font_size": 18,
      "primary_color": "&H00FFFFFF",
      "outline_color": "&H00000000",
      "margin_v": 260
    }
  },
  "audio": {
    "voice_name": "es-ES-AlvaroNeural",
    "voice_rate": "+0%",
    "voice_pitch": "-3Hz",
    "ambient_ducking_db": -18.0
  },
  "cadence": {
    "shorts_per_day": 2,
    "longs_per_week": 1,
    "priority_lane": "short_daily"
  }
}
```

---

## 3. Variables de Entorno y Desacoplamiento (.env)

El archivo `.env` controla el canal activo mediante una única variable directriz `CHANNEL_KEY`, junto con variables genéricas `CHANNEL_*` que evitan prefijos propietarios:

```bash
# Identificador del canal activo (coincide con el nombre de config/channels/<channel_id>.json)
CHANNEL_KEY=horror

# Overrides genéricos de metadata para el canal activo
CHANNEL_TITLE="Relatos de Ultratumba"
CHANNEL_HANDLE="@RelatosUltratumba"
CHANNEL_URL="https://youtube.com/@RelatosUltratumba"
CHANNEL_TOPIC="Terror y leyendas oscuras"
CHANNEL_TARGET_AUDIENCE="Audiencia hispanohablante de misterio"

# Credenciales de publicación asociadas al canal
CHANNEL_YOUTUBE_CHANNEL_ID=UCxxxxxxxxxxxxxxxxxxxxxx
CHANNEL_YOUTUBE_TOKEN_PATH=secrets/tokens/horror.json
CHANNEL_COOKIES_PATH=secrets/cookies/horror.json
```

Si ejecutas un canal específico (`--channel drama`), el sistema resolverá automáticamente sus configuraciones desde `config/channels/drama.json` y buscará credenciales en `secrets/tokens/drama.json` a menos que se especifique un override explícito.

---

## 4. Paso a Paso: Cómo Agregar un Nuevo Canal

Para crear un nuevo canal temático (ejemplo: `crimen` / true crime):

### Paso 1: Crear el Perfil JSON
Crea el archivo `config/channels/crimen.json` con los metadatos de identidad, audio, estilo visual y cadencia.

### Paso 2: Registrar en el Catálogo Maestro
Añade la entrada a `config/channels.json`:
```json
{
  "active_channels": ["horror", "drama", "scifi", "crimen"],
  "default_channel": "horror"
}
```

### Paso 3: Definir Plantillas Narrativas
Crea las plantillas de historias cortas y largas:
- `config/templates/narratives_crimen.json`
- `config/templates/longform_stories_crimen.json`

### Paso 4: (Opcional) Asignar Curador Editorial
Si el canal requiere reglas de puntuación o heurísticas especializadas, puedes crear `src/curators/crimen.py` heredando de `src/curators/base.py` (`BaseCurator`). Si no se especifica, el sistema utilizará el curador genérico predeterminado.

---

## 5. Comandos de Operación y Verificación

### Inspección del Perfil del Canal
```bash
# Inspeccionar la configuración consolidada del canal
python3 main.py profile show --channel crimen

# Listar todos los canales disponibles en el sistema
python3 main.py profile list
```

### Preflight y Diagnóstico de Seguridad
```bash
# Validar preflight completo para el canal (revisión de credenciales, rutas y DB)
python3 main.py run --channel crimen --preflight
```

### Autenticación Oficial OAuth de YouTube
```bash
# Iniciar flujo de autorización de YouTube Data API v3 para el canal
python3 main.py auth login --channel crimen

# Verificar estado de token y permisos
python3 main.py auth check --channel crimen
```

### Ejecución de Pipeline de Producción
```bash
# Generar video sin publicar (dry run / generate only)
python3 main.py run --channel crimen --lane short_daily --generate-only

# Ejecutar pipeline completo con puerta de revisión Telegram HITL
python3 main.py run --channel crimen --lane short_daily
```
