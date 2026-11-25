# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario

**Fecha de generación:** 2026-11-24 20:49:02  
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
- **Flujo máximo del sistema (Ford-Fulkerson / Edmonds-Karp):** $F_{max} = 0.35915$ m³/s; corte mínimo: P28, P3, P43, P53 ($\sum Q_{max} = 0.35915$ m³/s).
- **Admisión acotada y tope físico por rebose:** Tope configurado = 120.0%. El sistema admite hasta $(U_{tope}/100)\cdot F_{max}$; al llegar al tope no entra más agua, el porcentaje de uso deja de aumentar y el exceso rebosa en superficie.
- **Utilización acotada:** $O_i(t) = \min(U_{tope},\; (Q_{dem,i}(t) / Q_{max,ef,i}) \times 100)$ y $U_{sis}(t) = \min(U_{tope},\; (Q_{req}(t) / F_{max}) \times 100)$; la conducción física aguas abajo se limita a $Q_{max,ef,i}$.
- **Pozos finitos y rebose:** Capacidad máxima de pozo = 4.0 m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.
- **Nota dataset (P57):** Se conserva `P57 = 12"` (`0.08743 m³/s`) tal como figura en `DataSetBicentenario.xlsx` (el Anexo 2 gráfico del enunciado rotula `0.19`).

## 3. Resultados Globales y Conservación de Masa
- **Flujo máximo del sistema (Ford-Fulkerson):** 0.35915 m³/s
- **Uso máximo del sistema (% de F_max):** 120.00% (Demanda racional pico: 6757.54%)
- **Volumen total generado (Método Racional):** 87,369.840 m³
- **Volumen admitido en la red (≤ tope · F_max):** 1,551.509 m³
- **Volumen rebosado en entradas por tope:** 85,818.331 m³
- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** 993.761 m³
- **Caudal pico en PTAR Punta Canoa:** 0.3037 m³/s
- **Volumen remanente (en pozos + tránsito al cierre):** 166.866 m³
- **Rebose superficial acumulado total en vía:** 86,209.214 m³
- **Error máximo de balance de masa:** 1.695e-09 m³
- **Tuberías críticas (>75–100 %):** 21 (P1, P12, P13, P2, P22, P23, P25, P27, P28, P3, P31, P36, P37, P38, P39, P4, P43, P5, P51, P6, P7)
- **Tuberías sobrecargadas (>100 %):** 4 (P23, P25, P28, P3)
- **Tiempo de cómputo:** 229.37 ms

## 4. Ranking de Tuberías por Utilización Pico
| # | Tubería | Tramo | Q_cond (m³/s) | Q_max (m³/s) | Util (%) | Razón Qmax | Estado | Exceso (m³/s) |
|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|
| 1 | P25 | 23 -> J | 0.08743 | 0.08743 | 120.00% | 3.02x | Capacidad excedida | 0.17694 |
| 2 | P3 | C -> 31 | 0.08743 | 0.08743 | 120.00% | 1.83x | Capacidad excedida | 0.07282 |
| 3 | P23 | K -> 23 | 0.18829 | 0.18829 | 120.00% | 1.41x | Capacidad excedida | 0.07730 |
| 4 | P28 | G -> 30 | 0.18829 | 0.18829 | 104.23% | 1.04x | Capacidad excedida | 0.00797 |
| 5 | P31 | 17 -> 16 | 0.02581 | 0.02965 | 93.72% | 0.94x | Cercana a la capacidad máxima | 0.00000 |
| 6 | P36 | 18 -> 14 | 0.04679 | 0.05377 | 91.29% | 0.91x | Cercana a la capacidad máxima | 0.00000 |
| 7 | P27 | 24 -> G | 0.16212 | 0.18829 | 90.28% | 0.90x | Cercana a la capacidad máxima | 0.00000 |
| 8 | P5 | 6 -> R | 0.02581 | 0.02965 | 89.94% | 0.90x | Cercana a la capacidad máxima | 0.00000 |
| 9 | P37 | 14 -> 11 | 0.07751 | 0.08743 | 89.63% | 0.90x | Cercana a la capacidad máxima | 0.00000 |
| 10 | P39 | 20 -> B | 0.02581 | 0.02965 | 89.53% | 0.90x | Cercana a la capacidad máxima | 0.00000 |
| 11 | P13 | 9 -> L | 0.11477 | 0.13188 | 89.41% | 0.89x | Cercana a la capacidad máxima | 0.00000 |
| 12 | P2 | 27 -> C | 0.04679 | 0.05377 | 89.07% | 0.89x | Cercana a la capacidad máxima | 0.00000 |
| 13 | P7 | R -> P | 0.02581 | 0.02965 | 88.18% | 0.88x | Cercana a la capacidad máxima | 0.00000 |
| 14 | P1 | 1 -> C | 0.04679 | 0.05377 | 87.60% | 0.88x | Cercana a la capacidad máxima | 0.00000 |
| 15 | P43 | 19 -> A | 0.02581 | 0.02965 | 87.47% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 16 | P4 | 6 -> Q | 0.02581 | 0.02965 | 87.40% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 17 | P12 | 9 -> 8 | 0.04679 | 0.05377 | 87.39% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 18 | P22 | L -> K | 0.11477 | 0.13188 | 87.35% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 19 | P6 | Q -> O | 0.02581 | 0.02965 | 87.20% | 0.87x | Cercana a la capacidad máxima | 0.00000 |
| 20 | P51 | 11 -> 12 | 0.02290 | 0.02965 | 78.56% | 0.79x | Cercana a la capacidad máxima | 0.00000 |
| 21 | P38 | 11 -> K | 0.06752 | 0.08743 | 77.44% | 0.77x | Cercana a la capacidad máxima | 0.00000 |
| 22 | P29 | 30 -> 29 | 0.21629 | 0.34140 | 65.76% | 0.66x | Utilización alta | 0.00000 |
| 23 | P30 | 29 -> 31 | 0.21629 | 0.34140 | 65.76% | 0.66x | Utilización alta | 0.00000 |
| 24 | P24 | 26 -> 24 | 0.07469 | 0.13188 | 58.27% | 0.58x | Utilización alta | 0.00000 |
| 25 | P21 | 8 -> K | 0.01663 | 0.02965 | 56.81% | 0.57x | Utilización alta | 0.00000 |

