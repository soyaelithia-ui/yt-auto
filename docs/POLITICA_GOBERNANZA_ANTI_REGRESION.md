# Política de Gobernanza, Cadencia de Verificación y Cláusula de Negativa (Kill Switch)

> **Estado:** NORMA OFICIAL INNEGOCIABLE  
> **Ámbito:** Todos los Agentes de IA, Desarrolladores y Pipelines de Producción  
> **Script de Ejecución:** `scripts/verify_integrity.sh`

---

## 1. Cláusula de Negativa Obligatoria (Work Refusal / Kill Switch)

> [!CAUTION]
> **MANDATO DE DETENCIÓN INMEDIATA**:
> Si en cualquier momento se detecta una violación a los 5 invariantes del sistema, cualquier agente de IA o desarrollador **TIENE LA OBLIGACIÓN FORMAL DE NEGARSE A CONTINUAR TRABAJANDO**, abortar el lanzamiento de pipelines y emitir una alerta crítica inmediata al operador.
>
> **Bajo ninguna circunstancia se permite continuar implementando funcionalidades o generando videos sobre un árbol de trabajo comprometido.**

---

## 2. Los 5 Invariantes Innegociables de Calidad

1. **Aislamiento Absoluto de Medios (Zero-Browser Policy)**:
   - Cero imports de `playwright`, `puppeteer` o invocaciones de `chromium` en `src/media/`, `src/cli/`, `src/narrative/` o `src/core/`.
   - Playwright queda estrictamente restringido a `src/youtube/` para subidas de respaldo a YouTube Studio.
2. **Higiene de Árbol Git (Single SSOT)**:
   - Debe existir exactamente **1 worktree activo** reportado por `git worktree list`.
   - La rama `main` debe ser la única rama activa de producción y estar perfectamente sincronizada con `origin/main` en GitHub. Cero ramas muertas o divergentes.
3. **Candado Pre-Commit Activo**:
   - `.githooks/pre-commit` debe estar instalado, tener permisos `+x` y estar configurado en Git (`git config core.hooksPath == .githooks`).
4. **Cero Documentos Resucitados**:
   - Prohibida la existencia de planos antiguos en `docs/architecture/0*.md`.
   - Prohibida la existencia de directorios jubilados (`src/rendering/`, `src/compositing/`, `src/export/`).
5. **Certificación de Suite de Anti-Regresión**:
   - La suite de pruebas de guardrails (`tests/unit/test_anti_regression_guardrails.py`, REG-01 a REG-30) debe aprobar al 100% en tiempo de ejecución.

---

## 3. Cadencia de Verificación Obligatoria

La verificación de integridad mediante `./scripts/verify_integrity.sh` es obligatoria bajo las siguientes condiciones de cadencia:

| Disparador | Acción Obligatoria | Comportamiento si Falla |
|---|---|---|
| **Cada 25 Commits** | Auditoría completa automatizada con `./scripts/verify_integrity.sh`. | **Bloqueo**: Refusal activo. No se admite el commit 26 hasta subsanar. |
| **Inicio de Sesión de Agente** | Verificación de liveness y worktrees huérfanos antes de proponer cambios. | **Alerta al Usuario**: El agente notifica la anomalía y ejecuta saneamiento. |
| **Antes de Lanzar Pipeline de Producción** | Auditoría previa al renderizado de video real (carriles largos o Shorts). | **Abort**: El pipeline se niega a arrancar para no saturar CPU/RAM con navegadores. |

---

## 4. Procedimiento Estándar de Auditoría

Para verificar el cumplimiento en cualquier momento:

```bash
./scripts/verify_integrity.sh
```

- **Código de salida `0`**: Sistema saludable. Autorizado para proceder con desarrollo o generación.
- **Código de salida `1`**: Violación de gobernanza. El script detalla los puntos fallidos y activa el rechazo de trabajo.
