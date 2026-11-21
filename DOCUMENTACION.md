# Documentación Técnica y Guía de Estudio — Ciudad Bicentenario

Referencia técnica concisa y guía directa de estudio para la sustentación del **Simulador de Alcantarillado — Ciudad Bicentenario (Cartagena)** hasta la **PTAR Punta Canoa (Nodo `31`)**.

---

## 1. Resumen Ejecutivo, Métricas y Flujo de Datos Unidireccional

La aplicación sigue una arquitectura modular en capas con flujo de datos estrictamente unidireccional. Ningún módulo de dominio (`data_structures`, `io`, `algorithms`, `simulation`) importa `tkinter` ni `matplotlib`, y la GUI mantiene un único dueño del estado (`BicentenarioSewerApp` en `src/gui/app.py`).

```text
Excel (.xlsx) / CSV ──► src/io/data_loader.py (NetworkDataset validado)
                                │
                                ▼
              src/data_structures/ (DirectedGraph: HashTable + LinkedList)
                 ├──► src/algorithms/ (BFS, DFS, Kahn, Queries O(1), Ranking PQ)
                 └──► src/simulation/ (SewerSimulationEngine + PriorityQueue)
                                │
                                ▼
              SimulationResult (snapshots en LinkedList + métricas globales)
                 ├──► src/simulation/reporter.py (Markdown, CSV, Word .docx)
                 └──► src/gui/app.py (Orquestador — dueño único del estado UI)
                         ├──► NetworkCanvas (renderizado 2 fases < 2 ms)
                         ├──► ControlsPanel (escenarios + visor Queue/Stack)
                         ├──► InspectorTab & CriticalPipesTab
                         ├──► ChartsPanel (Matplotlib diferido + cursor rápido)
                         └──► ComparisonPanel (comparativa de 5 escenarios)
```

### Ficha Rápida de la Red y el Dataset Oficial

- **Origen de datos:** `data/DataSetBicentenario.xlsx` y espejo CSV normalizado en `data/csv/` (`pipes.csv`, `sources.csv`, `sinks.csv`, `drainage_basin.csv`, `precipitation_scenarios.csv`, `node_coords.csv`).
- **Topología verificada:** **46 nodos** (**8 fuentes**: `1, 6, 9, 17, 18, 19, 20, 27`; **37 pozos intermedios**; **1 sumidero**: PTAR Punta Canoa `31`), **59 tuberías dirigidas**, longitud acumulada **19 163.57 m**, **DAG válido** (0 ciclos).
- **Cuenca y lluvia:** coeficiente de escorrentía $C = 0.75$, área $A = 388.0\text{ ha}$, **5 escenarios** ($I \in \{0, 10, 30, 60, 100\}\text{ mm/h}$).
- **Validaciones en `src/io/data_loader.py` (318 L):** verifica columnas obligatorias (con alias tolerantes para Excel/CSV), valores numéricos positivos ($D > 0, Q_{\max} > 0, L > 0$), unicidad de `pipe_id`, existencia de fuentes/sumideros y paridad exacta entre Excel y CSV.

### Conteo Real de Líneas del Repositorio (`wc -l`)

| Capa / Módulo | Archivos | Líneas | Rol principal |
|:---|---:|---:|:---|
| `main.py` | 1 | 68 | Entrada GUI y modos CLI (`--data`, `--report`, `--report-docx`) |
| `src/data_structures/` | 7 | 576 | `LinkedList`, `Queue`, `Stack`, `HashTable`, `PriorityQueue`, `DirectedGraph` |
| `src/io/` | 2 | 336 | Carga/validación Excel y CSV, coordenadas de nodos y exportación CSV |
| `src/algorithms/` | 4 | 491 | BFS, DFS, ordenamiento topológico (Kahn), consultas `O(1)`, clasificación y ranking |
| `src/simulation/` | 5 | 693 | Modelos, motor temporal conservativo, comparador y exportador MD/CSV/DOCX |
| `src/gui/` | 8 | 1 871 | Interfaz Tkinter + Matplotlib en 7 submódulos + `__init__.py` |
| `src/__init__.py` | 1 | 1 | Inicialización del paquete `src` |
| **Subtotal ejecutable (`main.py` + `src/`)** | **28** | **4 036** | **Núcleo completo de la aplicación** |
| `tests/` | 6 | 561 | **24 pruebas unitarias** (`data_structures`: 5, `loader`: 4, `algorithms`: 5, `simulation`: 6, `gui`: 4) |
| **Total Python** | **34** | **4 579** | **Código fuente + pruebas automatizadas** |

