# Plan Final de Correcciones — Simulación Red de Alcantarillado Ciudad Bicentenario

> **Estado: COMPLETADO Y VERIFICADO** — Las 5 fases del plan han sido ejecutadas e integradas con **40/40 pruebas unitarias aprobadas** (`python -m unittest discover -s tests -v`) y exportación CLI verificada.

Plan técnico definitivo ejecutado para resolver los **25 hallazgos** documentados en [AUDITORIA_ERRORES.md](<AUDITORIA_ERRORES.md>) (`E1–E4`, `M1–M10`, `U1–U4`, `D1–D4`), alineando el motor hidráulico, la ingesta de datos, la interfaz gráfica, los reportes y las pruebas con [GuiaDocente.md](<GuiaDocente.md>).

---

## Decisiones Confirmadas

1. **Discrepancia `P57` (`D1`):** se mantiene `P57 = 12"` (`Qmax = 0.08743095 m³/s`) exactamente como figura en `data/DataSetBicentenario.xlsx` y `data/csv/pipes.csv`. No se modifica el archivo del docente; únicamente se deja documentada la diferencia frente al Anexo 2 (`0.19 m³/s` / `16"`).
2. **Selector `Escenario de precipitación` (`U4`):** se reemplaza `ttk.Combobox` por un **`tk.Menubutton` + `tk.Menu` estilizado** (misma apariencia visual, 100 % inmune al bug de `ComboboxPopdownFrame` en blanco bajo Windows `clam` + HiDPI), pausando la reproducción al abrir el menú y protegiendo el `<Leave>` de `left_panel`.
3. **Manejo del rebose superficial:** se conserva íntegramente la mecánica de almacenamiento en pozo (`max_manhole_storage_m3 = 4.0 m³`) y acumulación de **rebose superficial en vía** (`surface_flooding_m3`) cumpliendo la sección §5.5 de [GuiaDocente.md](<GuiaDocente.md>) y la conservación global de masa ($	ext{Error} < 10^{-9}\;\text{m}^3$), incorporándolo además a las gráficas de **Evolución** y a la tabla de **Comparación**.

---

## Orden de Ejecución por Dependencias

```text
Fase 1: Motor hidráulico y fórmulas oficiales (models.py, engine.py, analysis.py)
   ↓
Fase 2: Ingesta, validación de datos y comparación (data_loader.py, comparison.py)
   ↓
Fase 3: Gráficas y visualización del grafo (charts_panel.py, network_canvas.py, theme.py)
   ↓
Fase 4: Correcciones de interfaz GUI (app.py)
   ↓
Fase 5: Reportes, pruebas automatizadas, documentación y entrega (reporter.py, docx_exporter.py, tests/, docs)
```

---

## Fase 1 — Motor Hidráulico y Fórmulas Oficiales (`E1`, `E2`, `E3`, `E4`, `M1`, `M2`, `M3`, `M4`, `M8`)

**Archivos:** `src/simulation/models.py`, `src/simulation/engine.py`, `src/algorithms/analysis.py`

### 1.1 Parámetros por defecto fieles a la guía (`E2`)
- En `src/simulation/models.py` (`SimulationConfig`):
  - Cambiar `ingress_factor: float = 1.0` (100 % del Método Racional $Q = 0.00278 \cdot C \cdot I \cdot A$).
  - Cambiar `dry_weather_flow_per_source_m3s: float = 0.0` (sin caudal sanitario inventado; en Tiempo seco $I=0$, $Q=0\;\text{m}^3/\text{s}$ y utilización `0.0 %`).
  - Retirar el uso de `max_physical_utilization_pct` como techo artificial de cálculo.

