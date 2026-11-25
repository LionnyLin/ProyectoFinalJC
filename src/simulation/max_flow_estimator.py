"""Estimaciones y simulaciones de capacidad y porcentaje de uso basadas en Ford-Fulkerson."""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from src.algorithms.max_flow import MaxFlowResult, ford_fulkerson_max_flow
from src.io.data_loader import NetworkDataset
from .engine import SewerSimulationEngine
from .models import SimulationConfig, SimulationResult, resolve_pipe_hydraulics

DEFAULT_FMAX_ESTIMATION_PCTS: Tuple[float, ...] = (
    0.0,
    25.0,
    50.0,
    75.0,
    100.0,
    110.0,
    120.0,
    150.0,
    200.0,
)


@dataclass
class MaxFlowEstimationRow:
    """Resultado simulado para un nivel porcentual específico respecto al flujo máximo F_max."""

    target_fmax_pct: float
    requested_flow_m3s: float
    admitted_flow_m3s: float
    inlet_overflow_rate_m3s: float
    equivalent_intensity_mm_h: float
    system_utilization_pct: float
    max_pipe_utilization_pct: float
    most_critical_pipe: str
    num_near_capacity_pipes: int
    num_overloaded_pipes: int
    peak_sink_discharge_m3s: float
    ptar_fmax_efficiency_pct: float
    total_surface_flooding_m3: float
    is_overflow_capped: bool
    state_label: str
    result: SimulationResult


def _classify_fmax_state(sys_pct: float, is_capped: bool, num_overloaded: int) -> str:
    if sys_pct <= 1e-6:
        return "Sin flujo"
    if is_capped:
        return "Rebose total (tope)"
    if sys_pct > 100.0 + 1e-6:
        return "Sobrecarga parcial"
    if num_overloaded > 0 or sys_pct > 75.0:
        return "Cercano / cuello local"
    if sys_pct > 50.0:
        return "Carga alta"
    if sys_pct > 25.0:
        return "Carga moderada"
    return "Carga baja"


def estimate_fmax_scenarios(
    dataset: NetworkDataset,
    base_config: SimulationConfig,
    target_pcts: Optional[Sequence[float]] = None,
) -> Tuple[MaxFlowResult, List[MaxFlowEstimationRow]]:
    """Evalúa y simula el comportamiento de la red ante porcentajes de F_max (Ford-Fulkerson)."""
    interventions = base_config.interventions or {}
    eff_caps = {
        p.pipe_id: resolve_pipe_hydraulics(p, interventions.get(p.pipe_id))[0]
        for p in dataset.graph.pipes()
    }
    ff_res = ford_fulkerson_max_flow(dataset.graph, pipe_capacities=eff_caps)
    f_max = ff_res.max_flow_m3s

    pct_set = {float(p) for p in (target_pcts if target_pcts is not None else DEFAULT_FMAX_ESTIMATION_PCTS)}
    if base_config.max_physical_utilization_pct is not None:
        pct_set.add(float(base_config.max_physical_utilization_pct))
    ordered_pcts = sorted(pct_set)

    denom = (
        0.00278
        * dataset.basin.runoff_coefficient_c
        * dataset.basin.area_ha
        * max(base_config.ingress_factor, 1e-12)
    )
    engine = SewerSimulationEngine(dataset.graph, dataset.basin)
    rows: List[MaxFlowEstimationRow] = []

    for pct in ordered_pcts:
        q_req = (pct / 100.0) * f_max
        eq_intensity = (q_req / denom) if denom > 1e-12 else 0.0
        cfg = SimulationConfig(
            scenario_id=base_config.scenario_id,
            scenario_name=f"Estimación {pct:.0f}% F_max",
            intensity_mm_h=eq_intensity,
            duration_min=base_config.duration_min,
            storm_duration_min=base_config.storm_duration_min,
            dt_min=base_config.dt_min,
            ingress_factor=base_config.ingress_factor,
            dry_weather_flow_per_source_m3s=0.0,
            split_rule=base_config.split_rule,
            source_distribution=base_config.source_distribution,
            max_manhole_storage_m3=base_config.max_manhole_storage_m3,
            max_physical_utilization_pct=base_config.max_physical_utilization_pct,
            use_ford_fulkerson_admission=base_config.use_ford_fulkerson_admission,
            target_fmax_pct=pct,
            interventions=dict(interventions),
        )
        res = engine.run(cfg)
        most_crit = max(
            res.peak_pipe_utilization.items(),
            key=lambda kv: (kv[1], res.peak_pipe_demand_ratio.get(kv[0], 0.0)),
            default=("N/A", 0.0),
        )
        adm_q = max((s.admitted_inflow_m3s for s in res.snapshots), default=0.0)
        inlet_ov_q = max((s.inlet_overflow_m3s for s in res.snapshots), default=0.0)
        is_capped = any(s.system_overflow_capped for s in res.snapshots)
        ptar_eff = (res.peak_sink_discharge_m3s / f_max * 100.0) if f_max > 1e-12 else 0.0
        state_lbl = _classify_fmax_state(
            res.peak_system_utilization_pct,
            is_capped,
            len(res.ever_overloaded_pipes),
        )
        rows.append(
            MaxFlowEstimationRow(
                target_fmax_pct=pct,
                requested_flow_m3s=q_req,
                admitted_flow_m3s=adm_q,
                inlet_overflow_rate_m3s=inlet_ov_q,
                equivalent_intensity_mm_h=eq_intensity,
                system_utilization_pct=res.peak_system_utilization_pct,
                max_pipe_utilization_pct=most_crit[1],
                most_critical_pipe=most_crit[0],
                num_near_capacity_pipes=len(res.ever_near_capacity_pipes),
                num_overloaded_pipes=len(res.ever_overloaded_pipes),
                peak_sink_discharge_m3s=res.peak_sink_discharge_m3s,
                ptar_fmax_efficiency_pct=ptar_eff,
                total_surface_flooding_m3=res.total_surface_flooding_m3,
                is_overflow_capped=is_capped,
                state_label=state_lbl,
                result=res,
            )
        )

    return ff_res, rows
