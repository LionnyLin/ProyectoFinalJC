"""Comparador de múltiples escenarios de precipitación."""

from dataclasses import dataclass
from typing import List
from src.io.data_loader import NetworkDataset
from .engine import SewerSimulationEngine
from .models import SimulationConfig, SimulationResult


@dataclass
class ScenarioSummary:
    """Resumen comparativo de un escenario ejecutado."""

    scenario_id: int
    condition: str
    intensity_mm_h: float
    max_utilization_pct: float
    most_critical_pipe: str
    num_critical_pipes: int      # > 75% (total crítico)
    num_overloaded_pipes: int    # > 100%
    peak_sink_discharge_m3s: float
    total_inflow_m3: float
    total_sink_discharge_m3: float
    max_stored_surcharge_m3: float
    mass_balance_error_m3: float
    result: SimulationResult
    max_demand_ratio_pct: float = 0.0
    total_surface_flooding_m3: float = 0.0
    num_near_capacity_pipes: int = 0  # > 75% y <= 100%
    system_max_flow_m3s: float = 0.0
    peak_system_utilization_pct: float = 0.0
    peak_system_demand_ratio_pct: float = 0.0
    total_admitted_inflow_m3: float = 0.0
    total_inlet_overflow_m3: float = 0.0


def compare_all_scenarios(
    dataset: NetworkDataset,
    base_config: SimulationConfig,
) -> List[ScenarioSummary]:
    """Ejecuta todos los escenarios del dataset bajo la misma configuración base."""
    engine = SewerSimulationEngine(dataset.graph, dataset.basin)
    summaries: List[ScenarioSummary] = []

    for sc in dataset.scenarios:
        cfg = SimulationConfig(
            scenario_id=sc.scenario_id,
            scenario_name=sc.condition,
            intensity_mm_h=sc.intensity_mm_h,
            duration_min=base_config.duration_min,
            storm_duration_min=base_config.storm_duration_min,
            dt_min=base_config.dt_min,
            ingress_factor=base_config.ingress_factor,
            dry_weather_flow_per_source_m3s=base_config.dry_weather_flow_per_source_m3s,
            split_rule=base_config.split_rule,
            source_distribution=base_config.source_distribution,
            max_manhole_storage_m3=base_config.max_manhole_storage_m3,
            max_physical_utilization_pct=base_config.max_physical_utilization_pct,
            use_ford_fulkerson_admission=base_config.use_ford_fulkerson_admission,
            target_fmax_pct=None,
            interventions=dict(base_config.interventions),
        )
        res = engine.run(cfg)
        most_crit = max(
            res.peak_pipe_utilization.items(),
            key=lambda kv: (kv[1], res.peak_pipe_demand_ratio.get(kv[0], 0.0)),
            default=("N/A", 0.0),
        )
        max_dem = max(res.peak_pipe_demand_ratio.values(), default=0.0)
        summaries.append(
            ScenarioSummary(
                scenario_id=sc.scenario_id,
                condition=sc.condition,
                intensity_mm_h=sc.intensity_mm_h,
                max_utilization_pct=most_crit[1],
                most_critical_pipe=most_crit[0],
                num_critical_pipes=len(res.ever_critical_pipes),
                num_overloaded_pipes=len(res.ever_overloaded_pipes),
                peak_sink_discharge_m3s=res.peak_sink_discharge_m3s,
                total_inflow_m3=res.total_inflow_m3,
                total_sink_discharge_m3=res.total_sink_discharge_m3,
                max_stored_surcharge_m3=max(
                    (s.total_manhole_storage_m3 for s in res.snapshots),
                    default=0.0,
                ),
                mass_balance_error_m3=res.max_mass_balance_error_m3,
                result=res,
                max_demand_ratio_pct=max_dem,
                total_surface_flooding_m3=res.total_surface_flooding_m3,
                num_near_capacity_pipes=len(res.ever_near_capacity_pipes),
                system_max_flow_m3s=res.system_max_flow_m3s,
                peak_system_utilization_pct=res.peak_system_utilization_pct,
                peak_system_demand_ratio_pct=res.peak_system_demand_ratio_pct,
                total_admitted_inflow_m3=res.total_admitted_inflow_m3,
                total_inlet_overflow_m3=res.total_inlet_overflow_m3,
            )
        )

    return summaries
