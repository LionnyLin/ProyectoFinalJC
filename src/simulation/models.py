"""Modelos de datos para configuración, estado temporal y resultados de simulación."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
from src.algorithms.analysis import UtilizationCategory
from src.algorithms.max_flow import MaxFlowResult
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
    ingress_factor: float = 1.0  # 100% del Método Racional según guía docente (ajustable 0.01..1.0)
    dry_weather_flow_per_source_m3s: float = 0.0  # Caudal sanitario base opcional por fuente (m³/s)
    split_rule: str = "proportional"  # "proportional" (por Qmax) o "equal" (uniforme)
    source_distribution: str = "capacity"  # "capacity" (ponderado por Qmax) o "equal" (1/N)
    max_manhole_storage_m3: float = 4.0  # Capacidad física amortiguadora por pozo antes de rebose
    max_physical_utilization_pct: Optional[float] = 120.0  # Tope físico de uso por rebose (>=100%, ej. 120%)
    use_ford_fulkerson_admission: bool = True  # Activa recorte de admisión en entradas al alcanzar tope físico
    admission_mode: str = "source_local"  # "source_local" (tope/100 * Qmax fuente) o "system_fmax" (tope/100 * F_max)
    target_fmax_pct: Optional[float] = None  # Si se define, fija la demanda de lluvia como % de F_max
    interventions: Dict[str, PipeIntervention] = field(default_factory=dict)


def compute_fmax_calibrated_ingress(
    f_max_m3s: float,
    runoff_coefficient_c: float,
    area_ha: float,
    reference_intensity_mm_h: float = 30.0,
) -> float:
    """Calcula el factor de ingreso pluvial que iguala Q_racional(I_ref) con F_max."""
    q_raw = (
        0.00278
        * float(runoff_coefficient_c)
        * float(reference_intensity_mm_h)
        * float(area_ha)
    )
    if q_raw <= 1e-12 or f_max_m3s <= 0.0:
        return 0.001
    return max(0.001, min(1.0, float(f_max_m3s) / q_raw))


@dataclass
class PipeStepState:
    """Estado de una tubería en un instante de tiempo t."""

    pipe_id: str
    flow_m3s: float          # Caudal físico conducido aguas abajo (<= Qmax, coherente con node.outflow_m3s)
    conveyed_flow_m3s: float # Caudal físico transportado aguas abajo (<= Qmax)
    volume_in_transit_m3: float
    utilization_pct: float   # Utilización física acotada al tope de rebose (<= max_physical_utilization_pct)
    category: UtilizationCategory
    excess_flow_m3s: float   # Déficit/exceso de demanda por encima de Qmax (m³/s)
    demand_flow_m3s: float = 0.0     # Caudal de demanda total intentando ingresar (m³/s)
    demand_ratio_pct: float = 0.0    # Índice de demanda = (Q_demanda / Qmax_ef) * 100 (%) sin recorte
    effective_q_max_m3s: Optional[float] = None
    effective_velocity_ms: Optional[float] = None
    is_closed: bool = False
    is_overflow_capped: bool = False
    max_flow_share_m3s: float = 0.0
    in_min_cut: bool = False


@dataclass
class NodeStepState:
    """Estado de un pozo/alcantarilla en un instante de tiempo t."""

    node_id: str
    inflow_m3s: float
    outflow_m3s: float
    stored_volume_m3: float  # Almacenamiento temporal dentro del pozo (<= max_manhole_storage_m3)
    surface_flooding_m3: float = 0.0  # Rebose superficial acumulado en vía por pozo lleno (m³)
    flooding_rate_m3s: float = 0.0    # Tasa instantánea de rebose superficial (m³/s)
    active_surface_ponding_m3: float = 0.0  # Lámina/charco superficial transitorio con recesión (m³)


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
    total_surface_flooding_m3: float = 0.0
    pipe_states: Dict[str, PipeStepState] = field(default_factory=dict)
    node_states: Dict[str, NodeStepState] = field(default_factory=dict)
    critical_pipe_ids: List[str] = field(default_factory=list)       # > 75% (cercanas + sobrecargadas)
    near_capacity_pipe_ids: List[str] = field(default_factory=list)  # > 75% y <= 100%
    overloaded_pipe_ids: List[str] = field(default_factory=list)     # > 100%
    admitted_inflow_m3s: float = 0.0
    inlet_overflow_m3s: float = 0.0
    system_max_flow_m3s: float = 0.0
    system_utilization_pct: float = 0.0
    system_demand_ratio_pct: float = 0.0
    ptar_fmax_utilization_pct: float = 0.0
    system_overflow_capped: bool = False


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
    ever_near_capacity_pipes: List[str] = field(default_factory=list)
    pipe_overloaded_minutes: Dict[str, float] = field(default_factory=dict)
    peak_pipe_demand_ratio: Dict[str, float] = field(default_factory=dict)
    peak_pipe_demand_flow: Dict[str, float] = field(default_factory=dict)
    total_surface_flooding_m3: float = 0.0
    max_node_flooding_m3: Dict[str, float] = field(default_factory=dict)
    system_max_flow_m3s: float = 0.0
    max_flow_result: Optional[MaxFlowResult] = None
    min_cut_pipes: List[str] = field(default_factory=list)
    utilization_cap_pct: Optional[float] = 120.0
    peak_system_utilization_pct: float = 0.0
    peak_system_demand_ratio_pct: float = 0.0
    total_admitted_inflow_m3: float = 0.0
    total_inlet_overflow_m3: float = 0.0
    overflow_capped_pipes: List[str] = field(default_factory=list)
    total_source_capacity_m3s: float = 0.0


def compute_symlog_ticks(max_u_val: float) -> List[float]:
    """Calcula marcas legibles y espaciadas para ejes de utilización en escala symlog."""
    y_top = max(300.0, float(max_u_val) * 1.28)
    ticks: List[float] = [0.0]
    if max_u_val <= 650.0:
        ticks.append(50.0)
    ticks.append(100.0)
    candidates = [200.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0, 20000.0, 50000.0]
    min_ratio = 1.95 if max_u_val > 1200.0 else 1.85
    for cand in candidates:
        if cand > y_top * 0.96:
            break
        if cand >= ticks[-1] * min_ratio:
            ticks.append(cand)
    if ticks[-1] == 100.0 and max_u_val > 180.0:
        ticks.append(250.0 if max_u_val <= 300.0 else 500.0)
    return ticks
