# Arquitectura del Subsistema de Renderizado Dual: Motor Híbrido Cinemático IA & Motor Procedural Puro WebGL/Canvas (M1)

> **Documento:** Architectural Specification & Engineering Blueprint  
> **Identificador:** `ARCH-SPEC-01-DUAL-ENGINES-2026`  
> **Módulo:** Dual Rendering Subsystem (Hybrid AI + Procedural WebGL/Canvas)  
> **Versión:** 2.0.0 (Production Master)  
> **Estado:** APROBADO / ESPECIFICACIÓN CANÓNICA  

---

## 1. Visión General y Principios de Diseño

El subsistema de renderizado visual de `yt-auto` resuelve el compromiso fundamental entre **riqueza estética fotorrealista** y **eficiencia computacional determinista con cero consumo de cuotas API**. Para ello, se establece una arquitectura de dos motores de renderizado complementarios que operan bajo una interfaz de composición unificada:

```
                                  ┌─────────────────────────────────────────┐
                                  │           SCENE PLANNER AGENT           │
                                  │      (Evaluación Semántica de Beat)     │
                                  └────────────────────┬────────────────────┘
                                                       │
                                  ┌────────────────────┴────────────────────┐
                                  ▼                                         ▼
                   [Escena Narrativa / Fotorrealista]        [Escena Atmosférica / Abstracta]
                                  │                                         │
                                  ▼                                         ▼
            ┌────────────────────────────────────────┐   ┌────────────────────────────────────────┐
            │       MOTOR HÍBRIDO CINEMÁTICO IA      │   │      MOTOR PROCEDURAL PURO WEBGL       │
            ├────────────────────────────────────────┤   ├────────────────────────────────────────┤
            │ 1. AI Background Matte (Prompt+Negative)│   │ 1. Headless Chromium (Playwright)      │
            │ 2. Monocular Depth Map Estimation      │   │ 2. Virtual Time Stepping (t = n / fps) │
            │ 3. 2.5D Layer Slicing & Occlusion Fill │   │ 3. SDF Raymarching & Periodic FBM      │
            │ 4. 3D Ken Burns (Cubic Bezier Easing)  │   │ 4. Canvas2D Dynamic Multi-Layer Waves  │
            │ 5. Volumetric Light Shaders (God Rays) │   │ 5. Strict Rec.709 Palette Enforcement  │
            │ 6. Physics Particle Simulation (Motes) │   │ 6. Native 1080p / 4K UHD Scalability   │
            └───────────────────┬────────────────────┘   └───────────────────┬────────────────────┘
                                │                                            │
                                └─────────────────────┬──────────────────────┘
                                                      ▼
                                ┌───────────────────────────────────────────┐
                                │       MASTER COMPOSITOR & FFMPEG PIPE     │
                                │    (CRF 18-20, Lanczos Rescaling, Deband) │
                                └───────────────────────────────────────────┘
```

### Principios Fundamentales de Calidad:
1. **Cero Degradación Visual**: Eliminación radical de ruido de grano tosco sintético, dithering visible, macrobloques de compresión o artefactos plásticos de IA generativa.
2. **Determinismo Cuadro a Cuadro**: Todo fotograma $f_n$ a tiempo $t = n / \text{fps}$ es matemáticamente reproducible con idéntica semilla $S$.
3. **Resiliencia Fail-Closed**: Toda falla de API externa activa una cascada de fallback automático de 3 niveles sin interrupción del pipeline ni emisión de videos con pantallas negras.
4. **Fidelidad Cromática Rec.709**: Espacio de color estrictamente calibrado con matrices de luminancia y saturación acotadas para evitar colores chillones o disonancias estéticas.

---

## 2. Motor Híbrido Cinemático IA (Hybrid Cinematic AI Engine)

El Motor Híbrido Cinemático está diseñado para escenas que requieren locaciones concretas, habitaciones arquitectónicas detalladas, exteriores dramáticos o criaturas en claroscuro.

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  AI Background  │ ──► │ Monocular Depth Map │ ──► │  2.5D Layer Slicing │ ──► │  Ken Burns 3D with  │
│  Matte (2K/4K)  │     │  (MiDaS/ZoeDepth)   │     │  & Inpainting Fill  │     │   Cubic Bezier Pan  │
└─────────────────┘     └─────────────────────┘     └─────────────────────┘     └──────────┬──────────┘
                                                                                           │
