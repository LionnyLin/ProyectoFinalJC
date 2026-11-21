"""Modelos de datos para configuración, estado temporal y resultados de simulación."""

from dataclasses import dataclass, field
from typing import Dict, List

from src.algorithms.analysis import UtilizationCategory


@dataclass(slots=True)
class SimulationConfig:
    """Parámetros configurables de una simulación temporal."""

    scenario_id: int
    scenario_name: str
    intensity_mm_h: float
    duration_min: float = 90.0
    storm_duration_min: float = 60.0
    dt_min: float = 1.0
    split_rule: str = "proportional"       # "proportional" (por Qmax) | "equal" (1/k)
    source_distribution: str = "capacity"  # "capacity" (por Qmax saliente) | "equal" (1/N)
    max_manhole_storage_m3: float = 4.0    # Amortiguamiento en pozo antes de rebose superficial


@dataclass(slots=True)
class PipeStepState:
    """Estado hidráulico de una tubería en el instante de reporte t."""

    pipe_id: str
    flow_m3s: float              # Caudal físicamente conducido aguas abajo (<= Qmax)
    demand_flow_m3s: float       # Caudal total demandado sobre la tubería (m³/s)
    volume_in_transit_m3: float  # Volumen actualmente viajando dentro de la tubería (m³)
    utilization_pct: float       # O_i(t) = (Q_demanda / Qmax) * 100 sin recorte artificial
    category: UtilizationCategory
    excess_flow_m3s: float       # Exceso de demanda por encima de Qmax (m³/s)


@dataclass(slots=True)
class NodeStepState:
    """Estado de un pozo de inspección o alcantarilla en el instante t."""

    node_id: str
    inflow_m3s: float
    outflow_m3s: float
    stored_volume_m3: float      # Volumen retenido temporalmente en el pozo (m³)
    surface_flooding_m3: float   # Rebose superficial acumulado en este nodo (m³)
    flooding_rate_m3s: float     # Tasa de rebose durante el intervalo (m³/s)


@dataclass(slots=True)
class TimeStepSnapshot:
    """Instantánea completa de la red en un instante discreto de tiempo."""

    step_index: int
    time_min: float
    rain_intensity_mm_h: float
    total_source_inflow_m3s: float
    total_sink_discharge_m3s: float
    cumulative_inflow_m3: float
    cumulative_sink_discharge_m3: float
    total_manhole_storage_m3: float
    total_pipe_transit_m3: float
    total_surface_flooding_m3: float
    mass_balance_error_m3: float
    pipe_states: Dict[str, PipeStepState]
    node_states: Dict[str, NodeStepState]
    critical_pipe_ids: List[str] = field(default_factory=list)       # > 75 %
    near_capacity_pipe_ids: List[str] = field(default_factory=list)  # > 75 % y <= 100 %
    overloaded_pipe_ids: List[str] = field(default_factory=list)     # > 100 %


@dataclass(slots=True)
class SimulationResult:
    """Resultado consolidado de la simulación de un escenario."""

    config: SimulationConfig
    snapshots: List[TimeStepSnapshot]
    peak_pipe_utilization: Dict[str, float]
    peak_pipe_flow: Dict[str, float]
    max_manhole_storage_m3: Dict[str, float]
    peak_sink_discharge_m3s: float
    total_inflow_m3: float
    total_sink_discharge_m3: float
    final_residual_m3: float
    total_surface_flooding_m3: float
    max_mass_balance_error_m3: float
    ever_critical_pipes: List[str]
    ever_near_capacity_pipes: List[str]
    ever_overloaded_pipes: List[str]
    execution_time_ms: float
