"""Generación de reportes RF12 en Markdown y CSV (el Word vive en `docx_exporter`)."""

import csv
from datetime import datetime
import os
from typing import Dict, List, Optional

from src.algorithms.analysis import CriticalPipeRecord, rank_critical_pipes
from src.io.data_loader import NetworkDataset
from .comparison import ScenarioSummary
from .models import PipeIntervention, SimulationResult, resolve_pipe_hydraulics

MODEL_ASSUMPTIONS_TEXT = (
    "Supuestos del Modelo Computacional (Sección 11):\n"
    "1. Escorrentía (Método Racional): Q = 0.00278 · C · I · A · f_ing, con f_ing = factor de ingreso "
    "pluvial (100 % por defecto, configurable) durante la tormenta; opcionalmente se suma un caudal "
    "sanitario base Q_san por fuente (0 por defecto).\n"
    "2. Reparto en fuentes: ponderado por la capacidad Qmax efectiva saliente de cada alcantarilla "
    "(o uniforme 1/N).\n"
    "3. Capacidad máxima: Qmax se toma del dataset suministrado (Manning a tubo lleno).\n"
    "4. Tiempo de tránsito: V_i = Qmax / (π·D²/4), t_i = L_i / V_i, con eventos de llegada gestionados "
    "por PriorityQueue e integración en subpasos de ≤ 0.35·mín(t_i) acotados a [1, 15] s; "
    "los resultados son invariantes al paso de reporte Δt.\n"
    "5. Bifurcaciones: reparto proporcional a Qmax efectivo saliente (o equitativo 1/k).\n"
    "6. Utilización y sobrecarga: O_i(t) = (Q_demanda / Qmax_ef) × 100 sin tope artificial; la "
    "demanda de respaldo se drena con una escala fija de 60 s (independiente de Δt), la conducción "
    "física se limita a Qmax_ef y el exceso se almacena en el pozo (capacidad finita de 4 m³) antes "
    "de derivarse a rebose superficial, conservando la masa (error < 1e-8 m³).\n"
    "7. Intervenciones en vivo: la obstrucción (0–100 %) reduce Qmax por la fracción abierta y el "
    "cambio de diámetro comercial reescala Manning (Q ∝ D^(8/3), V ∝ D^(2/3)); al 100 % el tramo "
    "queda cerrado y la red aguas abajo puede quedar aislada de la PTAR."
)


def _split_rule_label(rule: str) -> str:
    return "Proporcional a Qmax" if rule == "proportional" else "Equitativa (1/k)"


def _source_dist_label(dist: str) -> str:
    return "Ponderada por capacidad" if dist == "capacity" else "Uniforme (1/N)"


def describe_interventions(interventions: Optional[Dict[str, PipeIntervention]]) -> str:
    """Texto `PIPE (obst. X%, Ø Y")` de las intervenciones activas ('' si no hay)."""
    return ", ".join(
        f"{pid} (obst. {inv.obstruction_pct:.0f}%"
        + (f', Ø {inv.diameter_in_override:.0f}"' if inv.diameter_in_override is not None else "")
        + ")"
        for pid, inv in sorted((interventions or {}).items())
    )


def rank_pipes_effective(dataset: NetworkDataset, result: SimulationResult) -> List[CriticalPipeRecord]:
    """Ranking completo de tuberías con Qmax efectivo, razón de demanda y exceso del pico."""
    ivs = result.config.interventions or {}
    qmax = {p.pipe_id: resolve_pipe_hydraulics(p, ivs.get(p.pipe_id))[0] for p in dataset.graph.pipes()}
    return rank_critical_pipes(
        dataset.graph, result.peak_pipe_flow, result.peak_pipe_utilization,
        pipe_qmax_overrides=qmax,
        pipe_demand_ratios_pct=result.peak_pipe_demand_ratio,
        pipe_excess_flows_m3s={
            pid: max(0.0, result.peak_pipe_demand_flow.get(pid, 0.0) - q) for pid, q in qmax.items()
        },
    )