---

## 2. Matriz de Cumplimiento del PDF (RF01–RF12, Secciones 4–14 y Nivel 5.0)

| Requisito / Sección | Alcance exigido en la guía | Implementación verificada |
|:---|:---|:---|
| **RF01 / Sec. 4 y 12** | Carga de archivos Excel (`.xlsx`) y CSV con validación | `src/io/data_loader.py` (`load_dataset`, `export_to_csv_dir`): 46 nodos, 59 tuberías, 8 fuentes, 1 sumidero (`31`), 19 163.57 m |
| **RF02 / Sec. 5.1 y 8** | Grafo dirigido y estructuras de datos propias | `src/data_structures/`: `DirectedGraph`, `LinkedList`, `Queue`, `Stack`, `HashTable`, `PriorityQueue` |
| **RF03 / Sec. 9** | Visualización del grafo respetando conexiones y coordenadas | `src/gui/network_canvas.py` (renderizado 2 fases `< 2 ms`, zoom, paneo y tooltips) |
| **RF04–RF05 / Sec. 6** | Selector de 5 escenarios + duración total, lluvia y `Δt` | `src/gui/controls_panel.py` + `src/simulation/models.py::SimulationConfig` |
| **RF06 / Sec. 5.2–5.4** | Simulación temporal (Racional, tránsito `L/V`, cola de prioridad e historial) | `src/simulation/engine.py::SewerSimulationEngine` (`PriorityQueue` + `HashTable` + `LinkedList`) |
| **RF07 / Sec. 7** | Representación de utilización con escala oficial de 5 colores y leyenda | `src/algorithms/analysis.py::classify_utilization` + `src/gui/theme.py` + `src/gui/app.py` |
| **RF08 / Sec. 8 y 9** | Búsqueda `O(1)` y consulta de atributos/estado temporal de tuberías y pozos | `src/algorithms/queries.py` (`search_entity`, `get_pipe_details`, `get_node_details`) + `InspectorTab` |
| **RF09 / Sec. 9** | Control temporal: iniciar, pausar, reanudar, paso atrás/adelante e historial | `src/gui/app.py` (reproductor temporal y barra deslizadora sobre `snapshots`) |
| **RF10 / Sec. 8 y 9** | Tabla de tuberías críticas y sobrecargadas ordenadas con `PriorityQueue` | `src/algorithms/analysis.py::rank_critical_pipes` + `CriticalPipesTab` |
| **RF11 / Sec. 10** | Comparación de los 5 escenarios hasta PTAR Punta Canoa (Nodo `31`) | `src/simulation/comparison.py::compare_all_scenarios` + `ComparisonPanel` |
| **RF12 / Sec. 6 y 13** | Reportes técnicos exportables (escenarios, tiempos, críticas, caudales, %) | `src/simulation/reporter.py` (Markdown, `*_tuberias.csv`, Word `.docx`) + CLI `main.py` |
| **Sec. 8 (Algoritmos)** | BFS (`Queue`), DFS (`Stack` + camino) y animación paso a paso | `src/algorithms/traversals.py` (`bfs`, `dfs`, `topological_sort`) + visor en vivo `Queue`/`Stack` |
| **Nivel Avanzado (5.0)** | `PriorityQueue`, almacenamiento en pozos, conservación de masa y visor vivo | Balance `< 1e-8 m³`, invarianza ante `Δt`, renderizado 2 fases `< 2 ms`, 23 pruebas |

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

---

## 4. Algoritmos Implementados (`src/algorithms/`) — Complejidad y Función

