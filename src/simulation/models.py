"""Modelos de datos para configuración, estado temporal y resultados de simulación."""

from dataclasses import dataclass, field
from typing import Dict, List
from src.algorithms.analysis import UtilizationCategory


@dataclass
class SimulationConfig:
    """Parámetros configurables de una simulación temporal."""

    scenario_id: int
    scenario_name: str
    intensity_mm_h: float
    duration_min: float = 90.0
    storm_duration_min: float = 60.0
    dt_min: float = 1.0
    ingress_factor: float = 0.025  # 2.5% ingreso pluvial a red sanitaria (ajustable 0.01..1.0)
    dry_weather_flow_per_source_m3s: float = 0.003  # Caudal sanitario base por fuente (m³/s)
    split_rule: str = "proportional"  # "proportional" (por Qmax) o "equal" (uniforme)
    hyetograph: str = "uniform"  # "uniform" (constante) o "triangular" (pico al 50%)


@dataclass
class PipeStepState:
    """Estado de una tubería en un instante de tiempo t."""

    pipe_id: str
    flow_m3s: float          # Caudal efectivo/demandado Q_i(t) (m³/s)
    conveyed_flow_m3s: float # Caudal físico transportado aguas abajo (<= Qmax)
    volume_in_transit_m3: float
    utilization_pct: float   # O_i(t) = (Q_i(t) / Qmax_i) * 100
    category: UtilizationCategory
    excess_flow_m3s: float   # Exceso por encima de Qmax (m³/s)


@dataclass
class NodeStepState:
    """Estado de un pozo/alcantarilla en un instante de tiempo t."""

    node_id: str
    inflow_m3s: float
    outflow_m3s: float
    stored_volume_m3: float  # Almacenamiento temporal por sobrecarga (m³)


@dataclass
class TimeStepSnapshot:
    """Instantánea completa de la red en el tiempo `time_min` (almacenada en LinkedList)."""

    step_index: int
    time_min: float
    rain_intensity_mm_h: float
    total_source_inflow_m3s: float
    total_sink_discharge_m3s: float
    cumulative_inflow_m3: float
    cumulative_sink_discharge_m3: float
    total_manhole_storage_m3: float
    total_pipe_transit_m3: float
    mass_balance_error_m3: float
    pipe_states: Dict[str, PipeStepState] = field(default_factory=dict)
    node_states: Dict[str, NodeStepState] = field(default_factory=dict)
    critical_pipe_ids: List[str] = field(default_factory=list)   # >= 75%
    overloaded_pipe_ids: List[str] = field(default_factory=list) # > 100%


@dataclass
class SimulationResult:
    """Resultado completo de una corrida de simulación."""

    config: SimulationConfig
    snapshots: List[TimeStepSnapshot]  # Espejo indexado de la LinkedList histórica
    peak_pipe_utilization: Dict[str, float]
    peak_pipe_flow: Dict[str, float]
    max_manhole_storage_m3: Dict[str, float]
    peak_sink_discharge_m3s: float
    total_inflow_m3: float
    total_sink_discharge_m3: float
    final_residual_m3: float
    max_mass_balance_error_m3: float
    ever_critical_pipes: List[str]
    ever_overloaded_pipes: List[str]
    execution_time_ms: float
