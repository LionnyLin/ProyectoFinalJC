# Simulador de Red de Alcantarillado — Ciudad Bicentenario (Cartagena)

Aplicación de escritorio en Python para modelar, simular en el tiempo y visualizar el comportamiento hidráulico de la red de alcantarillado del **Macroproyecto Ciudad Bicentenario** (**46 nodos**, **59 tuberías**, **19 163.57 m** totales) desde sus **8 alcantarillas fuente** (`1, 6, 9, 17, 18, 19, 20, 27`) hasta la descarga final en la **PTAR Punta Canoa (Nodo `31`)**.

Todo el núcleo algorítmico (grafo dirigido, listas doblemente enlazadas, cola, pila, tabla hash y cola de prioridad Min-Heap) está implementado **desde cero** en Python puro, cumpliendo íntegramente los requisitos funcionales **RF01–RF12** y el **Nivel Avanzado (5.0)** de la guía del proyecto.

## Requisitos e Instalación

- **Python:** `>= 3.11`
- **Dependencias directas (`requirements.txt`):** únicamente **3** paquetes externos:
  - `openpyxl>=3.1.2` — lectura del dataset oficial en Excel (`.xlsx`)
  - `matplotlib>=3.8.0` — hidrogramas, curvas de utilización y barras comparativas
  - `python-docx>=1.1.0` — exportación de reportes técnicos en Word (`.docx`)
- **Tkinter:** incluido por defecto en Python para Windows y macOS; en Linux (Debian/Ubuntu) instalar con `sudo apt install python3-tk`.

### Windows (instalación y ejecución automatizada)

```bat
setup.bat          :: Crea .venv, instala requirements.txt y verifica dependencias
setup.bat --run    :: Prepara el ambiente e inicia la interfaz gráfica
setup.bat --test   :: Prepara el ambiente y ejecuta la suite de pruebas unitarias
```

Una vez preparado el entorno virtual, también puedes iniciar directamente con `.venv\Scripts\python.exe main.py`.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

### 1. Interfaz Gráfica (GUI)

```bash
python main.py                   # Carga data/DataSetBicentenario.xlsx por defecto
python main.py --data data/csv   # Carga equivalente desde la carpeta CSV normalizada
```

### 2. Exportación CLI de Reportes (sin abrir ventana)

Ejecuta la comparativa completa de los 5 escenarios bajo parámetros equivalentes y exporta el reporte Markdown (junto con su archivo hermano `*_tuberias.csv`) y/o el documento Word (`.docx`):

```bash
python main.py --report reporte.md --report-docx reporte.docx
```

### 3. Pruebas Unitarias (24 pruebas en 5 suites)

```bash
python -m unittest discover -s tests -v
# o con pytest:
pytest -v
```

## Arquitectura Modular del Repositorio

El código ejecutable suma **4 036 líneas** (`main.py` + `src/`) y **543 líneas** de pruebas (`tests/`), para un total de **4 579 líneas** Python verificadas:

```text
ProyectoFinalJC/
├── main.py                      # (68 L)    Entrada GUI y CLI (--data, --report, --report-docx)
├── setup.bat                    # Script de preparación, ejecución y pruebas en Windows
├── requirements.txt             # 3 dependencias directas: openpyxl, matplotlib, python-docx
├── DESIGN.md                    # Sistema visual cartográfico (Lámina de Archivo Hidráulico)
├── DOCUMENTACION.md             # Referencia técnica y guía de estudio para sustentación
├── assets/fonts/                # Tipografía local Inter (Regular, Medium, SemiBold, Bold)
├── data/
│   ├── DataSetBicentenario.xlsx # Dataset oficial de la red, cuenca y 5 escenarios
│   └── csv/                     # Espejo CSV normalizado (pipes, sources, sinks, basin, coords)
├── docs/                        # Reportes generados (MD, CSV, DOCX) y figuras
├── src/                         # (3 968 L) Código fuente modular
│   ├── data_structures/         # (576 L)   LinkedList, Queue, Stack, HashTable, PriorityQueue, DirectedGraph
│   ├── io/                      # (336 L)   data_loader.py (carga/validación Excel y CSV + exportación CSV)
│   ├── algorithms/              # (491 L)   traversals.py (BFS/DFS/Kahn), queries.py (O(1)/trazado), analysis.py
│   ├── simulation/              # (693 L)   models.py, engine.py, comparison.py, reporter.py (MD/CSV/DOCX)
│   └── gui/                     # (1 871 L) Interfaz Tkinter + Matplotlib (7 submódulos):
│       ├── theme.py             # (166 L)   Paleta cartográfica, fuentes, DPI awareness y escala 5 colores
│       ├── network_canvas.py    # (373 L)   Lienzo interactivo en 2 fases (< 2 ms/frame), zoom y paneo
│       ├── controls_panel.py    # (298 L)   Escenarios, parámetros, BFS/DFS y visor en vivo Queue/Stack
│       ├── inspector_panel.py   # (257 L)   Inspector de nodo/tubería + ranking de tuberías críticas
│       ├── charts_panel.py      # (202 L)   Hidrograma y utilización con actualización diferida y cursor rápido
│       ├── comparison_panel.py  # (213 L)   Tabla y barras comparativas de los 5 escenarios
│       └── app.py               # (357 L)   Orquestador principal y dueño único del estado UI
└── tests/                       # (~560 L)  24 pruebas (data_structures, loader, algorithms, simulation, gui)
```

