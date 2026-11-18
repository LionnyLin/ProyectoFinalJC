# Simulador de Red de Alcantarillado — Ciudad Bicentenario (Cartagena)

Aplicación de escritorio en Python para la representación, simulación temporal y visualización por escala de colores del flujo en la red de alcantarillado del Macroproyecto Ciudad Bicentenario hasta el punto de descarga en la PTAR de Punta Canoa (Nodo `31`).

## Características Principales

- **Estructuras de datos implementadas desde cero** (`src/data_structures/`): `DirectedGraph`, `LinkedList` (listas de adyacencia e historial temporal), `Queue`, `PriorityQueue` (Min-Heap para eventos de tránsito y ranking), `Stack` y `HashTable`.
- **Algoritmos propios** (`src/algorithms/`): `BFS`, `DFS` iterativo con reconstrucción de caminos, ordenamiento topológico, búsqueda y trazado aguas arriba/abajo, y clasificación de criticidad según la escala de 5 colores de la guía (`0–25%`, `>25–50%`, `>50–75%`, `>75–100%`, `>100%`).
- **Carga dual validada** (`src/io/`): Lectura desde `data/DataSetBicentenario.xlsx` y desde archivos CSV normalizados en `data/csv/`.
- **Motor temporal conservativo de masa** (`src/simulation/`): Método racional ($Q = 0.00278 \cdot C \cdot I \cdot A$), velocidades de Manning, tiempos de tránsito $t_i = L_i / V_i$, distribución configurable en bifurcaciones y almacenamiento temporal en pozos ante sobrecarga.
- **Interfaz gráfica interactiva** (`src/gui/`): Lienzo con zoom/paneo y tooltips, reproductor temporal (iniciar, pausar, reanudar, paso a paso y barra de tiempo), tabla de tuberías críticas, gráficas Matplotlib y comparación entre los 5 escenarios.

## Requisitos

- Python 3.11+
- `openpyxl`
- `matplotlib`
- `tkinter` (incluido en Python estándar para Windows)

## Ejecución

### Interfaz Gráfica (GUI)
```bash
python main.py
```

### Generación de Reporte por Línea de Comandos (CLI)
```bash
python main.py --report docs/REPORTE_ESCENARIOS.md
```

### Pruebas Unitarias
```bash
python -m unittest discover -s tests -v
```

## Estructura del Proyecto

- `main.py`: Punto de entrada (GUI y modo CLI `--report`).
- `data/`: Dataset oficial `DataSetBicentenario.xlsx` y su versión en `csv/`.
- `src/data_structures/`: Estructuras de datos obligatorias propias.
- `src/algorithms/`: BFS, DFS, consultas y análisis de criticidad.
- `src/io/`: Cargadores y validadores Excel/CSV.
- `src/simulation/`: Motor de simulación, comparación de escenarios y reportes.
- `src/gui/`: Interfaz gráfica Tkinter + Matplotlib.
- `docs/DOCUMENTO_TECNICO.md`: Documento técnico completo del proyecto.
- `tests/`: Suite de pruebas unitarias.
