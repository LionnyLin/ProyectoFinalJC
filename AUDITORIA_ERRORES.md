# Auditoría Exhaustiva de Errores — Fórmulas, Manejo de Datos y Cumplimiento

Análisis forense del código fuente (`src/`), datos (`data/`) y pruebas (`tests/`) frente a [GuiaDocente.md](<GuiaDocente.md>) y la imagen del **Anexo 2** del PDF. Cada hallazgo incluye archivo, líneas exactas, evidencia numérica reproducida y causa raíz.

---

## Resumen Ejecutivo

| Categoría | Críticos (contradicen la guía o rompen física/matemática) | Moderados (manejo de datos / consistencia) | Externos / Menores (dataset / UI / entrega) | Total |
| :--- | :---: | :---: | :---: | :---: |
| **Fórmulas e hidráulica (`engine.py`, `models.py`, `analysis.py`)** | 4 | 4 | 1 | **9** |
| **Manejo de datos e ingesta (`data_loader.py`, `data/`)** | 0 | 3 | 2 | **5** |
| **Reportes, comparación e interfaz (`comparison.py`, `charts_panel.py`, `app.py`)** | 0 | 7 | 4 | **11** |
| **Total** | **4** | **14** | **7** | **25** |

---

## 1. Errores Críticos de Fórmulas y Simulación (Contradicen [GuiaDocente.md](<GuiaDocente.md>))

