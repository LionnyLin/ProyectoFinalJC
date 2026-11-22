# Documentación Técnica y Guía de Estudio — Ciudad Bicentenario

Referencia técnica y guía directa de estudio para la sustentación del **Simulador de Alcantarillado — Ciudad Bicentenario (Cartagena)** hasta la **PTAR Punta Canoa (Nodo `31`)**. Todas las cifras de este documento se obtuvieron ejecutando el código del repositorio (`wc -l`, `pytest --collect-only`, motor de simulación y exportadores).

> **Catálogo visual:** las 24 capturas están en `docs/screenshots/` (regenerables con `python scripts/capture_doc_screenshots.py`) y se incrustan en el entregable a dos columnas [`docs/DOCUMENTO_TECNICO.docx`](docs/DOCUMENTO_TECNICO.docx).

---

## 1. Resumen Ejecutivo, Métricas y Flujo de Datos Unidireccional

La aplicación sigue una arquitectura modular en capas con flujo de datos estrictamente unidireccional. Ningún módulo de dominio (`data_structures`, `io`, `algorithms`, `simulation` salvo los exportadores `charts_export.py`/`docx_exporter.py`) importa `tkinter`, y la GUI se compone de **paneles `tk.Frame` independientes** que se comunican con `BicentenarioSewerApp` (`src/gui/app.py`) mediante callbacks: `app.py` es el **único dueño del estado** (resultado, paso actual, selección, intervenciones, modo de mapa).

```text
Excel (.xlsx) / CSV ──► src/io/data_loader.py (NetworkDataset validado)
                                │
                                ▼
              src/data_structures/ (DirectedGraph: HashTable + LinkedList)
                 ├──► src/algorithms/ (BFS, DFS, Kahn, consultas O(1), trazados, ranking PQ, atribución por fuente)
                 └──► src/simulation/ (SewerSimulationEngine + PriorityQueue + intervenciones)
                                │
                                ▼
              SimulationResult (snapshots en LinkedList + picos, minutos en sobrecarga, balance de masa)
                 ├──► src/simulation/reporter.py · docx_exporter.py · charts_export.py (MD, CSV, Word, figuras)
                 └──► src/gui/app.py (Orquestador — dueño único del estado UI)
                         ├──► NetworkCanvas (2 fases, modos de mapa, pulsos, intervenciones, cámara)
                         ├──► ControlsPanel (escenario, parámetros, presets, búsqueda, BFS/DFS, bitácora Queue/Stack)
                         ├──► InspectorTab & CriticalPipesTab (intervención en vivo, composición por fuente)
                         ├──► ChartsPanel (hidrograma + perfil longitudinal) · ComparisonPanel (5 escenarios)
                         └──► GuidedTourController (recorrido guiado de 4 hallazgos)
```

### Ficha Rápida de la Red y el Dataset Oficial

- **Origen de datos:** `data/DataSetBicentenario.xlsx` y espejo CSV normalizado en `data/csv/` (`pipes.csv`, `sources.csv`, `sinks.csv`, `drainage_basin.csv`, `precipitation_scenarios.csv`, `node_coords.csv`).
- **Topología verificada:** **46 nodos** (**8 fuentes**: `1, 6, 9, 17, 18, 19, 20, 27`; **37 pozos intermedios**; **1 sumidero**: PTAR Punta Canoa `31`), **59 tuberías dirigidas**, longitud acumulada **19 163.57 m**, **DAG válido** (0 ciclos).
- **Tuberías:** diámetros comerciales `8"` a `20"` (capacidades $Q_{\max}$ de `0.02965` a `0.34140 m³/s`), $V_i \in [0.914, 1.684]\text{ m/s}$ y tiempos de tránsito $t_i \in [0.81, 18.05]\text{ min}$.
- **Cuenca y lluvia:** coeficiente de escorrentía $C = 0.75$, área $A = 388.0\text{ ha}$, **5 escenarios** ($I \in \{0, 10, 30, 60, 100\}\text{ mm/h}$).
- **Validaciones en `src/io/data_loader.py` (318 L):** columnas obligatorias (con alias tolerantes para Excel/CSV), valores numéricos positivos ($D > 0, Q_{\max} > 0, L > 0$), unicidad de `pipe_id`, existencia de fuentes/sumideros, DAG por Kahn y paridad exacta entre Excel y CSV. Nota de dataset: se conserva `P57 = 12"` (`0.08743 m³/s`) tal como figura en el `.xlsx`.

### Conteo Real de Líneas del Repositorio (`wc -l`)

| Capa / Módulo | Archivos | Líneas | Rol principal |
|:---|---:|---:|:---|
| `main.py` | 1 | 78 | Entrada GUI y modos CLI (`--data`, `--report`, `--report-docx`, `--technical-docx`) |
| `src/data_structures/` | 7 | 576 | `LinkedList`, `Queue`, `Stack`, `HashTable`, `PriorityQueue`, `DirectedGraph` |
| `src/io/` | 2 | 336 | Carga/validación Excel y CSV, coordenadas de nodos y exportación CSV |
| `src/algorithms/` | 4 | 931 | BFS/DFS (con fotogramas), Kahn, consultas `O(1)`, trazados, aislamiento, clasificación, ranking y atribución por fuente |
| `src/simulation/` | 8 | 2 095 | Modelos, motor, comparador, reporter MD/CSV, exportador Word (OMML) y figuras |
| `src/gui/` | 11 | 5 760 | Interfaz Tkinter + Matplotlib: `app`, `network_canvas`, `charts_panel`, `inspector_panel`, `controls_panel`, `guided_tour`, `comparison_panel`, `theme`, `icons`, `widgets` + `__init__` |
| `src/__init__.py` | 1 | 1 | Inicialización del paquete `src` |
| **Subtotal ejecutable (`main.py` + `src/`)** | **34** | **9 777** | **Núcleo completo de la aplicación** |
| `tests/` | 12 | 2 767 | **127 pruebas** en 11 archivos (ver §7) |
| `scripts/capture_doc_screenshots.py` | 1 | 465 | Generador de las 24 capturas |
| **Total Python** | **47** | **13 009** | **Código fuente + pruebas + script de capturas** |