### 1.2 Integración exacta de hietograma y sub-paso hidráulico continuo (`E3`, `M2`)
- En `src/simulation/engine.py`:
  - Reemplazar `_effective_intensity(config, t_curr_min)` por `_interval_mean_intensity(config, t0_min, t1_min)` usando la integral analítica exacta:
    $$\bar{I}_{[t_0, t_1]} = \frac{1}{t_1 - t_0} \int_{t_0}^{t_1} I_{\text{ef}}(\tau)\,d\tau$$
    - Cubre hietograma `"uniform"` y `"triangular"` sin pérdida de volumen cuando `storm_duration_min == dt_min` ni en duraciones no múltiplos de `dt_min`.
  - Implementar **sub-paso interno** $\Delta t_{\text{sim}} \le \min(\Delta t_{\text{usuario}},\; 10\;\text{s},\; 0.25 \cdot t_{\min,\text{red}})$ (con $t_{\min} = 48.66\;\text{s}$ en `P54`, nunca ocurre tránsito instantáneo en el mismo paso).
  - Programar eventos `_TransitEvent` en la `PriorityQueue` con tiempo continuo de llegada (`arrival_s = t_sub_end_s + eff_transit_s`), respetando el tiempo mínimo físico a PTAR `31` ($\ge 8.7529\;\text{min}$) y eliminando la variación de +14.6 % al cambiar `dt_min`.
  - Ajustar el último intervalo exactamente a `duration_min` y emitir `TimeStepSnapshot` en la malla solicitada por el usuario (`dt_min` + `duration_min`).

### 1.3 Intervenciones en fuentes y sumideros estrictos (`M8`, `M5` motor)
- En `compute_source_inflows_by_source` (`src/simulation/engine.py`):
  - Bajo `source_distribution == "capacity"`, usar `resolve_pipe_hydraulics(e, inv)[0]` (`eff_q_max`) en vez de `e.q_max_m3s` sin intervención.
- En el despacho nodal (`src/simulation/engine.py`):
  - Acreditar a `cum_sink_m3` **únicamente** cuando `node.node_type == "sink"`.

### 1.4 Utilización real sin recorte, coherencia nodo–tubería, vaciado de pozo y cierre 100 % (`E1`, `E4`, `M1`, `M3`)
- En `src/simulation/engine.py`:
  - **Demanda real (`M1`):** calcular `q_demand = demand_vol / dt_sim` (incluye llegadas + vaciado del volumen almacenado en pozo `node_stored[u]`).
  - **Coherencia nodo–tubería (`E4`):** asignar `PipeStepState.flow_m3s = conveyed_flow_m3s = sent_vol / dt_sim` ($\le Q_{\max,\text{ef}}$) garantizando `node.outflow_m3s == sum(pipe.flow_m3s)` en el **100 %** de los nodos y pasos. Mantener `PipeStepState.demand_flow_m3s = q_demand`.
  - **Utilización oficial sin tope (`E1`):** eliminar el piso `1.05 * Qmax` y la curva exponencial de techo `115 %`. Calcular:
    $$O_i(t) = \frac{Q_{\text{dem},i}(t)}{Q_{\max,\text{ef},i}} \times 100$$
  - **Tubería cerrada al 100 % (`M3`):** si `eff_q_max <= 1e-12`, reportar `flow_m3s = 0.0`, `utilization_pct = 0.0`, `demand_ratio_pct = 0.0`, `is_overloaded = False` y bandera `is_closed = True`.
- En `src/algorithms/analysis.py` (`compute_source_attribution`):
  - Omitir atribución de fuentes en tuberías cerradas (`eff_q_max <= 1e-12`).

### 1.5 Frontera exacta `75.0 %` y rangos excluyentes (`M4`)
- En `src/algorithms/analysis.py` y `src/simulation/engine.py`:
  - Alinear con [GuiaDocente.md](<GuiaDocente.md>) §7:
    - `0–25 %`: `u <= 25.0` (Verde — *Baja utilización*)
    - `>25–50 %`: `25.0 < u <= 50.0` (Amarillo — *Utilización moderada*)
    - `>50–75 %`: `50.0 < u <= 75.0` (Naranja — *Utilización alta*)
    - `>75–100 %`: `75.0 < u <= 100.0` (Rojo — *Cercana a la capacidad máxima*)
    - `>100 %`: `u > 100.0` (Rojo oscuro — *Capacidad excedida*)
  - Cambiar la condición en `engine.py` de `>= 75.0` a `> 75.0` y exponer tanto el conjunto `>75–100 %` como `>100 %` sin ambigüedad.

