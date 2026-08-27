# Arquitectura de Orquestación Multi-Escena y Dinamismo Narrativo (M2)

> **Documento:** Architectural Specification & Engineering Blueprint  
> **Identificador:** `ARCH-SPEC-02-SCENE-ORCHESTRATION-2026`  
> **Módulo:** Multi-Scene Orchestrator, Tension Synchronization & Ambient Matrices  
> **Versión:** 2.0.0 (Production Master)  
> **Estado:** APROBADO / ESPECIFICACIÓN CANÓNICA  

---

## 1. Visión General del Subsistema de Orquestación Multi-Escena

El subsistema de orquestación multi-escena de `yt-auto` tiene como objetivo erradicar la monotonía visual de los bucles estáticos continuos, transformando guiones narrativos de larga duración (10+ minutos) y YouTube Shorts verticales en **experiencias audiovisuales cinematográficas dinámicas**.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 NARRATIVE AUDIO & SCRIPT                               │
│                         (Voz en Off, Marcas de Tiempo & Párrafos)                      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SCRIPT CURATOR & BEAT PARSER                              │
│                (Segmentación en Actos Dramáticos 1..4 & Tensión 1..5)                  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SCENE ORCHESTRATION ENGINE                                │
│  ├─ Cadencia Temporal: 45-90s (Longform) / 8-15s (Shorts)                             │
│  ├─ Modulación de Parámetros por Nivel de Tensión (Cámara, Luces, Partículas)          │
│  ├─ Asignación de Matriz Ambiental por Carril (moku-horror, scp-shorts, aelithia-aita) │
│  └─ Interpolación de Transiciones Cinemáticas (Crossfade, Depth Dissolve, Volumetric)  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       CANONICAL MANIFEST CONTRACT (v2.0)                               │
│                     (scene_manifest.json -> Compositor Engine)                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cadencia Temporal y Pacing Multi-Escena

### 2.1 Videos Longform (10 a 20+ Minutos)
- **Ventana de Duración por Escena**: Todo ambiente visual se mantiene activo durante un intervalo acotado de **45 a 90 segundos** ($45.0 \le \Delta t_{\text{scene}} \le 90.0$).
- **Distribución de Escenas por Video**:
  Un video típico de 12 minutos ($\approx 720\text{s}$) se divide en 9 a 12 escenas visuales diferenciadas, evitando el agotamiento perceptivo del espectador.
- **Micro-Dinamismo Intra-Escena**:
  Dentro de cada ventana de 45-90s, la cámara ejecuta un movimiento 3D continuo (zoom in/out con curvatura Bezier, deriva lateral lenta o parallax multi-plano), garantizando que ningún fotograma sea estático.
- **Compensación de Deriva Temporal (Drift Elimination)**:
  La suma acumulada de las duraciones de las escenas debe coincidir de forma exacta con la duración del audio de narración:
  $$\sum_{i=1}^{N} \Delta t_i = T_{\text{narration}}$$
  Cualquier discrepancia por redondeo de coma flotante ($\epsilon < 0.05\text{s}$) se absorbe automáticamente en la última escena del video.

### 2.2 YouTube Shorts (45 a 58 Segundos)
- **Ventana de Duración por Beat**: Segmentación en tomas rápidas de **8 a 15 segundos** ($8.0 \le \Delta t_{\text{beat}} \le 15.0$).
- **Estructura de 4 Fases para Shorts**:
  1. **Hook Visual (0.0s - 3.0s)**: Toma de impacto máximo (tensión 4-5) con tipografía cinética en safe area superior.
  2. **Desarrollo / Planteamiento (3.0s - 25.0s)**: 2 tomas de ambientación con tensión 2-3.
  3. **Escalada / Clímax (25.0s - 45.0s)**: 1-2 tomas de alta tensión (tensión 4-5) con mayor velocidad de cámara y partículas.
  4. **Resolución / Call to Action (45.0s - final)**: Toma de cierre atmosférica.

---

## 3. Sincronizador de Tensión Dramática (Dramatic Tension Synchronizer)

