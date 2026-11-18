# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario

**Fecha de generación:** 2026-11-17 18:59:08  
**Fuente de datos:** `C:\Users\Canton Gourmet\OneDrive\Documents\ProyectoFinalJC\data\DataSetBicentenario.xlsx`  
**Descarga final (Sumidero):** 31 (PTAR Punta Canoa)  

## 1. Resumen de la Red
- **Vértices (Alcantarillas / Pozos):** 46 (8 fuentes, 1 sumidero)
- **Aristas dirigidas (Tuberías):** 59
- **Longitud total de la red:** 19,163.57 m (19.16 km)
- **Cuenca de drenaje:** C = 0.75, A = 388.0 ha

## 2. Supuestos y Parámetros del Escenario Evaluado
- **Escenario:** 3 — Moderate rain (30.0 mm/h)
- **Método Racional:** $Q = 0.00278 \cdot C \cdot I \cdot A$ con factor de ingreso pluvial = 2.5%
- **Caudal sanitario base (tiempo seco):** 0.0030 m³/s por fuente
- **Duración de simulación / lluvia:** 90.0 min / 60.0 min ($\Delta t$ = 1.00 min)
- **Perfil temporal (hietograma):** uniform
- **Regla de distribución en bifurcaciones:** proportional
- **Tiempo de tránsito:** $t_i = L_i / V_i$, con $V_i = Q_{max,i} / A_i$ (velocidad a tubo lleno de Manning)
- **Gestión de sobrecargas:** Almacenamiento temporal en el pozo aguas arriba sin pérdida de masa

## 3. Resultados Globales y Conservación de Masa
- **Volumen total inyectado:** 2,313.846 m³
- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** 1,134.978 m³
- **Caudal pico en PTAR Punta Canoa:** 0.3054 m³/s
- **Volumen remanente (en pozos + tránsito al cierre):** 1,178.868 m³
- **Error máximo de balance de masa:** 4.093e-11 m³
- **Tuberías críticas (>= 75 %):** 17 (P1, P2, P25, P27, P28, P3, P31, P36, P37, P38, P39, P4, P43, P5, P51, P6, P7)
- **Tuberías sobrecargadas (> 100 %):** 11 (P1, P2, P25, P3, P31, P36, P37, P39, P4, P43, P5)
- **Tiempo de cómputo:** 83.07 ms

## 4. Ranking de Tuberías por Utilización Pico
| # | Tubería | Tramo | Q_pico (m³/s) | Q_max (m³/s) | Utilización (%) | Estado | Exceso (m³/s) |
|---:|:---:|:---:|---:|---:|---:|:---|---:|
| 1 | P31 | 17 -> 16 | 0.07884 | 0.02965 | 265.87% | Capacidad excedida | 0.04919 |
| 2 | P39 | 20 -> B | 0.07884 | 0.02965 | 265.87% | Capacidad excedida | 0.04919 |
| 3 | P43 | 19 -> A | 0.07884 | 0.02965 | 265.87% | Capacidad excedida | 0.04919 |
| 4 | P25 | 23 -> J | 0.14875 | 0.08743 | 170.13% | Capacidad excedida | 0.06131 |
| 5 | P1 | 1 -> C | 0.07884 | 0.05377 | 146.64% | Capacidad excedida | 0.02507 |
| 6 | P2 | 27 -> C | 0.07884 | 0.05377 | 146.64% | Capacidad excedida | 0.02507 |
| 7 | P36 | 18 -> 14 | 0.07884 | 0.05377 | 146.64% | Capacidad excedida | 0.02507 |
| 8 | P4 | 6 -> Q | 0.03942 | 0.02965 | 132.93% | Capacidad excedida | 0.00977 |
| 9 | P5 | 6 -> R | 0.03942 | 0.02965 | 132.93% | Capacidad excedida | 0.00977 |
| 10 | P3 | C -> 31 | 0.10753 | 0.08743 | 122.99% | Capacidad excedida | 0.02010 |
| 11 | P37 | 14 -> 11 | 0.09180 | 0.08743 | 105.00% | Capacidad excedida | 0.00437 |
| 12 | P6 | Q -> O | 0.02965 | 0.02965 | 100.00% | Cercana a la capacidad máxima | 0.00000 |
| 13 | P7 | R -> P | 0.02965 | 0.02965 | 100.00% | Cercana a la capacidad máxima | 0.00000 |
| 14 | P28 | G -> 30 | 0.18588 | 0.18829 | 98.72% | Cercana a la capacidad máxima | 0.00000 |
| 15 | P38 | 11 -> K | 0.07636 | 0.08743 | 87.34% | Cercana a la capacidad máxima | 0.00000 |
| 16 | P51 | 11 -> 12 | 0.02590 | 0.02965 | 87.34% | Cercana a la capacidad máxima | 0.00000 |
| 17 | P27 | 24 -> G | 0.15584 | 0.18829 | 82.76% | Cercana a la capacidad máxima | 0.00000 |
| 18 | P23 | K -> 23 | 0.14048 | 0.18829 | 74.61% | Utilización alta | 0.00000 |
| 19 | P29 | 30 -> 29 | 0.21793 | 0.34140 | 63.83% | Utilización alta | 0.00000 |
| 20 | P30 | 29 -> 31 | 0.21793 | 0.34140 | 63.83% | Utilización alta | 0.00000 |
| 21 | P32 | 16 -> 15 | 0.02965 | 0.05377 | 55.15% | Utilización alta | 0.00000 |
| 22 | P40 | B -> 21 | 0.02965 | 0.05377 | 55.15% | Utilización alta | 0.00000 |
| 23 | P44 | A -> 13 | 0.02965 | 0.05377 | 55.15% | Utilización alta | 0.00000 |
| 24 | P8 | O -> 5 | 0.02965 | 0.05377 | 55.15% | Utilización alta | 0.00000 |
| 25 | P9 | P -> 7 | 0.02965 | 0.05377 | 55.15% | Utilización alta | 0.00000 |

## 5. Comparación entre Escenarios de Precipitación
| Escenario | Condición | Intensidad (mm/h) | Util. Máx (%) | Tubería Crítica | Críticas (>=75%) | Sobrecargadas (>100%) | Pico PTAR (m³/s) | Error Masa (m³) |
|:---:|:---|---:|---:|:---:|---:|---:|---:|---:|
| 1 | Dry weather | 0.0 | 10.25% | P25 | 0 | 0 | 0.0240 | 2.47e-12 |
| 2 | Light rain | 10.0 | 96.59% | P25 | 4 | 0 | 0.2262 | 8.64e-12 |
| 3 | Moderate rain | 30.0 | 265.87% | P31 | 17 | 11 | 0.3054 | 4.09e-11 |
| 4 | Heavy rain | 60.0 | 521.62% | P31 | 21 | 13 | 0.3078 | 1.27e-10 |
| 5 | Extreme rain | 100.0 | 862.63% | P31 | 21 | 15 | 0.3078 | 8.46e-11 |