| Algoritmo (`módulo::función`) | Estructura propia usada | Tiempo | Espacio | Propósito en el proyecto |
|:---|:---|:---:|:---:|:---|
| **BFS** (`traversals::bfs`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Recorrido por niveles, ruta más corta en saltos y frames de animación |
| **DFS** (`traversals::dfs`) | `Stack` + `HashTable` | $O(V + E)$ | $O(V)$ | Exploración iterativa en profundidad y reconstrucción de camino |
| **Kahn** (`traversals::topological_sort`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Orden topológico para el motor y verificación DAG (46/46 nodos) |
| **Búsqueda** (`queries::search_entity`) | `HashTable` (grafo) | $O(1)$ | $O(1)$ | Localización instantánea de cualquier pozo o tubería por ID |
| **Trazado** (`queries::trace_downstream/upstream`) | `Queue` + `HashTable` | $O(V + E)$ | $O(V)$ | Ruta hacia PTAR `31` (`outgoing_pipes`) o cuenca aportante (`incoming_pipes`) |
| **Clasificación** (`analysis::classify_utilization`) | Tupla inmutable de 5 niveles | $O(1)$ | $O(1)$ | Asigna color oficial y banderas `is_critical` (>75%) / `is_overloaded` (>100%) |
| **Ranking** (`analysis::rank_critical_pipes`) | `PriorityQueue` | $O(E \log E)$ | $O(E)$ | Ordena tuberías de mayor a menor utilización insertando `(-util_pct, pipe_id)` |

- **Escala oficial de 5 niveles (Sección 7 del PDF):** `0–25%` (`#22c55e`, *Baja*), `>25–50%` (`#eab308`, *Moderada*), `>50–75%` (`#f97316`, *Alta*), `>75–100%` (`#ef4444`, *Cercana a capacidad máxima*) y `>100%` (`#991b1b`, *Capacidad excedida*).
- **Reconstrucción de caminos en BFS/DFS:** ambos algoritmos registran una `HashTable` de padres (`parent_node`, `parent_pipe`) y reconstruyen el camino hacia atrás desde `target_id` hasta `start_id` en $O(V)$, grabando además `TraversalFrame` en cada paso para el visor en vivo.

---

## 5. Modelo Hidráulico y Supuestos Documentados (Sección 11)

Todos los supuestos coinciden exactamente con `MODEL_ASSUMPTIONS_TEXT` (`src/simulation/reporter.py`) y `SewerSimulationEngine` (`src/simulation/engine.py`, 257 L):

1. **Escorrentía por Método Racional:**
   $$Q_{\text{lluvia}} = 0.00278 \cdot C \cdot I \cdot A$$
   con $C = 0.75$ y $A = 388.0\text{ ha}$ ($Q = 0.80898 \cdot I\text{ m}^3/\text{s}$; p. ej., $24.2694\text{ m}^3/\text{s}$ para lluvia moderada de $30\text{ mm/h}$). Se aplica al 100 % durante `storm_duration_min` (`60 min` por defecto dentro de una ventana de `90 min`) sobre las **8 alcantarillas fuente** (`1, 6, 9, 17, 18, 19, 20, 27`) hacia el sumidero único **PTAR Punta Canoa (Nodo `31`)**.
2. **Capacidad $Q_{\max}$ exacta del dataset:** se lee directamente de `DataSetBicentenario.xlsx` / `pipes.csv` (calculada por Manning en el archivo oficial) sin recalcularla.
3. **Velocidad y tiempo de tránsito con `PriorityQueue` (sin teletransporte):** para cada tubería $i$, $A_i = \pi D_i^2 / 4$, $V_i = Q_{\max,i} / A_i$ y $t_i = L_i / V_i$. Todo volumen despachado pasa a `pipe_transit_vol` y se agenda en `event_queue` para arribar en $t + t_i$. La ruta más corta a la PTAR `31` es `27 -> C -> 31` (**8.75 min** de tránsito físico; primer paso con caudal visible en **10.0 min** con $\Delta t = 1\text{ min}$). Los subpasos internos son adaptativos (`sub_dt <= 0.35 * min(t_i)`, en `[1, 15] s`).
4. **Distribución en fuentes y bifurcaciones:**
   - **Fuentes (`source_distribution`):** `"capacity"` (ponderada por $\sum Q_{\max}$ saliente, por defecto) o `"equal"` ($1/8$ uniforme).
   - **Bifurcaciones (`split_rule`):** `"proportional"` (ponderada por $Q_{\max}$ saliente, por defecto) o `"equal"` ($1/k$).
5. **Gestión conservativa de sobrecargas y balance de masa exacto:**
   - Conducción física limitada a $Q_{\text{cond}} = \min(Q_{\text{demanda}}, Q_{\max})$.
   - Utilización reportada $O_i(t) = (Q_{\text{demanda}} / Q_{\max}) \times 100$ sin tope artificial (permite detectar $>100\%$).
   - El volumen excedente se retiene primero en el pozo hasta `max_manhole_storage_m3` (**4.0 m³** por defecto) y el remanente pasa a **rebose superficial**.
   - **Balance de masa exacto verificado en cada paso:**
     $$V_{\text{in}} = V_{\text{PTAR}} + V_{\text{pozos}} + V_{\text{tránsito}} + V_{\text{rebose}} \quad (\text{error} < 10^{-8}\text{ m}^3)$$

### Ciclo de Ejecución de Cada Subpaso Interno (`SewerSimulationEngine.run`)

1. **Llegadas programadas:** extrae de `event_queue` (`PriorityQueue`) todos los lotes con `t_llegada <= t1_s`, descuenta `pipe_transit_vol` (`HashTable.add`) y suma el volumen al nodo destino.
2. **Inyección pluvial:** si `t0_s < storm_s`, distribuye el volumen de lluvia del subpaso entre las 8 fuentes según `source_distribution`.
3. **Barrido topológico (Kahn):** recorre los 46 nodos en orden topológico. Si es sumidero (`31`), descarga a la PTAR; si no, reparte `avail = stored + arr` entre sus tuberías salientes según `split_rule`, limita cada envío a `q_max * sub_dt_s`, agenda su llegada en `event_queue`, retiene el excedente en el pozo hasta `4.0 m³` y contabiliza el sobrante como rebose superficial.
4. **Consolidación de instantánea:** al cierre de cada $\Delta t$ del usuario, calcula $Q_{\text{demanda}}$ (invariante a $\Delta t$ mediante escala fija `_DRAIN_SCALE_S = 60 s`), clasifica las 59 tuberías, calcula `mass_balance_error_m3` y guarda `TimeStepSnapshot` en `self.history` (`LinkedList`).

### Resultados de Referencia — 5 Escenarios (`duration=90 min`, `storm=60 min`, `dt=1 min`)

| Esc. | Condición | $I$ (mm/h) | Util. Máx. (%) | Tubería crítica | >75–100% / >100% | Pico PTAR 31 | Rebose (m³) | Error masa (m³) |
|:---:|:---|---:|---:|:---:|:---:|---:|---:|---:|
| 1 | Tiempo seco | 0.0 | 0.00 % | — | 0 / 0 | 0.0000 m³/s | 0.00 | `0.00e+00` |
| 2 | Lluvia ligera | 10.0 | 1 858.38 % | `P31` | 19 / 15 | 0.3078 m³/s | 27 885.86 | `6.00e-10` |
| 3 | Lluvia moderada | 30.0 | 5 125.52 % | `P31` | 19 / 15 | 0.3078 m³/s | 86 132.42 | `1.35e-09` |
| 4 | Lluvia fuerte | 60.0 | 10 026.22 % | `P31` | 19 / 15 | 0.3078 m³/s | 173 502.26 | `1.85e-09` |
| 5 | Lluvia extrema | 100.0 | 16 560.49 % | `P31` | 19 / 15 | 0.3078 m³/s | 289 995.38 | `3.26e-09` |

*(El pico en la PTAR 31 satura en `0.3078 m³/s`, suma física exacta de $Q_{\max}$ de las tuberías que descargan en el Nodo 31).* 

---

## 6. Arquitectura GUI Tkinter (`src/gui/` — 7 Módulos, 1 871 L)

- **Sistema visual (*Lámina Cartográfica de Archivo Hidráulico*, `theme.py` + `DESIGN.md`):** paleta editorial de 4 tonos base — Grafito `#4A4A4A` (barra superior y KPIs), Plata Mineral `#CBCBCB` (dock lateral y separadores), Marfil Vitela `#FFFFE3` (lienzo y fichas) y Azul Pizarra `#6D8196` (acento primario) — reservando el color saturado exclusivamente para la escala hidráulica de 5 niveles. Registra la fuente local `Inter` (`assets/fonts/`) y habilita DPI awareness en Windows.
- **Los 7 módulos desacoplados:**
  1. **`theme.py` (166 L):** tokens de color, leyenda oficial de 5 colores, traducciones al español, fuentes y estilos `ttk`.
  2. **`network_canvas.py` (373 L):** **renderizado en 2 fases** — *Fase A (`rebuild_geometry`)* construye líneas, flechas, nodos y textos solo al cargar el grafo, hacer zoom/paneo o redimensionar (debounce `80 ms`); *Fase B (`update_visuals`)* actualiza colores, grosores y etiquetas con `itemconfigure` en **$O(V+E)$ sin borrar el canvas** (**`< 2 ms`** por paso).
  3. **`controls_panel.py` (298 L):** carga Excel/CSV, selector de escenario y parámetros hidráulicos, buscador `O(1)`, recorridos BFS/DFS/Trazado y **visor en vivo de `Queue` (FIFO) / `Stack` (LIFO)**.
  4. **`inspector_panel.py` (257 L):** pestañas `Inspector` (ficha detallada de pozo/tubería + resumen global) y `Críticas` (tabla filtrable: *Todas*, *Críticas >75%*, *Sobrecargadas >100%*).
  5. **`charts_panel.py` (202 L):** pestaña `Gráficas` (hidrograma + top-3 de utilización) con **actualización diferida por pestaña** (si está oculta marca `_dirty` y solo redibuja al activarse) y **cursor temporal rápido** (throttle `100 ms` actualizando únicamente `set_xdata` sin reconstruir ejes).
  6. **`comparison_panel.py` (213 L):** pestaña `Comparación` (tabla y barras + pico PTAR de los 5 escenarios) con redibujado diferido y selección rápida hacia el visor principal.
  7. **`app.py` (357 L):** orquestador `BicentenarioSewerApp` con reproductor (`0.5x`, `1x`, `2x`, `4x`, paso a paso, barra de tiempo), toggles `IDs` / `% Util.`, diálogo `Supuestos`, caché de comparativa y exportación MD/CSV/DOCX.

### Exportación de Reportes RF12 (`src/simulation/reporter.py`, 236 L) y CLI (`main.py`, 68 L)

- **Markdown + CSV hermano (`generate_markdown_report`):** genera el reporte estructurado (escenario, supuestos de la Sección 11, métricas globales hasta PTAR `31`, Top 25 de tuberías críticas y tabla comparativa de los 5 escenarios) junto con `<nombre>_tuberias.csv` conteniendo el detalle completo de las 59 tuberías.
- **Word limpio de 1 columna (`generate_docx_report`):** genera un documento `.docx` directamente con `python-docx` (sin Pandoc ni dependencias externas extra) con encabezado, parámetros, supuestos, resultados globales, tabla Top 25 y comparativa de escenarios.
- **Comandos CLI desde `main.py`:**
  ```bash
  python main.py --data data/DataSetBicentenario.xlsx
  python main.py --data data/csv
  python main.py --report docs/REPORTE_ESCENARIOS.md --report-docx docs/REPORTE_ESCENARIOS.docx
  ```

---

## 7. Verificación y Suite de Pruebas Automatizadas (`tests/` — 24 Pruebas, 561 L)

La calidad funcional y numérica se verifica mediante `python -m unittest discover -s tests -v` (o `pytest -v`):

| Archivo de pruebas | Pruebas | Qué valida exactamente |
|:---|---:|:---|
| `tests/test_data_structures.py` (122 L) | 5 | CRUD, colisiones y rehash potencia de 2 en `HashTable` (incl. `add()`), `LinkedList`/`Queue`/`Stack`, `PriorityQueue` determinista, `DirectedGraph` y ausencia AST de `collections`/`heapq`/`networkx` |
| `tests/test_loader.py` (110 L) | 4 | Paridad exacta `.xlsx` vs. `data/csv/`, round-trip CSV, filas en blanco, rechazo `DataLoadError` (ciclos, dead-ends, IDs duplicados, diámetros inconsistentes, NaN) y layout topológico en redes externas |
| `tests/test_algorithms.py` (104 L) | 5 | BFS y DFS desde las 8 fuentes a PTAR `31`, grabación de `TraversalFrame` (`Queue`/`Stack`), `topological_sort`, búsqueda `O(1)`, trazado aguas arriba/abajo, escala 5 colores y ranking `PriorityQueue` |
| `tests/test_simulation.py` (118 L) | 6 | Método Racional (incl. `I=0`), retardo físico e invarianza ante `Δt`, historial `LinkedList`, sobrecargas, conservación de masa ($< 10^{-6}\text{ m}^3$) en los 5 escenarios, repetibilidad, reportes MD/CSV/DOCX y rendimiento |
| `tests/test_gui.py` (106 L) | 4 | Paleta, escala oficial y traducciones de `theme.py`, contrato de los 7 módulos GUI, smoke test integral de `BicentenarioSewerApp` y regresión de selección sin bucle en `CriticalPipesTab` |

---

## 8. Guía Rápida de Preguntas Típicas de Sustentación

1. **¿Por qué implementaron estructuras propias si Python ya trae `dict`, `list` y `heapq`?**
   Porque el proyecto (RF02) exige diseñar y dominar las estructuras desde cero. Implementamos `LinkedList` doblemente enlazada (base de adyacencias, `Queue`, `Stack` e historial), `HashTable` potencia de 2 con máscara de bits y `add()` en una búsqueda, y `PriorityQueue` Min-Heap binario determinista con `seq`. Así garantizamos `O(1)` en consultas y `O(log n)` en eventos sin cajas negras.

2. **¿Por qué usan una `PriorityQueue` en la simulación y no una `Queue` FIFO normal?**
   Porque cada tubería tiene longitud $L_i$ y velocidad $V_i$ distintas, por lo que su tiempo de tránsito $t_i = L_i/V_i$ varía entre tramos. Un paquete enviado después por una tubería corta puede llegar antes que uno enviado antes por una tubería larga. El Min-Heap ordena los arribos por tiempo de llegada en $O(\log n)$ y además construye el ranking de tuberías críticas en $O(E \log E)$.

3. **¿Por qué el agua no se teletransporta hasta la PTAR 31 en `t = 0`?**
   Porque el motor modela el retardo físico de viaje: al despachar volumen por la tubería $i$, se registra en `pipe_transit_vol` y se agenda en `event_queue` para $t + L_i/V_i$. Por eso la PTAR 31 permanece en `0 m³/s` durante los primeros **8.75–10 min** (ruta mínima `27 -> C -> 31`) y responde progresivamente conforme llegan las ondas desde las 8 fuentes.

4. **¿Cómo garantizan la conservación de masa cuando hay sobrecargas mayores al 100 %?**
   Ninguna tubería conduce más que su capacidad física $Q_{\max} \cdot \Delta t_{\text{sub}}$. El exceso no se pierde: primero llena el almacenamiento temporal del pozo (hasta `4.0 m³`) y cualquier excedente se suma al rebose superficial. En cada paso se comprueba $|V_{\text{in}} - (V_{\text{PTAR}} + V_{\text{pozos}} + V_{\text{tránsito}} + V_{\text{rebose}})| < 10^{-8}\text{ m}^3$.

5. **¿Por qué la utilización supera el 100 % si el flujo conducido se limita a $Q_{\max}$?**
   Porque distinguimos el **caudal conducido** $Q_{\text{cond}} \le Q_{\max}$ (agua que realmente avanza aguas abajo) del **caudal demandado** $Q_{\text{demanda}}$ (aportes entrantes + presión del agua retenida en el pozo). Mostrar $O_i(t) = (Q_{\text{demanda}}/Q_{\max}) \times 100$ sin tope artificial permite identificar con precisión qué tramos colapsan más severamente (como `P31`).

6. **¿Cómo logran un rendimiento tan rápido tanto en el motor como en Tkinter?**
   En el motor (~35 ms por escenario de 90 min): orden topológico precalculado, tablas planas de adyacencia por índice, agrupación de eventos por *slot* temporal en `PriorityQueue` y `HashTable.add()` en un solo lookup. En la GUI: renderizado en 2 fases en `NetworkCanvas` (`itemconfigure` sin borrar objetos, `< 2 ms` por frame), actualización diferida de pestañas ocultas y cursor temporal ligero (`set_xdata`) en `ChartsPanel`.
