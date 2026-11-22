# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario

**Fecha de generación:** 2026-11-22 01:51:35  
**Fuente de datos:** `data/DataSetBicentenario.xlsx`  
**Descarga final (Sumidero):** 31 (PTAR Punta Canoa)  

## 1. Resumen de la Red
- **Vértices (Alcantarillas / Pozos):** 46 (8 fuentes, 1 sumidero)
- **Aristas dirigidas (Tuberías):** 59
- **Longitud total de la red:** 19,163.57 m (19.16 km)
- **Cuenca de drenaje:** C = 0.75, A = 388.0 ha

## 2. Supuestos y Parámetros del Escenario Evaluado
- **Escenario:** 3 — Moderate rain (30.0 mm/h)
- **Método Racional:** $Q = 0.00278 \cdot C \cdot I \cdot A$ con factor de ingreso pluvial = 100.0%
- **Caudal sanitario base (tiempo seco):** 0.0000 m³/s por fuente
- **Duración de simulación / lluvia:** 90.0 min / 60.0 min ($\Delta t$ = 1.00 min)
- **Perfil temporal:** Uniforme constante durante 60.0 min
- **Reparto entre fuentes:** capacity (por capacidad instalada o uniforme 1/8)
- **Regla de distribución en bifurcaciones:** proportional
- **Tiempo de tránsito:** $t_i = L_i / V_i$, con $V_i = Q_{max,i} / A_i$ (Manning) e integración con sub-paso hidráulico continuo ($\Delta t_{sim} \le 10\;s$).
- **Utilización oficial:** $O_i(t) = (Q_{dem,i}(t) / Q_{max,ef,i}) \times 100$ sin techo artificial; la conducción física aguas abajo se limita a $Q_{max,ef,i}$.
- **Pozos finitos y rebose:** Capacidad máxima de pozo = 4.0 m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.
- **Nota dataset (P57):** Se conserva `P57 = 12"` (`0.08743 m³/s`) tal como figura en `DataSetBicentenario.xlsx` (el Anexo 2 gráfico del enunciado rotula `0.19`).

## 3. Resultados Globales y Conservación de Masa
- **Volumen total inyectado:** 87,369.840 m³
- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** 1,033.681 m³
- **Caudal pico en PTAR Punta Canoa:** 0.3078 m³/s
- **Volumen remanente (en pozos + tránsito al cierre):** 202.648 m³
- **Rebose superficial acumulado en vía:** 86,133.511 m³
- **Error máximo de balance de masa:** 1.710e-09 m³
- **Tuberías críticas (>75–100 %):** 20 (P1, P12, P13, P2, P22, P23, P25, P27, P28, P3, P36, P37, P38, P39, P4, P43, P5, P51, P6, P7)
- **Tuberías sobrecargadas (>100 %):** 18 (P1, P12, P13, P2, P22, P23, P25, P28, P3, P31, P36, P37, P39, P4, P43, P5, P6, P7)
- **Tiempo de cómputo:** 414.05 ms