┌─────────────────┐     ┌─────────────────────┐                                            │
│   Atmospheric   │ ──► │   Volumetric Light  │ ◄──────────────────────────────────────────┘
│  Particles (2D) │     │  Shaders (God Rays) │
└─────────────────┘     └──────────┬──────────┘
                                   │
                                   ▼
                        [Composed RGBA Frame Stream]
```

### 2.1 Generación y Control de Fondos IA (AI Background Matte)
- **Resolución Nativa de Entrada**:
  - Horizontal (16:9 Longform): $1920 \times 1080$ px nativo (o $2048 \times 1152$ px para oversampling).
  - Vertical (9:16 Shorts): $1080 \times 1920$ px nativo (o $1152 \times 2048$ px para oversampling).
- **Control de Prompts Estructurado**:
  - *Directivas Positivas Obligatorias*: `dark cinematic matte painting, atmospheric lighting, volumetric chiaroscuro, 35mm photography, masterwork, highly detailed texture, 8k render, photorealistic depth`.
  - *Directivas Negativas Estrictas*: `ugly, deformed, noisy grain, film grain, dithering, lowres, blurry, cartoonish, 3d render plastic, saturated colors, neon clownish colors, text, watermark, bad anatomy, mutated limbs, anime, sketch`.
- **Caché y Deduplicación**: Almacenamiento en disco indexado mediante hash SHA-256 del prompt normalizado y parámetros: `data/worksets/generated/{scene_id}_{sha256[:12]}.png`. Si el asset ya existe en caché, se reutiliza instantáneamente sin invocar la API.

### 2.2 Estimación de Profundidad Monocular y Descomposición 2.5D
- **Mapa de Profundidad Normalizado**: Estimación del mapa de profundidad $D(x,y) \in [0.0, 1.0]$, donde $0.0$ corresponde al plano de fuga infinito (horizonte/cielo) y $1.0$ representa el plano frontal más próximo a la lente.
- **Segmentación de Capas (Layer Slicing)**:
  - **Fondo (Background Layer)**: $z \in [0.0, 0.35)$ — Cielo, bruma lejana, horizonte, montañas distantes.
  - **Plano Medio (Midground Layer)**: $z \in [0.35, 0.70)$ — Sujetos principales, estructuras arquitectónicas, muros, vegetación intermedia.
  - **Primer Plano (Foreground Layer)**: $z \in [0.70, 1.00]$ — Siluetas frontales, marcos de ventanas, ramas en penumbra, columnas.
- **Inpainting y Dilatación de Bordes**: Para evitar bordes desgarrados o halos vacíos durante el desplazamiento parallax, la máscara de oclusión de cada capa se dilata en un radio de $\delta = 12\text{px}$ y se sintetizan los píxeles ocultos mediante inpainting de gradiente direccional basado en Navier-Stokes / Telea.

### 2.3 Cámara Ken Burns 3D con Amortiguación Cúbica (Cubic Bezier Easing)
- **Función de Amortiguación Cinemática**: En lugar de traslaciones lineales robóticas, la cámara sigue una curva Bezier cúbica $B(t)$ con $t \in [0, 1]$:
  $$\text{ease\_cinematic}(t) = \text{cubic-bezier}(0.25, 0.1, 0.25, 1.0)$$
- **Ecuación de Desplazamiento Parallax Diferencial**:
  Para cada plano $i$ con profundidad media $z_i \in [0.0, 1.0]$:
  $$\vec{P}_i(t) = \vec{P}_{\text{cam}}(t) \cdot \left(1.0 - z_i \cdot k_{\text{parallax}}\right)$$
  Donde $k_{\text{parallax}} \in [0.05, 0.35]$ modula la fuerza del efecto tridimensional según el nivel de tensión dramática.
- **Zoom Óptico y Reencuadre**:
  $$S(t) = S_{\text{start}} + (S_{\text{end}} - S_{\text{start}}) \cdot \text{ease\_cinematic}(t)$$
  Con $S_{\text{start}} = 1.00$ y $S_{\text{end}} \in [1.05, 1.15]$, garantizando que los bordes de la imagen nunca queden expuestos fuera del viewport de renderizado.
- **Profundidad de Campo Dinámica (Depth of Field & Bokeh)**:
  Se aplica un desenfoque gaussiano espacial selectivo en función de la distancia al plano focal $z_{\text{focus}}$:
  $$\sigma_{\text{blur}}(x,y) = \left| D(x,y) - z_{\text{focus}} \right| \cdot A_{\text{aperture}}$$
  Donde $A_{\text{aperture}}$ define la apertura simulada del diafragma.

### 2.4 Shaders de Iluminación Volumétrica (Volumetric Light Shaders)
- **Rayos Crepusculares (God Rays / Sun Shafts)**:
  Cálculo de iluminación volumétrica mediante muestreo radial en GLSL:
  $$I_{\text{vol}}(x,y) = \frac{1}{N} \sum_{i=0}^{N-1} \tau^i \cdot L\left(\vec{p} - i \cdot \Delta \vec{p}\right)$$
  Donde $\vec{p}$ es la coordenada del píxel, $\Delta \vec{p} = \frac{\vec{p} - \vec{p}_{\text{light}}}{N} \cdot \text{density}$, $\tau$ es el factor de atenuación luminosa y $L(\cdot)$ es la máscara de luminancia de la escena.
- **Flicker Dinámico de Luz Ambiental**:
  Modulación temporal de la intensidad de luz $I(t)$ para emular velas, fluorescentes parpadeantes o relámpagos lejanos:
  $$I(t) = I_0 \cdot \left[1.0 + A_{\text{flicker}} \cdot \left(\sin(\omega_1 t) \cdot 0.5 + \sin(\omega_2 t) \cdot 0.3 + \text{noise}(t \cdot \omega_3) \cdot 0.2\right)\right]$$
- **Rim Lighting en Siluetas Frontales**:
  Extracción de bordes mediante filtro Sobel en la capa de primer plano y aplicación de iluminación de contorno con el color de acento de la escena.

### 2.5 Simulación Física de Partículas Atmosféricas (Atmospheric Particles)
- **Tipologías de Partículas**:
  - `dust_motes`: Micro-partículas de polvo en suspensión flotando en corrientes brownianas lentas.
  - `ember_sparks`: Brasas incandescentes flotando verticalmente con turbulencia FBM y enfriamiento térmico.
  - `fog_mist`: Bandas de niebla volumétrica con desplazamiento laminar y atenuación de bordes.
  - `spores`: Esporas biológicas bioluminiscentes con pulsación cromática sutil.
  - `rain_streaks`: Trazas de lluvia con refracción y velocidad direccional constante.
- **Determinismo y Formulación Física**:
  Cada partícula $j \in [0, M-1]$ se define por una función analítica del tiempo $t$ y la semilla $S$:
  $$\vec{x}_j(t) = \vec{x}_{j,0} + \vec{v}_j \cdot t + \vec{T}_{\text{FBM}}(\vec{x}_j, t, S)$$
  Donde $\vec{T}_{\text{FBM}}$ es un vector de turbulencia armónica calculada sobre octavas periódicas. No se requiere integración numérica dependiente de delta-time mutable, asegurando 100% de reproducibilidad.

---

## 3. Motor Procedural Puro 1080p/4K (Pure Procedural WebGL/Canvas Engine)

El Motor Procedural es una solución de computación gráfica en tiempo real completamente determinista, ejecutada en Headless Chromium (Playwright) y renderizada cuadro a cuadro con tiempo virtual.

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  Headless Chromium   │ ──► │ Inyección de Tiempo  │ ──► │  Ejecución Shader    │
│  (Playwright Worker) │     │ Virtual (t = n / fps)│     │  (WebGL / Three.js)  │
└──────────────────────┘     └──────────────────────┘     └──────────┬───────────┘
                                                                     │
┌──────────────────────┐     ┌──────────────────────┐                │
│ Master MP4 Video     │ ◄── │ FFmpeg Pipe stdin    │ ◄──────────────┘
│ (CRF 18-20, Rec.709) │     │ (Raw RGBA Frame Byte)│
└──────────────────────┘     └──────────────────────┘
```

