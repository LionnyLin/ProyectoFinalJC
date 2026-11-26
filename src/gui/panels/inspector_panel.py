"""Panel derecho — Pestaña Inspector (ficha técnica, intervenciones en vivo y fuentes)."""

import math
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.algorithms import classify_overload_persistence
from src.data_structures import PipeEdge
from src.io.data_loader import NetworkDataset
from src.simulation import PipeIntervention, SimulationResult, TimeStepSnapshot, resolve_pipe_hydraulics
from .. import theme
from ..view3d import PipeInspector3DWidget
from ..widgets import (
    COMMERCIAL_DIAMETERS_IN,
    SourceBarWidget,
    StyledButton,
    blocked_signals,
    make_separator,
)


def parse_diameter_override(raw: str, base_diam_in: float) -> Optional[float]:
    """Convierte el texto de diámetro comercial o personalizado a pulgadas."""
    text = raw.strip()
    if not text or text.lower().startswith("original"):
        return None
    cleaned = text.replace('"', "").replace("pulg", "").strip()
    val = float(cleaned)
    if not math.isfinite(val) or val <= 0.0 or val > 120.0:
        raise ValueError("El diámetro debe estar entre > 0 y 120 pulgadas.")
    if abs(val - base_diam_in) < 1e-6:
        return None
    return val