def _source_display(dataset: NetworkDataset) -> str:
    """Ruta del dataset relativa al repositorio cuando es posible (legible y portable)."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    abs_src = os.path.abspath(dataset.source_path)
    try:
        if os.path.commonpath([repo_root, abs_src]) == repo_root:
            return os.path.relpath(abs_src, repo_root).replace("\\", "/")
    except ValueError:
        pass
    return os.path.basename(abs_src)


def generate_markdown_report(
    dataset: NetworkDataset,
    result: SimulationResult,
    comparisons: Optional[List[ScenarioSummary]],
    out_path: str,
) -> str:
    """Genera un reporte completo en Markdown y exporta el detalle tabular en CSV hermano."""
    n_nodes, n_pipes, n_src, n_sink, total_len = dataset.graph.summary()
    cfg = result.config
    ranked = rank_pipes_effective(dataset, result)
    last_snap = result.snapshots[-1] if result.snapshots else None
    iv_text = describe_interventions(cfg.interventions)

    lines: List[str] = [
        "# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario",
        "",
        f"**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Fuente de datos:** `{_source_display(dataset)}`  ",
        f"**Descarga final (Sumidero):** {', '.join(dataset.graph.sink_ids())} (PTAR Punta Canoa)  ",
        "",
        "## 1. Resumen de la Red",
        f"- **Vértices (Alcantarillas / Pozos):** {n_nodes} ({n_src} fuentes, {n_sink} sumidero)",
        f"- **Aristas dirigidas (Tuberías):** {n_pipes}",
        f"- **Longitud total de la red:** {total_len:,.2f} m ({total_len / 1000.0:.2f} km)",
        f"- **Cuenca de drenaje:** C = {dataset.basin.runoff_coefficient_c}, A = {dataset.basin.area_ha} ha",
        "",
        "## 2. Supuestos y Parámetros del Escenario Evaluado",
        f"- **Escenario:** {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.1f} mm/h)",
        f"- **Método Racional:** $Q = 0.00278 \\cdot C \\cdot I \\cdot A$ con factor de ingreso pluvial = {cfg.ingress_factor * 100:.1f}%",
        f"- **Caudal sanitario base (tiempo seco):** {cfg.dry_weather_flow_per_source_m3s:.4f} m³/s por fuente",
        f"- **Duración de simulación / lluvia:** {cfg.duration_min:.1f} min / {cfg.storm_duration_min:.1f} min ($\\Delta t$ = {cfg.dt_min:.2f} min)",
        f"- **Perfil temporal:** Uniforme constante durante {cfg.storm_duration_min:.1f} min",
        f"- **Reparto entre fuentes:** {_source_dist_label(cfg.source_distribution)} (por capacidad instalada o uniforme 1/{n_src})",
        f"- **Regla de distribución en bifurcaciones:** {_split_rule_label(cfg.split_rule)}",
        "- **Tiempo de tránsito:** $t_i = L_i / V_i$, con $V_i = Q_{max,i} / A_i$ (Manning), integrado en subpasos $\\Delta t_{sim} \\le 0.35 \\cdot \\min t_i$ acotados a [1, 15] s (resultados invariantes a $\\Delta t$).",
        "- **Utilización oficial:** $O_i(t) = (Q_{dem,i}(t) / Q_{max,ef,i}) \\times 100$ sin techo artificial; la conducción física aguas abajo se limita a $Q_{max,ef,i}$.",
        f"- **Pozos finitos y rebose:** Capacidad máxima de pozo = {cfg.max_manhole_storage_m3:.1f} m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.",
        "- **Nota dataset (P57):** Se conserva `P57 = 12\"` (`0.08743 m³/s`) tal como figura en `DataSetBicentenario.xlsx` (el Anexo 2 gráfico del enunciado rotula `0.19`).",
    ]
    if iv_text:
        lines.append(f"- **Intervenciones activas:** {iv_text}")
    lines.extend([
        "",
        "## 3. Resultados Globales y Conservación de Masa",
        f"- **Volumen total inyectado:** {result.total_inflow_m3:,.3f} m³",
        f"- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** {result.total_sink_discharge_m3:,.3f} m³",
        f"- **Caudal pico en PTAR Punta Canoa:** {result.peak_sink_discharge_m3s:.4f} m³/s",
        f"- **Volumen remanente (en pozos + tránsito al cierre):** {result.final_residual_m3:,.3f} m³",
        f"- **Rebose superficial acumulado en vía:** {result.total_surface_flooding_m3:,.3f} m³",
        f"- **Error máximo de balance de masa:** {result.max_mass_balance_error_m3:.3e} m³",
        f"- **Tuberías críticas (>75–100 %):** {len(result.ever_near_capacity_pipes)} ({', '.join(result.ever_near_capacity_pipes) or 'Ninguna'})",
        f"- **Tuberías sobrecargadas (>100 %):** {len(result.ever_overloaded_pipes)} ({', '.join(result.ever_overloaded_pipes) or 'Ninguna'})",
        f"- **Tiempo de cómputo:** {result.execution_time_ms:.2f} ms",
        "",
        "## 4. Ranking de Tuberías por Utilización Pico",
        "| # | Tubería | Tramo | Q_cond (m³/s) | Q_max (m³/s) | Util (%) | Razón Qmax | Estado | Exceso (m³/s) |",
        "|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|",
    ])
    for rec in ranked[:25]:
        lines.append(
            f"| {rec.rank} | {rec.pipe_id} | {rec.from_node} -> {rec.to_node} | "
            f"{rec.flow_m3s:.5f} | {rec.q_max_m3s:.5f} | {rec.utilization_pct:.2f}% | "
            f"{rec.demand_ratio_pct / 100.0:.2f}x | {rec.category.label} | {rec.excess_flow_m3s:.5f} |"
        )

    if comparisons:
        lines.extend([
            "",
            "## 5. Comparación entre Escenarios de Precipitación",
            "| Escenario | Condición | Intensidad (mm/h) | Util. Máx (%) | Razón Máx | Tubería Crítica | Críticas (>75–100%) | Sobrec. (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |",
            "|:---:|:---|---:|---:|---:|:---:|---:|---:|---:|---:|---:|",
        ])
        for sc in comparisons:
            lines.append(
                f"| {sc.scenario_id} | {sc.condition} | {sc.intensity_mm_h:.1f} | "
                f"{sc.max_utilization_pct:.2f}% | {sc.max_demand_ratio_pct / 100.0:.2f}x | {sc.most_critical_pipe} | "
                f"{sc.num_near_capacity_pipes} | {sc.num_overloaded_pipes} | "
                f"{sc.peak_sink_discharge_m3s:.4f} | {sc.total_surface_flooding_m3:,.2f} | "
                f"{sc.mass_balance_error_m3:.2e} |"
            )

    abs_out = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)
    with open(abs_out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    csv_path = os.path.splitext(abs_out)[0] + "_tuberias.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank", "pipe_id", "from_node", "to_node", "peak_flow_m3s", "q_max_m3s",
            "peak_utilization_pct", "peak_demand_factor", "state", "excess_flow_m3s",
            "final_utilization_pct",
        ])
        for rec in ranked:
            final_u = (
                last_snap.pipe_states[rec.pipe_id].utilization_pct
                if (last_snap is not None and rec.pipe_id in last_snap.pipe_states)
                else 0.0
            )
            w.writerow([
                rec.rank, rec.pipe_id, rec.from_node, rec.to_node,
                round(rec.flow_m3s, 6), round(rec.q_max_m3s, 6),
                round(rec.utilization_pct, 2), round(rec.demand_ratio_pct / 100.0, 3),
                rec.category.label, round(rec.excess_flow_m3s, 6), round(final_u, 2),
            ])
    return abs_out
