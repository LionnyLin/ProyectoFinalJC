# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop

## Users

- **Estudiantes y evaluadores académicos (inferido del repositorio):** Presentan, operan y validan el proyecto de la asignatura *Estructuras de Datos* en computadores portátiles y proyectores de aula, necesitando que los recorridos de grafos (`BFS`, `DFS`), las estructuras implementadas desde cero y la conservación de masa sean visibles y demostrables al instante.
- **Analistas e ingenieros hidráulicos (inferido del repositorio):** Evalúan el comportamiento temporal de la red de alcantarillado de Ciudad Bicentenario (Cartagena) hacia la PTAR Punta Canoa (Nodo `31`) bajo distintos escenarios de lluvia, calibran parámetros y exportan reportes técnicos.

## Product Purpose

Representar, simular paso a paso y visualizar mediante escala de colores la red dirigida de alcantarillado del Macroproyecto Ciudad Bicentenario (**46 nodos** —8 fuentes, 37 pozos intermedios, 1 sumidero PTAR Nodo `31`— y **59 tuberías dirigidas** `P1`–`P59`, `19,163.57 m`), integrando estructuras de datos propias con un motor hidráulico temporal conservativo de masa.

El éxito del rediseño significa:
1. Mantener cumplimiento íntegro de todos los requisitos funcionales y técnicos del proyecto sin regresiones.
2. Adaptarse de forma fluida a distintos tamaños de ventana (desde pantallas compactas de portátil ~`900×620` hasta monitores amplios `1920×1080+`) mediante paneles colapsables/redimensionables, tablas adaptables y controles que nunca se recortan ni colisionan.
3. Ofrecer una experiencia de operación fluida, legible y visualmente cuidada en tiempo real (reproducción sin parpadeos, selección sincronizada entre grafo/tabla/gráficas/inspector, atajos de teclado y estados claros).

## Positioning

Simulador hidráulico y laboratorio visual de estructuras de datos sobre un grafo real de alcantarillado en Cartagena: combina implementaciones propias desde cero (`DirectedGraph`, `LinkedList`, `Queue`, `PriorityQueue`, `Stack`, `HashTable`) con un motor temporal discreto conservativo de masa (`Q = 0.00278 · C · I · A`, tiempos de tránsito por Manning y almacenamiento temporal en pozos ante sobrecarga).

## Operating Context

- Aplicación de escritorio ejecutada localmente con `python main.py` (Python 3.11+, Tkinter + Matplotlib embebido), además de modos CLI para reportes (`--report`, `--report-docx`, `--technical-docx`).
- Se opera tanto en pantallas de escritorio amplias como en portátiles de resolución reducida o ventanas divididas durante sustentaciones y análisis.
- Flujo típico de uso: cargar dataset (Excel `.xlsx` o carpeta CSV) → configurar escenario de lluvia (`Dry weather`, `Light`, `Moderate`, `Heavy`, `Extreme`) y parámetros hidráulicos → ejecutar simulación → reproducir/explorar pasos temporales en el lienzo interactivo → inspeccionar tuberías críticas, recorridos `BFS`/`DFS`/trazados y gráficas → comparar los 5 escenarios → exportar CSV o reporte `.docx`/`.md`.

## Capabilities and Constraints

- **Stack obligatorio preservado (inferido del repositorio):** Python 3.11+, `tkinter`/`ttk`, `matplotlib`, `openpyxl`, `python-docx`, `lxml`, `Pillow`. Debe seguir iniciando con `python main.py` y pasando `python -m unittest discover -s tests -v`.
- **Estructuras y algoritmos propios:** `DirectedGraph`, `LinkedList`, `Queue`, `PriorityQueue`, `Stack`, `HashTable`; recorridos `BFS`, `DFS` iterativo con reconstrucción de camino, ordenamiento topológico (DAG 46/46), búsqueda por ID/subcadena, trazado aguas abajo (`trace_downstream`) y aguas arriba (`trace_upstream`), y ranking de criticidad (`rank_critical_pipes`).
- **Escala oficial de colores (Sección 7 — no negociable):**
  - `0–25 %`: `#22c55e` (Baja utilización)
  - `>25–50 %`: `#eab308` (Utilización moderada)
  - `>50–75 %`: `#f97316` (Utilización alta)
  - `>75–100 %`: `#ef4444` (Cercana a capacidad máxima)
  - `>100 %`: `#991b1b` (Capacidad excedida)
- **Requisitos funcionales a conservar:** Carga Excel/CSV, exportación CSV, generación de reportes `.docx`/`.md`, diálogo de supuestos del modelo, presets (`Calibrado 2.5%` / `Racional 100%`), configuración de duración/lluvia/`Δt`/ingreso pluvial/caudal sanitario/bifurcación/hietograma, reproductor temporal (`Inicio`, `-1`, `Play/Pause`, `+1`, velocidades `1x`–`10x`, barra deslizante), auditoría de balance de masa, lienzo con zoom/paneo/tooltips/etiquetas opcionales, inspector de nodo/tubería/escenario, tabla filtrable de tuberías críticas, gráficas temporales (balance de caudales y utilización) y comparación de los 5 escenarios.
- **Restricciones de ventana y comportamiento (solicitud explícita del usuario):** Rediseñar la UI actual (sin compromiso vinculante con la paleta previa Plum/Xanthous, inferido del pedido de rediseño completo) para soportar correctamente múltiples tamaños de ventana (compacta, media, amplia), evitar desbordamientos o controles ocultos y mejorar la fluidez operativa de la aplicación.

## Evidence on Hand

- Dataset real: `data/DataSetBicentenario.xlsx` y `data/csv/*.csv` (46 nodos, 59 tuberías, 5 escenarios de precipitación, cuenca `C=0.75`, `A=388 ha`).
- Documentación técnica real: `docs/DOCUMENTO_TECNICO.md`, `docs/REPORTE_ESCENARIOS.md`, `README.md`.
- Suite de pruebas existente: `tests/` (16 pruebas unitarias).

## Product Principles

1. **Claridad cartográfica e hidráulica ante todo:** El grafo de la red es la pieza central; las alertas de criticidad y el flujo deben leerse sin ruido visual ni etiquetas superpuestas.
2. **Adaptabilidad real a cualquier ventana:** Ningún control esencial ni lectura crítica puede desaparecer o superponerse al reducir la ventana; la interfaz reorganiza paneles y densidad con gracia.
3. **Sincronización viva entre vistas:** Seleccionar una tubería o nodo en el lienzo, la tabla crítica o la búsqueda actualiza de inmediato el inspector, las gráficas y el contexto de recorridos.
4. **Rigor académico verificable:** Los algoritmos de grafos (`BFS`, `DFS`, trazados aguas arriba/abajo) y la auditoría de conservación de masa están accesibles de forma directa y transparente.