### 3.1 Entorno de Ejecución Determinista y Tiempo Virtual
- **Aislamiento de Navegador**: Instancia headless de Chromium lanzada con banderas de aislamiento:
  `--disable-gpu` (o `--use-gl=angle/swiftshader`), `--no-sandbox`, `--disable-dev-shm-usage`, `--hide-scrollbars`.
- **Tiempo Virtual (Virtual Time Stepping)**:
  El renderizado no depende del reloj de pared del sistema operativo. El controlador Python avanza los frames secuencialmente:
  ```javascript
  window.renderSceneFrame(frameIndex, totalFrames, frameIndex / fps, durationSec);
  ```
  Esto garantiza que incluso shaders complejos de raymarching de 500ms/frame se capturen a exactamente 30fps sin saltos ni pérdida de fotogramas (zero frame-drops).
- **Streaming Directo a FFmpeg Pipe**:
  La imagen de cada fotograma se extrae del canvas HTML5 (`#c`) como buffer binario y se escribe directamente en el descriptor `stdin` del subproceso FFmpeg mediante `-f image2pipe -vcodec png -i -`.

### 3.2 Shaders Matemáticos de Raymarching y Ruido Armónico Periódico
- **Raymarching con Funciones de Distancia con Signo (SDF)**:
  Modelado analítico de horizontes de eventos cósmicos, esferas de contención y monolitos dimensionales sin mallas poligonales pesadas:
  $$d_{\text{sphere}}(\vec{p}, r) = \|\vec{p}\| - r$$
  $$d_{\text{box}}(\vec{p}, \vec{b}) = \|\max(|\vec{p}| - \vec{b}, 0)\| + \min(\max(p_x - b_x, \max(p_y - b_y, p_z - b_z)), 0)$$
  $$d_{\text{torus}}(\vec{p}, t_{\text{rad}}, r_{\text{tube}}) = \left\|\begin{pmatrix}\sqrt{p_x^2 + p_z^2} - t_{\text{rad}} \\ p_y\end{pmatrix}\right\| - r_{\text{tube}}$$
