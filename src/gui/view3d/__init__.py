"""Módulo de visualización hidráulica 3D nativa sobre QPainter (PySide6 puro)."""

from .basin_3d_widget import Basin3DWidget
from .elevation import ElevationProfile, TerrainCell, compute_network_elevations
from .pipe_inspector_3d import PipeInspector3DWidget
from .projection import OrbitCamera, ProjectedPoint

__all__ = [
    "Basin3DWidget",
    "ElevationProfile",
    "OrbitCamera",
    "PipeInspector3DWidget",
    "ProjectedPoint",
    "TerrainCell",
    "compute_network_elevations",
]