**Criterio de verificación Fase 1:** E1 = `0.0 m³` y `0 %`; E3–E5 diferenciados con `util > 115 %`; `0` discrepancias nodo–tubería; error de masa $< 10^{-9}\;\text{m}^3$; llegada a PTAR `31` $\ge 8.75\;\text{min}$ e invarianza de descarga PTAR para `dt = 0.5, 1.0, 2.0, 5.0 min`; hietograma triangular `storm=1, dt=1` exacto.

---

## Fase 2 — Ingesta, Validación de Datos y Comparación (`M5`, `M6`, `M7`, `M9`, `D1`, `D3`)

**Archivos:** `src/io/data_loader.py`, `src/simulation/comparison.py`

### 2.1 Validación topológica estricta (`M5`)
- En `_validate_graph_and_data`:
  - Exigir `out_degree > 0` para todo nodo con `node_type != "sink"`.
  - Verificar mediante BFS reverso desde sumideros que todas las fuentes alcanzan al menos un `sink`.

### 2.2 Paridad CSV/Excel, encabezados y precisión (`M6`, `D3`)
- En `load_from_csv_dir`: añadir fallback Manning si falta `q_max_m3s` y validar coherencia `diameter_in` vs. `diameter_m` (tolerancia 2 %).
- En `load_from_excel`: resolver columnas de `Pipe(s)` por encabezado normalizado (soportando `"Lenght (m)"` y `"Length (m)"`) con fallback posicional, y detectar fórmulas sin valor cacheado.
- En `export_to_csv_dir`: conservar precisión completa de `q_max_m3s` en lugar de truncar a 8 decimales (`D3`).

### 2.3 Coordenadas por defecto desacopladas (`M7`)
- Aplicar `DEFAULT_NODE_COORDS` únicamente cuando el grafo cargado corresponda a Ciudad Bicentenario; en cualquier red externa sin `node_coords.csv`, usar `_assign_missing_coordinates`.

### 2.4 Pico simultáneo de almacenamiento (`M9`)
- En `src/simulation/comparison.py`: calcular `max_stored_surcharge_m3 = max((s.total_manhole_storage_m3 for s in res.snapshots), default=0.0)` (pico simultáneo real, no suma asíncrona).

### 2.5 Discrepancia `P57` (`D1`)
- Mantener `DataSetBicentenario.xlsx` y `data/csv/pipes.csv` intactos (`P57 = 12"`).

---

## Fase 3 — Gráficas y Visualización del Grafo (`M10`, `D2`, `M3` visual)

**Archivos:** `src/gui/charts_panel.py`, `src/gui/network_canvas.py`, `src/gui/theme.py`

### 3.1 Gráficas con rebose, almacenamiento y utilización real (`M10`)
- En `TemporalChartsPanel`:
  - `ax_flow`: añadir serie de **tasa de rebose superficial** ($\Delta V_{\text{rebose}}/\Delta t$) junto a Entrada y Descarga PTAR `31`.
  - `ax_util`: graficar utilización real sin techo `115 %` con autoescala Y y líneas de referencia en `75 %` y `100 %`.
  - `Perfil longitudinal`: graficar `conveyed_flow_m3s` ($\le Q_{\max}$), línea/barra de `Qmax` y demanda excedente cuando exista sobrecarga.
- En `ComparisonChartsPanel`: alinear leyendas con categorías excluyentes (`>75–100 %` y `>100 %`).

### 3.2 Mapa de red: etiquetas compactas y tuberías cerradas (`D2`, `M3`)
- En `src/gui/network_canvas.py`:
  - Compactar etiquetas muy altas sobre el mapa (ej. `>= 1000%` $\to$ `1.4k%`) manteniendo el valor exacto en Inspector, tooltips y tablas.
  - Dibujar tuberías cerradas al 100 % (`is_closed`) con estilo gris punteado y etiqueta `CERRADA`.
  - Unificar el código de color de `>100 %` entre `analysis.py`, `theme.py` y `network_canvas.py`.

---

## Fase 4 — Correcciones de Interfaz Gráfica (`U1`, `U2`, `U3`, `U4`, `E2` GUI)

**Archivo:** `src/gui/app.py`

