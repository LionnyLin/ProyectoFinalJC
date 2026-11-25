"""Tarjeta flotante y constructor de paradas del Recorrido Guiado (4 Hallazgos por escenario)."""

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.io.data_loader import NetworkDataset, PrecipitationScenario
from src.simulation import SimulationConfig, SimulationResult, TimeStepSnapshot
from .. import theme
from ..widgets import StyledButton, make_separator


@dataclass(frozen=True)
class TourStop:
    """Parada individual de la Guía de Sustentación."""

    title: str
    target_min: float
    step_idx: int
    nodes: Set[str]
    pipes: Set[str]
    desc: str
    metrics: str


def build_tour_stops(
    dataset: Optional[NetworkDataset],
    result: Optional[SimulationResult],
    selected_scenario: Optional[PrecipitationScenario] = None,
) -> List[TourStop]:
    """Construye los 4 hallazgos específicos para el escenario activo."""
    if dataset is None:
        return []
    g = dataset.graph

    def _snap_for_min(target_m: float) -> Tuple[int, Optional[TimeStepSnapshot]]:
        if not result or not result.snapshots:
            return (0, None)
        best_i = min(
            range(len(result.snapshots)),
            key=lambda i: abs(result.snapshots[i].time_min - target_m),
        )
        return (best_i, result.snapshots[best_i])

    def _endpoints(pipe_ids: List[str]) -> Set[str]:
        nodes: Set[str] = set()
        for pid in pipe_ids:
            e = g.get_pipe(pid)
            if e is not None:
                nodes.update((e.from_node, e.to_node))
        return nodes

    def _existing_pipes(*candidates: str) -> List[str]:
        return [pid for pid in candidates if g.has_pipe(pid)]

    def _max_util(snap: Optional[TimeStepSnapshot], pipe_ids: List[str]) -> float:
        if snap is None:
            return 0.0
        return max(
            (snap.pipe_states[p].utilization_pct for p in pipe_ids if p in snap.pipe_states),
            default=0.0,
        )

    def _max_dem(snap: Optional[TimeStepSnapshot], pipe_ids: List[str]) -> float:
        if snap is None:
            return 0.0
        return max(
            (snap.pipe_states[p].demand_ratio_pct / 100.0 for p in pipe_ids if p in snap.pipe_states),
            default=0.0,
        )

    def _sum_storage(snap: Optional[TimeStepSnapshot], node_ids: Tuple[str, ...]) -> float:
        if snap is None:
            return 0.0
        return sum(
            (snap.node_states[n].stored_volume_m3 for n in node_ids if n in snap.node_states),
            0.0,
        )

    def _sum_flood(snap: Optional[TimeStepSnapshot], node_ids: Tuple[str, ...]) -> float:
        if snap is None:
            return 0.0
        return sum(
            (snap.node_states[n].surface_flooding_m3 for n in node_ids if n in snap.node_states),
            0.0,
        )

    def _pipe_qud(snap: Optional[TimeStepSnapshot], pid: str) -> Tuple[float, float, float]:
        if snap is None or pid not in snap.pipe_states:
            return (0.0, 0.0, 0.0)
        ps = snap.pipe_states[pid]
        return (ps.flow_m3s, ps.utilization_pct, ps.demand_ratio_pct / 100.0)

    cfg = result.config if result else None
    sc_id = cfg.scenario_id if cfg else (selected_scenario.scenario_id if selected_scenario else 3)
    intensity = (
        cfg.intensity_mm_h if cfg else (selected_scenario.intensity_mm_h if selected_scenario else 30.0)
    )

    src_ids = g.source_ids()
    src_pipes = [e.pipe_id for s in src_ids for e in g.outgoing_pipes(s)]
    t_vals = [e.transit_time_s / 60.0 for e in g.pipes()]
    t_min_r = min(t_vals) if t_vals else 0.81
    t_max_r = max(t_vals) if t_vals else 18.05
    err4 = result.max_mass_balance_error_m3 if result else 0.0

    p_head8 = _existing_pipes("P31", "P39", "P43")
    n_head8 = _endpoints(p_head8)
    p_25 = _existing_pipes("P25")
    n_25 = _endpoints(p_25)
    p_ptar = _existing_pipes("P29", "P30")
    n_ptar = ({"31"} if g.has_node("31") else set(g.sink_ids())) | _endpoints(p_ptar)

    idx1, s1 = _snap_for_min(5.0)
    q_in1 = s1.total_source_inflow_m3s if s1 else 0.0
    stor1 = s1.total_manhole_storage_m3 if s1 else 0.0
    flood1 = s1.total_surface_flooding_m3 if s1 else 0.0

    idx2, s2 = _snap_for_min(25.0)
    u2_max = _max_util(s2, p_head8)
    d2_max = _max_dem(s2, p_head8)
    v2_stor = _sum_storage(s2, ("17", "19", "20"))
    v2_flood = _sum_flood(s2, ("17", "19", "20"))

    idx4, s4 = _snap_for_min(65.0)
    q_ptar4 = s4.total_sink_discharge_m3s if s4 else 0.0
    u_ptar4 = _max_util(s4, p_ptar)
    stor4 = s4.total_manhole_storage_m3 if s4 else 0.0
    flood4 = s4.total_surface_flooding_m3 if s4 else 0.0

    if sc_id == 1:
        idx3, s3 = _snap_for_min(40.0)
        q25, u25, _d25 = _pipe_qud(s3, "P25")
        return [
            TourStop(
                title="Tiempo seco sin escorrentía en las 8 fuentes (0 mm/h)",
                target_min=5.0,
                step_idx=idx1,
                nodes=set(src_ids),
                pipes=set(src_pipes),
                desc=(
                    "Con I = 0 mm/h y Q_san = 0 por defecto, el Método Racional genera caudal nulo "
                    "en las 8 fuentes (puede activarse Q_san opcional desde el panel izquierdo)."
                ),
                metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Tránsito: {t_min_r:.2f}–{t_max_r:.2f} min",
            ),
            TourStop(
                title='Cabeceras de 8" en reposo hidráulico',
                target_min=25.0,
                step_idx=idx2,
                nodes=n_head8,
                pipes=set(p_head8),
                desc=(
                    'Las tuberías iniciales P31, P39 y P43 (8") permanecen en banda verde (0%–25%), '
                    "sin acumulación en pozos ni rebose superficial."
                ),
                metrics=f"Util. máx: {u2_max:.2f}%  ·  Pozo/Rebose: {v2_stor:.2f}/{v2_flood:.2f} m³",
            ),
            TourStop(
                title="Convergencia sin congestión en tramo P25",
                target_min=40.0,
                step_idx=idx3,
                nodes=n_25,
                pipes=set(p_25),
                desc=(
                    'Al confluir las subcuencas sobre el pozo 23 hacia J (P25, 12"), toda la red '
                    "mantiene 100% de reserva hidráulica."
                ),
                metrics=f"P25: Q = {q25:.5f} m³/s  ·  Utilización = {u25:.2f}%",
            ),
            TourStop(
                title="Balance nulo verificado hacia PTAR Punta Canoa",
                target_min=65.0,
                step_idx=idx4,
                nodes=n_ptar,
                pipes=set(p_ptar),
                desc=(
                    'Los colectores troncales P29 y P30 (20") hacia el Nodo sumidero 31 verifican '
                    "conservación exacta de masa sin aportes no contabilizados."
                ),
                metrics=f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  P29/P30: {u_ptar4:.2f}%  ·  Err = {err4:.1e} m³",
            ),
        ]

    if sc_id == 2:
        idx3, s3 = _snap_for_min(50.0)
        q25, u25, d25 = _pipe_qud(s3, "P25")
        return [
            TourStop(
                title="Escorrentía ligera (10 mm/h) en las 8 fuentes",
                target_min=5.0,
                step_idx=idx1,
                nodes=set(src_ids),
                pipes=set(src_pipes),
                desc=(
                    "La lluvia ligera activa el Método Racional (C=0.75, A=388 ha) ponderado por "
                    "capacidad instalada o 1/8 más el caudal sanitario base."
                ),
                metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Pozo/Rebose: {stor1:.1f}/{flood1:.1f} m³",
            ),
            TourStop(
                title='Cabeceras de 8" sin congestión severa',
                target_min=25.0,
                step_idx=idx2,
                nodes=n_head8,
                pipes=set(p_head8),
                desc=(
                    'Con reparto por capacidad, P31, P39 y P43 (8") operan cerca del 48%–96% sin '
                    "desbordar sus pozos (17, 19 y 20)."
                ),
                metrics=f"Util. máx: {u2_max:.2f}% ({d2_max:.2f}×)  ·  Rebose: {v2_flood:.2f} m³",
            ),
            TourStop(
                title="Convergencia máxima en colector P25 (23 → J)",
                target_min=50.0,
                step_idx=idx3,
                nodes=n_25,
                pipes=set(p_25),
                desc=(
                    'La suma de aportes aguas arriba lleva a P25 (12") al punto de mayor exigencia '
                    "de toda la red en lluvia ligera, marcando el primer cuello local."
                ),
                metrics=f"P25: Q = {q25:.4f} m³/s  ·  Util. física = {u25:.1f}% (Dem. {d25:.2f}×)",
            ),
            TourStop(
                title="Recesión limpia hacia PTAR Punta Canoa",
                target_min=65.0,
                step_idx=idx4,
                nodes=n_ptar,
                pipes=set(p_ptar),
                desc=(
                    'Al cesar la lluvia, los colectores troncales P29 y P30 (20") evacuan la onda '
                    "descendente hacia el Nodo 31 sin saturar la troncal principal."
                ),
                metrics=f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  P29/P30: {u_ptar4:.1f}%  ·  Rebose red: {flood4:.1f} m³",
            ),
        ]

    if sc_id == 4:
        p2_pipes = _existing_pipes("P31", "P39", "P43", "P1", "P2")
        n2_nodes = _endpoints(p2_pipes)
        u_p12 = _max_util(s2, _existing_pipes("P1", "P2"))
        d_p12 = _max_dem(s2, _existing_pipes("P1", "P2"))
        p3_pipes = _existing_pipes("P23", "P25", "P28")
        n3_nodes = _endpoints(p3_pipes)
        idx3, s3 = _snap_for_min(40.0)
        _, u25, d25 = _pipe_qud(s3, "P25")
        _, u23, _ = _pipe_qud(s3, "P23")
        _, u28, _ = _pipe_qud(s3, "P28")
        p4_pipes = _existing_pipes("P29", "P30", "P3")
        n4_nodes = n_ptar | _endpoints(p4_pipes)
        return [
            TourStop(
                title="Sobrecarga temprana en las 8 fuentes (60 mm/h)",
                target_min=5.0,
                step_idx=idx1,
                nodes=set(src_ids),
                pipes=set(src_pipes),
                desc=(
                    "Con 60 mm/h, las cabeceras superan el 100% de su capacidad Qmax y "
                    "llenan los pozos de 4 m³, iniciando rebose superficial en vía."
                ),
                metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Pozos: {stor1:.1f} m³  ·  Rebose: {flood1:.1f} m³",
            ),
            TourStop(
                title='Tope físico en 8" y 10" (P1, P2) con rebose',
                target_min=25.0,
                step_idx=idx2,
                nodes=n2_nodes,
                pipes=set(p2_pipes),
                desc=(
                    "Las cabeceras conducen al límite Qmax mientras la demanda racional "
                    "supera con holgura su capacidad, derivando el excedente a rebose superficial."
                ),
                metrics=f'8": {u2_max:.1f}% ({d2_max:.2f}×)  ·  P1/P2: {u_p12:.1f}% ({d_p12:.2f}×)  ·  Rebose: {v2_flood:.0f} m³',
            ),
            TourStop(
                title='Cuello en cascada: P23, P25 y P28 (16")',
                target_min=40.0,
                step_idx=idx3,
                nodes=n3_nodes,
                pipes=set(p3_pipes),
                desc=(
                    'La congestión avanza sobre los colectores de 16" (P23 y P28) mientras el tramo '
                    'P25 (12") concentra la mayor restricción hidráulica del eje central.'
                ),
                metrics=f"P25: {u25:.1f}% ({d25:.2f}×)  ·  P23: {u23:.1f}%  ·  P28: {u28:.1f}%",
            ),
            TourStop(
                title="Límite de entrega en PTAR 31 y balance de rebose",
                target_min=65.0,
                step_idx=idx4,
                nodes=n4_nodes,
                pipes=set(p4_pipes),
                desc=(
                    "P3 y P29/P30 sostienen la descarga máxima posible hacia la PTAR 31 mientras la "
                    "masa no absorbida por la red queda contabilizada exactamente como rebose en vía."
                ),
                metrics=f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
            ),
        ]

    if sc_id == 5:
        p2_pipes = _existing_pipes("P31", "P39", "P43", "P12", "P13")
        n2_nodes = _endpoints(p2_pipes)
        _, u_p13, d_p13 = _pipe_qud(s2, "P13")
        p3_pipes = _existing_pipes("P23", "P25", "P28", "P3")
        n3_nodes = _endpoints(p3_pipes)
        idx3, s3 = _snap_for_min(40.0)
        _, u25, d25 = _pipe_qud(s3, "P25")
        _, u_p3, _ = _pipe_qud(s3, "P3")
        flood3 = s3.total_surface_flooding_m3 if s3 else 0.0
        p4_pipes = _existing_pipes("P29", "P30", "P3")
        n4_nodes = n_ptar | _endpoints(p4_pipes)
        return [
            TourStop(
                title="Aporte extremo en las 8 fuentes (100 mm/h)",
                target_min=5.0,
                step_idx=idx1,
                nodes=set(src_ids),
                pipes=set(src_pipes),
                desc=(
                    "El evento extremo satura de inmediato las cabeceras por encima de Qmax "
                    "llenando los pozos y generando escorrentía superficial por rebose."
                ),
                metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Pozos: {stor1:.1f} m³  ·  Rebose: {flood1:.1f} m³",
            ),
            TourStop(
                title='Presurización en cabeceras (8", 10" y 14")',
                target_min=25.0,
                step_idx=idx2,
                nodes=n2_nodes,
                pipes=set(p2_pipes),
                desc=(
                    "Los tubos conducen exactamente hasta Qmax mientras la utilización de demanda "
                    "supera ampliamente el 100%; el exceso rebosa en superficie sin romper la masa."
                ),
                metrics=f'8": {u2_max:.1f}% ({d2_max:.2f}×)  ·  P13: {u_p13:.1f}% ({d_p13:.2f}×)  ·  Rebose: {v2_flood:.0f} m³',
            ),
            TourStop(
                title="Saturación troncal en P25, P23, P28 y P3",
                target_min=40.0,
                step_idx=idx3,
                nodes=n3_nodes,
                pipes=set(p3_pipes),
                desc=(
                    "Los ejes colectores hacia PTAR 31 operan a capacidad física plena mientras la "
                    "vía absorbe el excedente superficial acumulado durante el aguacero."
                ),
                metrics=f"P25: {u25:.1f}% ({d25:.2f}×)  ·  P3: {u_p3:.1f}%  ·  Rebose red: {flood3:.0f} m³",
            ),
            TourStop(
                title="Descarga tope en PTAR 31 y volumen rebosado",
                target_min=65.0,
                step_idx=idx4,
                nodes=n4_nodes,
                pipes=set(p4_pipes),
                desc=(
                    "Finalizada la tormenta, PTAR 31 mantiene su caudal máximo laminado mientras la "
                    "ecuación de masa audita exactamente descarga + pozos + tránsito + rebose."
                ),
                metrics=f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
            ),
        ]

    if sc_id == 3:
        idx3, s3 = _snap_for_min(40.0)
        q25, u25, d25 = _pipe_qud(s3, "P25")
        return [
            TourStop(
                title="Inyección en las 8 alcantarillas fuente",
                target_min=5.0,
                step_idx=idx1,
                nodes=set(src_ids),
                pipes=set(src_pipes),
                desc=(
                    "Los 8 nodos fuente (1, 6, 9, 17, 18, 19, 20 y 27) inyectan el aporte del Método "
                    "Racional (C=0.75, A=388 ha) más el caudal sanitario según Manning."
                ),
                metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Tránsito: {t_min_r:.2f}–{t_max_r:.2f} min",
            ),
            TourStop(
                title='Saturación física inicial en tuberías de 8"',
                target_min=25.0,
                step_idx=idx2,
                nodes=n_head8,
                pipes=set(p_head8),
                desc=(
                    'Los tramos iniciales P31, P39 y P43 (8") operan en sobrecarga (>100% de Qmax), '
                    "llenan la capacidad de sus pozos y generan rebose superficial controlado."
                ),
                metrics=f"Util. fís: {u2_max:.1f}% ({d2_max:.2f}×)  ·  Pozo/Rebose: {v2_stor:.1f}/{v2_flood:.0f} m³",
            ),
            TourStop(
                title="Convergencia crítica en el tramo P25",
                target_min=40.0,
                step_idx=idx3,
                nodes=n_25,
                pipes=set(p_25),
                desc=(
                    "La unión de varias subcuencas sobre el pozo 23 hacia J (P25) lleva el tubo al "
                    "límite presurizado mientras la demanda supera más del doble de Qmax."
                ),
                metrics=f"P25: Q_fís = {q25:.4f} m³/s  ·  Util. = {u25:.1f}% (Dem. {d25:.2f}×)",
            ),
            TourStop(
                title="Amortiguación y descarga en PTAR Punta Canoa",
                target_min=65.0,
                step_idx=idx4,
                nodes=n_ptar,
                pipes=set(p_ptar),
                desc=(
                    'Los colectores troncales de 20" (P29 y P30) reciben la onda laminada aguas arriba '
                    "y estabilizan la entrega al Nodo sumidero 31."
                ),
                metrics=f"PTAR 31 = {q_ptar4:.4f} m³/s  ·  Rebose: {flood4:.0f} m³  ·  Err = {err4:.1e} m³",
            ),
        ]

    ranked = sorted(
        (result.peak_pipe_utilization.items() if result else []),
        key=lambda kv: (
            -kv[1],
            -(result.peak_pipe_demand_ratio.get(kv[0], 0.0) if result else 0.0),
        ),
    )
    top_head = [pid for pid, _ in ranked[:3]] or p_head8
    top_mid = [pid for pid, _ in ranked[3:6]] or p_25 or top_head
    idx3, s3 = _snap_for_min(40.0)
    return [
        TourStop(
            title=f"Inyección inicial en fuentes ({intensity:.0f} mm/h)",
            target_min=5.0,
            step_idx=idx1,
            nodes=set(src_ids),
            pipes=set(src_pipes),
            desc="Ingreso inicial por las fuentes activas de la red según el escenario seleccionado.",
            metrics=f"Q_in = {q_in1:.4f} m³/s  ·  Almacenado: {stor1:.2f} m³",
        ),
        TourStop(
            title="Tramos de mayor exigencia temprana",
            target_min=25.0,
            step_idx=idx2,
            nodes=_endpoints(top_head),
            pipes=set(top_head),
            desc=f"Evaluación de los tramos más exigidos ({', '.join(top_head)}) durante el desarrollo de la onda.",
            metrics=f"Util. máx: {_max_util(s2, top_head):.2f}%  ·  Almacenado: {s2.total_manhole_storage_m3 if s2 else 0.0:.2f} m³",
        ),
        TourStop(
            title="Propagación y convergencia intermedia",
            target_min=40.0,
            step_idx=idx3,
            nodes=_endpoints(top_mid),
            pipes=set(top_mid),
            desc=f"Seguimiento de la convergencia hidráulica en {', '.join(top_mid)} cerca del pico de tormenta.",
            metrics=f"Util. máx: {_max_util(s3, top_mid):.2f}%  ·  Almacenado: {s3.total_manhole_storage_m3 if s3 else 0.0:.2f} m³",
        ),
        TourStop(
            title="Entrega final en sumidero PTAR",
            target_min=65.0,
            step_idx=idx4,
            nodes=n_ptar,
            pipes=set(p_ptar),
            desc="Estabilización y descarga final hacia el sumidero de la red con auditoría de masa.",
            metrics=f"PTAR = {q_ptar4:.4f} m³/s  ·  Almacenado: {stor4:.2f} m³  ·  Err = {err4:.1e} m³",
        ),
    ]


