"""Motor de simulación temporal, comparación multiescenario y reportes RF12."""

from .models import (
    NodeStepState,
    PipeIntervention,
    PipeStepState,
    SimulationConfig,
    SimulationResult,
    TimeStepSnapshot,
    compute_symlog_ticks,
    resolve_pipe_hydraulics,
)
from .engine import SewerSimulationEngine
from .comparison import ScenarioSummary, compare_all_scenarios
from .reporter import MODEL_ASSUMPTIONS_TEXT, generate_markdown_report
from .docx_exporter import generate_docx_report, generate_technical_document_docx

__all__ = [
    "SimulationConfig",
    "PipeIntervention",
    "resolve_pipe_hydraulics",
    "compute_symlog_ticks",
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
    "generate_technical_document_docx",
]
