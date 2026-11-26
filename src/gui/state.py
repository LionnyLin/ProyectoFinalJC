"""Estado centralizado de la aplicación GUI (Capa 1: Estado y reglas puras)."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.algorithms import MaxFlowResult, SourceAttributionResult, TraversalAnimFrame
from src.data_structures import PipeEdge
from src.io.data_loader import NetworkDataset
from src.simulation import (
    MaxFlowEstimationRow,
    PipeIntervention,
    ScenarioSummary,
    SewerSimulationEngine,
    SimulationResult,
    TimeStepSnapshot,
)


@dataclass
class AppState:
    """Modelo de estado único compartido por el orquestador y los paneles."""

    dataset: Optional[NetworkDataset] = None
    engine: Optional[SewerSimulationEngine] = None
    result: Optional[SimulationResult] = None
    baseline_result: Optional[SimulationResult] = None
    previous_result: Optional[SimulationResult] = None
    comparisons: List[ScenarioSummary] = field(default_factory=list)
    comparisons_dirty: bool = True
    max_flow_result: Optional[MaxFlowResult] = None
    max_flow_estimations: List[MaxFlowEstimationRow] = field(default_factory=list)
    max_flow_dirty: bool = True
    active_target_fmax_pct: Optional[float] = None

    current_step: int = 0
    is_playing: bool = False
    speed_label: str = "2x"
    selected_pipe_id: Optional[str] = None
    selected_node_id: Optional[str] = None

    interventions: Dict[str, PipeIntervention] = field(default_factory=dict)
    isolated_nodes: Set[str] = field(default_factory=set)
    isolated_pipes: Set[str] = field(default_factory=set)
    basin_isolated: bool = False
    inspector_trace_state: Optional[Tuple[str, str]] = None

    map_mode: str = "instant"
    view_mode: str = "2d"
    active_route_pipes: List[PipeEdge] = field(default_factory=list)
    last_traversal_alg: str = "BFS"
    anim_frames: List[TraversalAnimFrame] = field(default_factory=list)
    anim_idx: int = 0
    is_animating_traversal: bool = False

    tour_active: bool = False
    tour_step: int = 0
    source_attribution: Optional[SourceAttributionResult] = None
    last_attr_key: Optional[tuple] = None

    show_left: bool = True
    show_right: bool = True
    rail_tab: str = "sim"
    layout_tier: str = ""
    topbar_mode: str = ""
    dataset_summary_text: str = "Sin conjunto de datos cargado"

    def current_snapshot(self) -> Optional[TimeStepSnapshot]:
        """Retorna la instantánea correspondiente a `current_step`, si existe."""
        if self.result is None or not self.result.snapshots:
            return None
        idx = max(0, min(len(self.result.snapshots) - 1, self.current_step))
        return self.result.snapshots[idx]

    def global_stress_maps(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Retorna `(peak_util_global, overload_min_global, duracion_total_min)`."""
        if self.result is None or not self.result.snapshots:
            return ({}, {}, 90.0)
        dur_total = max(
            1.0,
            float(self.result.snapshots[-1].time_min),
            float(self.result.config.duration_min),
        )
        return (
            self.result.peak_pipe_utilization,
            self.result.pipe_overloaded_minutes,
            dur_total,
        )

    def diameter_overrides_map(self) -> Dict[str, float]:
        """Retorna el mapa `pipe_id -> diameter_in` de intervenciones con cambio de diámetro."""
        return {
            pid: inv.diameter_in_override
            for pid, inv in self.interventions.items()
            if inv.diameter_in_override is not None
        }

    def speed_factor(self) -> float:
        """Factor de velocidad visual para los pulsos direccionales de Manning."""
        return {"1x": 1.0, "2x": 1.35, "5x": 1.85, "10x": 2.4}.get(self.speed_label, 1.2)

    def frame_delay_ms(self) -> int:
        """Intervalo en milisegundos entre pasos durante la reproducción."""
        return {"1x": 420, "2x": 210, "5x": 85, "10x": 40}.get(self.speed_label, 200)

    def reset_for_dataset(
        self,
        dataset: NetworkDataset,
        engine: SewerSimulationEngine,
        summary_text: str,
    ) -> None:
        """Reinicia resultados, selecciones e intervenciones al cargar un nuevo dataset."""
        self.dataset = dataset
        self.engine = engine
        self.result = None
        self.baseline_result = None
        self.previous_result = None
        self.comparisons = []
        self.comparisons_dirty = True
        self.max_flow_result = None
        self.max_flow_estimations = []
        self.max_flow_dirty = True
        self.active_target_fmax_pct = None
        self.current_step = 0
        self.is_playing = False
        self.selected_pipe_id = None
        self.selected_node_id = None
        self.interventions.clear()
        self.isolated_nodes.clear()
        self.isolated_pipes.clear()
        self.basin_isolated = False
        self.inspector_trace_state = None
        self.active_route_pipes = []
        self.anim_frames = []
        self.anim_idx = 0
        self.is_animating_traversal = False
        self.tour_active = False
        self.tour_step = 0
        self.source_attribution = None
        self.last_attr_key = None
        self.dataset_summary_text = summary_text