### E1. Utilización recortada al 115 % con curva exponencial y piso artificial de 105 %
- **Ubicación:** [src/simulation/engine.py:296-309](<src/simulation/engine.py#L296-L309>), [src/simulation/models.py:76](<src/simulation/models.py#L76>)
- **Regla violada:** Sección 5.5 de [GuiaDocente.md](<GuiaDocente.md>):
  $$O_i(t) = \frac{Q_i(t)}{Q_{\max,i}} \times 100$$
- **Qué hace el código actualmente:**
  - Cuando existe exceso ($V_{\text{exc},i} > 10^{-9}$ o $Q_{\text{dem},i} > Q_{\max,\text{ef},i}$), fuerza un piso de $1.05\,Q_{\max}$ y aplica:
    $$U_i(t) = 100.0 + (115.0 - 100.0)\left(1 - e^{-1.6\,f_{\text{sobre}}}\right)$$
  - La razón real sin recorte se relega a `demand_ratio_pct`, mientras `utilization_pct` (el indicador usado en gráficas, tabla de críticas, mapa de colores y `ScenarioSummary.max_utilization_pct`) queda aplastada en $(100\%, 115\%]$.
- **Evidencia reproducida (configuración por defecto):**
  - **E3 (30 mm/h):** `max_util = 113.06 %` vs. real **`227.70 %`**.
  - **E4 (60 mm/h):** `max_util = 113.75 %` vs. real **`255.15 %`**.
  - **E5 (100 mm/h):** `max_util = 114.91 %` vs. real **`418.51 %`**.
  - Los escenarios E3, E4 y E5 se comprimen en una banda de 1.85 puntos porcentuales y resultan visualmente casi indistinguibles.
- **Corrección requerida:** calcular el porcentaje oficial sin tope artificial ($O_i(t) = (Q_{\text{dem},i}/Q_{\max,\text{ef},i}) \times 100$) y mantener separado el caudal físicamente conducido aguas abajo (`conveyed_flow_m3s = min(Q_dem, Q_max)`).

---

### E2. Alteración por defecto del Método Racional (`ingress_factor = 0.025` y `Q_san = 0.003`)
- **Ubicación:** [src/simulation/models.py:70-73](<src/simulation/models.py#L70-L73>), [src/simulation/engine.py:72-91](<src/simulation/engine.py#L72-L91>), [src/gui/app.py:148-149](<src/gui/app.py#L148-L149>)
- **Regla violada:** Sección 5.2 de [GuiaDocente.md](<GuiaDocente.md>):
  $$Q = 0.00278 \cdot C \cdot I \cdot A$$
  La guía solo permite incorporar caudal sanitario *"si se dispone de información sobre el caudal sanitario en tiempo seco"*, pero `DataSetBicentenario.xlsx` no incluye ese dato.
- **Qué hace el código actualmente:**
  - Por defecto aplica `ingress_factor = 0.025` ($2.5\%$) y `dry_weather_flow_per_source_m3s = 0.003` $\text{m}^3/\text{s}$ por fuente.
  - En **Escenario 1 (Tiempo seco, $I = 0\;\text{mm/h}$)** inyecta `0.024 m³/s` continuos y lleva las tuberías a $\sim 10\%$ de uso cuando debería ser `0.000 m³/s` ($0\%$).
  - En los escenarios de lluvia descarta el $97.5\%$ del caudal racional oficial.
- **Corrección requerida:** establecer por defecto `ingress_factor = 1.0` ($100\%$) y `dry_weather_flow_per_source_m3s = 0.0`, conservando el `2.5% + Q_san` únicamente como *preset* opcional de análisis de sensibilidad en la GUI.

---

### E3. Tránsito instantáneo en tramos cortos, retroceso temporal en pasos y sensibilidad del 14.6 % a $\Delta t$
- **Ubicación:** [src/simulation/engine.py:256-274](<src/simulation/engine.py#L256-L274>)
- **Regla violada:** Sección 5.4 de [GuiaDocente.md](<GuiaDocente.md>): *"El algoritmo deberá gestionar el tiempo de desplazamiento; no deberá suponer que el agua llega instantáneamente al siguiente nodo."*
- **Causa matemática exacta:**
  1. Al despachar desde el nodo $u$ en el intervalo $[t_{k-1}, t_k]$, todo el volumen disponible (incluido el que **acaba de llegar** al nodo $u$ durante el paso $k$ en `t_curr_s` o en algún punto intermedio) se programa con `arrival_s = t_prev_s + eff_transit_s`, es decir, **retrocediendo el reloj al inicio del intervalo `t_prev_s`**.
  2. Cuando `arrival_s <= t_curr_s` (por ejemplo en `P54` con $t_{\text{trans}} = 48.66\;\text{s} < 60\;\text{s}$, o en cualquier tubería con $t_i \le \Delta t$), el agua llega al nodo destino en el mismo paso $k$ con retardo efectivo **cero** y `volume_in_transit_m3 = 0.0`.
- **Evidencia reproducida (Escenario 3):**
  - El camino más rápido desde cualquier fuente hasta la PTAR `31` es `27 → C (5.048 min) → 31 (3.705 min)` = **`8.7529 min`**.
  - Con `dt_min = 2.0 min`, un pulso enviado desde `27` en $t=0$ llega a `C` en `5.048 min` (dentro del paso `[4, 6]`), pero desde `C` se programa con `t_prev = 4.0`, dando `4.0 + 3.705 = 7.705 min <= 8.0 min`. Resultado: **el agua llega a la PTAR en `8.0 min` (< `8.7529 min` físico)**.
  - Variando $\Delta t$, el volumen descargado en PTAR `31` cambia en **+14.6 %**:
    - `dt = 0.5 min`: primera llegada `9.0 min`, descarga `1,070.32 m³`
    - `dt = 1.0 min`: primera llegada `9.0 min`, descarga `1,101.15 m³`
    - `dt = 2.0 min`: primera llegada **`8.0 min`**, descarga `1,177.14 m³`
    - `dt = 5.0 min`: primera llegada `10.0 min`, descarga `1,226.55 m³`
- **Corrección requerida:** propagar el tiempo continuo real de llegada por paquete (`event.arrival_time_s`) en lugar de reiniciar contra `t_prev_s`, o usar un sub-stepping / reloj continuo por evento de modo que ningún volumen cruce un nodo antes de su instante de llegada real ni cambie la descarga al variar $\Delta t$.

---

### E4. Incoherencia del 25.5 % entre caudal saliente de nodos y caudal reportado en tuberías
- **Ubicación:** [src/simulation/engine.py:250-335](<src/simulation/engine.py#L250-L335>), [src/gui/app.py:3725, 3768](<src/gui/app.py#L3725>)
- **Causa raíz:** `NodeStepState.outflow_m3s` se calcula con el volumen realmente enviado (`sent_vol / dt_s <= eff_q_max`), mientras `PipeStepState.flow_m3s` se asigna a `q_physical = eff_q_max * (util_pct / 100)` (hasta `1.15 * eff_q_max`).
- **Evidencia reproducida (Escenario 3):**
  - En `NODO 20` a $t = 30.0\;\text{min}$, el nodo reporta salida **`0.02965 m³/s`**, mientras su única tubería saliente `P39` reporta **`0.03146 m³/s`**.
  - Al verificar todos los nodos con salida en los 90 pasos de Escenario 3, **`1,033` de `4,050` evaluaciones (`25.5 %`)** presentan discrepancia entre `node.outflow_m3s` y $\sum \text{pipe.flow\_m3s}$.
- **Corrección requerida:** que `PipeStepState.flow_m3s` (o `conveyed_flow_m3s`) represente exactamente el caudal real transportado ($\le Q_{\max}$, coherente con `node.outflow_m3s`), y que `demand_flow_m3s` represente la demanda entrante que define la utilización.

---

## 2. Errores Moderados de Fórmulas, Algoritmos y Manejo de Datos

### M1. Exclusión del volumen almacenado en pozo (`node_stored[u]`) en `q_demand` durante el vaciado
- **Ubicación:** [src/simulation/engine.py:277, 299](<src/simulation/engine.py#L277>)
- **Qué ocurre:** `demand_vol = (node_stored[u] + node_arrivals[u]) * w`, pero `q_arrival_share = (node_arrivals[u] * w) / dt_s` omite `node_stored[u]`.
- **Consecuencia:** al cesar la lluvia (ej. `t = 61 min` en `NODO 20`, con `4.0 m³` en el pozo + `0.18 m³` sanitarios), la demanda real sobre `P39` es `4.180 / 60 = 0.06967 m³/s` (**235 %** de $Q_{\max}$), pero `q_arrival_share` vale `0.0030 m³/s` y `q_demand` cae a `0.02965 m³/s` (`100%`). Actualmente solo aparecía sobrecargado (`101.15%`) gracias al piso artificial `1.05 * Qmax`; al eliminar ese piso, si no se usa `demand_vol / dt_s`, las tuberías que vacían pozos llenos aparecerán falsamente al `100.0%` en vez de reflejar la carga del pozo.
- **Inconsistencia interna adicional:** para tuberías cerradas (`eff_q_max <= 1e-12`, línea 287), el código *sí* usa `max(q_arrival_share, demand_vol / dt_s)`, contradiciendo la línea 299 de tuberías abiertas.

### M2. Error de integración discreta en hietograma triangular y en `duration_min` / `storm_duration_min` no múltiplos de $\Delta t$
- **Ubicación:** [src/simulation/engine.py:44-58, 114, 211](<src/simulation/engine.py#L44-L58>)
- **Qué ocurre:**
  1. `_effective_intensity(t_curr_min)` evalúa el hietograma en el extremo derecho del intervalo $[t_{k-1}, t_k]$ en lugar de promediar/integrar sobre $[t_{k-1}, t_k]$.
  2. `n_steps = math.ceil(duration_min / dt_min)` usa siempre el mismo `dt_s = dt_min * 60` en el último paso, sin recortar el paso final a `duration_min - t_prev_min`.
- **Evidencia reproducida (con `ingress=1.0, Q_san=0`):**
  - Con `storm_duration_min = 1.0` y `dt_min = 1.0`, en el hietograma triangular `t_curr_min = 1.0 == storm_duration_min` $\implies$ $I_{\text{ef}}(1.0) = 0.0$, entrando **`0.0 m³`** de agua en toda la tormenta (esperado: `1,456.2 m³`).
  - Con `storm_duration_min = 45.0, dt_min = 2.0`, el hietograma uniforme pierde un paso de lluvia: **`64,071.2 m³`** vs. **`65,527.4 m³`** exactos (**-2.22 %**).
  - Con `duration_min = 10.0, dt_min = 3.0`, la simulación termina en **`t = 12.0 min`** (20 % más larga que lo configurado).

### M3. Tubería cerrada al 100 % reporta `utilization = 115 %`, `demand_ratio = 357 %` y recibe atribución de fuentes
- **Ubicación:** [src/simulation/engine.py:285-291](<src/simulation/engine.py#L285-L291>), [src/algorithms/analysis.py:239](<src/algorithms/analysis.py#L239>)
- **Qué ocurre:** cuando `P39` tiene `obstruction_pct = 100.0` (`eff_q_max = 0`, `flow_m3s = 0.0`), `engine.py` marca `utilization_pct = 115.0%` aunque el flujo es nulo, calcula `demand_ratio = 357.45%` contra el `edge.q_max_m3s` original, y `compute_source_attribution` sigue asignando `pipe_shares['P39'] = [('20', 1.0)]` pese a estar bloqueada (mientras `P40` aguas abajo muestra `[]`).

### M4. Contradicción en frontera exacta `75.0 %` entre `classify_utilization` y los contadores de críticas
- **Ubicación:** [src/algorithms/analysis.py:35-38](<src/algorithms/analysis.py#L35-L38>) vs. [src/simulation/engine.py:317](<src/simulation/engine.py#L317>), [src/gui/app.py:3530](<src/gui/app.py#L3530>)
- **Qué ocurre:** [GuiaDocente.md](<GuiaDocente.md>) §7 define `>50–75 %` como Naranja (*Utilización alta*) y `>75–100 %` como Rojo (*Cercana a capacidad máxima*). `classify_utilization(75.0)` retorna Naranja (`is_critical=False`), pero `engine.py:317` (`util_pct >= 75.0`) y el filtro de tabla (`min_u = 75.0`) incluyen `75.0%` como crítica. (En los 5 escenarios actuales ningún tramo cae en exactamente `75.000000%`, pero es una inconsistencia de frontera ante otros datos).

### M5. Falta de validación de nodos muertos / fuentes aisladas en `_validate_graph_and_data` + acreditación falsa a PTAR
- **Ubicación:** [src/io/data_loader.py:190-243](<src/io/data_loader.py#L190-L243>), [src/simulation/engine.py:224-228](<src/simulation/engine.py#L224-L228>)
- **Qué ocurre:**
  - `_validate_graph_and_data` comprueba que el grafo sea un DAG, pero **no valida** que las fuentes puedan llegar a un sumidero ni que los pozos intermedios tengan al menos una salida (`out_degree > 0`).
  - En `engine.py:224`: `if node.node_type == "sink" or not out_pipes: cum_sink_m3 += avail_vol`. Si un archivo CSV/Excel externo tiene un error tipográfico en `to_node` (ej. `"3l"` en vez de `"31"`), el cargador crea un pozo callejón sin salida y el motor suma toda su agua a **Descarga PTAR** sin lanzar error de validación.

### M6. Falta de validación cruzada de unidades y fallback de Manning en CSV vs. Excel
- **Ubicación:** [src/io/data_loader.py:308-329, 430-441](<src/io/data_loader.py#L308-L329>)
- **Qué ocurre:**
  - `load_from_csv_dir` no verifica consistencia entre `diameter_in` y `diameter_m` (ni entre `q_max_m3s` y Manning) ni ofrece fallback Manning si falta `q_max_m3s`, a diferencia de `load_from_excel`.
  - `load_from_excel` asume orden posicional fijo de columnas (`1..11`, incluyendo la columna `"Lenght (m)"` del Excel original) y salta filas resumen solo porque la columna 9 está vacía; además, si una celda numérica sin fallback (`length_m`, `slope`, `n`) contiene fórmula sin valor cacheado, `_parse_float` falla al intentar convertir la fórmula a float.

### M7. Acoplamiento de `DEFAULT_NODE_COORDS` al dataset de Bicentenario al cargar redes externas
- **Ubicación:** [src/io/data_loader.py:50-97, 368, 474](<src/io/data_loader.py#L50-L97>)
- **Qué ocurre:** tanto `load_from_excel` como `load_from_csv_dir` precargan siempre `DEFAULT_NODE_COORDS` (coordenadas fijas de los 46 nodos de Bicentenario). Si se carga un dataset diferente que use IDs numéricos como `"1"`, `"3"`, `"6"` sin `node_coords.csv`, heredará posiciones de Bicentenario en lugar de usar `_assign_missing_coordinates`.

### M8. `compute_source_inflows_by_source` ignora intervenciones en tuberías salientes de fuentes
- **Ubicación:** [src/simulation/engine.py:76-89](<src/simulation/engine.py#L76-L89>)
- **Qué ocurre:** bajo `source_distribution = "capacity"`, el peso de cada fuente usa `e.q_max_m3s` original del grafo en lugar de la capacidad efectiva `resolve_pipe_hydraulics(e, inv)[0]` si el usuario amplió o cerró una tubería saliente de fuente.

### M9. `max_stored_surcharge_m3` suma picos asíncronos y no se muestra en la comparativa
- **Ubicación:** [src/simulation/comparison.py:75](<src/simulation/comparison.py#L75>)
- **Qué ocurre:** `sum(res.max_manhole_storage_m3.values())` suma el máximo individual de cada pozo alcanzado en instantes distintos, en lugar de `max_t(snap.total_manhole_storage_m3)` (máximo simultáneo en la red), y el campo no se expone en las tablas comparativas.

### M10. `TemporalChartsPanel` omite rebose/almacenamiento y usa caudal recortado en perfil
- **Ubicación:** [src/gui/charts_panel.py:90-190, 260-336](<src/gui/charts_panel.py#L90-L190>)
- **Qué ocurre:** `ax_flow` solo grafica caudal de entrada y descarga PTAR (sin mostrar el almacenamiento en pozos ni la tasa de rebose superficial); `Perfil longitudinal` grafica `ps.flow_m3s` recortado al 115 %.

---

## 3. Discrepancias Externas del Dataset y Detalles Menores de UI / Entrega

### D1. Discrepancia en tubería `P57 (F → H)` entre Excel/CSV y Anexo 2 del PDF
- **Evidencia verificada:**
  - En la imagen de **Anexo 2** (pág. 9 del PDF de la guía), la arista `F → H` figura con capacidad **`0.19 (P57)`** (correspondiente a **16"**, `0.18829 m³/s`).
  - En `DataSetBicentenario.xlsx` (fila 54) y [data/csv/pipes.csv](<data/csv/pipes.csv>), `P57` figura con **`12"`** (`0.3048 m`, `Qmax = 0.08743 m³/s`, nota `**`).
  - Las otras **58** de 59 tuberías coinciden exactamente entre el Excel/CSV y el Anexo 2 (la suma de capacidades de entrada a PTAR `31` es `P30 (0.3414) + P3 (0.0874) = 0.4288 ≈ 0.43 m³/s`).
- **Acción:** no alterar `DataSetBicentenario.xlsx` sin autorización del docente; consultar cuál prevalece y documentar la discrepancia.

### D2. Desproporción de escala hidráulica en `DataSetBicentenario.xlsx`
- Con `A = 388.0 ha` y `C = 0.75`, el Método Racional puro genera entre **`8.09 m³/s`** (E2, 10 mm/h) y **`80.90 m³/s`** (E5, 100 mm/h), frente a una entrada a PTAR `31` de `0.4288 m³/s` (`0.43 m³/s`) y `0.4952 m³/s` totales en las 8 fuentes. Esto explica las utilizaciones de varios cientos o miles por ciento al aplicar la fórmula oficial sin atenuación (no es un bug de cálculo sino característica del dataset académico). En el mapa visual conviene abreviar etiquetas muy grandes (ej. `≥ 200%` o formato compacto) manteniendo el porcentaje exacto en inspector, tablas y reportes.

### D3. Redondeo menor al exportar CSV (`export_to_csv_dir`)
- [src/io/data_loader.py:523](<src/io/data_loader.py#L523>) redondea `q_max_m3s` a 8 decimales, introduciendo una diferencia de hasta $5 \times 10^{-9}\;\text{m}^3/\text{s}$ respecto a la fórmula del Excel original.

### D4. Detalles de UI, textos *hardcoded* y empaquetado
1. **Textos fijos sobre el 115 % y 2.5 %:** en `app.py:2544-2552` (diálogo *Supuestos*), `app.py:4296-4505` (Guía de Sustentación), [reporter.py:73](<src/simulation/reporter.py#L73>), [docx_exporter.py:539-554](<src/simulation/docx_exporter.py#L539-L554>) y [DOCUMENTACION.md](<DOCUMENTACION.md>) se describe explícitamente la cota `≤115 %` y el `2.5 %` por defecto; deberán actualizarse junto con las correcciones de E1–E4.
2. **Pruebas acopladas al comportamiento antiguo:** [tests/test_simulation.py:169-206](<tests/test_simulation.py#L169-L206>) asume `<= 115.0%` y `2.5 %` por defecto, y deberá actualizarse al corregir E1 y E2.
3. **Anchos de columnas en tablas (`tree_comp`, `tree_critical`):** ampliado y detallado como **U2** y **U3** en la Sección 4.
4. **Entrega y entorno Linux:** incluir nota sobre `python3-tk` en Linux en `README.md` y excluir `.git/`, `.dsh/`, `.impeccable/` y archivos temporales al generar el `.zip` de entrega.
---

## 4. Errores de Interfaz Gráfica y Usabilidad (Verificados en Inspección Visual)

### U1. Botones `Aguas arriba` / `Aguas abajo` del Inspector no restauran la vista al volver a hacer clic
- **Ubicación:** [src/gui/app.py:1834-1851, 3264-3268, 3455-3478](<src/gui/app.py#L1834-L1851>)
- **Qué ocurre:** En el Inspector de nodos, a diferencia de `Aislar cuenca` (`_action_toggle_basin_isolation`, que alterna encendido/apagado y cambia su estilo visual entre `primary` y `light_secondary`), los botones `Aguas arriba` y `Aguas abajo` llaman unidireccionalmente a `_trace_from_selected()` $\to$ `_run_trace()`. Si el usuario vuelve a hacer clic en el mismo botón, el resaltado no se desactiva ni restaura la vista normal del grafo.
- **Alcance obligatorio de corrección:** implementar el comportamiento *toggle* **únicamente en el Inspector** (rastreando el estado activo, ej. `_inspector_trace_mode: Optional[Tuple[str, str]]`, y restaurando con `set_highlights(set(), set())` en el segundo clic). **No modificar** los botones `Aguas abajo` / `Aguas arriba` del panel izquierdo **Recorridos**, donde la limpieza debe seguir realizándose explícitamente con el botón `Limpiar`.

### U2. Botón `Comparar 5 Escenarios` sin efecto visible y columna `Escenario` recortada en la pestaña `Comparación`
- **Ubicación:** [src/gui/app.py:2160-2177, 2253-2305, 2360-2361, 3830-3848](<src/gui/app.py#L2160-L2177>)
- **Qué ocurre:**
  1. Al entrar a la pestaña `Comparación`, `_on_tab_changed` ejecuta automáticamente `_action_compare_scenarios()` si `not self.comparisons or self._comparisons_dirty`. Como la tabla y las gráficas ya aparecen pobladas, al pulsar el botón `Comparar 5 Escenarios` recalcula exactamente los mismos datos sin ningún cambio visual ni indicación de estado, dando la impresión de ser un título estático o un botón roto.
  2. En la tabla `tree_comp`, el ancho asignado a `esc` (`ratio=0.27`) recorta los nombres largos de escenario (ej. `E3 Lluvia moderada` se corta a `E3 Lluvia moderad`, y `E5 Lluvia extrema` roza el borde derecho).
- **Qué debería hacer el botón:**
  - Reflejar explícitamente el estado de sincronización: mostrar texto/estilo neutro cuando los 5 escenarios ya están al día (ej. `Recalcular 5 Escenarios` o indicador de última actualización con tiempo de cómputo y estado `Al día`), resaltarse en `primary` / `"Recalcular 5 Escenarios *"` cuando `_comparisons_dirty == True`, y al pulsarlo forzar recálculo con feedback inmediato (barra de estado + etiqueta de hora/duración).
  - Reajustar los pesos de `_resize_comp_columns` para dar mayor holgura a `Escenario` y evitar cualquier truncamiento.

### U3. Clasificación mezclada en `Tuberías Críticas` (vs. divisiones de la guía) y columna `Estado` recortada
- **Ubicación:** [src/gui/app.py:2064-2083, 2230-2252, 3529-3540](<src/gui/app.py#L2064-L2083>), [src/algorithms/analysis.py:29-40](<src/algorithms/analysis.py#L29-L40>)
- **Qué ocurre:**
  1. El filtro `Críticas (≥75%)` de la pestaña `Tuberías Críticas` usa `min_u = 75.0` sin cota superior, por lo que mezcla tuberías en banda roja (`>75–100 %`) junto con tuberías en banda rojo oscuro (`> 100 %`), en lugar de separar estrictamente las divisiones solicitadas según [GuiaDocente.md](<GuiaDocente.md>): **`>75–100 %`**, **`> 100 %`** y **`Resto (≤ 75 %)`** (además de `Todas`).
  2. En la columna `Estado`, la etiqueta `"Capacidad excedida"` se recorta visualmente a `"Capacidad e"` por ancho insuficiente (`ratio=0.21, min=70`).
- **Corrección requerida:**
  - Reemplazar los filtros por categorías mutuamente excluyentes alineadas con la guía: `Todas`, `Resto (≤75%)`, `Críticas (>75–100%)` y `Sobrec. (>100%)` (y separar claramente en conteos/leyenda los tramos `>75–100 %` de los `>100 %`).
  - Ampliar el ancho de `Estado` en `_resize_critical_columns` y/o usar etiquetas concisas completas sin recorte (`Cap. excedida`, `Cercana máx.`, `Alta`, `Moderada`, `Baja`) para que nunca se corte texto.

### U4. Desplegable `Escenario de precipitación` abre ocasionalmente en blanco sin opciones
- **Ubicación:** [src/gui/app.py:238-243, 320-334, 649-650, 708-741, 1047-1054](<src/gui/app.py#L238-L243>)
- **Causa raíz identificada en Windows / Tk `clam` + HiDPI:**
  1. `combo_scenario` es un `ttk.Combobox(state="readonly", style="Light.TCombobox")` sobre Windows con `SetProcessDpiAwareness(1)` y tema `clam`. Al desplegar el menú, Tk crea un `Toplevel` flotante (`ComboboxPopdownFrame`).
  2. Cuando se hace clic mientras la simulación está reproduciéndose (`is_playing == True`, ticks cada `40–210 ms` con redibujo de `NetworkCanvas` / Matplotlib) o con `_resize_after_id` / `_schedule_param_rerun` pendientes, la ventana emergente `overrideredirect` pierde prioridad de pintado y queda renderizada en blanco.
  3. Al desplazarse el puntero hacia el desplegable (`Toplevel` que no es descendiente de `self.left_panel`), se dispara `<Leave>` en `left_panel` (`app.py:650`) ejecutando `unbind_all("<MouseWheel>")` justo durante el `grab` del popdown.
  4. Además, `exportselection` queda activo por defecto en el `Entry` interno del `Combobox` (dejando la selección gris residual observada en captura) y los colores del `Listbox` dependen solo de `option_add` global previo a `theme_use("clam")`.
- **Corrección requerida:** pausar reproducción al desplegar (`postcommand`), fijar `exportselection=False`, estilizar explícitamente el `Listbox` del popdown vía `ttk::combobox::PopdownWindow` (o sustituir por un selector `tk.Menubutton` / menú estilizado inmune al bug de `PopdownFrame` de `clam` en Windows), fijar `height` explícito y no ejecutar `unbind_all` mientras un popdown esté abierto.

---

## 5. Plan Técnico de Corrección Integral (Pendiente de Autorización)

> **Estado de ejecución:** Todas las correcciones de las Fases 1–5 (`E1–E4`, `M1–M10`, `U1–U4`, `D2–D4`) han sido **implementadas y verificadas** mediante la suite completa de `40/40` pruebas unitarias (`python -m unittest discover -s tests -v`). El hallazgo `D1` (`P57 = 12"`) se mantiene documentado sin modificar el Excel oficial del docente.

### Fase 1 — Motor Hidráulico y Fórmulas Oficiales (`models.py`, `engine.py`, `analysis.py`)
1. **E2 (Parámetros por defecto de la guía):** cambiar en `SimulationConfig` y variables iniciales de `app.py` a `ingress_factor = 1.0` (100 %) y `dry_weather_flow_per_source_m3s = 0.0`. Conservar `Calibrado (2.5% + Q_san)` como botón preset de sensibilidad.
2. **E1 + E4 + M1 + M3 (Utilización real sin recorte y coherencia nodo–tubería):**
   - Eliminar la curva exponencial de tope `115%` y el piso `1.05 * Qmax`.
   - Calcular `utilization_pct = (q_demand / eff_q_max) * 100.0` sin techo artificial.
   - Igualar `PipeStepState.flow_m3s = conveyed_flow_m3s` ($le Q_{\max,\text{ef}}$, garantizando $\text{node.outflow} = \sum \text{pipe.flow}$ en el 100 % de pasos) y mantener `demand_flow_m3s` como la demanda que alimenta $O_i(t)$.
   - Incluir `demand_vol / dt_sim` en `q_demand` cuando el pozo descarga almacenamiento retenido, y en tuberías cerradas al 100 % (`eff_q_max <= 1e-12`) reportar `flow_m3s = 0.0`, `utilization_pct = 0.0` (con marca `Cerrada 100%`) y omitir atribución de fuentes si el flujo es nulo.
3. **E3 + M2 (Sub-paso hidráulico continuo e integración exacta de hietograma):**
   - Integrar internamente con sub-pasos $\Delta t_{\text{sim}} \le 10\;\text{s}$ (siempre menor a $t_{\min} = 48.66\;\text{s}$ de `P54`), encadenando tiempos continuos de llegada en la `PriorityQueue` y ajustando el paso final exactamente a `duration_min`; emitir `TimeStepSnapshot` únicamente en los múltiplos del `dt_min` configurado por el usuario.
   - Reemplazar `_effective_intensity(t_curr)` por el promedio integral exacto $\frac{1}{t_b - t_a}\int_{t_a}^{t_b} I_{\text{ef}}(\tau)\,d\tau$ sobre cada sub-intervalo para hietogramas uniforme y triangular.
4. **M4 (Frontera exacta `75.0 %`):** alinear `engine.py` y `rank_critical_pipes` con [GuiaDocente.md](<GuiaDocente.md>) §7 (`> 75.0%` para Rojo / `Cercana a la capacidad máxima`, `> 100.0%` para Rojo oscuro / `Capacidad excedida`).

### Fase 2 — Validación e Ingesta de Datos (`data_loader.py`, `comparison.py`)
5. **M5 (Integridad topológica de sumideros):** en `_validate_graph_and_data`, exigir que todo nodo distinto de `sink` tenga salida (`out_degree > 0`) y que toda fuente alcance al menos un `sink`; en `engine.py`, acreditar descarga PTAR únicamente en nodos `node_type == "sink"`.
6. **M6–M7 (Consistencia CSV/Excel y coordenadas):** añadir fallback Manning y validación de coherencia `diameter_in` vs. `diameter_m` en `load_from_csv_dir`; aplicar `DEFAULT_NODE_COORDS` únicamente cuando el grafo coincida con los nodos de Bicentenario.
7. **M8–M9 (Intervenciones en fuentes y comparación):** usar `eff_q_max` en `compute_source_inflows_by_source` cuando `source_distribution == "capacity"`; calcular `max_stored_surcharge_m3` como pico simultáneo `max(s.total_manhole_storage_m3 for s in res.snapshots)`.
8. **D1 (Discrepancia `P57`):** mantener los valores de `DataSetBicentenario.xlsx` (`12"`) hasta confirmación del docente sobre si debe prevalecer el Anexo 2 (`16"`).

### Fase 3 — Correcciones de Interfaz Gráfica y Gráficas (`app.py`, `network_canvas.py`, `charts_panel.py`)
9. **U1 (Toggle `Aguas arriba` / `Aguas abajo` en Inspector):** agregar estado `_inspector_trace_state` para que el segundo clic en el mismo botón del Inspector apague el resaltado y restaure el lienzo (sin alterar la pestaña `Recorridos` del panel izquierdo).
10. **U2 (Botón y tabla de `Comparación`):** dar estado visual claro al botón (`Recalcular 5 Escenarios` / indicador de estado `Actualizado` + timestamp) y ampliar el ancho de la columna `Escenario` en `_resize_comp_columns`.
11. **U3 (Clasificación `Tuberías Críticas` y anchos):** separar filtros exclusivos `Todas`, `Resto (≤75%)`, `Críticas (>75–100%)` y `Sobrec. (>100%)`, y ampliar la columna `Estado` en `_resize_critical_columns` para eliminar el recorte `"Capacidad e"`.
12. **U4 (Desplegable `Escenario de precipitación`):** corregir el popdown en blanco pausando reproducción en `postcommand`, configurando `exportselection=False`, estilizando/refrescando el `Listbox` del popdown (o migrando a un selector `Menubutton` robusto) y protegiendo `<Leave>` de `left_panel` cuando el menú esté abierto.
13. **M10 + D2 (Gráficas y etiquetas de mapa):** añadir tasa de rebose / almacenamiento a `TemporalChartsPanel`, graficar utilización real en `ax_util` y caudal conducido vs. demanda en `Perfil longitudinal`, y compactar etiquetas >200 % sobre el mapa manteniendo el dato exacto en tablas e inspector.

### Fase 4 — Reportes, Pruebas y Entrega (`reporter.py`, `docx_exporter.py`, `tests/`, `DOCUMENTACION.md`, `README.md`)
14. Actualizar los textos de *Supuestos*, *Guía de Sustentación*, `reporter.py`, `docx_exporter.py` y [DOCUMENTACION.md](<DOCUMENTACION.md>) eliminando las menciones al tope de 115 % y reflejando el comportamiento por defecto 100 % racional.
15. Actualizar y ampliar [tests/](<tests/test_simulation.py>) para cubrir: E1 (utilización > 115 % real), E2 (Tiempo seco = 0 y Racional 100 %), E3 (invarianza frente a $\Delta t$ y llegada a PTAR $\ge 8.75\;\text{min}$), E4 (0 % discrepancia nodo–tubería), M2 (hietograma triangular en duraciones impares), M5 (rechazo de nodos muertos), U1–U3 (toggle Inspector, filtros exclusivos de críticas).
16. Añadir instrucción de `python3-tk` para Linux en `README.md` y limpiar carpetas internas antes de empaquetar el entregable final.