El sistema sincroniza dinámicamente los parámetros de cámara, iluminación, partículas y shaders con la escala de tensión narrativa clasificada de **1 a 5**:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              MATRIZ DE MODULACIÓN POR NIVEL DE TENSIÓN                                 │
├──────┬──────────────────────┬──────────────┬──────────────┬──────────────────┬─────────────────────────┤
│ Nivel│ Estado Dramático     │ Velocidad    │ Parallax $k$ │ Iluminación      │ Partículas & Shaders    │
├──────┼──────────────────────┼──────────────┼──────────────┼──────────────────┼─────────────────────────┤
│  1   │ Exposición / Calma   │ Zoom 1.02x   │ Bajo (0.05)  │ Difusa, sombras  │ Polvo sutil (15 part.), │
│      │                      │ Deriva lenta │              │ suaves, bajo cnt │ bruma casi estática     │
├──────┼──────────────────────┼──────────────┼──────────────┼──────────────────┼─────────────────────────┤
│  2   │ Inquietud / Misterio │ Zoom 1.05x   │ Med-Bajo(0.1)│ Sombras alargadas│ Niebla laminar lenta,   │
│      │                      │ Push sosten. │              │ penumbra lateral │ polvo medio (30 part.)  │
├──────┼──────────────────────┼──────────────┼──────────────┼──────────────────┼─────────────────────────┤
│  3   │ Investigación        │ Zoom 1.08x   │ Medio (0.20) │ Claroscuro medio │ Brasas tenues / esporas │
│      │ Tensión Creciente    │ Pan + Tilt   │              │ focos puntuales  │ turbulencia media       │
├──────┼──────────────────────┼──────────────┼──────────────┼──────────────────┼─────────────────────────┤
│  4   │ Amenaza / Pre-Clímax │ Zoom 1.12x   │ Alto (0.35)  │ Claroscuro severo│ Brasas densas, pulsos   │
│      │                      │ Empuje rápido│              │ luz parpadeante  │ volumétricos, distorsión│
├──────┼──────────────────────┼──────────────┼──────────────┼──────────────────┼─────────────────────────┤
│  5   │ Terror Pico / Shock  │ Zoom 1.15x   │ Extremo(0.50)│ Alto contraste,  │ Vórtice acelerado, rayos│
│      │ Revelación Final     │ Vórtice / Cam│              │ destellos breves │ aberrantes, glitch sutil│
└──────┴──────────────────────┴──────────────┴──────────────┴──────────────────┴─────────────────────────┘
```

### 3.1 Ecuaciones de Modulación Paramétrica:
- **Factor de Zoom de Cámara**:
  $$S_{\text{end}}(L) = 1.00 + 0.03 \times L \quad (L \in [1..5] \implies S_{\text{end}} \in [1.03, 1.15])$$
- **Intensidad de Parallax**:
  $$k_{\text{parallax}}(L) = 0.05 + 0.1125 \times (L - 1) \quad (L=1 \implies 0.05, \; L=5 \implies 0.50)$$
- **Densidad de Partículas**:
  $$D_{\text{particles}}(L) = 15 + 25 \times (L - 1) \quad (L=1 \implies 15, \; L=5 \implies 115)$$
- **Velocidad de Turbulencia Shader**:
  $$u_{\text{speed}}(L) = 0.6 + 0.25 \times (L - 1) \quad (L=1 \implies 0.60, \; L=5 \implies 1.60)$$

---

## 4. Matrices de Ambientes por Carril Temático

Cada carril de producción posee una biblioteca temática de ambientes visuales diseñada para mantener coherencia estilística absoluta:

```
                                  ┌────────────────────────┐
                                  │   LANE CONFIGURATION   │
                                  └───────────┬────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         ▼                                    ▼                                    ▼
