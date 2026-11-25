"""Paneles modulares de la interfaz PySide6 (Capa 3B)."""

from .center_panel import CenterPanel
from .charts_panel import ComparisonChartsPanel, TemporalChartsPanel
from .comparison_panel import ComparisonPanel
from .controls_panel import ControlsPanel
from .critical_panel import CriticalPipesPanel
from .inspector_panel import InspectorPanel, parse_diameter_override
from .top_bar import TopBar
from .tour_overlay import GuidedTourCard, TourStop, build_tour_stops

__all__ = [
    "CenterPanel",
    "ComparisonChartsPanel",
    "ComparisonPanel",
    "ControlsPanel",
    "CriticalPipesPanel",
    "GuidedTourCard",
    "InspectorPanel",
    "TemporalChartsPanel",
    "TopBar",
    "TourStop",
    "build_tour_stops",
    "parse_diameter_override",
]