class InspectorPanel(QWidget):
    """Pestaña Inspector: acciones topológicas, intervenciones en vivo, fuentes y ficha."""

    focusSelectedRequested = Signal()
    toggleBasinIsolationRequested = Signal()
    toggleNodeTraceRequested = Signal(str)
    applyInterventionRequested = Signal(float, str)
    restorePipeRequested = Signal()
    restoreAllRequested = Signal()
    pipe3dToggled = Signal(bool)

    def __init__(
        self,
        icons: Dict[str, QIcon],
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        display_font: str = "Inter",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._display_font = display_font
        self._current_source_shares: List[Tuple[str, float]] = []
        self._pipe_3d_expanded: bool = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Barra de acciones topológicas
        self.inspector_actions = QFrame(self)
        self.inspector_actions.setObjectName("InspectorActionsDock")
        act_lay = QHBoxLayout(self.inspector_actions)
        act_lay.setContentsMargins(8, 5, 8, 5)
        act_lay.setSpacing(4)

        self.btn_focus_selected = StyledButton(
            " Centrar",
            variant="light_secondary",
            icon=icons["crosshair_light"],
            icon_size=12,
            font_pt=8,
            pad_x=7,
            pad_y=3,
            parent=self.inspector_actions,
        )
        self.btn_focus_selected.clicked.connect(self.focusSelectedRequested.emit)
        act_lay.addWidget(self.btn_focus_selected)

        self.btn_isolate_basin = StyledButton(
            "Aislar cuenca",
            variant="light_secondary",
            font_pt=8,
            pad_x=8,
            pad_y=3,
            parent=self.inspector_actions,
        )
        self.btn_isolate_basin.clicked.connect(self.toggleBasinIsolationRequested.emit)
        act_lay.addWidget(self.btn_isolate_basin)

        self.btn_insp_upstream = StyledButton(
            "Aguas arriba",
            variant="light_secondary",
            font_pt=8,
            pad_x=7,
            pad_y=3,
            parent=self.inspector_actions,
        )
        self.btn_insp_upstream.clicked.connect(
            lambda: self.toggleNodeTraceRequested.emit("up")
        )
        act_lay.addWidget(self.btn_insp_upstream)

        self.btn_insp_downstream = StyledButton(
            "Aguas abajo",
            variant="light_secondary",
            font_pt=8,
            pad_x=7,
            pad_y=3,
            parent=self.inspector_actions,
        )
        self.btn_insp_downstream.clicked.connect(
            lambda: self.toggleNodeTraceRequested.emit("down")
        )
        act_lay.addWidget(self.btn_insp_downstream)
        act_lay.addStretch(1)

        self._actions_sep = make_separator("h", theme.DOCK_BORDER, 1, self)
        self.inspector_actions.setVisible(False)
        self._actions_sep.setVisible(False)
        lay.addWidget(self.inspector_actions)
        lay.addWidget(self._actions_sep)

        # 2. Tarjeta de intervención en vivo sobre tubería
        self.pipe_intervention_card = QFrame(self)
        self.pipe_intervention_card.setObjectName("InspectorSubCard")
        int_lay = QVBoxLayout(self.pipe_intervention_card)
        int_lay.setContentsMargins(8, 6, 8, 6)
        int_lay.setSpacing(4)

        int_hdr = QHBoxLayout()
        lbl_int = QLabel("Intervención en vivo", self.pipe_intervention_card)
        lbl_int.setFont(QFont(display_font, 8, QFont.Weight.Bold))
        lbl_int.setStyleSheet(f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;")
        int_hdr.addWidget(lbl_int)
        int_hdr.addStretch(1)

        self.lbl_active_interventions = QLabel("", self.pipe_intervention_card)
        self.lbl_active_interventions.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        self.lbl_active_interventions.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        int_hdr.addWidget(self.lbl_active_interventions)

        self.btn_restore_all = StyledButton(
            "Restaurar red",
            variant="light_secondary",
            font_pt=7,
            pad_x=6,
            pad_y=1,
            parent=self.pipe_intervention_card,
        )
        self.btn_restore_all.clicked.connect(self.restoreAllRequested.emit)
        self.btn_restore_all.setVisible(False)
        int_hdr.addWidget(self.btn_restore_all)
        int_lay.addLayout(int_hdr)

        row_obst = QHBoxLayout()
        row_obst.setSpacing(6)
        lbl_ob = QLabel("Obstrucción (%)", self.pipe_intervention_card)
        lbl_ob.setFont(QFont(ui_font, 8))
        row_obst.addWidget(lbl_ob)

        self.scale_obstruction = QSlider(Qt.Orientation.Horizontal, self.pipe_intervention_card)
        self.scale_obstruction.setRange(0, 100)
        self.scale_obstruction.setSingleStep(5)
        self.scale_obstruction.setPageStep(5)
        self.scale_obstruction.setValue(0)
        self.scale_obstruction.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scale_obstruction.valueChanged.connect(self._on_obstruction_changed)
        row_obst.addWidget(self.scale_obstruction, 1)

        self.lbl_obst_val = QLabel("0%", self.pipe_intervention_card)
        self.lbl_obst_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_obst_val.setFixedWidth(44)
        self.lbl_obst_val.setFont(QFont(mono_font, 8, QFont.Weight.Bold))
        self.lbl_obst_val.setStyleSheet(
            f"background-color: {theme.PAPER_BG}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.DOCK_BORDER}; padding: 1px 4px;"
        )
        row_obst.addWidget(self.lbl_obst_val)
        int_lay.addLayout(row_obst)

        row_diam = QHBoxLayout()
        row_diam.setSpacing(6)
        lbl_dm = QLabel("Diámetro", self.pipe_intervention_card)
        lbl_dm.setFont(QFont(ui_font, 8))
        row_diam.addWidget(lbl_dm)

        self.lbl_diam_current = QLabel("Actual: -", self.pipe_intervention_card)
        self.lbl_diam_current.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        self.lbl_diam_current.setStyleSheet(
            f"background-color: {theme.PAPER_BG}; color: {theme.ACCENT_TEXT_ON_LIGHT}; "
            f"border: 1px solid {theme.PAPER_BORDER}; padding: 1px 5px;"
        )
        row_diam.addWidget(self.lbl_diam_current)
        row_diam.addStretch(1)

        self.combo_diam_override = QComboBox(self.pipe_intervention_card)
        self.combo_diam_override.setEditable(True)
        self.combo_diam_override.addItems(COMMERCIAL_DIAMETERS_IN)
        self.combo_diam_override.setMinimumWidth(112)
        row_diam.addWidget(self.combo_diam_override)
        int_lay.addLayout(row_diam)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(4)
        btn_apply = StyledButton(
            "Aplicar y re-simular",
            variant="primary",
            font_pt=8,
            pad_x=8,
            pad_y=3,
            parent=self.pipe_intervention_card,
        )
        btn_apply.clicked.connect(self._emit_apply_intervention)
        row_btns.addWidget(btn_apply, 1)

        btn_restore_pipe = StyledButton(
            "Restaurar tramo",
            variant="dock_secondary",
            font_pt=8,
            pad_x=7,
            pad_y=3,
            parent=self.pipe_intervention_card,
        )
        btn_restore_pipe.clicked.connect(self.restorePipeRequested.emit)
        row_btns.addWidget(btn_restore_pipe)
        int_lay.addLayout(row_btns)

        self._int_sep = make_separator("h", theme.DOCK_BORDER, 1, self)
        self.pipe_intervention_card.setVisible(False)
        self._int_sep.setVisible(False)
        lay.addWidget(self.pipe_intervention_card)
        lay.addWidget(self._int_sep)

        # 2b. Tarjeta colapsable de Visor 3D de tramo
        self.pipe_3d_card = QFrame(self)
        self.pipe_3d_card.setObjectName("InspectorSubCard")
        p3d_lay = QVBoxLayout(self.pipe_3d_card)
        p3d_lay.setContentsMargins(8, 5, 8, 6)
        p3d_lay.setSpacing(4)

        p3d_hdr = QHBoxLayout()
        p3d_hdr.setContentsMargins(0, 0, 0, 0)
        p3d_hdr.setSpacing(6)
        self.btn_toggle_pipe_3d = StyledButton(
            "Visor 3D de tramo ▾",
            variant="light_secondary",
            font_pt=8,
            pad_x=6,
            pad_y=2,
            parent=self.pipe_3d_card,
        )
        self.btn_toggle_pipe_3d.clicked.connect(self._toggle_pipe_3d)
        p3d_hdr.addWidget(self.btn_toggle_pipe_3d)
        p3d_hdr.addStretch(1)

        self.lbl_pipe_3d_hint = QLabel("Arrastrar: rotar · Doble clic: reset", self.pipe_3d_card)
        self.lbl_pipe_3d_hint.setFont(QFont(mono_font, 7))
        self.lbl_pipe_3d_hint.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        p3d_hdr.addWidget(self.lbl_pipe_3d_hint)
        p3d_lay.addLayout(p3d_hdr)

        self.pipe_inspector_3d = PipeInspector3DWidget(
            ui_font=ui_font,
            mono_font=mono_font,
            parent=self.pipe_3d_card,
        )
        p3d_lay.addWidget(self.pipe_inspector_3d)

        self._pipe_3d_sep = make_separator("h", theme.DOCK_BORDER, 1, self)
        self.pipe_3d_card.setVisible(False)
        self._pipe_3d_sep.setVisible(False)
        lay.addWidget(self.pipe_3d_card)
        lay.addWidget(self._pipe_3d_sep)

        # 3. Tarjeta de composición por fuente aportante
        self.source_attribution_card = QFrame(self)
        self.source_attribution_card.setObjectName("InspectorSubCard")
        src_lay = QVBoxLayout(self.source_attribution_card)
        src_lay.setContentsMargins(8, 6, 8, 6)
        src_lay.setSpacing(3)

        src_hdr = QHBoxLayout()
        lbl_src = QLabel("Composición por Fuente Aportante", self.source_attribution_card)
        lbl_src.setFont(QFont(display_font, 8, QFont.Weight.Bold))
        lbl_src.setStyleSheet(f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;")
        src_hdr.addWidget(lbl_src)
        src_hdr.addStretch(1)

        self.lbl_source_entity = QLabel("", self.source_attribution_card)
        self.lbl_source_entity.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        self.lbl_source_entity.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        src_hdr.addWidget(self.lbl_source_entity)
        src_lay.addLayout(src_hdr)

        self.source_bar = SourceBarWidget(mono_font, self.source_attribution_card)
        src_lay.addWidget(self.source_bar)

        self.lbl_source_breakdown = QLabel("", self.source_attribution_card)
        self.lbl_source_breakdown.setWordWrap(True)
        self.lbl_source_breakdown.setFont(QFont(mono_font, 8))
        self.lbl_source_breakdown.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        src_lay.addWidget(self.lbl_source_breakdown)

        self._src_sep = make_separator("h", theme.DOCK_BORDER, 1, self)
        self.source_attribution_card.setVisible(False)
        self._src_sep.setVisible(False)
        lay.addWidget(self.source_attribution_card)
        lay.addWidget(self._src_sep)

        # 4. Ficha técnica en vitela (#FFFFE3)
        self.txt_inspector = QTextEdit(self)
        self.txt_inspector.setObjectName("InspectorText")
        self.txt_inspector.setReadOnly(True)
        lay.addWidget(self.txt_inspector, 1)

        self._fmt_heading = QTextCharFormat()
        self._fmt_heading.setFont(QFont(display_font, 10, QFont.Weight.Bold))
        self._fmt_heading.setForeground(QColor(theme.ACCENT_TEXT_ON_LIGHT))

        self._fmt_section = QTextCharFormat()
        self._fmt_section.setFont(QFont(display_font, 9, QFont.Weight.Bold))
        self._fmt_section.setForeground(QColor(theme.INK_PRIMARY))

        self._fmt_muted = QTextCharFormat()
        self._fmt_muted.setFont(QFont(mono_font, 8))
        self._fmt_muted.setForeground(QColor(theme.INK_MUTED))

        self._fmt_alert = QTextCharFormat()
        self._fmt_alert.setFont(QFont(mono_font, 9, QFont.Weight.Bold))
        self._fmt_alert.setForeground(QColor(theme.STATUS_ERR_LIGHT))

        self._fmt_normal = QTextCharFormat()
        self._fmt_normal.setFont(QFont(mono_font, 9))
        self._fmt_normal.setForeground(QColor(theme.INK_PRIMARY))

    def _on_obstruction_changed(self, value: int) -> None:
        self.lbl_obst_val.setText(f"{int(value)}%")

    def _emit_apply_intervention(self) -> None:
        self.applyInterventionRequested.emit(
            float(self.scale_obstruction.value()),
            self.combo_diam_override.currentText(),
        )

    def set_obstruction_pct(self, pct: float) -> None:
        val = max(0, min(100, int(round(pct))))
        with blocked_signals(self.scale_obstruction):
            self.scale_obstruction.setValue(val)
        self.lbl_obst_val.setText(f"{val}%")

    def set_diameter_override_text(self, text: str) -> None:
        self.combo_diam_override.setCurrentText(text)

    def sync_intervention_controls(
        self,
        edge: Optional[PipeEdge],
        intervention: Optional[PipeIntervention],
    ) -> None:
        if edge is None:
            return
        eff_diam = (
            intervention.diameter_in_override
            if (intervention is not None and intervention.diameter_in_override is not None)
            else edge.diameter_in
        )
        self.lbl_diam_current.setText(f'Actual: {eff_diam:.0f}" ({eff_diam * 0.0254:.3f} m)')
        orig_label = f'Original ({edge.diameter_in:.0f}")'
        with blocked_signals(self.combo_diam_override):
            self.combo_diam_override.clear()
            self.combo_diam_override.addItems([orig_label] + COMMERCIAL_DIAMETERS_IN[1:])
            if intervention is None:
                self.combo_diam_override.setCurrentText(orig_label)
            elif intervention.diameter_in_override is None:
                self.combo_diam_override.setCurrentText(orig_label)
            else:
                self.combo_diam_override.setCurrentText(f'{intervention.diameter_in_override:g}"')

        if intervention is None:
            self.set_obstruction_pct(0.0)
        else:
            self.set_obstruction_pct(round(intervention.obstruction_pct))

    def _toggle_pipe_3d(self) -> None:
        self.set_pipe_3d_expanded(not self._pipe_3d_expanded)
        self.pipe3dToggled.emit(self._pipe_3d_expanded)

    def is_pipe_3d_expanded(self) -> bool:
        return self._pipe_3d_expanded

    def set_pipe_3d_expanded(self, expanded: bool) -> None:
        self._pipe_3d_expanded = bool(expanded)
        self.pipe_inspector_3d.setVisible(self._pipe_3d_expanded)
        self.lbl_pipe_3d_hint.setVisible(self._pipe_3d_expanded)
        self.btn_toggle_pipe_3d.setText(
            "Visor 3D de tramo ▾" if self._pipe_3d_expanded else "Visor 3D de tramo ▸"
        )

    def update_pipe_3d(
        self,
        edge: Optional[PipeEdge],
        pipe_state,
        upstream_node_state,
        intervention: Optional[PipeIntervention],
        max_manhole_storage_m3: float = 4.0,
    ) -> None:
        self.pipe_inspector_3d.update_state(
            edge,
            pipe_state,
            upstream_node_state,
            intervention,
            max_manhole_storage_m3=max_manhole_storage_m3,
        )

    def sync_action_bars(
        self,
        *,
        sel_kind: str,
        n_interventions: int,
        basin_isolated: bool,
        trace_dir: Optional[str],
    ) -> None:
        has_sel = sel_kind != "none"
        self.inspector_actions.setVisible(has_sel)
        self._actions_sep.setVisible(has_sel)
        self.btn_insp_upstream.setVisible(sel_kind == "node")
        self.btn_insp_downstream.setVisible(sel_kind == "node")

        self.pipe_intervention_card.setVisible(sel_kind == "pipe")
        self._int_sep.setVisible(sel_kind == "pipe")
        self.pipe_3d_card.setVisible(sel_kind == "pipe")
        self._pipe_3d_sep.setVisible(sel_kind == "pipe")

        self.source_attribution_card.setVisible(has_sel)
        self._src_sep.setVisible(has_sel)

        self.btn_isolate_basin.set_variant("primary" if basin_isolated else "light_secondary")
        self.btn_insp_upstream.set_variant("primary" if trace_dir == "up" else "light_secondary")
        self.btn_insp_downstream.set_variant("primary" if trace_dir == "down" else "light_secondary")

        self.lbl_active_interventions.setText(f"{n_interventions} act." if n_interventions else "")
        self.btn_restore_all.setVisible(n_interventions > 0)

    def update_source_attribution(
        self,
        entity_label: str,
        shares: List[Tuple[str, float]],
        split_rule: str,
    ) -> None:
        self.lbl_source_entity.setText(entity_label)
        self._current_source_shares = list(shares)
        self.source_bar.set_shares(shares)
        if not shares:
            self.lbl_source_breakdown.setText("Sin aporte de fuentes hacia esta entidad.")
        else:
            split_es = "Proporcional" if split_rule == "proportional" else "Equitativa"
            parts = [f"F{src}: {frac * 100.0:.1f}%" for src, frac in shares]
            self.lbl_source_breakdown.setText(
                " · ".join(parts) + f"\nBifurcación: {split_es}"
            )

    def current_source_shares(self) -> List[Tuple[str, float]]:
        return list(self._current_source_shares)

    def render_details(
        self,
        *,
        dataset: Optional[NetworkDataset],
        result: Optional[SimulationResult],
        snap: Optional[TimeStepSnapshot],
        selected_pipe_id: Optional[str],
        selected_node_id: Optional[str],
        interventions: Dict[str, PipeIntervention],
        isolated_nodes: Set[str],
        isolated_pipes: Set[str],
    ) -> None:
        self.txt_inspector.clear()
        cursor = self.txt_inspector.textCursor()

        def add_line(text: str, tag: Optional[str] = None) -> None:
            fmt = {
                "heading": self._fmt_heading,
                "section": self._fmt_section,
                "muted": self._fmt_muted,
                "alert": self._fmt_alert,
            }.get(tag or "", self._fmt_normal)
            cursor.insertText(text + "\n", fmt)

        if dataset is None:
            add_line("Cargue un archivo Excel o carpeta CSV para comenzar.", "muted")
        else:
            g = dataset.graph
            if selected_pipe_id and g.has_pipe(selected_pipe_id):
                p = g.get_pipe(selected_pipe_id)
                assert p is not None
                inv = interventions.get(p.pipe_id)
                eff_qmax, eff_vel, eff_t_s, eff_diam = resolve_pipe_hydraulics(p, inv)
                add_line(f"TUBERÍA {p.pipe_id}  ({p.from_node} → {p.to_node})", "heading")
                add_line("─" * 40, "muted")
                if inv:
                    add_line(
                        f'INTERVENCIÓN    : OBST {inv.obstruction_pct:.0f}% · Ø {eff_diam:.0f}" (orig. {p.diameter_in:.0f}")',
                        "alert",
                    )
                if p.pipe_id in isolated_pipes:
                    add_line("[AISLADO DE 31] : Tramo sin conexión hacia PTAR", "alert")
                add_line(f'Diámetro        : {eff_diam:.0f}" ({eff_diam * 0.0254:.4f} m)')
                add_line(f"Longitud        : {p.length_m:.2f} m")
                add_line(f"Pendiente (S)   : {p.slope:.4f} m/m  |  n: {p.manning_n:.3f}")
                add_line(f"Capacidad Qmax  : {eff_qmax:.5f} m³/s (base {p.q_max_m3s:.5f})")
                add_line(f"Velocidad ref.  : {eff_vel:.3f} m/s")
                add_line(f"Tiempo tránsito : {eff_t_s / 60.0:.2f} min ({eff_t_s:.1f} s)")
                if p.note:
                    add_line(f"Marca dataset   : {p.note}")
                if snap and p.pipe_id in snap.pipe_states:
                    ps = snap.pipe_states[p.pipe_id]
                    if ps.in_min_cut:
                        add_line("[CORTE MÍN. FF]  : Tramo crítico de flujo máximo", "alert")
                    add_line(f"Flujo FF máx.   : {ps.max_flow_share_m3s:.5f} m³/s")
                    add_line("")
                    add_line(f"Estado en t = {snap.time_min:.1f} min", "section")
                    if ps.is_closed:
                        add_line("Estado tramo    : CERRADA 100% (caudal nulo)", "alert")
                        add_line(f"Demanda retenida: {ps.demand_flow_m3s:.5f} m³/s")
                    else:
                        add_line(f"Caudal conducido: {ps.flow_m3s:.5f} m³/s")
                        add_line(
                            f"Demanda entrante: {ps.demand_flow_m3s:.5f} m³/s ({ps.demand_ratio_pct / 100.0:.2f}× Qmax)"
                        )
                        add_line(f"Vol. tránsito   : {ps.volume_in_transit_m3:.2f} m³")
                        cap_tag = " (TOPE REBOSE)" if ps.is_overflow_capped else ""
                        add_line(
                            f"Utilización     : {ps.utilization_pct:.2f} %{cap_tag}",
                            "alert" if ps.utilization_pct > 100.0 else None,
                        )
                        add_line(f"Clasificación   : {ps.category.label}")
                        add_line(f"Exceso no cond. : {ps.excess_flow_m3s:.5f} m³/s")
                if result:
                    pk_u = result.peak_pipe_utilization.get(p.pipe_id, 0.0)
                    pk_dem = result.peak_pipe_demand_ratio.get(p.pipe_id, pk_u)
                    add_line(f"Pico utilización: {pk_u:.2f} % (Dem. {pk_dem / 100.0:.2f}× Qmax)")
                    ov_m = result.pipe_overloaded_minutes.get(p.pipe_id, 0.0)
                    _, _, ov_desc = classify_overload_persistence(ov_m, result.config.duration_min)
                    add_line(
                        f"Estrés >100%    : {ov_m:.0f} min ({ov_desc})",
                        "alert" if ov_m > 0.0 else None,
                    )
            elif selected_node_id and g.has_node(selected_node_id):
                n = g.get_node(selected_node_id)
                assert n is not None
                out_p = [e.pipe_id for e in g.outgoing_pipes(n.node_id)]
                in_p = [e.pipe_id for e in g.incoming_pipes(n.node_id)]
                tipo_es = {
                    "source": "FUENTE",
                    "sink": "SUMIDERO PTAR",
                    "manhole": "POZO DE INSPECCIÓN",
                }.get(n.node_type, n.node_type.upper())
                add_line(f"NODO {n.node_id}  ({tipo_es})", "heading")
                add_line("─" * 40, "muted")
                if n.node_id in isolated_nodes:
                    add_line("[AISLADO DE 31] : Sin ruta activa hacia la PTAR", "alert")
                add_line(f"Tuberías entrantes : {', '.join(in_p) or 'Ninguna (Fuente)'}")
                add_line(f"Tuberías salientes : {', '.join(out_p) or 'Ninguna (PTAR 31)'}")
                if snap and n.node_id in snap.node_states:
                    ns = snap.node_states[n.node_id]
                    cap_p = result.config.max_manhole_storage_m3 if result else 4.0
                    add_line("")
                    add_line(f"Estado en t = {snap.time_min:.1f} min", "section")
                    add_line(f"Caudal entrada  : {ns.inflow_m3s:.5f} m³/s")
                    add_line(f"Caudal salida   : {ns.outflow_m3s:.5f} m³/s")
                    add_line(
                        f"Vol. en pozo    : {ns.stored_volume_m3:.3f} m³ (máx {cap_p:.1f} m³)",
                        "alert" if ns.stored_volume_m3 > 1e-3 else None,
                    )
                    add_line(
                        f"Rebose en vía   : {ns.surface_flooding_m3:.2f} m³",
                        "alert" if ns.surface_flooding_m3 > 1e-3 else None,
                    )
            else:
                add_line("Seleccione una tubería o pozo del grafo para inspeccionarlo.", "muted")

            add_line("")
            add_line("RESUMEN DEL ESCENARIO", "section")
            add_line("─" * 40, "muted")
            if result and snap:
                cfg = result.config
                scen_es = theme.translate_scenario_name(cfg.scenario_name)
                src_es = theme.SOURCE_DIST_TO_ES.get(cfg.source_distribution, cfg.source_distribution)
                add_line(
                    f"Escenario       : {cfg.scenario_id} — {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                )
                add_line(
                    f"Cuenca          : C={dataset.basin.runoff_coefficient_c}, A={dataset.basin.area_ha} ha"
                )
                add_line(
                    f"Ingreso / Fuent.: {cfg.ingress_factor*100:.1f}% · {src_es} | Q_san={cfg.dry_weather_flow_per_source_m3s:.4f}"
                )
                add_line(f"Entrada acum.   : {snap.cumulative_inflow_m3:,.2f} m³")
                cap_lbl = (
                    f"{result.utilization_cap_pct:.0f}%"
                    if result.utilization_cap_pct is not None
                    else "Sin tope"
                )
                add_line(
                    f"Flujo máx. (FF) : {result.system_max_flow_m3s:.4f} m³/s (Corte: {', '.join(result.min_cut_pipes) or '-'})"
                )
                sys_tag = " [TOPE REBOSE]" if snap.system_overflow_capped else ""
                add_line(
                    f"Uso sistema (FF): {snap.system_utilization_pct:.1f}% (Dem. {snap.system_demand_ratio_pct:.1f}% · Tope {cap_lbl}){sys_tag}",
                    "alert" if snap.system_utilization_pct > 100.0 else None,
                )
                add_line(
                    f"Admitido / Reb. : {snap.admitted_inflow_m3s:.4f} / {snap.inlet_overflow_m3s:.4f} m³/s"
                )
                add_line(
                    f"Descarga PTAR 31: {snap.cumulative_sink_discharge_m3:,.2f} m³ (pico {result.peak_sink_discharge_m3s:.4f} m³/s)"
                )
                add_line(
                    f"Pozos / Tránsito: {snap.total_manhole_storage_m3:,.2f} / {snap.total_pipe_transit_m3:,.2f} m³"
                )
                add_line(
                    f"Rebose superf.  : {snap.total_surface_flooding_m3:,.2f} m³",
                    "alert" if snap.total_surface_flooding_m3 > 1e-3 else None,
                )
                add_line(f"Error balance   : {result.max_mass_balance_error_m3:.3e} m³")
                add_line(f"Crít. (>75–100%): {len(result.ever_near_capacity_pipes)} tuberías")
                add_line(f"Sobrec. (>100%) : {len(result.ever_overloaded_pipes)} tuberías")
                if interventions:
                    add_line(
                        f"Intervenciones  : {', '.join(sorted(interventions))} ({len(isolated_nodes)} aislados)",
                        "alert" if isolated_nodes else "section",
                    )

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.txt_inspector.setTextCursor(cursor)