## Características Principales (RF01–RF12 + Nivel Avanzado 5.0)

- **Estructuras de datos desde cero (RF01–RF02):** `DirectedGraph` con listas de adyacencia (`LinkedList`) e indexación `O(1)` (`HashTable` potencia de 2 con método `add()`), `Queue` FIFO, `Stack` LIFO y `PriorityQueue` Min-Heap binario determinista.
- **Carga dual validada (RF01):** Lectura desde `DataSetBicentenario.xlsx` o carpeta `data/csv/`, validación topológica de grafo acíclico dirigido (DAG) mediante Kahn y exportación a CSV normalizado.
- **Recorridos BFS y DFS con visor en vivo (RF03–RF04):** Búsqueda en anchura (`Queue`) y profundidad iterativa (`Stack`) con reconstrucción de ruta y reproducción paso a paso mostrando el contenido en vivo de la cola/pila y el orden de visita.
- **Consultas O(1) y trazado direccional (RF05):** Búsqueda instantánea por ID de pozo o tubería, ficha técnica detallada y trazado aguas abajo (hacia PTAR `31`) o aguas arriba (subcuenca aportante).
- **Simulación física conservativa con retardo de tránsito (RF06–RF08):**
  - Escorrentía por Método Racional ($Q = 0.00278 \cdot C \cdot I \cdot A$, con $C = 0.75$ y $A = 388\text{ ha}$).
  - Capacidad $Q_{\max}$ tomada directamente del dataset, velocidad $V_i = Q_{\max}/(\pi D^2/4)$ y tiempo de viaje $t_i = L_i/V_i$ programado con `PriorityQueue` (sin teletransporte; llegada mínima a PTAR `31` en ~8.75–10 min).
  - Conducción limitada a $\min(Q_{\text{demanda}}, Q_{\max})$, almacenamiento temporal en pozos (`4.0 m³` por defecto) y rebose superficial con balance de masa exacto (error $< 10^{-8}\text{ m}^3$).
- **Escala oficial de 5 colores y ranking crítico (RF09–RF10):** Clasificación visual y ordenamiento descendente con `PriorityQueue` según la Sección 7 del PDF:

| Rango de Utilización $O_i(t)$ | Color Oficial | Estado Hidráulico |
|:---:|:---:|:---|
| `0–25 %` | `#22c55e` (Verde) | Baja utilización |
| `>25–50 %` | `#eab308` (Amarillo) | Utilización moderada |
| `>50–75 %` | `#f97316` (Naranja) | Utilización alta |
| `>75–100 %` | `#ef4444` (Rojo) | Cercana a capacidad máxima |
| `>100 %` | `#991b1b` (Rojo oscuro) | Capacidad excedida (sobrecarga) |

- **Comparación de 5 escenarios y reportes (RF11–RF12):** Evaluación simultánea de los 5 escenarios de lluvia (`0, 10, 30, 60, 100 mm/h`), hidrogramas y barras sincronizadas, y exportación a **Markdown, CSV y Word (`.docx`)** desde GUI o CLI.

Para consultar complejidades Big-O, ecuaciones del modelo, desglose de módulos, matriz de cumplimiento del PDF y preguntas frecuentes de sustentación, consulta [DOCUMENTACION.md](DOCUMENTACION.md).
