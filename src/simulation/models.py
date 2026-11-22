"""Modelos de datos para configuración, estado temporal y resultados de simulación."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

from src.algorithms.analysis import UtilizationCategory
from src.data_structures import PipeEdge


@dataclass(frozen=True, slots=True)
class PipeIntervention:
    """Intervención operativa temporal sobre una tubería sin mutar el grafo base."""

    pipe_id: str
    obstruction_pct: float = 0.0               # 0 = libre, 100 = cierre total
    diameter_in_override: Optional[float] = None  # Diámetro comercial alternativo (pulgadas)

    def __post_init__(self) -> None:
        if not math.isfinite(self.obstruction_pct) or not (0.0 <= self.obstruction_pct <= 100.0):
            raise ValueError(
                f"El porcentaje de obstrucción debe estar entre 0 y 100 (recibido: {self.obstruction_pct})."
            )
        if self.diameter_in_override is not None and (
            not math.isfinite(self.diameter_in_override) or self.diameter_in_override <= 0.0
        ):
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
    """Retorna `(q_max_m3s, velocity_ms, transit_time_s, diameter_in)` efectivos de un tramo.

    Escalado de Manning a tubo lleno: Q ∝ D^(8/3) y V ∝ D^(2/3); la obstrucción reduce
    la capacidad por la fracción abierta sin alterar la velocidad de referencia.
    """
    if intervention is None:
        return edge.q_max_m3s, edge.reference_velocity_ms, edge.transit_time_s, edge.diameter_in
    eff_diam_in = (
        intervention.diameter_in_override if intervention.diameter_in_override is not None else edge.diameter_in
    )
    scale_d = (eff_diam_in / edge.diameter_in) if edge.diameter_in > 0.0 else 1.0
    q_diam = edge.q_max_m3s * (scale_d ** (8.0 / 3.0))
    v_diam = edge.reference_velocity_ms * (scale_d ** (2.0 / 3.0))
    eff_q_max = q_diam * max(0.0, 1.0 - intervention.obstruction_pct / 100.0)
    eff_transit_s = (edge.length_m / v_diam) if v_diam > 0.0 else 0.0
    return eff_q_max, v_diam, eff_transit_s, eff_diam_in


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
    ingress_factor: float = 1.0            # Fracción del Método Racional que ingresa (1.0 = 100 % guía)
    dry_weather_flow_per_source_m3s: float = 0.0  # Caudal sanitario base opcional por fuente (m³/s)
    interventions: Dict[str, PipeIntervention] = field(default_factory=dict)


@dataclass(slots=True)
class PipeStepState:
    """Estado hidráulico de una tubería en el instante de reporte t."""

    pipe_id: str
    flow_m3s: float              # Caudal físicamente conducido aguas abajo (<= Qmax efectivo)
    demand_flow_m3s: float       # Caudal total demandado sobre la tubería (m³/s)
    volume_in_transit_m3: float  # Volumen actualmente viajando dentro de la tubería (m³)
    utilization_pct: float       # O_i(t) = (Q_demanda / Qmax_ef) * 100 sin recorte artificial
    category: UtilizationCategory
    excess_flow_m3s: float       # Exceso de demanda por encima de Qmax (m³/s)
    effective_q_max_m3s: Optional[float] = None    # Qmax tras intervención (None = dataset)
    effective_velocity_ms: Optional[float] = None  # Velocidad de referencia tras intervención
    is_closed: bool = False                        # Obstrucción del 100 % (sin conducción)

    @property
    def conveyed_flow_m3s(self) -> float:
        """Alias de compatibilidad: caudal físico conducido (= flow_m3s)."""
        return self.flow_m3s

    @property
    def demand_ratio_pct(self) -> float:
        """Índice de demanda (Q_demanda / Qmax_ef) × 100; coincide con utilization_pct."""
        return self.utilization_pct


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
    pipe_overloaded_minutes: Dict[str, float] = field(default_factory=dict)  # Minutos con O_i > 100 %
    peak_pipe_demand_ratio: Dict[str, float] = field(default_factory=dict)   # Máx. (Q_dem / Qmax_ef) × 100
    peak_pipe_demand_flow: Dict[str, float] = field(default_factory=dict)    # Máx. Q_demanda (m³/s)
    max_node_flooding_m3: Dict[str, float] = field(default_factory=dict)     # Rebose acumulado final por nodo


def compute_symlog_ticks(max_u_val: float) -> List[float]:
    """Calcula marcas legibles y espaciadas para ejes de utilización en escala symlog."""
    y_top = max(300.0, float(max_u_val) * 1.28)
    ticks: List[float] = [0.0]
    if max_u_val <= 650.0:
        ticks.append(50.0)
    ticks.append(100.0)
    min_ratio = 1.95 if max_u_val > 1200.0 else 1.85
    for cand in (200.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0, 20000.0, 50000.0):
        if cand > y_top * 0.96:
            break
        if cand >= ticks[-1] * min_ratio:
            ticks.append(cand)
    if ticks[-1] == 100.0 and max_u_val > 180.0:
        ticks.append(250.0 if max_u_val <= 300.0 else 500.0)
    return ticks
