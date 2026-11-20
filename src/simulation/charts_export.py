"""Script de generación de figuras Matplotlib dimensionadas a una columna (3.5 × 2.8 in)."""

import os
from typing import List
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.io.data_loader import load_dataset
from src.simulation.comparison import ScenarioSummary, compare_all_scenarios
from src.simulation.models import SimulationConfig, SimulationResult

SINGLE_COL_FIGSIZE = (3.5, 2.8)
DPI = 300


def _apply_publication_rc() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 7.5,
        "axes.titlesize": 8.2,
        "axes.titleweight": "bold",
        "axes.labelsize": 7.5,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
        "legend.fontsize": 6.5,
        "axes.edgecolor": "#475569",
        "axes.linewidth": 0.7,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })


def generate_single_column_figures(
    result: SimulationResult,
    comparisons: List[ScenarioSummary],
    out_dir: str,
) -> List[str]:
    """Genera 3 figuras PNG en español a 3.5 × 2.8 in (300 DPI) para columnas Word."""
    _apply_publication_rc()
    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []

    # Figura 1: Balance temporal de caudales (Entrada vs PTAR 31)
    fig1, ax1 = plt.subplots(figsize=SINGLE_COL_FIGSIZE, dpi=DPI, constrained_layout=True)
    ts = [s.time_min for s in result.snapshots]
    q_in = [s.total_source_inflow_m3s for s in result.snapshots]
    q_ptar = [s.total_sink_discharge_m3s for s in result.snapshots]
    q_flood = [0.0]
    for idx in range(1, len(result.snapshots)):
        dt_s = max((ts[idx] - ts[idx - 1]) * 60.0, 1e-6)
        dv = max(0.0, result.snapshots[idx].total_surface_flooding_m3 - result.snapshots[idx - 1].total_surface_flooding_m3)
        q_flood.append(dv / dt_s)
    ax1.plot(ts, q_in, label="Entrada total (fuentes)", color="#3B153A", linewidth=1.6)
    if any(v > 1e-6 for v in q_flood):
        ax1.plot(ts, q_flood, label="Rebose superficial", color="#dc2626", linestyle="--", linewidth=1.3)
    ax1.plot(ts, q_ptar, label="Descarga PTAR (nodo 31)", color="#059669", linewidth=1.7)
    ax1.fill_between(ts, q_ptar, color="#059669", alpha=0.12)
    ax1.set_title(
        f"Hidrograma Escenario {result.config.scenario_id} ({result.config.intensity_mm_h:.0f} mm/h)"
    )
    ax1.set_xlabel("Tiempo (min)")
    ax1.set_ylabel("Caudal (m³/s)")
    max_q = max(q_in + q_ptar + q_flood, default=1.0)
    ax1.set_ylim(0.0, max(0.05, max_q * 1.32))
    ax1.grid(True)
    ax1.legend(loc="upper right", frameon=True)
    p1 = os.path.join(out_dir, "fig1_hidrograma_ptar.png")
    fig1.savefig(p1, dpi=DPI)
    plt.close(fig1)
    paths.append(p1)

    # Figura 2: Top 5 tuberías con mayor utilización
    fig2, ax2 = plt.subplots(figsize=SINGLE_COL_FIGSIZE, dpi=DPI, constrained_layout=True)
    top5 = sorted(
        result.peak_pipe_utilization.items(),
        key=lambda kv: (kv[1], result.peak_pipe_demand_ratio.get(kv[0], 0.0)),
        reverse=True,
    )[:5]
    palette = ["#991b1b", "#dc2626", "#ea580c", "#ca8a04", "#0284c7"]
    for idx, (pid, pk) in enumerate(top5):
        utils = [s.pipe_states[pid].utilization_pct for s in result.snapshots]
        lbl = f"{pid} ({pk:.0f}%)"
        ax2.plot(ts, utils, label=lbl, color=palette[idx % len(palette)], linewidth=1.4)
    ax2.axhline(100.0, color="#991b1b", linestyle="--", linewidth=1.1, label="Cap. 100%")
    max_u = max((pk for _, pk in top5), default=100.0)
    ax2.set_ylim(0.0, max(135.0, max_u * 1.36))
    ax2.set_title("Utilización — Top 5 Tuberías Críticas")
    ax2.set_xlabel("Tiempo (min)")
    ax2.set_ylabel("Utilización (%)")
    ax2.grid(True)
    ax2.legend(loc="upper right", ncol=2, frameon=True)
    p2 = os.path.join(out_dir, "fig2_top5_utilizacion.png")
    fig2.savefig(p2, dpi=DPI)
    plt.close(fig2)
    paths.append(p2)

    # Figura 3: Comparación multiescenario
    fig3, ax3 = plt.subplots(figsize=SINGLE_COL_FIGSIZE, dpi=DPI, constrained_layout=True)
    labels = [f"E{s.scenario_id}\n{s.intensity_mm_h:.0f}mm" for s in comparisons]
    crit = [s.num_near_capacity_pipes for s in comparisons]
    over = [s.num_overloaded_pipes for s in comparisons]
    x = list(range(len(labels)))
    w = 0.36
    ax3.bar([i - w / 2 for i in x], crit, width=w, label="Críticas (>75–100%)", color="#ef4444")
    ax3.bar([i + w / 2 for i in x], over, width=w, label="Sobrecargadas (>100%)", color="#991b1b")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels)
    max_b = max(crit + over, default=10)
    ax3.set_ylim(0.0, max(5.0, max_b * 1.28))
    ax3.set_title("Comparación de Escenarios de Precipitación")
    ax3.set_ylabel("Número de tuberías")
    ax3.grid(True, axis="y")
    ax3.legend(loc="upper left", frameon=True)
    p3 = os.path.join(out_dir, "fig3_comparacion_escenarios.png")
    fig3.savefig(p3, dpi=DPI)
    plt.close(fig3)
    paths.append(p3)

    return paths


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ds = load_dataset(os.path.join(base_dir, "data", "DataSetBicentenario.xlsx"))
    base_cfg = SimulationConfig(scenario_id=3, scenario_name="Moderate rain", intensity_mm_h=30.0)
    comps = compare_all_scenarios(ds, base_cfg)
    out = os.path.join(base_dir, "docs", "figuras")
    primary = comps[2] if len(comps) > 2 else comps[0]
    generated = generate_single_column_figures(primary.result, comps, out)
    for g in generated:
        print("Figura 3.5x2.8 in generada:", g)