Detalle de `src/gui/` (líneas): `app.py` 1 253 · `network_canvas.py` 1 255 · `charts_panel.py` 1 033 · `inspector_panel.py` 640 · `controls_panel.py` 540 · `guided_tour.py` 318 · `comparison_panel.py` 235 · `theme.py` 225 · `icons.py` 147 · `widgets.py` 109 · `__init__.py` 5.

---

## 2. Matriz de Cumplimiento del PDF (RF01–RF12, Secciones 4–14 y Nivel 5.0)

| Requisito / Sección | Alcance exigido en la guía | Implementación verificada |
|:---|:---|:---|
| **RF01 / Sec. 4 y 12** | Carga de archivos Excel (`.xlsx`) y CSV con validación | `src/io/data_loader.py` (`load_dataset`, `export_to_csv_dir`): 46 nodos, 59 tuberías, 8 fuentes, 1 sumidero (`31`), 19 163.57 m |
| **RF02 / Sec. 5.1 y 8** | Grafo dirigido y estructuras de datos propias | `src/data_structures/`: `DirectedGraph`, `LinkedList`, `Queue`, `Stack`, `HashTable`, `PriorityQueue` |
| **RF03 / Sec. 9** | Visualización del grafo respetando conexiones y coordenadas | `src/gui/network_canvas.py` (2 fases, zoom, paneo, tooltips, 3 modos de mapa, pulsos de flujo, cámara animada) |
| **RF04–RF05 / Sec. 6** | Selector de 5 escenarios + duración total, lluvia y `Δt` | `src/gui/controls_panel.py` (5 parámetros, presets, reglas) + `src/simulation/models.py::SimulationConfig` |
| **RF06 / Sec. 5.2–5.4** | Simulación temporal (Racional, tránsito `L/V`, cola de prioridad e historial) | `src/simulation/engine.py::SewerSimulationEngine` (`PriorityQueue` + `HashTable` + `LinkedList`), factor de ingreso, $Q_{\text{san}}$ e intervenciones |
| **RF07 / Sec. 7** | Escala oficial de 5 colores y leyenda | `analysis.py::classify_utilization` + `theme.py` + leyenda dinámica por modo de mapa en `app.py` |
| **RF08 / Sec. 8 y 9** | Búsqueda `O(1)` y consulta de atributos/estado temporal | `queries.py` (`search_entity`, `search_entities`, `get_pipe_details`, `get_node_details`) + `InspectorTab` |
| **RF09 / Sec. 9** | Control temporal: iniciar, pausar, reanudar, paso atrás/adelante e historial | `app.py` (reproductor, velocidades `0.5x`–`10x`, slider, atajos de teclado) sobre `snapshots` |
| **RF10 / Sec. 8 y 9** | Tabla de tuberías críticas ordenadas con `PriorityQueue` | `analysis.py::rank_critical_pipes` + `CriticalPipesTab` (4 filtros, selección bidireccional) |
| **RF11 / Sec. 10** | Comparación de los 5 escenarios hasta PTAR Punta Canoa (Nodo `31`) | `comparison.py::compare_all_scenarios` + `ComparisonPanel` + `ComparisonChartsPanel` |
| **RF12 / Sec. 6 y 13** | Reportes técnicos exportables (escenarios, tiempos, críticas, caudales, %) | `reporter.py` (Markdown + `*_tuberias.csv`), `docx_exporter.py` (Word a 2 columnas con OMML y Documento Técnico) + CLI `main.py` |
| **Sec. 8 (Algoritmos)** | BFS (`Queue`), DFS (`Stack` + camino) y animación paso a paso | `traversals.py` (`bfs`, `dfs`, `bfs_anim_frames`, `dfs_anim_frames`, `topological_sort`) + bitácora en vivo `Queue`/`Stack` |
| **Nivel Avanzado (5.0)** | `PriorityQueue`, almacenamiento en pozos, conservación de masa y visor vivo | Balance `< 1e-8 m³`, invarianza ante `Δt`, intervenciones, modos de mapa, recorrido guiado, comparación y 127 pruebas |

---

## 3. Estructuras de Datos Propias y Complejidades Big-O (`src/data_structures/`)

| Estructura (Archivo) | Diseño interno | Operaciones clave | Complejidad Big-O |
|:---|:---|:---|:---|
| **`LinkedList`** (`linked_list.py`, 149 L) | Lista doblemente enlazada con `head`, `tail`, `_size` y `DoublyLinkedNode` (`__slots__`) | `append`, `prepend`, `pop_front`, `pop_back`, `peek_*`<br>`get_at(i)` (avanza desde extremo más cercano), `remove_if` | **O(1)** extremos<br>**O(n)** acceso / borrado |
| **`Queue`** (`queue.py`, 34 L) | Cola FIFO respaldada por `LinkedList` | `enqueue` (`append`), `dequeue` (`pop_front`), `peek` | **O(1)** todas |
| **`Stack`** (`stack.py`, 34 L) | Pila LIFO respaldada por `LinkedList` | `push` (`append`), `pop` (`pop_back`), `peek` | **O(1)** todas |
| **`HashTable`** (`hash_table.py`, 128 L) | Encadenamiento separado, capacidad potencia de 2 ($2^k$), índice por máscara `hash(k) & (cap - 1)`, rehash en `0.75` | `put`, `get`, `contains`, `remove`, `setdefault`<br>**`add(key, delta)`** (incrementa en 1 sola búsqueda) | **O(1)** promedio (amort.)<br>**O(n)** peor caso |
| **`PriorityQueue`** (`priority_queue.py`, 71 L) | Min-Heap binario en arreglo con tuplas `(priority, seq, item)` — el contador `seq` da desempate FIFO determinista | `push` (`_sift_up`), `pop` (`_sift_down`)<br>`peek`, `is_empty` | **O(log n)** push / pop<br>**O(1)** peek |
| **`DirectedGraph`** (`graph.py`, 147 L) | `HashTable` para nodos (`ManholeNode`), tuberías (`PipeEdge`), `_adj` (salientes) y `_radj` (entrantes) con listas `LinkedList` | `add_node`, `add_pipe`, `get_node`, `get_pipe`, `outgoing_pipes`, `incoming_pipes`<br>`pipe_between(u, v)` | **O(1)** acceso / inserción<br>**O(deg+(u))** búsqueda arista |