## 4. Ranking de Tuberías por Utilización Pico
| # | Tubería | Tramo | Q_cond (m³/s) | Q_max (m³/s) | Util (%) | Razón Qmax | Estado | Exceso (m³/s) |
|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|
| 1 | P31 | 17 -> 16 | 0.02965 | 0.02965 | 5125.52% | 51.26x | Capacidad excedida | 1.49028 |
| 2 | P39 | 20 -> B | 0.02965 | 0.02965 | 5125.52% | 51.26x | Capacidad excedida | 1.49028 |
| 3 | P43 | 19 -> A | 0.02965 | 0.02965 | 5125.52% | 51.26x | Capacidad excedida | 1.49028 |
| 4 | P1 | 1 -> C | 0.05377 | 0.05377 | 5024.69% | 50.25x | Capacidad excedida | 2.64786 |
| 5 | P2 | 27 -> C | 0.05377 | 0.05377 | 5024.69% | 50.25x | Capacidad excedida | 2.64786 |
| 6 | P36 | 18 -> 14 | 0.05377 | 0.05377 | 5024.69% | 50.25x | Capacidad excedida | 2.64786 |
| 7 | P4 | 6 -> Q | 0.02965 | 0.02965 | 5013.11% | 50.13x | Capacidad excedida | 1.45695 |
| 8 | P5 | 6 -> R | 0.02965 | 0.02965 | 5013.11% | 50.13x | Capacidad excedida | 1.45695 |
| 9 | P12 | 9 -> 8 | 0.05377 | 0.05377 | 4936.61% | 49.37x | Capacidad excedida | 2.60050 |
| 10 | P13 | 9 -> L | 0.13188 | 0.13188 | 4936.61% | 49.37x | Capacidad excedida | 6.37869 |
| 11 | P25 | 23 -> J | 0.08743 | 0.08743 | 303.95% | 3.04x | Capacidad excedida | 0.17831 |
| 12 | P3 | C -> 31 | 0.08743 | 0.08743 | 199.24% | 1.99x | Capacidad excedida | 0.08677 |
| 13 | P37 | 14 -> 11 | 0.08743 | 0.08743 | 178.12% | 1.78x | Capacidad excedida | 0.06830 |
| 14 | P23 | K -> 23 | 0.18829 | 0.18829 | 156.15% | 1.56x | Capacidad excedida | 0.10573 |
| 15 | P28 | G -> 30 | 0.18829 | 0.18829 | 143.37% | 1.43x | Capacidad excedida | 0.08167 |
| 16 | P7 | R -> P | 0.02965 | 0.02965 | 101.33% | 1.01x | Capacidad excedida | 0.00039 |
| 17 | P22 | L -> K | 0.13188 | 0.13188 | 100.37% | 1.00x | Capacidad excedida | 0.00049 |
| 18 | P6 | Q -> O | 0.02965 | 0.02965 | 100.20% | 1.00x | Capacidad excedida | 0.00006 |
| 19 | P27 | 24 -> G | 0.17325 | 0.18829 | 96.48% | 0.96x | Cercana a la capacidad máxima | 0.00000 |
| 20 | P51 | 11 -> 12 | 0.02590 | 0.02965 | 88.85% | 0.89x | Cercana a la capacidad máxima | 0.00000 |
| 21 | P38 | 11 -> K | 0.07636 | 0.08743 | 87.58% | 0.88x | Cercana a la capacidad máxima | 0.00000 |
| 22 | P29 | 30 -> 29 | 0.22034 | 0.34140 | 67.00% | 0.67x | Utilización alta | 0.00000 |
| 23 | P30 | 29 -> 31 | 0.22034 | 0.34140 | 67.00% | 0.67x | Utilización alta | 0.00000 |
| 24 | P24 | 26 -> 24 | 0.08582 | 0.13188 | 66.95% | 0.67x | Utilización alta | 0.00000 |
| 25 | P21 | 8 -> K | 0.01911 | 0.02965 | 65.28% | 0.65x | Utilización alta | 0.00000 |

## 5. Comparación entre Escenarios de Precipitación
| Escenario | Condición | Intensidad (mm/h) | Util. Máx (%) | Razón Máx | Tubería Crítica | Críticas (>75–100%) | Sobrec. (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |
|:---:|:---|---:|---:|---:|:---:|---:|---:|---:|---:|---:|
| 1 | Dry weather | 0.0 | 0.00% | 0.00x | P1 | 0 | 0 | 0.0000 | 0.00 | 0.00e+00 |
| 2 | Light rain | 10.0 | 1858.38% | 18.58x | P31 | 20 | 18 | 0.3078 | 27,886.95 | 1.53e-09 |
| 3 | Moderate rain | 30.0 | 5125.52% | 51.26x | P31 | 20 | 18 | 0.3078 | 86,133.51 | 1.71e-09 |
| 4 | Heavy rain | 60.0 | 10026.22% | 100.26x | P31 | 20 | 18 | 0.3078 | 173,503.35 | 2.78e-09 |
| 5 | Extreme rain | 100.0 | 16560.49% | 165.60x | P31 | 20 | 18 | 0.3078 | 289,996.47 | 2.74e-09 |
