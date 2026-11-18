"""Modelos de datos para configuración, estado temporal y resultados de simulación."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
from src.algorithms.analysis import UtilizationCategory
from src.data_structures import PipeEdge


@dataclass(frozen=True)
class PipeIntervention:
    """Intervención operativa temporal sobre una tubería sin mutar el grafo base."""

    pipe_id: str
    obstruction_pct: float = 0.0
    diameter_in_override: Optional[float] = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.obstruction_pct) or not (0.0 <= self.obstruction_pct <= 100.0):
            raise ValueError(
                f"El porcentaje de obstrucción debe estar entre 0 y 100 (recibido: {self.obstruction_pct})."
            )
        if self.diameter_in_override is not None:
            if not math.isfinite(self.diameter_in_override) or self.diameter_in_override <= 0.0:
                raise ValueError(
                    f"El diámetro intervenido debe ser mayor a 0 pulgadas (recibido: {self.diameter_in_override})."
                )

    @property
    def is_closed(self) -> bool:
        return self.obstruction_pct >= 100.0 - 1e-6

    @property
    def has_obstruction(self) -> bool:
        return self.obstruction_pct > 1e-6


def resolve_pipe_hydraulics(
    edge: PipeEdge, intervention: Optional[PipeIntervention]
) -> Tuple[float, float, float, float]:
    """Calcula `(q_max_m3s, velocity_ms, transit_time_s, diameter_in)` efectivos para un tramo."""
    if intervention is None:
        return (
            edge.q_max_m3s,
            edge.reference_velocity_ms,
            edge.transit_time_s,
            edge.diameter_in,
        )

    eff_diam_in = (
        intervention.diameter_in_override
        if intervention.diameter_in_override is not None
        else edge.diameter_in
    )
    scale_d = (eff_diam_in / edge.diameter_in) if edge.diameter_in > 0.0 else 1.0
    q_diam = edge.q_max_m3s * (scale_d ** (8.0 / 3.0))
    v_diam = edge.reference_velocity_ms * (scale_d ** (2.0 / 3.0))
    open_fraction = max(0.0, 1.0 - intervention.obstruction_pct / 100.0)
    eff_q_max = q_diam * open_fraction
    eff_transit_s = (edge.length_m / v_diam) if v_diam > 0.0 else 0.0
    return eff_q_max, v_diam, eff_transit_s, eff_diam_in


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
    interventions: Dict[str, PipeIntervention] = field(default_factory=dict)


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
    effective_q_max_m3s: Optional[float] = None
    effective_velocity_ms: Optional[float] = None


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
