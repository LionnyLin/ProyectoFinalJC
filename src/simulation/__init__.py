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
from .docx_exporter import generate_docx_report, generate_technical_document_docx

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
    "generate_docx_report",
    "generate_technical_document_docx",
]
