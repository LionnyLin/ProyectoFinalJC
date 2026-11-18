"""Paquete de simulación temporal, comparación de escenarios y reportes."""

from .models import (
    SimulationConfig,
    PipeIntervention,
    PipeStepState,
    NodeStepState,
    TimeStepSnapshot,
    SimulationResult,
    resolve_pipe_hydraulics,
)
from .engine import SewerSimulationEngine
from .comparison import ScenarioSummary, compare_all_scenarios
from .reporter import generate_markdown_report
from .docx_exporter import generate_docx_report, generate_technical_document_docx

__all__ = [
    "SimulationConfig",
    "PipeIntervention",
    "PipeStepState",
    "NodeStepState",
    "TimeStepSnapshot",
    "SimulationResult",
    "resolve_pipe_hydraulics",
    "SewerSimulationEngine",
    "ScenarioSummary",
    "compare_all_scenarios",
    "generate_markdown_report",
    "generate_docx_report",
    "generate_technical_document_docx",
]