- **Ruido Fractal Armónico Periódico (Periodic FBM)**:
  Para garantizar bucles continuos de $T$ segundos sin costuras:
  $$\phi(t) = \frac{t}{T} \cdot 2\pi$$
  $$\text{FBM}_{\text{periodic}}(\vec{x}, t) = \sum_{k=0}^{K-1} \frac{1}{2^k} \cdot \text{noise}\left(2^k \vec{x} + \begin{pmatrix}\cos(\phi(t)) \\ \sin(\phi(t)) \\ \cos(2\phi(t))\end{pmatrix}\right)$$
  Cumpliendo estrictamente $f(0) = f(T)$ y $\frac{df}{dt}(0) = \frac{df}{dt}(T)$ ($C^1$ continuity).

### 3.3 Generador Atmosférico Canvas2D
- **Sistemas de Siluetas y Niebla Multicapa**:
  Renderizado en HTML5 Canvas con doble búfer (`OffscreenCanvas`), aplicando transformaciones lineales y gradientes radiales oscuros.
- **Ondas Reactivas de Audio y Gradientes Noir**:
  Generación de formas de onda sintetizadas armónicamente para canales de drama y AITA, eliminando la necesidad de video real y manteniendo una estética minimalista elegante.

### 3.4 Matriz de Paletas de Color Prémium Estrictas
Se prohíbe explícitamente el uso de colores saturados estridentes, estilizaciones caricaturescas o degradados planos:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             MATRIZ CROMÁTICA CANÓNICA POR CARRIL                                 │
├───────────────────────┬────────────────────────┬────────────────────────┬────────────────────────┤
│ Carril Temático       │ Fondo Base (60-70%)    │ Tono Medio (20-30%)    │ Acento (5-10%)         │
├───────────────────────┼────────────────────────┼────────────────────────┼────────────────────────┤
│ moku-horror-long      │ Negro Abisal           │ Violeta Profundo /     │ Carmesí Sangre /       │
│ (Cosmic Horror)       │ #020104, #07020d       │ Índigo Oscuro          │ Bruma Púrpura          │
│                       │                        │ #1e0838, #0f172a       │ #780a1e, #9333ea       │
├───────────────────────┼────────────────────────┼────────────────────────┼────────────────────────┤
│ moku-horror-long      │ Verde Bosque Umbrío    │ Musgo Cenizo /         │ Esporas Bioluminisc. / │
│ (Dark Forest)         │ #030a05, #08140c       │ Sombra Pétrea          │ Bruma Fría             │
│                       │                        │ #1b2e1f, #1e2923       │ #34d399, #94a3b8       │
├───────────────────────┼────────────────────────┼────────────────────────┼────────────────────────┤
│ moku-scp-shorts       │ Gris Pizarra           │ Acero Industrial /     │ Ámbar Alerta /         │
│ (SCP Foundation)      │ #0b0d10, #111827       │ Cian Militar           │ CRT Fosforescente      │
│                       │                        │ #1f2937, #0e3a43       │ #d97706, #10b981       │
├───────────────────────┼────────────────────────┼────────────────────────┼────────────────────────┤
│ aelithia-aita-long    │ Negro Carbón Mate      │ Grafito Minimalista /  │ Oro Champagne /        │
│ (Drama AITA)          │ #09090b, #121214       │ Azul Medianoche        │ Oro Rosa Sutil         │
│                       │                        │ #1f1f23, #172554       │ #d4af37, #be185d       │
└───────────────────────┴────────────────────────┴────────────────────────┴────────────────────────┘
```

**Reglas de Validación Matemática del Color**:
- Saturación máxima permitida: $S_{\text{HSV}} \le 0.85$ (85%).
- Luminancia media ponderada: $Y = 0.2126 R + 0.7152 G + 0.0722 B \in [22.0, 110.0]$ sobre escala 255 (prohibidos blancos puros o fondos sobreexpuestos).
- Espacio de Color: Señalización obligatoria Rec.709 (`bt709` primaries, transfer function y matrix).

### 3.5 Escalabilidad Nativa 1080p y 4K UHD
El renderizador procedural soporta resoluciones nativas arbitrarias mediante el ajuste dinámico del viewport:
- **Full HD Horizontal (16:9)**: $1920 \times 1080$ px
- **Full HD Vertical (9:16)**: $1080 \times 1920$ px
- **4K UHD Horizontal (16:9)**: $3840 \times 2160$ px
- **4K UHD Vertical (9:16)**: $2160 \times 3840$ px

---

## 4. Lógica de Selección de Motor y Jerarquía de Fallback (Fail-Closed)

El agente **Scene Planner** asigna el motor óptimo evaluando los metadatos narrativos de cada escena:

```
                                 [Evaluación de la Escena]
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
            [Entorno Arquitectónico/                    [Espacio Abstracto/
              Locación Específica]                        Atmósfera Continua]
                       │                                           │
                       ▼                                           ▼
          [Motor Híbrido Cinemático IA]               [Motor Procedural WebGL/Canvas]
                       │                                           │
          ┌────────────┴────────────┐                 ┌────────────┴────────────┐
          ▼ (Éxito)                 ▼ (Fallo API)     ▼ (Éxito)                 ▼ (Crash)
    [Renderizado 2.5D]       [Fallback 1: Banco]   [Renderizado GPU]    [Fallback 3: SQLite]
                                    │                                           │
                             ┌──────┴──────┐                             [Loop Pre-renderizado]
                             ▼ (No match)  ▼ (Match)
                       [Fallback 2: Procedural] [Asset Banco]