┌──────────────────┐                 ┌──────────────────┐                 ┌──────────────────┐
│ moku-horror-long │                 │ moku-scp-shorts  │                 │aelithia-aita-long│
├──────────────────┤                 ├──────────────────┤                 ├──────────────────┤
│ - 16:9 Full HD   │                 │ - 9:16 Full HD   │                 │ - 16:9 Full HD   │
│ - 10-20 min dur. │                 │ - 45-58s dur.    │                 │ - 8-15 min dur.  │
│ - 6 Ambientes:   │                 │ - 4 Ambientes:   │                 │ - 4 Ambientes:   │
│   * Mansión      │                 │   * CRT Terminal │                 │   * Sala Noir    │
│   * Bosque Oscuro│                 │   * Celda Titanio│                 │   * Audio Waves  │
│   * Cripta / Lab │                 │   * Tanque Bio   │                 │   * Split Screen │
│   * Vacío Cósmico│                 │   * Pasillo Búnk.│                 │   * Balcón Noche │
└──────────────────┘                 └──────────────────┘                 └──────────────────┘
```

### 4.1 `moku-horror-long` (Carril Principal de Terror en Español)
- **Formato**: $1920 \times 1080$ px, 30 fps, horizontal 16:9.
- **Catálogo de Ambientes Canónicos**:
  1. `abandoned_manor`: Interior victoriano derruido, vigas carcomidas, luz de luna filtrada.
  2. `dark_forest`: Bosque de coníferas en niebla densa, ramas retorcidas, esporas verdes.
  3. `subterranean_crypt`: Cripta gótica de piedra húmeda, nichos con calaveras, penumbra.
  4. `cosmic_abyss`: Vacío interestelar con singularidad gravitacional y nebulosa púrpura.
  5. `abandoned_lab`: Quirófano / laboratorio de investigación clandestino de los años 60.
  6. `misty_cemetery`: Cementerio en la niebla con cruces de hierro y faroles tenues.

### 4.2 `moku-scp-shorts` (Carril de Anomalías SCP Verticales)
- **Formato**: $1080 \times 1920$ px, 30 fps, vertical 9:16.
- **Catálogo de Ambientes Canónicos**:
  1. `scp_terminal_o5`: Interfaz CRT verde fósforo con textos clasificados y scanlines.
  2. `containment_cell`: Celda de hormigón reforzado y titanio con puerta blindada hermética.
  3. `bio_stasis_tank`: Cilindro de contención criogénica con líquido turbio y burbujas.
  4. `bunker_corridor`: Pasillo subterráneo del Sitio-19 con balizas de emergencia ámbar.

### 4.3 `aelithia-aita-long` (Carril de Conflicto Dramático y Dilemas Morales)
- **Formato**: $1920 \times 1080$ px, 30 fps, horizontal 16:9.
- **Catálogo de Ambientes Canónicos**:
  1. `minimalist_noir_room`: Sala de estar moderna en penumbra con iluminación de acento dorada.
  2. `reactive_drama_waves`: Ondas sonoras armónicas minimalistas sobre gradientes de grafito.
  3. `split_dialogue_stage`: Composición en pantalla dividida en claroscuro para confrontaciones.
  4. `nocturnal_balcony`: Vista panorámica urbana nocturna con luces desenfocadas (bokeh suave).

---

## 5. Mecánicas de Transición Cinemática

Para evitar cortes abruptos sin justificación dramática, el sistema emplea 5 tipos de transiciones con parámetros temporales calibrados:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             MECÁNICAS DE TRANSICIÓN CINEMÁTICA                         │
├────────────────────┬──────────────┬──────────────────────┬─────────────────────────────┤
│ Tipo de Transición │ Duración     │ Comportamiento       │ Contexto de Uso Recomendado │
├────────────────────┼──────────────┼──────────────────────┼─────────────────────────────┤
│ `crossfade`        │ 0.8s - 1.2s  │ Disolución cruzada   │ Transición estándar entre   │
│                    │              │ en espacio lineal    │ ambientes del mismo acto    │
├────────────────────┼──────────────┼──────────────────────┼─────────────────────────────┤
│ `volumetric_fade`  │ 0.6s - 1.0s  │ Descenso a sombra de │ Cambio de acto dramático o  │
│                    │              │ paleta base          │ salto temporal mayor        │
├────────────────────┼──────────────┼──────────────────────┼─────────────────────────────┤
│ `depth_dissolve`   │ 1.0s - 1.5s  │ El fondo se disuelve │ Transiciones en Motor       │
│                    │              │ antes que el frente  │ Híbrido Cinemático 2.5D     │
├────────────────────┼──────────────┼──────────────────────┼─────────────────────────────┤
│ `glitch_cut`       │ 0.2s - 0.4s  │ Interferencia CRT y  │ Exclusivo para SCP shorts y │
│                    │              │ aberración RGB       │ anomalías electrónicas      │
├────────────────────┼──────────────┼──────────────────────┼─────────────────────────────┤
│ `cut` (Hard Cut)   │ 0.0s         │ Corte directo sin    │ Shock / Jump scare en pico  │
│                    │              │ fundido              │ de tensión dramática 5      │
└────────────────────┴──────────────┴──────────────────────┴─────────────────────────────┘
```

### 5.1 Ecuación de Offset para FFmpeg `xfade`:
Para encadenar la escena $n$ con la escena $n+1$ con duración de transición $\delta$:
$$\text{offset}_n = \text{start\_sec}_{n+1} - \delta = \sum_{k=1}^{n} \text{duration}_k - \delta \cdot n$$
El pipeline de postprocesamiento ajusta los streams de video en el filtergraph para evitar pérdida de sincronía con la pista de audio.

---

## 6. Especificación de Safe Area e Interfaz de Usuario

Para evitar que los subtítulos o elementos visuales clave colisionen con las barras de interfaz de YouTube:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 ESPECIFICACIÓN DE SAFE AREA                            │
├──────────────────────────────┬────────────────────────────┬────────────────────────────┤
│ Parámetro                    │ Vertical (9:16 Shorts)     │ Horizontal (16:9 Longform) │
├──────────────────────────────┼────────────────────────────┼────────────────────────────┤
│ Resolución Objetivo          │ 1080 x 1920 px             │ 1920 x 1080 px             │
│ Margen Superior (`margin_top`)│ 60 px (Zona de Canal)     │ 60 px (Título y controles) │
│ Margen Inferior (`margin_btm`)│ 330 px (Botones / Descr.) │ 124 px (Barra de progreso) │
│ Margen Izquierdo (`margin_l`)| 72 px (Borde pantalla)     │ 85 px (Borde pantalla)     │
│ Margen Derecho (`margin_r`)  │ 72 px (Botones Like/Share) │ 85 px (Borde pantalla)     │
│ Franja Segura Subtítulos     │ Y = 1350 px .. 1580 px     │ Y = 880 px .. 950 px       │
└──────────────────────────────┴────────────────────────────┴────────────────────────────┘
```

---

## 7. Mapeo de Archivos y Contratos de Interfaces

| Componente | Archivo Fuente | Descripción |
|------------|----------------|-------------|
| Contrato Canónico | `schemas/scene_manifest.schema.json` | Esquema JSON Draft-07 formal |
| Parser y Validador | `src/scene_manifest.py` | Modelos Pydantic v2 y serializador/validador |
| Segmentador de Beats | `src/curators/beats.py` | Extracción de beats narrativos y curvas de tensión |
| Pipeline Compositor | `src/media/loop_video_engine.py` | Ensamblaje FFmpeg con transiciones y debanding |
