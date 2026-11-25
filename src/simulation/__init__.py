"""Paquete de simulación temporal, comparación de escenarios y reportes."""

from .models import (
    SimulationConfig,
    PipeIntervention,
    PipeStepState,
    NodeStepState,
    TimeStepSnapshot,
    SimulationResult,
    compute_fmax_calibrated_ingress,
    resolve_pipe_hydraulics,
)
from .engine import SewerSimulationEngine
from .comparison import ScenarioSummary, compare_all_scenarios
from .max_flow_estimator import (
    DEFAULT_FMAX_ESTIMATION_PCTS,
    MaxFlowEstimationRow,
    estimate_fmax_scenarios,
)
from .reporter import generate_markdown_report
from .docx_exporter import generate_docx_report, generate_technical_document_docx

__all__ = [
    "SimulationConfig",
    "PipeIntervention",
    "PipeStepState",
    "NodeStepState",
    "TimeStepSnapshot",
    "SimulationResult",
    "compute_fmax_calibrated_ingress",
    "resolve_pipe_hydraulics",
    "SewerSimulationEngine",
    "ScenarioSummary",
    "compare_all_scenarios",
    "DEFAULT_FMAX_ESTIMATION_PCTS",
    "MaxFlowEstimationRow",
    "estimate_fmax_scenarios",
    "generate_markdown_report",
    "generate_docx_report",
    "generate_technical_document_docx",
]
