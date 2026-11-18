"""Paquete de simulación temporal, comparación de escenarios y reportes."""

from .models import (
    SimulationConfig,
    PipeStepState,
    NodeStepState,
    TimeStepSnapshot,
    SimulationResult,
)
from .engine import SewerSimulationEngine
from .comparison import ScenarioSummary, compare_all_scenarios
from .reporter import generate_markdown_report

__all__ = [
    "SimulationConfig",
    "PipeStepState",
    "NodeStepState",
    "TimeStepSnapshot",
    "SimulationResult",
    "SewerSimulationEngine",
    "ScenarioSummary",
    "compare_all_scenarios",
    "generate_markdown_report",
]
