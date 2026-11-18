# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario

**Fecha de generación:** 2026-11-18 15:30:30  
**Fuente de datos:** `C:\Users\lionn\OneDrive\Documents\ProyectoFinalJC\data\DataSetBicentenario.xlsx`  
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
- **Reparto entre fuentes:** capacity (por capacidad instalada o uniforme 1/8)
- **Regla de distribución en bifurcaciones:** proportional
- **Tiempo de tránsito:** $t_i = L_i / V_i$, con $V_i = Q_{max,i} / A_i$ (velocidad a tubo lleno de Manning)
- **Utilización física vs. demanda:** Conducción física acotada a $\le 115\%$ bajo sobrepresión; el exceso de demanda se reporta por separado como índice ($\times Q_{max}$) y déficit.
- **Pozos finitos y rebose:** Capacidad máxima de pozo = 4.0 m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.

## 3. Resultados Globales y Conservación de Masa
- **Volumen total inyectado:** 2,313.846 m³
- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** 1,101.146 m³
- **Caudal pico en PTAR Punta Canoa:** 0.3078 m³/s
- **Volumen remanente (en pozos + tránsito al cierre):** 170.250 m³
- **Rebose superficial acumulado en vía:** 1,042.450 m³
- **Error máximo de balance de masa:** 3.547e-11 m³
- **Tuberías críticas (>= 75 %):** 21 (P1, P12, P13, P2, P22, P23, P25, P27, P28, P3, P31, P36, P37, P38, P39, P4, P43, P5, P51, P6, P7)
- **Tuberías sobrecargadas (> 100 %):** 15 (P1, P12, P13, P2, P23, P25, P28, P3, P31, P36, P37, P39, P4, P43, P5)
- **Tiempo de cómputo:** 142.68 ms

## 4. Ranking de Tuberías por Utilización Física Pico
| # | Tubería | Tramo | Q_físico (m³/s) | Q_max (m³/s) | Util. Fís (%) | Demanda | Estado | Déficit (m³/s) |
|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|
| 1 | P25 | 23 -> J | 0.09885 | 0.08743 | 113.06% | 2.28x | Capacidad excedida | 0.11165 |
| 2 | P31 | 17 -> 16 | 0.03146 | 0.02965 | 106.10% | 1.33x | Capacidad excedida | 0.00968 |
| 3 | P39 | 20 -> B | 0.03146 | 0.02965 | 106.10% | 1.33x | Capacidad excedida | 0.00968 |
| 4 | P43 | 19 -> A | 0.03146 | 0.02965 | 106.10% | 1.33x | Capacidad excedida | 0.00968 |
| 5 | P1 | 1 -> C | 0.05669 | 0.05377 | 105.43% | 1.28x | Capacidad excedida | 0.01511 |
| 6 | P2 | 27 -> C | 0.05669 | 0.05377 | 105.43% | 1.28x | Capacidad excedida | 0.01511 |
| 7 | P36 | 18 -> 14 | 0.05669 | 0.05377 | 105.43% | 1.28x | Capacidad excedida | 0.01511 |
| 8 | P4 | 6 -> Q | 0.03124 | 0.02965 | 105.35% | 1.28x | Capacidad excedida | 0.00818 |
| 9 | P5 | 6 -> R | 0.03124 | 0.02965 | 105.35% | 1.28x | Capacidad excedida | 0.00818 |
| 10 | P12 | 9 -> 8 | 0.05635 | 0.05377 | 104.80% | 1.24x | Capacidad excedida | 0.01298 |
| 11 | P13 | 9 -> L | 0.13822 | 0.13188 | 104.80% | 1.24x | Capacidad excedida | 0.03183 |
| 12 | P3 | C -> 31 | 0.09147 | 0.08743 | 104.62% | 1.23x | Capacidad excedida | 0.02010 |
| 13 | P23 | K -> 23 | 0.19627 | 0.18829 | 104.24% | 1.21x | Capacidad excedida | 0.03906 |
| 14 | P28 | G -> 30 | 0.19167 | 0.18829 | 101.80% | 1.08x | Capacidad excedida | 0.01500 |
| 15 | P37 | 14 -> 11 | 0.08844 | 0.08743 | 101.15% | 1.05x | Capacidad excedida | 0.00437 |
| 16 | P22 | L -> K | 0.13188 | 0.13188 | 100.00% | 1.00x | Cercana a la capacidad máxima | 0.00000 |
| 17 | P6 | Q -> O | 0.02965 | 0.02965 | 100.00% | 1.00x | Cercana a la capacidad máxima | 0.00000 |
| 18 | P7 | R -> P | 0.02965 | 0.02965 | 100.00% | 1.00x | Cercana a la capacidad máxima | 0.00000 |
| 19 | P27 | 24 -> G | 0.17325 | 0.18829 | 92.01% | 0.92x | Cercana a la capacidad máxima | 0.00000 |
| 20 | P38 | 11 -> K | 0.07636 | 0.08743 | 87.34% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 21 | P51 | 11 -> 12 | 0.02590 | 0.02965 | 87.34% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 22 | P24 | 26 -> 24 | 0.08582 | 0.13188 | 65.07% | 0.65x | Utilización alta | 0.00000 |
| 23 | P29 | 30 -> 29 | 0.22034 | 0.34140 | 64.54% | 0.65x | Utilización alta | 0.00000 |
| 24 | P30 | 29 -> 31 | 0.22034 | 0.34140 | 64.54% | 0.65x | Utilización alta | 0.00000 |
| 25 | P14 | 8 -> 7 | 0.03465 | 0.05377 | 64.45% | 0.64x | Utilización alta | 0.00000 |

## 5. Comparación entre Escenarios de Precipitación
| Escenario | Condición | Intensidad (mm/h) | Util. Fís. Máx (%) | Demanda Máx | Tubería Crítica | Críticas (>=75%) | Sobrecargadas (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |
|:---:|:---|---:|---:|---:|:---:|---:|---:|---:|---:|---:|
| 1 | Dry weather | 0.0 | 10.25% | 0.10x | P25 | 0 | 0 | 0.0240 | 0.00 | 2.47e-12 |
| 2 | Light rain | 10.0 | 104.46% | 1.22x | P25 | 1 | 1 | 0.2070 | 48.24 | 9.32e-12 |
| 3 | Moderate rain | 30.0 | 113.06% | 2.28x | P25 | 21 | 15 | 0.3078 | 1,042.45 | 3.55e-11 |
| 4 | Heavy rain | 60.0 | 113.75% | 2.55x | P31 | 21 | 15 | 0.3078 | 3,226.70 | 6.82e-11 |
| 5 | Extreme rain | 100.0 | 114.91% | 4.19x | P31 | 21 | 15 | 0.3078 | 6,139.02 | 5.55e-11 |
