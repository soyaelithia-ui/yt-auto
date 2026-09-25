# Propuesta de Evolución del Pipeline Visual: Dirección Cinemática y Montaje Narrativo

> **Estado:** OFICIAL / ESPECIFICACIÓN ACTIVA | **Actualización:** 2026-09 | Estructura en 4 actos, montaje narrativo y control fotométrico.

## 1. Visión: Dirección Cinemática y Coherencia Narrativa

Superar la reproducción mecánica coordinando el ritmo de la narración, la iluminación ambiental y la progresión de encuadres mediante razonamiento cinematográfico temprano:

```mermaid
flowchart LR
    G[Guión / Historia] --> C["Curaduría (4 Actos)"]
    C --> V["Composición Dinámica (Encuadres, Rec.709, Pacing)"]
    V --> M["Master Final FFmpeg (Stream-Copy / Ken Burns)"]
```

## 2. Estructura Dramática en 4 Actos y Pacing

```mermaid
graph TD
    A1["Acto I: Exposición / Inception (Tensión 1-2, calm_slow)"] --> A2["Acto II: Tensión Creciente / Dread (Tensión 2-4, steady_dramatic)"]
    A2 --> A3["Acto III: Clímax / Confrontación (Tensión 4-5, intense_urgent)"]
    A3 --> A4["Acto IV: Desenlace / Aftermath (Tensión 3-1, whispered_grave)"]
```

- **Acto I (Exposición)**: Presentación de la premisa y contexto geográfico (`WIDE_ESTABLISHING`, `calm_slow`).
- **Acto II (Dread)**: Progresión del conflicto y pérdida de control (`MEDIUM_ACTION`, `tense_accelerando`).
- **Acto III (Clímax)**: Punto de máxima tensión y quiebre argumental (`CLOSEUP_TENSION`, `intense_urgent`).
- **Acto IV (Resolución)**: Consecuencias, veredicto o advertencia final (`DETAIL_REVEAL`, `whispered_grave`).

**Vocabulario de Pacing**: `calm_slow`, `steady_dramatic`, `tense_accelerando`, `intense_urgent`, `whispered_grave`.

## 3. Composición Dinámica y Reglas Fotométricas

1. **Segmentación Semántica**: Cortes coordinados con pausas naturales de oraciones TTS ($t_{\text{end}}$), nunca por segundos fijos.
2. **Encuadres Canónicos**: Alternancia de `WIDE_ESTABLISHING`, `MEDIUM_ACTION`, `CLOSEUP_TENSION` y `DETAIL_REVEAL`.
3. **Piso Fotométrico (15% - 25%)**: Sombras con texturas visibles en pantallas OLED móviles sin aplastamiento de negros; calibración Rec.709.

## 4. Colaboración de Agentes (`src/agents/`)

```mermaid
sequenceDiagram
    autonumber
    participant Story as StoryDirectorAgent
    participant Mood as AtmosphericDirectorAgent
    participant Engine as Media Engine (FFmpeg)

    Story->>Story: Estructura guión en 4 actos con tension curve
    Story->>Mood: Emite escaleta con pacing y roles dramáticos
    Mood->>Mood: Clasifica atmósfera y resuelve loops de assets/loops/
    Mood->>Engine: SceneManifest compilado con arquetipos
    Engine->>Engine: Stream-copy concat demuxer (-c:v copy)
```

- **`StoryDirectorAgent` (`src/agents/story_director.py`)**: Sanitización editorial, división en 4 actos y modulación de tensión.
- **`AtmosphericDirectorAgent` (`src/agents/atmospheric_director.py`)**: Asignación de paleta Rec.709, atmósfera lumínica y selección de bucles de catálogo.
- **Media Engine (`src/media/director_assembly.py`)**: Ensamble stream-copy y muxing de subtítulos.

## 5. Delimitación de Alcance y Principios de Eficiencia (YAGNI)

- **100% Asset-Based**: Producción exclusivamente sustentada en el catálogo local (`assets/loops/`) y fotos fijas Ken Burns. Cero generación por shaders, WebGL o APIs externas lentas.
- **Límites de Rendimiento**: Gobernanza estricta de $\le 2$ Cores CPU, $\le 2.0$ GiB RAM y persistencia SQLite WAL.