```

### Cascada de Fallback en 3 Niveles:
1. **Tier 1 (Fallback por Banco Visual Local)**: Si la API de generación de imágenes falla o agota su cuota, el sistema realiza una búsqueda semántica de imágenes fotorrealistas pre-aprobadas en `assets/visual_bank/` utilizando dHash y coincidencia de tags temáticos.
2. **Tier 2 (Fallback por Render Procedural Dinámico)**: Si no se encuentra ningún asset local en el banco, el sistema conmuta la escena a **Pure Procedural WebGL** utilizando la plantilla y paleta cromática asignada al carril.
3. **Tier 3 (Fallback por Catálogo SQLite de Loops Precomputados)**: Si ocurre un fallo en el entorno WebGL/Headless Chromium (ej. timeout o memoria de GPU agotada), el sistema recupera un bucle de video verificado directamente desde la base de datos `loop_catalog.db`.

---

## 5. Resumen de Implementación y Mapeo de Archivos

| Componente | Archivo Fuente Principal | Responsabilidad Técnica |
|------------|--------------------------|-------------------------|
| Interfaz de Composición | `src/compositor_interface.py` | Clase abstracta `BaseVideoCompositor` y despachador de motores |
| Motor Procedural WebGL | `src/media/web_video_renderer.py` | Orquestación Playwright headless y streaming a FFmpeg |
| Plantillas Procedurales | `src/media/web_templates/` | Shaders GLSL (`cosmic_horror_three.html`, `space_abyss_three.html`) y Canvas2D (`dark_forest_canvas.html`, `drama_waves_canvas.html`) |
| Catálogo de Bucles SQLite | `src/core/loop_catalog.py` | Persistencia y recuperación transaccional de loops precomputados |
| Quality Gates y Validación | `src/core/quality.py` | Validación de nitidez, luminancia y ausencia de artefactos |