## 5. Estimaciones y Simulaciones Basadas en % de Flujo Máximo (Ford-Fulkerson)
| % F_max | Q_req (m³/s) | Q_adm (m³/s) | I_eq (mm/h) | Uso Sis. (%) | Máx Tub. (%) | Tub. Crítica | >100% | Pico PTAR (m³/s) | Rebose Total (m³) | Estado |
|---:|---:|---:|---:|---:|---:|:---:|---:|---:|---:|:---|
| 0% | 0.0000 | 0.0000 | 0.00 | 0.0% | 0.0% | P1 | 0 | 0.0000 | 0.00 | Sin flujo |
| 25% | 0.0898 | 0.0898 | 0.11 | 25.0% | 51.2% | P25 | 0 | 0.0898 | 0.00 | Carga baja |
| 50% | 0.1796 | 0.1796 | 0.22 | 50.0% | 102.5% | P25 | 1 | 0.1796 | 0.00 | Cercano / cuello local |
| 75% | 0.2694 | 0.2694 | 0.33 | 75.0% | 120.0% | P25 | 1 | 0.2266 | 120.40 | Cercano / cuello local |
| 100% | 0.3591 | 0.3591 | 0.44 | 100.0% | 120.0% | P25 | 1 | 0.2730 | 259.80 | Cercano / cuello local |
| 110% | 0.3951 | 0.3951 | 0.49 | 110.0% | 120.0% | P25 | 2 | 0.2915 | 317.66 | Sobrecarga parcial |
| 120% | 0.4310 | 0.4310 | 0.53 | 120.0% | 120.0% | P25 | 4 | 0.3037 | 390.88 | Rebose total (tope) |
| 150% | 0.5387 | 0.4310 | 0.67 | 120.0% | 120.0% | P25 | 4 | 0.3037 | 778.76 | Rebose total (tope) |
| 200% | 0.7183 | 0.4310 | 0.89 | 120.0% | 120.0% | P25 | 4 | 0.3037 | 1,425.22 | Rebose total (tope) |

## 6. Comparación entre Escenarios de Precipitación
| Escenario | Condición | Intensidad (mm/h) | Uso Sis. (%) | Util. Máx (%) | Razón Máx | Tubería Crítica | Críticas (>75–100%) | Sobrec. (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |
|:---:|:---|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---:|
| 1 | Dry weather | 0.0 | 0.0% | 0.00% | 0.00x | P1 | 0 | 0 | 0.0000 | 0.00 | 0.00e+00 |
| 2 | Light rain | 10.0 | 120.0% | 120.00% | 3.02x | P25 | 21 | 4 | 0.3037 | 27,962.65 | 1.55e-09 |
| 3 | Moderate rain | 30.0 | 120.0% | 120.00% | 3.02x | P25 | 21 | 4 | 0.3037 | 86,209.21 | 1.70e-09 |
| 4 | Heavy rain | 60.0 | 120.0% | 120.00% | 3.02x | P25 | 21 | 4 | 0.3037 | 173,579.05 | 3.33e-09 |
| 5 | Extreme rain | 100.0 | 120.0% | 120.00% | 3.02x | P25 | 21 | 4 | 0.3037 | 290,072.17 | 4.66e-09 |
