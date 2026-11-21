"""Motor de simulación temporal, comparación multiescenario y reportes RF12."""

from .models import (
    NodeStepState,
    PipeStepState,
    SimulationConfig,
    SimulationResult,
    TimeStepSnapshot,
)
from .engine import SewerSimulationEngine
from .comparison import ScenarioSummary, compare_all_scenarios
from .reporter import (
    MODEL_ASSUMPTIONS_TEXT,
    generate_docx_report,
    generate_markdown_report,
)

__all__ = [
    "SimulationConfig",
    "PipeStepState",
    "NodeStepState",
    "TimeStepSnapshot",
    "SimulationResult",
    "SewerSimulationEngine",
    "ScenarioSummary",
    "compare_all_scenarios",
    "MODEL_ASSUMPTIONS_TEXT",
    "generate_markdown_report",
    "generate_docx_report",
]
