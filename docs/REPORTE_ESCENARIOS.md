# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario

**Fecha de generación:** 2026-11-24 22:15:43  
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
- **Admisión local y tope físico por rebose:** Tope configurado = 120.0%. Cada fuente admite hasta $(U_{tope}/100)\cdot Q_{max,fuente}$ (0.59427 m³/s en conjunto); al llegar al tope no entra más agua, el porcentaje de uso deja de aumentar y el exceso rebosa en superficie.
- **Utilización acotada:** $O_i(t) = \min(U_{tope},\; (Q_{dem,i}(t) / Q_{max,ef,i}) \times 100)$ y $U_{sis}(t) = \min(U_{tope},\; (Q_{req}(t) / F_{max}) \times 100)$; la conducción física aguas abajo se limita a $Q_{max,ef,i}$.
- **Pozos finitos y rebose:** Capacidad máxima de pozo = 4.0 m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.
- **Nota dataset (P57):** Se conserva `P57 = 12"` (`0.08743 m³/s`) tal como figura en `DataSetBicentenario.xlsx` (el Anexo 2 gráfico del enunciado rotula `0.19`).

## 3. Resultados Globales y Conservación de Masa
- **Flujo máximo del sistema (Ford-Fulkerson):** 0.35915 m³/s
- **Uso máximo del sistema (% de F_max):** 120.00% (Demanda racional pico: 6757.54%)
- **Volumen total generado (Método Racional):** 87,369.840 m³
- **Volumen admitido en las fuentes (≤ tope local):** 2,139.363 m³
- **Volumen rebosado en entradas por tope:** 85,230.477 m³
- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** 1,033.681 m³
- **Caudal pico en PTAR Punta Canoa:** 0.3078 m³/s
- **Volumen remanente (en pozos + tránsito al cierre):** 202.648 m³
- **Rebose superficial acumulado total en vía:** 86,133.511 m³
- **Error máximo de balance de masa:** 1.921e-09 m³
- **Tuberías críticas (>75–100 %):** 20 (P1, P12, P13, P2, P22, P23, P25, P27, P28, P3, P36, P37, P38, P39, P4, P43, P5, P51, P6, P7)
- **Tuberías sobrecargadas (>100 %):** 18 (P1, P12, P13, P2, P22, P23, P25, P28, P3, P31, P36, P37, P39, P4, P43, P5, P6, P7)
- **Tiempo de cómputo:** 279.14 ms

## 4. Ranking de Tuberías por Utilización Pico
| # | Tubería | Tramo | Q_cond (m³/s) | Q_max (m³/s) | Util (%) | Razón Qmax | Estado | Exceso (m³/s) |
|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|
| 1 | P31 | 17 -> 16 | 0.02965 | 0.02965 | 120.00% | 3.45x | Capacidad excedida | 0.07260 |
| 2 | P39 | 20 -> B | 0.02965 | 0.02965 | 120.00% | 3.45x | Capacidad excedida | 0.07260 |
| 3 | P43 | 19 -> A | 0.02965 | 0.02965 | 120.00% | 3.45x | Capacidad excedida | 0.07260 |
| 4 | P25 | 23 -> J | 0.08743 | 0.08743 | 120.00% | 3.04x | Capacidad excedida | 0.17831 |
| 5 | P1 | 1 -> C | 0.05377 | 0.05377 | 120.00% | 2.44x | Capacidad excedida | 0.07742 |
| 6 | P2 | 27 -> C | 0.05377 | 0.05377 | 120.00% | 2.44x | Capacidad excedida | 0.07742 |
| 7 | P36 | 18 -> 14 | 0.05377 | 0.05377 | 120.00% | 2.44x | Capacidad excedida | 0.07742 |
| 8 | P4 | 6 -> Q | 0.02965 | 0.02965 | 120.00% | 2.32x | Capacidad excedida | 0.03926 |
| 9 | P5 | 6 -> R | 0.02965 | 0.02965 | 120.00% | 2.32x | Capacidad excedida | 0.03926 |
| 10 | P3 | C -> 31 | 0.08743 | 0.08743 | 120.00% | 1.99x | Capacidad excedida | 0.08677 |
| 11 | P37 | 14 -> 11 | 0.08743 | 0.08743 | 120.00% | 1.78x | Capacidad excedida | 0.06830 |
| 12 | P23 | K -> 23 | 0.18829 | 0.18829 | 120.00% | 1.56x | Capacidad excedida | 0.10573 |
| 13 | P12 | 9 -> 8 | 0.05377 | 0.05377 | 120.00% | 1.56x | Capacidad excedida | 0.03006 |
| 14 | P13 | 9 -> L | 0.13188 | 0.13188 | 120.00% | 1.56x | Capacidad excedida | 0.07374 |
| 15 | P28 | G -> 30 | 0.18829 | 0.18829 | 120.00% | 1.43x | Capacidad excedida | 0.08167 |
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
| 150% | 0.5387 | 0.5387 | 0.67 | 120.0% | 120.0% | P31 | 18 | 0.3078 | 703.06 | Rebose total (tope) |
| 200% | 0.7183 | 0.5943 | 0.89 | 120.0% | 120.0% | P31 | 18 | 0.3078 | 1,349.52 | Rebose total (tope) |

## 6. Comparación entre Escenarios de Precipitación
| Escenario | Condición | Intensidad (mm/h) | Uso Sis. (%) | Util. Máx (%) | Razón Máx | Tubería Crítica | Críticas (>75–100%) | Sobrec. (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |
|:---:|:---|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---:|
| 1 | Dry weather | 0.0 | 0.0% | 0.00% | 0.00x | P1 | 0 | 0 | 0.0000 | 0.00 | 0.00e+00 |
| 2 | Light rain | 10.0 | 120.0% | 120.00% | 3.45x | P31 | 20 | 18 | 0.3078 | 27,886.95 | 1.38e-09 |
| 3 | Moderate rain | 30.0 | 120.0% | 120.00% | 3.45x | P31 | 20 | 18 | 0.3078 | 86,133.51 | 1.92e-09 |
| 4 | Heavy rain | 60.0 | 120.0% | 120.00% | 3.45x | P31 | 20 | 18 | 0.3078 | 173,503.35 | 2.88e-09 |
| 5 | Extreme rain | 100.0 | 120.0% | 120.00% | 3.45x | P31 | 20 | 18 | 0.3078 | 289,996.47 | 2.79e-09 |