**Detalles clave de implementación para la sustentación:**
- **`HashTable` potencia de 2 + `add()`:** usar capacidades $2^k$ reemplaza el módulo `%` por la operación binaria `hash(key) & self._mask`. El método `add(key, delta)` evita hacer `get()` + `put()` separados al actualizar volúmenes en tránsito y reboses miles de veces por simulación.
- **`PriorityQueue` determinista:** almacenar `(priority, self._seq, item)` impide errores de comparación cuando dos eventos empatan exactamente en tiempo y garantiza orden FIFO ante empates.
- **Uso en memoria eficiente:** `DoublyLinkedNode`, `_Entry`, `HashTable`, `PriorityQueue`, `ManholeNode`, `PipeEdge` y todos los modelos de simulación utilizan `__slots__` / `@dataclass(slots=True)`.
- **Sin atajos de librería:** una prueba AST (`tests/test_data_structures.py`) verifica que `src/data_structures` no importa `collections`, `heapq` ni `networkx`.

---

## 4. Algoritmos Implementados (`src/algorithms/`) — Complejidad y Función

| Algoritmo (`módulo::función`) | Estructura propia usada | Tiempo | Espacio | Propósito en el proyecto |
|:---|:---|:---:|:---:|:---|
| **BFS** (`traversals::bfs`, `bfs_anim_frames`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Recorrido por niveles, ruta más corta en saltos y fotogramas de animación con el contenido de la cola |
| **DFS** (`traversals::dfs`, `dfs_anim_frames`) | `Stack` + `HashTable` | $O(V + E)$ | $O(V)$ | Exploración iterativa en profundidad, reconstrucción de camino y fotogramas con frente activo y backtracking |
| **Kahn** (`traversals::topological_sort`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Orden topológico para el motor y verificación DAG (46/46 nodos) |
| **Búsqueda** (`queries::search_entity`, `find_node`, `find_pipe`) | `HashTable` (grafo) | $O(1)$ | $O(1)$ | Localización instantánea de cualquier pozo o tubería por ID exacto |
| **Búsqueda parcial** (`queries::search_entities`) | Recorrido de `node_ids`/`pipe_ids` | $O(V + E)$ | $O(k)$ | Respaldo por subcadena en id, etiqueta, tipo y extremos de tubería |
| **Trazado** (`queries::trace_downstream`, `trace_upstream`, `trace_upstream_result`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Ruta hacia PTAR `31` (`outgoing_pipes`) o cuenca aportante (`incoming_pipes`) con fotogramas |
| **Aislamiento** (`queries::find_isolated_from_sinks`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Nodos y tramos que quedan sin camino a la PTAR al cerrar tuberías |
| **Ruta al sumidero** (`queries::build_route_to_sink`) | `HashTable` + recorrido | $O(V + E)$ | $O(V)$ | Ruta dirigida usada por el perfil longitudinal |
| **Clasificación** (`analysis::classify_utilization`) | Tupla inmutable de 5 niveles | $O(1)$ | $O(1)$ | Asigna color oficial y banderas `is_critical` (>75%) / `is_overloaded` (>100%) |
| **Persistencia** (`analysis::classify_overload_persistence`) | Tupla de 5 niveles | $O(1)$ | $O(1)$ | Clasifica los minutos acumulados en sobrecarga: `0 min`, `≤25 %`, `≤50 %`, `≤75 %`, `>75 %` de la duración |
| **Ranking** (`analysis::rank_critical_pipes`) | `PriorityQueue` | $O(E \log E)$ | $O(E)$ | Ordena tuberías de mayor a menor utilización con desempate por razón de demanda $\times Q_{\max}$ |
| **Atribución** (`analysis::compute_source_attribution`) | `Queue` + `HashTable` (orden topológico) | $O(F \cdot (V + E))$ | $O(F \cdot V)$ | Porcentaje con que cada una de las $F = 8$ fuentes aporta a cada pozo y tubería |

- **Escala oficial de 5 niveles (Sección 7 del PDF):** `0–25%` (`#22c55e`, *Baja*), `>25–50%` (`#eab308`, *Moderada*), `>50–75%` (`#f97316`, *Alta*), `>75–100%` (`#ef4444`, *Cercana a capacidad máxima*) y `>100%` (`#991b1b`, *Capacidad excedida*). La frontera es estricta (`U > 75.0`, `U > 100.0`).
- **Conjuntos separados:** `near_capacity_pipe_ids` (`>75–100 %`), `overloaded_pipe_ids` (`>100 %`) y `critical_pipe_ids` (unión). En el Escenario 3 (90 min): 19 tuberías estuvieron en `>75–100 %`, 15 superaron `100 %` y la unión crítica es de 21.
- **Reconstrucción de caminos en BFS/DFS:** ambos registran una `HashTable` de padres y reconstruyen el camino hacia atrás desde `target_id` en $O(V)$, grabando además `TraversalFrame` (visitados, actual, arista activa, frente activo y nodos/aristas con backtracking del DFS).

---

## 5. Modelo Hidráulico y Supuestos Documentados (Sección 11)

Todos los supuestos coinciden con `MODEL_ASSUMPTIONS_TEXT` (`src/simulation/reporter.py`) y `SewerSimulationEngine` (`src/simulation/engine.py`, 317 L):

1. **Escorrentía por Método Racional con ingreso y caudal sanitario:**
   $$Q_{\text{lluvia}} = 0.00278 \cdot C \cdot I \cdot A \cdot f_{\text{ing}}, \qquad Q_{\text{in},s} = Q_{\text{lluvia}} \cdot w_s + Q_{\text{san}}$$
   con $C = 0.75$, $A = 388.0\text{ ha}$ ($0.00278 \cdot C \cdot A = 0.80898\text{ m}^3/\text{s}$ por mm/h; p. ej., $24.2694\text{ m}^3/\text{s}$ para $30\text{ mm/h}$ con $f_{\text{ing}} = 1$). El **factor de ingreso** $f_{\text{ing}}$ (`100 %` oficial por defecto, `0.5–100 %`) y el **caudal sanitario** $Q_{\text{san}}$ por fuente (`0.000 m³/s` por defecto, hasta `0.05`) se configuran en la GUI; los presets son `Oficial Guía (100%)` ($f_{\text{ing}} = 1$, $Q_{\text{san}} = 0$) y `Calibrado (2.5% + Q_san)` ($f_{\text{ing}} = 0.025$, $Q_{\text{san}} = 0.003\text{ m}^3/\text{s}$). La lluvia es un bloque **uniforme** durante `storm_duration_min` (`60 min` por defecto dentro de `90 min`); $Q_{\text{san}}$ se inyecta durante toda la simulación. La API pública `compute_source_inflows_by_source(config, intensity)` devuelve el caudal total y por fuente.
2. **Capacidad $Q_{\max}$ exacta del dataset:** se lee de `DataSetBicentenario.xlsx` / `pipes.csv` (Manning a tubo lleno en el archivo oficial) sin recalcularla; solo si falta o es $\le 0$ el cargador aplica $Q_{\max} = \tfrac{1}{n} A \left(\tfrac{D}{4}\right)^{2/3} S^{1/2}$.
3. **Velocidad y tiempo de tránsito con `PriorityQueue` (sin teletransporte):** para cada tubería $i$, $A_i = \pi D_i^2 / 4$, $V_i = Q_{\max,i} / A_i$ y $t_i = L_i / V_i$. Todo volumen despachado pasa a `pipe_transit_vol` y se agenda en `event_queue` para arribar en $t + t_i$. La ruta más corta a la PTAR `31` es `27 -> C -> 31` (**8.75 min**; con $\Delta t = 1\text{ min}$ la descarga es `0.0` hasta $t = 9$ y aparece en $t = 10\text{ min}$). Los subpasos internos son adaptativos: $\Delta t_{\text{sim}} \le \min(\Delta t_{\text{usuario}}, 0.35 \cdot \min t_i)$ acotado a `[1, 15] s`.
4. **Distribución en fuentes y bifurcaciones:**
   - **Fuentes (`source_distribution`):** `"capacity"` (ponderada por $\sum Q_{\max,\text{ef}}$ saliente, por defecto; $w_{20} = 0.02965436/0.49522283 = 5.9881\%$) o `"equal"` ($1/8$ uniforme).
   - **Bifurcaciones (`split_rule`):** `"proportional"` (ponderada por $Q_{\max,\text{ef}}$ saliente, por defecto) o `"equal"` ($1/k$).
5. **Intervenciones por tubería (`PipeIntervention`):** obstrucción `0–100 %` y/o diámetro comercial nuevo. `resolve_pipe_hydraulics()` aplica las leyes de escala de Manning sin mutar el grafo base:
   $$\text{scale}_D = \frac{D_{\text{ef}}}{D}, \quad Q_{\text{diam}} = Q_{\max}\,\text{scale}_D^{8/3}, \quad V_{\text{ef}} = V\,\text{scale}_D^{2/3}, \quad Q_{\max,\text{ef}} = Q_{\text{diam}}\,\max\!\left(0,\, 1 - \tfrac{p_{\text{obst}}}{100}\right), \quad t_{\text{ef}} = \frac{L}{V_{\text{ef}}}$$
   Con `100 %` la tubería queda **cerrada** ($Q_{\max,\text{ef}} = 0$, `is_closed`), y `find_isolated_from_sinks` calcula los nodos/tramos incomunicados de la PTAR. Ejemplo (Esc. 3, `P29`): al `80 %` el pico en la PTAR cae de `0.3078` a `0.1557 m³/s`; al `100 %` queda en `0.0874 m³/s` con `41` nodos y `54` tramos aislados.
6. **Gestión conservativa de sobrecargas y balance de masa exacto:**
   - Conducción física limitada a $Q_{\text{cond}} = \min(Q_{\text{demanda}}, Q_{\max,\text{ef}})$.
   - Utilización reportada $O_i(t) = (Q_{\text{demanda}} / Q_{\max,\text{ef}}) \times 100$ **sin techo artificial** (permite detectar $>100\%$; la razón $\times Q_{\max}$ es $O_i/100$). En tuberías cerradas $O_i = 0\%$ y toda la demanda es exceso.
   - El volumen excedente se retiene primero en el pozo hasta `max_manhole_storage_m3` (**4.0 m³** por defecto) y el remanente pasa a **rebose superficial** acumulado, que no reingresa a la red.
   - **Balance de masa exacto verificado en cada paso:**
     $$V_{\text{in}} = V_{\text{PTAR}} + V_{\text{pozos}} + V_{\text{tránsito}} + V_{\text{rebose}} \quad (\text{error} < 10^{-8}\text{ m}^3)$$
7. **Métricas globales del resultado:** `peak_pipe_utilization`, `peak_pipe_demand_ratio`, `peak_pipe_demand_flow`, `pipe_overloaded_minutes` (minutos con $O_i > 100\%$, base de la persistencia y del modo `Minutos en Sobrecarga`) y `max_node_flooding_m3`.

### Ciclo de Ejecución de Cada Subpaso Interno (`SewerSimulationEngine.run`)

1. **Preparación:** resuelve la hidráulica efectiva por tubería (`resolve_pipe_hydraulics`), construye la tabla plana de aristas salientes `(índice, id, destino, Qmax, tránsito, peso, desfase)` en orden topológico y precalcula el calendario de pasos/subpasos.
2. **Llegadas programadas:** extrae de `event_queue` (`PriorityQueue`, un evento por *slot* temporal) todos los lotes con `t_llegada <= t1_s`, descuenta `pipe_transit_vol` (`HashTable.add`) y suma el volumen al nodo destino.
3. **Inyección:** distribuye el volumen de lluvia (si `t0_s < storm_s`) y el sanitario entre las 8 fuentes según `source_distribution`.
4. **Barrido topológico (Kahn):** recorre los nodos con aportes o volumen almacenado. Si es sumidero (`31`) descarga a la PTAR; si no, reparte `avail = stored + arr` entre sus tuberías salientes según `split_rule`, limita cada envío a `q_max * sub_dt_s`, agenda su llegada, retiene el excedente en el pozo hasta `4.0 m³` y contabiliza el sobrante como rebose.
5. **Consolidación de instantánea:** al cierre de cada $\Delta t$ del usuario calcula $Q_{\text{dem}}$ (invariante a $\Delta t$ mediante la escala fija `_DRAIN_SCALE_S = 60 s`), clasifica las 59 tuberías, acumula minutos en sobrecarga, calcula `mass_balance_error_m3` y guarda `TimeStepSnapshot` en `self.history` (`LinkedList`).

### Resultados de Referencia — 5 Escenarios (`duration=90 min`, `storm=60 min`, `dt=1 min`, `f_ing=100 %`, `Q_san=0`)

| Esc. | Condición | $I$ (mm/h) | Util. Máx. (%) | Tubería crítica | >75–100% / >100% | Pico PTAR 31 | Rebose (m³) | Error masa (m³) |
|:---:|:---|---:|---:|:---:|:---:|---:|---:|---:|
| 1 | Tiempo seco | 0.0 | 0.00 % | — | 0 / 0 | 0.0000 m³/s | 0.00 | `0.00e+00` |
| 2 | Lluvia ligera | 10.0 | 1 858.38 % | `P31` | 19 / 15 | 0.3078 m³/s | 27 885.86 | `6.00e-10` |
| 3 | Lluvia moderada | 30.0 | 5 125.52 % | `P31` | 19 / 15 | 0.3078 m³/s | 86 132.42 | `1.35e-09` |
| 4 | Lluvia fuerte | 60.0 | 10 026.22 % | `P31` | 19 / 15 | 0.3078 m³/s | 173 502.26 | `1.85e-09` |
| 5 | Lluvia extrema | 100.0 | 16 560.49 % | `P31` | 19 / 15 | 0.3078 m³/s | 289 995.38 | `3.26e-09` |

*(El pico en la PTAR 31 satura en `0.3078 m³/s`, suma física exacta de $Q_{\max}$ de las tuberías que descargan en el Nodo 31.)* Con el preset **Calibrado** (`2.5 %` + `0.003 m³/s`) la respuesta es gradual: utilización máxima `10.25 %`, `198.32 %`, `357.45 %`, `479.96 %` y `643.32 %` (Esc. 1–5), tuberías en `>75–100 %` `0/1/19/19/19`, sobrecargadas `0/1/15/15/15` (unión crítica `0/1/21/21/21`), pico PTAR `0.0240/0.2070/0.3078` m³/s y rebose `0.00/46.26/1 034.35/3 218.60/6 130.92 m³`.

**Rendimiento medido:** ≈ 36 ms por escenario de 90 min (91 instantáneas; ≈ 8 ms el tiempo seco) y ≈ 156 ms los 5 escenarios (`compare_all_scenarios`).

### Ejemplo Numérico Verificado (Esc. 3, $t = 30\text{ min}$, configuración oficial)

- **Nodo `20` (fuente):** $Q_{\text{in}} = 24.2694 \cdot 0.0598808 + 0 = 1.45327\text{ m}^3/\text{s}$; $Q_{\text{out}} = Q_{\text{cond},P39} = 0.029654\text{ m}^3/\text{s}$; `Vol. en pozo = 4.000 m³`; `Rebose = 2 558.51 m³`.
- **Tubería `P39`** ($20 \to B$, `8"`, $L = 222.21\text{ m}$, $V = 0.9144\text{ m/s}$, $t = 243.0\text{ s}$): demanda $1.5199\text{ m}^3/\text{s}$, utilización $1.5199/0.029654 \times 100 = 5\,125.52\%$ (`51.26×`), `7.56 m³` en tránsito.
- **Resumen del escenario:** entrada acumulada `43 684.92 m³`; descarga PTAR `87.49 m³`; pozos / tránsito `44.74 / 707.53 m³`; rebose `42 845.17 m³`; error de balance global `1.353e-09 m³`. Verificación: $87.486 + 44.736 + 707.531 + 42\,845.166 = 43\,684.920\text{ m}^3$.

---

## 6. Arquitectura GUI Tkinter (`src/gui/` — 11 archivos, 5 760 L)

### 6.1 Sistema Visual y Layout Responsivo

- **Sistema visual (*Lámina Cartográfica de Archivo Hidráulico*, `theme.py`):** paleta editorial de 4 tonos base — Grafito `#4A4A4A` (barra superior y KPIs), Plata Mineral `#CBCBCB` (dock lateral y separadores), Marfil Vitela `#FFFFE3` (lienzo y fichas) y Azul Pizarra `#6D8196` (acento primario) — reservando el color saturado para la escala hidráulica de 5 niveles. Fuente local `Inter` (`assets/fonts/`), escala DPI y DPI awareness en Windows.
- **Iconos (`icons.py`):** `build_icon_set()` dibuja con Pillow a mayor resolución y reduce (supermuestreo) los iconos de marca, reproductor, búsqueda, paneles y acciones.
- **Franjas globales:** barra superior (insignia, título, toggles `Controles` / `Análisis`, menú `Archivo y Modelo`, exportaciones y `Recorrido guiado`), área principal en un `tk.PanedWindow` (panel izquierdo, centro, notebook derecho) y barra de estado inferior con el mensaje vigente y la pista de atajos.
- **Breakpoints (`theme.py`):** `wide` (≥ 1 220 px), `medium` (940–1 219 px) y `compact` (< 940 px). Con ≥ 1 660 px las acciones de archivo se muestran como botones individuales; por debajo se agrupan en `Archivo y Modelo`. En `compact` el subtítulo se oculta, los textos se acortan (`Ciudad Bicentenario`, `Archivo`, `Guía Esc. N`), los paneles izquierdo y derecho son **mutuamente excluyentes** y la pista de atajos se oculta bajo 980 px.
- **Atajos (`app.py`):** `Espacio` reproducir/pausar, `←`/`→` paso, `Inicio` volver a `t = 0`, `Ctrl+F` abrir la búsqueda, `Esc` limpiar (recorrido, cuenca, foco, recorrido guiado); se ignoran al escribir en `Entry`, `Spinbox` o `Text`.

### 6.2 Paneles Desacoplados

1. **`controls_panel.py` (540 L) — panel izquierdo con pestañas `Simulación` / `Recorridos`** y scroll con rueda acotado y scrollbar auto-oculta:
   - *Escenario y parámetros:* selector de escenario (`_ScenarioMenuButton`, `Menubutton` + `Menu`, inmune al bug de popdown de Windows), 5 `Spinbox` — Duración `10–360` (default `90`), Lluvia `0–360` (`60`), $\Delta t$ `0.5–10` (`1.0`), Ingreso pluvial `0.5–100 %` (`100`) y Caudal sanitario `0–0.05 m³/s` (`0.000`) — con re-simulación automática con *debounce* de `140 ms`; presets `Oficial Guía` / `Calibrado`; selectores `Bifurcación` (`Proporcional` | `Equitativa`) y `Reparto fuentes` (`Por capacidad` | `Uniforme (1/8)`); botón `Ejecutar simulación` (con auto-reproducción).
   - *Búsqueda y recorridos:* buscador (ID exacto `O(1)` y respaldo por subcadena, con feedback de error), nodos `Inicio`/`Destino`, `BFS`, `DFS`, `Limpiar`, `Animar recorrido` (`560 ms` BFS, `340 ms` DFS), `Aguas abajo` y `Aguas arriba` con colores distintos para cada modo.
   - *Bitácora de recorrido:* tira de la estructura activa (primeros 6 elementos; `Cola (Queue) · FRENTE → FINAL` o `Pila (Stack) · TOPE ↑`, cabeza resaltada) y caja de texto con el registro (visitados, ruta, tránsito acumulado).
2. **Centro (`app.py`, `network_canvas.py`):**
   - *Cabecera KPI:* píldora de contexto (`t = X / 90 min · Escenario`, `Pico 0–90m` o `Sobrecarga 0–90m`), casillas `IDs` / `% Util.` y 4 tarjetas KPI sincronizadas con el modo: `Instantáneo O(t)` → `UTILIZACIÓN MÁX.`, `CRÍTICAS (>75–100%)`, `SOBRECARGA (>100%)`, `DESCARGA PTAR 31`; `Pico Máximo` → picos globales; `Minutos en Sobrecarga` → `MÁX. SOBREC. ACUM.`, `TUBERÍAS >0 min >100%`, `COLAPSO CRÓNICO (>75%)`, `VOLUMEN PTAR 31`.
   - *Selector de modo cartográfico:* `Instantáneo O(t)` / `Pico Máximo` / `Minutos en Sobrecarga`. Los dos últimos son **vistas globales congeladas** (`0–duración total`): pausan la reproducción, usan los resultados completos del motor (`peak_pipe_utilization`, `pipe_overloaded_minutes`) y conservan `current_step`, que se restaura al volver a `Instantáneo` o al navegar en el tiempo. La leyenda de la barra superior muestra conteos por banda y cambia según el modo (`Escala oficial · t = X min`, `Pico máximo · 0–X min`, `Sobrecarga acumulada · 0–X min`).
   - *Reproductor:* `Inicio` (`Inicio`), `-1`, `Reproducir/Pausar`, `+1`, velocidades `0.5x`/`1x`/`2x`/`5x`/`10x` (`840/420/210/85/40 ms`), slider robusto, indicador `Masa OK · Err …` y auto-reproducción al ejecutar.
   - *Lienzo en dos fases:* **Fase A** (`rebuild_geometry`) crea todos los ítems (incluidos los auxiliares ocultos: halos, anillos de rebose, pulsos, barras de obstrucción) solo al cargar, hacer zoom/paneo, redimensionar (*debounce* `80 ms`) o cambiar la forma por una intervención; **Fase B** (`update_visuals`) usa solo `itemconfigure`/`coords` sin borrar ítems. Zoom `0.55–4.5×` con rueda, arrastre para paneo, doble clic para ajustar, barra de zoom `+ − ⟲`, sello de título del mapa y barra de pistas; tooltips con diámetro, $Q$, $Q_{\max}$ efectivo, demanda $\times Q_{\max}$ y rebose; etiquetas sin colisión y radio de nodo responsivo.
   - *Visuales del modelo:* pulsos de flujo animados durante la reproducción (velocidad proporcional a la velocidad efectiva y al factor de reproducción), anillos de rebose/almacenamiento, halo de sobrecarga, doble línea al ampliar el diámetro (`[ØXX"]`), barras de obstrucción (`[OBST XX%]`), `×` de cierre, nodos y tramos aislados punteados (`[AISLADO DE 31]`), insignias `Fuente` y `PTAR Punta Canoa · 31`, atenuación para foco de cuenca y de recorrido, y cámara animada (`animate_focus_region`, `animate_reset_view`, `focus_node`, `focus_pipe`).
3. **`inspector_panel.py` (640 L) — pestañas `Inspector` y `Tuberías Críticas`:**
   - *Inspector:* barra de acciones (`Centrar`, `Aislar cuenca`, `Aguas arriba` / `Aguas abajo` como *toggles* para nodos), ficha técnica de pozo o tubería (incluye `Qmax` efectivo y base, caudal conducido, demanda retenida, estrés `>100 %` en minutos con su persistencia), tarjeta **`Intervención en vivo`** (obstrucción `0–100 %` en pasos de `5`, diámetro `Original` + comerciales `6"…48"`, `Aplicar y re-simular`, `Restaurar tramo`, `Restaurar red`; conserva el resultado base para `Antes / Después`), tarjeta **`Composición por Fuente Aportante`** (barra apilada monocromática + porcentajes de `compute_source_attribution`) y bloque `RESUMEN DEL ESCENARIO`.
   - *Tuberías Críticas:* filtros `Todas`, `Resto (≤75%)`, `Críticas (>75–100%)` y `Sobrec. (>100%)`, ranking con `Q`, `Qmax`, utilización, razón $\times Q_{\max}$ y estado, selección bidireccional con el grafo y doble clic para centrar la cámara.
4. **`charts_panel.py` (1 033 L) — pestaña `Evolución`:**
   - *`Hidrograma y %`:* entrada total, descarga en PTAR `31` con relleno, curva `Antes` tras una intervención, cursor vertical de tiempo, utilización de la tubería seleccionada (o top 3 críticas), línea del `100 %`, eje *symlog* con marcas dinámicas, doble eje y banner de impacto de la intervención.
   - *`Perfil longitudinal`:* ruta hacia la PTAR con `build_route_to_sink` (o la ruta del último recorrido con destino) y barras de utilización coloreadas por banda, con modos `% Uso vs Cap. (100%)` y `Caudal (m³/s)` (Qmax vs $Q(t)$) y nota de cuello de botella.
   - *Rendimiento:* si la pestaña está oculta marca `_dirty` y no redibuja; el cursor temporal actualiza solo el trazo (*throttle* `80 ms`) y el perfil se redibuja con *throttle* de `140 ms`.
5. **`comparison_panel.py` (235 L) — pestaña `Comparación`:** botón `Recalcular 5 Escenarios` con estado *dirty* y pista con hora y duración del cálculo (se recalcula automáticamente al entrar si hay cambios), tabla de **9 columnas** (`Escenario`, `mm/h`, `Máx %`, `Razón Máx`, `Crítica`, `>75–100%`, `>100%`, `Pico PTAR`, `Rebose (m³)`) con scroll horizontal y vertical (y `Shift`+rueda), doble clic para activar el escenario en la simulación principal, y `ComparisonChartsPanel` con selector de métrica (`Rebose (m³)` / `PTAR 31 (m³/s)`) y reflujo de diseño `2×1` / `1×2` según el espacio.
6. **`guided_tour.py` (318 L) — recorrido guiado:** 4 hallazgos por escenario en `t = 5, 25, 40 y 65 min` (en el Esc. 2 la tercera parada usa el instante de máxima exigencia de `P25`) con ficha flotante (título, descripción, métricas calculadas del `SimulationResult`, `Anterior` / `Siguiente hallazgo` / `Cerrar`), foco con atenuación del resto del grafo y cámara animada que reserva el ancho de la ficha. Se cierra al reproducir, al cambiar de modo de mapa, con `Esc` o al ejecutar con auto-reproducción; al cambiar de escenario con el recorrido abierto se recalculan las paradas.
7. **`app.py` (1 253 L):** `BicentenarioSewerApp` ensambla los paneles, mantiene el estado único y coordina simulación, línea base para `Antes / Después`, aislamiento por cierres, composición por fuente (con *throttle* durante la reproducción), caché de comparativa invalidable, exportaciones y el diálogo `Supuestos del Modelo`.

### 6.3 Exportación de Reportes RF12, Documento Técnico y CLI (`main.py`, 78 L)

- **Markdown + CSV hermano (`reporter.py`, 185 L):** reporte estructurado (escenario, supuestos incluida la nota de `P57`, factor de ingreso, $Q_{\text{san}}$, intervenciones activas, métricas globales hasta PTAR `31`, Top 25 de tuberías con columna `Razón Qmax` y comparativa de los 5 escenarios) junto con `<nombre>_tuberias.csv` (59 tuberías, incluye `peak_demand_factor`).
- **Word a dos columnas con ecuaciones OMML (`docx_exporter.py`, 890 L; `omml_equations.py`, 171 L):** `generate_docx_report` crea el reporte con `python-docx` y `lxml` (sin Pandoc) con ecuaciones nativas editables en Word y figuras a una columna; `generate_technical_document_docx` genera el **Documento Técnico** completo con Anexos A–D, figuras y las capturas de `docs/screenshots/`.
- **Figuras (`charts_export.py`, 233 L):** `python -m src.simulation.charts_export` produce `fig1_hidrograma_ptar.png`, `fig2_top5_utilizacion.png` y `fig3_comparacion_escenarios.png` a `3.5 × 2.8 in` en `docs/figuras/`.
- **Comandos CLI desde `main.py`:**
  ```bash
  python main.py --data data/DataSetBicentenario.xlsx
  python main.py --data data/csv
  python main.py --report docs/REPORTE_ESCENARIOS.md --report-docx docs/REPORTE_ESCENARIOS.docx
  python main.py --technical-docx docs/DOCUMENTO_TECNICO.docx
  ```
- **Capturas (`scripts/capture_doc_screenshots.py`, 465 L):** abre la app real, reproduce los 24 estados de la documentación y captura con `PrintWindow` (Windows) o ImageMagick (`import -window`, Linux/X11); las tres tarjetas de terminal (`04_1`, `04_2`, `04_3`) ejecutan de verdad la exportación CSV, el CLI y la suite de pruebas. Orden de regeneración: figuras → reportes → capturas → `--technical-docx`.

---

## 7. Verificación y Suite de Pruebas Automatizadas (`tests/` — 127 Pruebas, 2 767 L)

La calidad funcional y numérica se verifica con `python -m pytest -q` (o `python -m unittest discover -s tests -v`). Las pruebas de GUI abren ventanas Tk reales y se omiten sin display.

| Archivo de pruebas | Pruebas | Qué valida |
|:---|---:|:---|
| `tests/test_data_structures.py` | 5 | CRUD, colisiones y rehash potencia de 2 en `HashTable` (incl. `add()`), `LinkedList`/`Queue`/`Stack`, `PriorityQueue` determinista, `DirectedGraph` y ausencia AST de `collections`/`heapq`/`networkx` |
| `tests/test_loader.py` | 4 | Paridad exacta `.xlsx` vs. `data/csv/`, round-trip CSV, filas en blanco, rechazo `DataLoadError` (ciclos, dead-ends, IDs duplicados, diámetros inconsistentes, NaN) |
| `tests/test_algorithms.py` | 10 | BFS/DFS desde las 8 fuentes a PTAR `31`, fotogramas (cola/pila y backtracking), Kahn, búsqueda `O(1)` y por subcadena, trazados, aislamiento, ruta al sumidero, escala de 5 colores, ranking con desempate, atribución por fuente y persistencia de sobrecarga |
| `tests/test_simulation.py` | 13 | Método Racional (incl. `I=0`), retardo físico e invarianza ante `Δt`, intervenciones, factor de ingreso y $Q_{\text{san}}$, API de caudales por fuente, minutos en sobrecarga, reglas de bifurcación/reparto, conservación de masa y rendimiento |
| `tests/test_docx_exporter.py` | 3 | Figuras a una columna con dimensiones exactas (`3.5 × 2.8 in`), Word a dos columnas con OMML, Documento Técnico y marcas *symlog* |
| `tests/test_canvas.py` | 16 | Lienzo en 2 fases (guardia de rendimiento de la Fase B), modos de mapa, foco de cuenca y de recorrido, intervenciones visuales y aislados, anillos de rebose, tooltips, insignias, etiquetas sin colisión, pulsos y cámara |
| `tests/test_charts_panels.py` | 13 | Hidrograma, perfil longitudinal, actualización diferida, cursor, comparación y reflujo |
| `tests/test_gui.py` | 25 | Tema y escala oficial, humo integral de `BicentenarioSewerApp`, layout responsivo y *toggles* de paneles, atajos (incluida su omisión al escribir), parámetros y presets, velocidades del reproductor, recorridos aguas arriba/abajo con bitácora, iconos y regresiones de selección |
| `tests/test_gui_inspector.py` | 17 | Búsqueda, inspector, intervención en vivo, composición por fuente y filtros críticos |
| `tests/test_gui_modes.py` | 13 | Modos de mapa, KPI y leyenda por modo, pausa y restauración del paso, pulsos de flujo, backtracking del DFS hacia el lienzo, ruta activa en el perfil y comparación *dirty* |
| `tests/test_gui_tour.py` | 8 | Recorrido guiado: ficha, paradas por escenario, navegación, cierre con `Esc` y recálculo al cambiar de escenario |
| **Total** | **127** | `python3 -m pytest -q --collect-only` |

---

## 8. Guía Rápida de Preguntas Típicas de Sustentación

1. **¿Por qué implementaron estructuras propias si Python ya trae `dict`, `list` y `heapq`?**
   Porque el proyecto (RF02) exige diseñar y dominar las estructuras desde cero. Implementamos `LinkedList` doblemente enlazada (base de adyacencias, `Queue`, `Stack` e historial), `HashTable` potencia de 2 con máscara de bits y `add()` en una búsqueda, y `PriorityQueue` Min-Heap binario determinista con `seq`. Así garantizamos `O(1)` en consultas y `O(log n)` en eventos sin cajas negras, y una prueba AST impide importar `collections`/`heapq`.

2. **¿Por qué usan una `PriorityQueue` en la simulación y no una `Queue` FIFO normal?**
   Porque cada tubería tiene longitud $L_i$ y velocidad $V_i$ distintas, por lo que su tiempo de tránsito $t_i = L_i/V_i$ varía entre tramos. Un paquete enviado después por una tubería corta puede llegar antes que uno enviado antes por una tubería larga. El Min-Heap ordena los arribos por tiempo de llegada en $O(\log n)$ y además construye el ranking de tuberías críticas en $O(E \log E)$.

3. **¿Por qué el agua no se teletransporta hasta la PTAR 31 en `t = 0`?**
   Porque el motor modela el retardo físico de viaje: al despachar volumen por la tubería $i$, se registra en `pipe_transit_vol` y se agenda en `event_queue` para $t + L_i/V_i$. Por eso la PTAR 31 permanece en `0 m³/s` durante los primeros **8.75–10 min** (ruta mínima `27 -> C -> 31`) y responde progresivamente conforme llegan las ondas desde las 8 fuentes.

4. **¿Cómo garantizan la conservación de masa cuando hay sobrecargas mayores al 100 %?**
   Ninguna tubería conduce más que su capacidad física $Q_{\max,\text{ef}} \cdot \Delta t_{\text{sub}}$. El exceso no se pierde: primero llena el almacenamiento temporal del pozo (hasta `4.0 m³`) y cualquier excedente se suma al rebose superficial. En cada paso se comprueba $|V_{\text{in}} - (V_{\text{PTAR}} + V_{\text{pozos}} + V_{\text{tránsito}} + V_{\text{rebose}})| < 10^{-8}\text{ m}^3$ (máximo observado: `3.26e-09 m³` en el Esc. 5).

5. **¿Por qué la utilización supera el 100 % si el flujo conducido se limita a $Q_{\max}$?**
   Porque distinguimos el **caudal conducido** $Q_{\text{cond}} \le Q_{\max}$ (agua que realmente avanza aguas abajo) del **caudal demandado** $Q_{\text{demanda}}$ (aportes entrantes + presión del agua retenida en el pozo). Mostrar $O_i(t) = (Q_{\text{demanda}}/Q_{\max}) \times 100$ sin tope artificial permite identificar qué tramos colapsan más severamente (como `P31`, `51.26×` en el Esc. 3).

6. **¿Qué hace una intervención y cómo se mantiene el grafo intacto?**
   `PipeIntervention` (obstrucción y/o diámetro) vive en `SimulationConfig.interventions`. El motor llama a `resolve_pipe_hydraulics`, que aplica las leyes de escala de Manning ($Q \propto D^{8/3}$, $V \propto D^{2/3}$) y el factor de apertura, sin modificar el `DirectedGraph`. La GUI conserva el resultado sin intervenciones para graficar `Antes / Después` y recalcula los tramos/nodos aislados de la PTAR cuando hay cierres totales.

7. **¿Para qué sirven el factor de ingreso y el caudal sanitario?**
   El Método Racional puro (`100 %`) satura una red de conducción sanitaria pequeña ($Q_{\max} \le 0.34\text{ m}^3/\text{s}$ frente a $24\text{ m}^3/\text{s}$ de lluvia a 30 mm/h). El preset `Calibrado` (`2.5 %` + `0.003 m³/s` por fuente) representa infiltración y conexiones erradas y produce una respuesta gradual entre escenarios (utilización máxima de `10.25 %` a `643.32 %`), mientras que `Oficial Guía` replica la formulación de la guía.

8. **¿Cómo logran un rendimiento tan rápido tanto en el motor como en Tkinter?**
   En el motor (≈ 36 ms por escenario de 90 min, ≈ 156 ms los cinco): orden topológico y tablas planas de adyacencia precalculados, agrupación de eventos por *slot* temporal en `PriorityQueue` y `HashTable.add()` en un solo lookup. En la GUI: lienzo en 2 fases (`itemconfigure` sin borrar ítems), pestañas ocultas marcadas como *dirty* sin redibujar, cursor temporal ligero en `ChartsPanel`, composición por fuente con *throttle* durante la reproducción y *debounce* de `140 ms` al editar parámetros.

9. **¿Cómo se organiza la GUI y quién es dueño del estado?**
   Cada panel (`ControlsPanel`, `InspectorTab`, `CriticalPipesTab`, `ChartsPanel`, `ComparisonPanel`, `GuidedTourController` y `NetworkCanvas`) es un componente independiente que recibe callbacks y empuja eventos; `BicentenarioSewerApp` mantiene el único estado (resultado, paso, selección, intervenciones, modo de mapa) y distribuye las actualizaciones, lo que facilita probar cada panel por separado (127 pruebas).