### 4.1 Defaults de la guía y preset de sensibilidad (`E2`)
- Inicializar `var_ingress_pct = 100.0` y `var_q_san = 0.0`.
- Incluir presets claros: **`Oficial Guía (100% · Q_san=0)`** (por defecto) y **`Calibrado (2.5% + Q_san)`** (opcional).

### 4.2 Toggle `Aguas arriba` / `Aguas abajo` únicamente en el Inspector (`U1`)
- Añadir `self._inspector_trace_state: Optional[Tuple[str, str]] = None`.
- Al pulsar `Aguas arriba` o `Aguas abajo` en el **Inspector**:
  - Primer clic: resalta la traza y marca el botón en `primary`.
  - Segundo clic sobre el mismo botón y nodo: apaga el resaltado (`set_highlights(set(), set())`), limpia `_inspector_trace_state` y restaura el botón a `light_secondary`.
- **No modificar** el panel izquierdo **Recorridos** (mantiene limpieza explícita con el botón `Limpiar`).

### 4.3 Botón y tabla de la pestaña `Comparación` (`U2`)
- Añadir etiqueta de estado (`Al día · HH:MM:SS (X.XX s)` vs. `Desactualizado`).
- Sincronizar el botón con `self._comparisons_dirty`: neutro (`Recalcular 5 Escenarios`) cuando está al día, y `primary` (`Recalcular 5 Escenarios *`) cuando cambiaron parámetros; al pulsar, forzar recálculo con feedback inmediato.
- Añadir columna `Rebose (m³)` y ajustar `_resize_comp_columns` para que `Escenario` nunca recorte `"E3 Lluvia moderada"` ni `"E5 Lluvia extrema"`.

### 4.4 Filtros excluyentes y anchos en `Tuberías Críticas` (`U3`)
- Reemplazar filtros por 4 categorías mutuamente excluyentes alineadas con [GuiaDocente.md](<GuiaDocente.md>):
  - `Todas`
  - `Resto (≤75%)`
  - `Críticas (>75–100%)`
  - `Sobrec. (>100%)`
- Ampliar columna `Estado` en `_resize_critical_columns` y usar etiquetas completas sin recorte (`Cap. excedida`, `Cercana máx.`, `Alta`, `Moderada`, `Baja`, `Cerrada`).

### 4.5 Selector `Escenario de precipitación` robusto (`U4`)
- Reemplazar `ttk.Combobox` por un **`tk.Menubutton` + `tk.Menu` estilizado** (visualmente coherente con la paleta `Light`, 100 % libre del bug de `ComboboxPopdownFrame` en blanco en Windows `clam` + HiDPI).
- Pausar reproducción si `is_playing` está activo al abrir el menú y proteger `<Leave>` de `left_panel` mientras el menú esté desplegado.

---

## Fase 5 — Reportes, Pruebas Automatizadas, Documentación y Entrega (`D4`)

**Archivos:** `src/simulation/reporter.py`, `src/simulation/docx_exporter.py`, `src/simulation/charts_export.py`, `tests/`, `DOCUMENTACION.md`, `README.md`, `AUDITORIA_ERRORES.md`

### 5.1 Actualización de textos y reportes
- Actualizar *Supuestos del Modelo*, *Guía de Sustentación* (`app.py`), `reporter.py`, `docx_exporter.py` y `charts_export.py` eliminando referencias al techo `115 %` y al `2.5 %` por defecto, incorporando el sub-paso continuo, el rebose y la nota técnica de `P57`.

### 5.2 Suite de pruebas automatizadas
- Actualizar y ampliar `tests/test_simulation.py`, `tests/test_loader.py` y `tests/test_gui.py` con pruebas específicas para `E1–E4`, `M1–M9` y `U1–U4`.
- Ejecutar `python -m unittest discover -s tests -v` hasta obtener 100 % verde y verificar exportación CLI (`python main.py --report ... --report-docx ... --technical-docx ...`).

### 5.3 Documentación y empaquetado final
- Actualizar [DOCUMENTACION.md](<DOCUMENTACION.md>) con los nuevos resultados verificados y comportamiento final.
- Añadir nota de `python3-tk` para Linux en `README.md`.
- Actualizar el estado de resolución en [AUDITORIA_ERRORES.md](<AUDITORIA_ERRORES.md>).