class GuidedTourCard(QFrame):
    """Ficha flotante de hallazgos sobre NetworkCanvas."""

    previousRequested = Signal()
    nextRequested = Signal()
    closeRequested = Signal()

    def __init__(
        self,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        display_font: str = "Inter",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TourCard")
        self.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QFrame(self)
        hdr.setObjectName("TourHeader")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(9, 4, 4, 4)
        self.lbl_hdr = QLabel("ESC. 3 · HALLAZGO 1/4 · MIN 5", hdr)
        self.lbl_hdr.setFont(QFont(mono_font, 8, QFont.Weight.Bold))
        self.lbl_hdr.setStyleSheet(f"color: {theme.ACCENT_INK}; background: transparent;")
        hdr_lay.addWidget(self.lbl_hdr, 1)

        btn_x = QPushButton("×", hdr)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setFont(QFont(ui_font, 10, QFont.Weight.Bold))
        btn_x.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.ACCENT_INK}; border: none; padding: 0 6px; }}"
            f"QPushButton:hover {{ background-color: {theme.ACCENT_HOVER}; }}"
        )
        btn_x.clicked.connect(self.closeRequested.emit)
        hdr_lay.addWidget(btn_x)
        outer.addWidget(hdr)

        body = QWidget(self)
        body.setObjectName("TourBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(8, 6, 8, 6)
        body_lay.setSpacing(3)

        self.lbl_scenario = QLabel("", body)
        self.lbl_scenario.setWordWrap(True)
        self.lbl_scenario.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        self.lbl_scenario.setStyleSheet(f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;")
        body_lay.addWidget(self.lbl_scenario)

        self.lbl_title = QLabel("", body)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setFont(QFont(display_font, 9, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        body_lay.addWidget(self.lbl_title)

        self.lbl_desc = QLabel("", body)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setFont(QFont(ui_font, 8))
        self.lbl_desc.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        body_lay.addWidget(self.lbl_desc)

        self.lbl_metrics = QLabel("", body)
        self.lbl_metrics.setWordWrap(True)
        self.lbl_metrics.setFont(QFont(mono_font, 8, QFont.Weight.Bold))
        self.lbl_metrics.setStyleSheet(
            f"background-color: {theme.PAPER_SUBTLE}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.PAPER_BORDER}; padding: 3px 6px;"
        )
        body_lay.addWidget(self.lbl_metrics)
        outer.addWidget(body)

        outer.addWidget(make_separator("h", theme.PAPER_BORDER, 1, self))

        ftr = QFrame(self)
        ftr.setObjectName("TourFooter")
        ftr_lay = QHBoxLayout(ftr)
        ftr_lay.setContentsMargins(8, 4, 8, 4)
        ftr_lay.setSpacing(5)

        self.btn_prev = StyledButton(
            "Anterior", variant="light_secondary", font_pt=8, pad_x=7, pad_y=2, parent=ftr
        )
        self.btn_prev.clicked.connect(self.previousRequested.emit)
        ftr_lay.addWidget(self.btn_prev)

        self.btn_next = StyledButton(
            "Siguiente", variant="primary", font_pt=8, pad_x=8, pad_y=2, parent=ftr
        )
        self.btn_next.clicked.connect(self.nextRequested.emit)
        ftr_lay.addWidget(self.btn_next)

        ftr_lay.addStretch(1)

        btn_close = StyledButton(
            "Cerrar", variant="dock_secondary", font_pt=8, pad_x=7, pad_y=2, parent=ftr
        )
        btn_close.clicked.connect(self.closeRequested.emit)
        ftr_lay.addWidget(btn_close)

        outer.addWidget(ftr)

    def show_stop(
        self,
        cfg: SimulationConfig,
        stop_idx: int,
        total_stops: int,
        stop: TourStop,
        time_min: float,
    ) -> None:
        scen_es = theme.translate_scenario_name(cfg.scenario_name, compact=False)
        scen_short = theme.translate_scenario_name(cfg.scenario_name, compact=True)
        self.lbl_hdr.setText(
            f"ESC. {cfg.scenario_id} ({scen_short.upper()}) · HALLAZGO {stop_idx + 1}/{total_stops} · MIN {time_min:.0f}"
        )
        self.lbl_scenario.setText(
            f"Escenario {cfg.scenario_id}: {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
        )
        self.lbl_title.setText(stop.title)
        self.lbl_desc.setText(stop.desc)
        self.lbl_metrics.setText(stop.metrics)
        self.btn_prev.setEnabled(stop_idx > 0)
        self.btn_next.setText(
            "Finalizar" if stop_idx == total_stops - 1 else "Siguiente hallazgo"
        )
        self.show()
        self.raise_()
