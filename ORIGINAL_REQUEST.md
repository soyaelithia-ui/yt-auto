# Original User Request

## 2026-08-28T04:42:04Z

<USER_REQUEST>
Exploración y optimización integral de recursos en yt-auto: reducción segura de huella en disco (~5.2 GB en work/ y output/), optimización de pipelines de renderizado y medios (FFmpeg/Three.js/Pipes), y eliminación de cuellos de botella de concurrencia y memoria sin regresiones.

Working directory: /home/tzpnyahvsj/project/yt-auto
Integrity mode: development

## Context & Baseline
El Milestone 1 (R1 - Profiling y Telemetría) ya ha sido implementado y verificado en `src/core/profiling.py`, `src/pipeline.py` y `src/cli/handlers/profile.py`. Proceder inmediatamente con la ejecución paralela y coordinada de los siguientes hitos:

## Requirements

### R2. Reducción Segura de Huella en Disco y Retención Automatizada
- Purgar y depurar de forma segura los archivos temporales huérfanos, fragmentos de prueba de desarrollo y buffers intermedios acumulados en `work/` (~1.4 GB) y `output/` (~3.8 GB), preservando estrictamente los videos maestros terminados y las miniaturas esenciales.
- Reforzar y automatizar en `src/cleaner.py` y `src/retention.py` las políticas de auto-limpieza post-render para evitar que futuros runs acumulen gigabytes de temporales innecesarios.

### R3. Optimización de Rendimiento en Motores de Video y Medios
- Optimizar los flujos de `lib/ffmpeg.py`, `src/media/realtime_video_engine.py`, `src/media/loop_engine.py` y `src/media/compositor.py`:
  - Configurar particionamiento óptimo de hilos (`-threads`), aceleración y presets balanceados de compresión.
  - Reemplazar la escritura intermedia de frames individuales a disco por pipes directos/streaming hacia FFmpeg donde sea aplicable.
  - Eliminar dobles codificaciones y normalizaciones redundantes de audio.

### R4. Eficiencia de Memoria, Concurrencia y Persistencia
- Optimizar el consumo de RAM en el procesamiento de frames e imágenes en memoria por lotes.
- Garantizar que las transacciones en SQLite WAL bajo concurrencia multi-carril (*multi-lane*) operen sin bloqueos (`database is locked`) ni contención de hilos.

## Verification Resources

- Suite de pruebas de regresión y E2E: `tests/e2e/test_r1_r4_e2e.py`, `tests/unit/test_profiling.py`, `tests/unit/test_scoring.py`, `tests/unit/test_db.py`.
- Módulos de limpieza y retención: `src/cleaner.py`, `src/retention.py`.
- Motores de medios y ffmpeg: `lib/ffmpeg.py`, `src/media/`, `src/audio_processor.py`.

## Acceptance Criteria

### Huella en Disco
- [ ] Reducción drástica del espacio ocupado en `work/` y `output/` eliminando temporales de desarrollo sin afectar los videos maestros ni miniaturas existentes.
- [ ] Pruebas unitarias de limpieza demostrando que `cleaner.py` elimina temporales expirados y respeta artefactos protegidos.

### Optimización de Medios y Pipeline
- [ ] Mejora medible en el tiempo de renderizado/compresión de video mediante pipes y presets eficientes sin pérdida perceptible de calidad visual o sonora.
- [ ] Eliminación de escrituras innecesarias a disco de archivos intermedios de frame.

### Estabilidad y Cero Regresiones
- [ ] Toda la suite de pruebas del proyecto (`pytest`) ejecuta satisfactoriamente al 100% tras las optimizaciones.
- [ ] Cero errores de contención en base de datos (`database is locked`) bajo estrés concurrente multi-carril.
</USER_REQUEST>
