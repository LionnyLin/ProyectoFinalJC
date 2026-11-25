"""Panel izquierdo de controles (Simulación, Recorridos BFS/DFS, Leyenda y Scroll)."""

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QLocale, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.algorithms import (
    OVERLOAD_PERSISTENCE_LEVELS,
    MaxFlowResult,
    classify_overload_persistence,
    classify_utilization,
)
from src.simulation import TimeStepSnapshot
from .. import theme
from ..widgets import (
    PauseOnOpenComboBox,
    SectionCard,
    SegmentedControl,
    StructureStrip,
    StyledButton,
    blocked_signals,
    make_separator,
)


class ControlsPanel(QFrame):
    """Muelle izquierdo modular: parámetros hidráulicos, leyenda y recorridos BFS/DFS."""

    railTabChanged = Signal(str)
    scenarioChanged = Signal()
    aboutToOpenSelector = Signal()
    paramsChanged = Signal()
    executeSimulationRequested = Signal()
    calibrateFmaxRequested = Signal()
    simulateTargetFmaxRequested = Signal(float)
    maxFlowHighlightRequested = Signal()

    searchRequested = Signal(str)
    traversalRequested = Signal(str)
    toggleTraversalAnimRequested = Signal()
    traceRequested = Signal(str)
    clearHighlightsRequested = Signal()

    def __init__(
        self,
        icons: Dict[str, QIcon],
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LeftPanel")
        self._ui_font = ui_font
        self._mono_font = mono_font

        self._param_timer = QTimer(self)
        self._param_timer.setSingleShot(True)
        self._param_timer.setInterval(140)
        self._param_timer.timeout.connect(self.paramsChanged.emit)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Barra superior de pestañas del riel izquierdo
        tabs_wrap = QWidget(self)
        tabs_lay = QHBoxLayout(tabs_wrap)
        tabs_lay.setContentsMargins(10, 10, 10, 6)
        self.rail_tabs = SegmentedControl(
            [("sim", "Simulación"), ("trav", "Recorridos")],
            initial_key="sim",
            inactive_variant="light_secondary",
            font_pt=8,
            pad_x=8,
            pad_y=5,
            spacing=6,
            framed=False,
            parent=tabs_wrap,
        )
        for key in ("sim", "trav"):
            b = self.rail_tabs.button(key)
            if b is not None:
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rail_tabs.selectionChanged.connect(self._on_rail_tab_selected)
        tabs_lay.addWidget(self.rail_tabs)
        outer.addWidget(tabs_wrap)
        outer.addWidget(make_separator("h", theme.DOCK_BORDER, 1, self))

        # Área desplazable nativa sin huecos en blanco
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("LeftScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget(self.scroll_area)
        scroll_content.setObjectName("LeftScrollContent")
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(0, 0, 0, 8)
        scroll_lay.setSpacing(0)

        self.stack = QStackedWidget(scroll_content)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._sim_page = self._build_sim_page(icons)
        self._trav_page = self._build_trav_page(icons)
        self.stack.addWidget(self._sim_page)
        self.stack.addWidget(self._trav_page)
        scroll_lay.addWidget(self.stack)
        scroll_lay.addStretch(1)

        self.scroll_area.setWidget(scroll_content)
        outer.addWidget(self.scroll_area, 1)

    def _build_sim_page(self, icons: Dict[str, QIcon]) -> QWidget:
        page = QWidget(self)
        page.setObjectName("LeftScrollPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.setSpacing(8)

        # Lámina 1: Escenario y parámetros
        sec_sim = SectionCard("Escenario y parámetros", dark_header=True, parent=page)
        sec_sim.body_layout.setContentsMargins(8, 7, 8, 7)

        lbl_sc = QLabel("Escenario de precipitación", sec_sim)
        lbl_sc.setFont(QFont(self._ui_font, 8, QFont.Weight.Bold))
        sec_sim.body_layout.addWidget(lbl_sc)

        self.combo_scenario = PauseOnOpenComboBox(sec_sim)
        self.combo_scenario.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.combo_scenario.setMinimumWidth(120)
        self.combo_scenario.aboutToShowPopup.connect(self.aboutToOpenSelector.emit)
        self.combo_scenario.currentIndexChanged.connect(lambda _idx: self.scenarioChanged.emit())
        sec_sim.body_layout.addWidget(self.combo_scenario)

        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 2)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)

        c_loc = QLocale(QLocale.Language.C)

        def _make_spin(min_v: float, max_v: float, step: float, decimals: int, init_v: float) -> QDoubleSpinBox:
            sb = QDoubleSpinBox(sec_sim)
            sb.setLocale(c_loc)
            sb.setRange(min_v, max_v)
            sb.setSingleStep(step)
            sb.setDecimals(decimals)
            sb.setValue(init_v)
            sb.setMinimumWidth(72)
            sb.setMaximumWidth(84)
            sb.valueChanged.connect(lambda _v: self._param_timer.start())
            sb.editingFinished.connect(self._flush_param_change)
            return sb

        self.spin_duration = _make_spin(0.0, 1440.0, 10.0, 0, 90.0)
        self.spin_storm_dur = _make_spin(0.0, 1440.0, 5.0, 0, 60.0)
        self.spin_dt = _make_spin(0.0, 60.0, 0.5, 1, 1.0)
        self.spin_ingress_pct = _make_spin(0.0, 100.0, 0.5, 2, 100.0)
        self.spin_dry_flow = _make_spin(0.0, 10.0, 0.001, 3, 0.0)
        self.spin_util_cap_pct = _make_spin(100.0, 300.0, 5.0, 0, 120.0)
        self.spin_util_cap_pct.setToolTip(
            "Tope físico de uso (% de F_max y Q_max) al cual el sistema rebosa y no admite más agua."
        )

        fields = [
            ("Duración simulación (min)", self.spin_duration),
            ("Duración lluvia (min)", self.spin_storm_dur),
            ("Paso temporal Δt (min)", self.spin_dt),
            ("Ingreso pluvial (%)", self.spin_ingress_pct),
            ("Caudal sanitario (m³/s)", self.spin_dry_flow),
            ("Tope físico uso (%)", self.spin_util_cap_pct),
        ]
        for row_i, (label_txt, sb) in enumerate(fields):
            lbl = QLabel(label_txt, sec_sim)
            lbl.setFont(QFont(self._ui_font, 8))
            grid.addWidget(lbl, row_i, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(sb, row_i, 1, Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(0, 1)
        sec_sim.body_layout.addLayout(grid)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        btn_p1 = StyledButton(
            "Oficial Guía (100%)", variant="dock_secondary", font_pt=7, pad_x=4, pad_y=3, parent=sec_sim
        )
        btn_p1.clicked.connect(lambda: self.apply_preset(100.0, 0.0))
        btn_p2 = StyledButton(
            "Calibrado (2.5% + Q_san)", variant="dock_secondary", font_pt=7, pad_x=4, pad_y=3, parent=sec_sim
        )
        btn_p2.clicked.connect(lambda: self.apply_preset(2.5, 0.003))
        preset_row.addWidget(btn_p1, 1)
        preset_row.addWidget(btn_p2, 1)
        sec_sim.body_layout.addLayout(preset_row)

        self.btn_fmax_preset = StyledButton(
            "Calibrado F_max (E3 = 100%)",
            variant="dock_secondary",
            font_pt=7,
            pad_x=6,
            pad_y=3,
            parent=sec_sim,
        )
        self.btn_fmax_preset.setToolTip(
            "Ajusta el ingreso pluvial para que Lluvia moderada (30 mm/h) iguale el flujo máximo F_max de Ford-Fulkerson."
        )
        self.btn_fmax_preset.clicked.connect(self.calibrateFmaxRequested.emit)
        sec_sim.body_layout.addWidget(self.btn_fmax_preset)

        self.lbl_fmax_badge = QLabel(
            "Ford-Fulkerson: F_max = - · Tope = 120%", sec_sim
        )
        self.lbl_fmax_badge.setWordWrap(True)
        self.lbl_fmax_badge.setFont(QFont(self._mono_font, 7))
        self.lbl_fmax_badge.setStyleSheet(
            f"background-color: {theme.PAPER_SUBTLE}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.PAPER_BORDER}; padding: 3px 5px;"
        )
        sec_sim.body_layout.addWidget(self.lbl_fmax_badge)

        fmax_sim_row = QHBoxLayout()
        fmax_sim_row.setSpacing(4)
        lbl_tf = QLabel("Simular % F_max", sec_sim)
        lbl_tf.setFont(QFont(self._ui_font, 8))
        fmax_sim_row.addWidget(lbl_tf)
        fmax_sim_row.addStretch(1)

        self.spin_target_fmax_pct = QDoubleSpinBox(sec_sim)
        self.spin_target_fmax_pct.setLocale(c_loc)
        self.spin_target_fmax_pct.setRange(0.0, 300.0)
        self.spin_target_fmax_pct.setSingleStep(5.0)
        self.spin_target_fmax_pct.setDecimals(0)
        self.spin_target_fmax_pct.setValue(100.0)
        self.spin_target_fmax_pct.setMinimumWidth(58)
        self.spin_target_fmax_pct.setMaximumWidth(68)
        fmax_sim_row.addWidget(self.spin_target_fmax_pct)

        self.btn_sim_fmax = StyledButton(
            "Simular %",
            variant="dock_secondary",
            font_pt=7,
            pad_x=6,
            pad_y=3,
            parent=sec_sim,
        )
        self.btn_sim_fmax.setToolTip(
            "Simula directamente una demanda equivalente al porcentaje indicado de F_max."
        )
        self.btn_sim_fmax.clicked.connect(
            lambda: self.simulateTargetFmaxRequested.emit(float(self.spin_target_fmax_pct.value()))
        )
        fmax_sim_row.addWidget(self.btn_sim_fmax)
        sec_sim.body_layout.addLayout(fmax_sim_row)

        rule_grid = QGridLayout()
        rule_grid.setContentsMargins(0, 2, 0, 2)
        rule_grid.setHorizontalSpacing(6)
        rule_grid.setVerticalSpacing(4)

        lbl_split = QLabel("Bifurcación", sec_sim)
        lbl_split.setFont(QFont(self._ui_font, 8))
        self.combo_split_rule = PauseOnOpenComboBox(sec_sim)
        self.combo_split_rule.addItems(list(theme.SPLIT_RULE_TO_ES.values()))
        self.combo_split_rule.aboutToShowPopup.connect(self.aboutToOpenSelector.emit)
        self.combo_split_rule.currentIndexChanged.connect(lambda _i: self._flush_param_change())
        rule_grid.addWidget(lbl_split, 0, 0)
        rule_grid.addWidget(self.combo_split_rule, 0, 1)

        lbl_src = QLabel("Reparto fuentes", sec_sim)
        lbl_src.setFont(QFont(self._ui_font, 8))
        self.combo_source_dist = PauseOnOpenComboBox(sec_sim)
        self.combo_source_dist.addItems(list(theme.SOURCE_DIST_TO_ES.values()))
        self.combo_source_dist.aboutToShowPopup.connect(self.aboutToOpenSelector.emit)
        self.combo_source_dist.currentIndexChanged.connect(lambda _i: self._flush_param_change())
        rule_grid.addWidget(lbl_src, 1, 0)
        rule_grid.addWidget(self.combo_source_dist, 1, 1)
        rule_grid.setColumnStretch(0, 1)
        sec_sim.body_layout.addLayout(rule_grid)

        self.btn_run_sim = StyledButton(
            " Ejecutar simulación",
            variant="primary",
            icon=icons["play_on_accent"],
            icon_size=11,
            font_pt=9,
            pad_x=10,
            pad_y=6,
            parent=sec_sim,
        )
        self.btn_run_sim.clicked.connect(self.executeSimulationRequested.emit)
        sec_sim.body_layout.addWidget(self.btn_run_sim)
        lay.addWidget(sec_sim)

        # Lámina 2: Leyenda dinámica de escala oficial / estrés acumulado
        self.sec_legend = SectionCard(
            "Escala oficial de utilización", dark_header=False, parent=page
        )
        self.sec_legend.body_layout.setContentsMargins(8, 7, 8, 7)
        self._legend_count_labels: List[QLabel] = []
        self._legend_text_labels: List[QLabel] = []
        short_desc = {"Cercana a capacidad máxima": "Cercana a cap. máx."}

        for rng, color_hex, desc in theme.COLOR_SCALE_LEGEND:
            row = QHBoxLayout()
            row.setContentsMargins(0, 1, 0, 1)
            row.setSpacing(7)

            swatch = QFrame(self.sec_legend)
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; border: 1px solid {theme.DOCK_BORDER};"
            )
            row.addWidget(swatch)

            txt_lbl = QLabel(f"{rng} · {short_desc.get(desc, desc)}", self.sec_legend)
            txt_lbl.setFont(QFont(self._ui_font, 8))
            row.addWidget(txt_lbl, 1)

            cnt_lbl = QLabel("0", self.sec_legend)
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cnt_lbl.setFixedWidth(28)
            cnt_lbl.setFont(QFont(self._mono_font, 8, QFont.Weight.Bold))
            cnt_lbl.setStyleSheet(
                f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; padding: 1px 2px;"
            )
            row.addWidget(cnt_lbl)

            self.sec_legend.body_layout.addLayout(row)
            self._legend_text_labels.append(txt_lbl)
            self._legend_count_labels.append(cnt_lbl)

        lay.addWidget(self.sec_legend)
        return page

    def _build_trav_page(self, icons: Dict[str, QIcon]) -> QWidget:
        page = QWidget(self)
        page.setObjectName("LeftScrollPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.setSpacing(8)

        # Lámina 3: Búsqueda y recorridos
        sec_alg = SectionCard("Búsqueda y recorridos", dark_header=True, parent=page)
        sec_alg.body_layout.setContentsMargins(8, 7, 8, 7)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.entry_search = QLineEdit(sec_alg)
        self.entry_search.setPlaceholderText("Nodo o tubería (ej. P31)")
        self.entry_search.returnPressed.connect(
            lambda: self.searchRequested.emit(self.entry_search.text())
        )
        search_row.addWidget(self.entry_search, 1)

        btn_search = StyledButton(
            " Buscar",
            variant="primary",
            icon=icons["search_ink"],
            icon_size=12,
            font_pt=8,
            pad_x=9,
            pad_y=4,
            parent=sec_alg,
        )
        btn_search.clicked.connect(
            lambda: self.searchRequested.emit(self.entry_search.text())
        )
        search_row.addWidget(btn_search)
        sec_alg.body_layout.addLayout(search_row)

        trav_grid = QGridLayout()
        trav_grid.setContentsMargins(0, 4, 0, 2)
        trav_grid.setHorizontalSpacing(6)
        trav_grid.setVerticalSpacing(4)

        lbl_o = QLabel("Nodo origen", sec_alg)
        lbl_o.setFont(QFont(self._ui_font, 8))
        self.combo_bfs_start = QComboBox(sec_alg)
        self.combo_bfs_start.setEditable(True)
        self.combo_bfs_start.setMinimumWidth(92)
        self.combo_bfs_start.setCurrentText("6")
        trav_grid.addWidget(lbl_o, 0, 0)
        trav_grid.addWidget(self.combo_bfs_start, 0, 1)

        lbl_d = QLabel("Nodo destino", sec_alg)
        lbl_d.setFont(QFont(self._ui_font, 8))
        self.combo_bfs_target = QComboBox(sec_alg)
        self.combo_bfs_target.setEditable(True)
        self.combo_bfs_target.setMinimumWidth(92)
        self.combo_bfs_target.setCurrentText("31")
        trav_grid.addWidget(lbl_d, 1, 0)
        trav_grid.addWidget(self.combo_bfs_target, 1, 1)
        trav_grid.setColumnStretch(0, 1)
        sec_alg.body_layout.addLayout(trav_grid)

        row_b1 = QHBoxLayout()
        row_b1.setSpacing(4)
        btn_bfs = StyledButton(
            "BFS", variant="dock_secondary", font_pt=8, pad_x=6, pad_y=4, parent=sec_alg
        )
        btn_bfs.clicked.connect(lambda: self.traversalRequested.emit("BFS"))
        btn_dfs = StyledButton(
            "DFS", variant="dock_secondary", font_pt=8, pad_x=6, pad_y=4, parent=sec_alg
        )
        btn_dfs.clicked.connect(lambda: self.traversalRequested.emit("DFS"))
        btn_clr = StyledButton(
            "Limpiar", variant="dock_secondary", font_pt=8, pad_x=6, pad_y=4, parent=sec_alg
        )
        btn_clr.clicked.connect(self.clearHighlightsRequested.emit)
        row_b1.addWidget(btn_bfs, 1)
        row_b1.addWidget(btn_dfs, 1)
        row_b1.addWidget(btn_clr, 1)
        sec_alg.body_layout.addLayout(row_b1)

        self.btn_anim_traversal = StyledButton(
            "Animar recorrido", variant="primary", font_pt=8, pad_x=8, pad_y=4, parent=sec_alg
        )
        self.btn_anim_traversal.clicked.connect(self.toggleTraversalAnimRequested.emit)
        sec_alg.body_layout.addWidget(self.btn_anim_traversal)

        row_b2 = QHBoxLayout()
        row_b2.setSpacing(4)
        btn_dn = StyledButton(
            "Aguas abajo", variant="dock_secondary", font_pt=8, pad_x=5, pad_y=4, parent=sec_alg
        )
        btn_dn.clicked.connect(lambda: self.traceRequested.emit("down"))
        btn_up = StyledButton(
            "Aguas arriba", variant="dock_secondary", font_pt=8, pad_x=5, pad_y=4, parent=sec_alg
        )
        btn_up.clicked.connect(lambda: self.traceRequested.emit("up"))
        row_b2.addWidget(btn_dn, 1)
        row_b2.addWidget(btn_up, 1)
        sec_alg.body_layout.addLayout(row_b2)

        self.btn_ford_fulkerson = StyledButton(
            "Ford-Fulkerson (F_max y Corte Mín.)",
            variant="dock_secondary",
            font_pt=8,
            pad_x=6,
            pad_y=4,
            parent=sec_alg,
        )
        self.btn_ford_fulkerson.clicked.connect(self.maxFlowHighlightRequested.emit)
        sec_alg.body_layout.addWidget(self.btn_ford_fulkerson)
        lay.addWidget(sec_alg)

        # Lámina 4: Bitácora oscura + tira visual Queue/Stack
        sec_log = SectionCard("Bitácora de recorrido", dark_header=False, parent=page)
        sec_log.body_layout.setContentsMargins(8, 7, 8, 7)
        self.structure_strip = StructureStrip(self._mono_font, sec_log)
        sec_log.body_layout.addWidget(self.structure_strip)

        self.txt_traversal = QPlainTextEdit(sec_log)
        self.txt_traversal.setObjectName("TraversalLog")
        self.txt_traversal.setReadOnly(True)
        self.txt_traversal.setFixedHeight(120)
        sec_log.body_layout.addWidget(self.txt_traversal)
        lay.addWidget(sec_log)

        return page

    def _on_rail_tab_selected(self, tab_id: str) -> None:
        self.switch_rail_tab(tab_id)
        self.railTabChanged.emit(tab_id)

    def switch_rail_tab(self, tab_id: str) -> None:
        self.rail_tabs.set_current(tab_id)
        self.stack.setCurrentIndex(1 if tab_id == "trav" else 0)
        self.scroll_area.verticalScrollBar().setValue(0)

    def _flush_param_change(self) -> None:
        if self._param_timer.isActive():
            self._param_timer.stop()
        self.paramsChanged.emit()

    def cancel_pending_param_rerun(self) -> None:
        if self._param_timer.isActive():
            self._param_timer.stop()

    def apply_preset(self, ingress_pct: float, dry_flow: float) -> None:
        with blocked_signals(self.spin_ingress_pct, self.spin_dry_flow):
            self.spin_ingress_pct.setValue(ingress_pct)
            self.spin_dry_flow.setValue(dry_flow)
        self._flush_param_change()

    def set_scenarios(self, labels: Sequence[str], current_idx: int = 0) -> None:
        with blocked_signals(self.combo_scenario):
            self.combo_scenario.clear()
            self.combo_scenario.addItems(list(labels))
            if labels:
                self.combo_scenario.setCurrentIndex(max(0, min(len(labels) - 1, current_idx)))

    def set_scenario_text(self, text: str) -> None:
        idx = self.combo_scenario.findText(text)
        if idx >= 0:
            with blocked_signals(self.combo_scenario):
                self.combo_scenario.setCurrentIndex(idx)

    def set_node_choices(
        self,
        node_ids: Sequence[str],
        start_id: str = "6",
        target_id: str = "31",
    ) -> None:
        with blocked_signals(self.combo_bfs_start, self.combo_bfs_target):
            self.combo_bfs_start.clear()
            self.combo_bfs_target.clear()
            self.combo_bfs_start.addItems(list(node_ids))
            self.combo_bfs_target.addItems(list(node_ids))
            self.combo_bfs_start.setCurrentText(start_id)
            self.combo_bfs_target.setCurrentText(target_id)

    def read_util_cap_pct(self) -> float:
        return float(self.spin_util_cap_pct.value())

    def set_util_cap_pct(self, cap_pct: float) -> None:
        with blocked_signals(self.spin_util_cap_pct):
            self.spin_util_cap_pct.setValue(float(cap_pct))
        self._flush_param_change()

    def update_fmax_summary(
        self, max_flow_res: Optional[MaxFlowResult], cap_pct: Optional[float]
    ) -> None:
        if max_flow_res is None:
            self.lbl_fmax_badge.setText("Ford-Fulkerson: F_max = -")
            return
        f_max = max_flow_res.max_flow_m3s
        cut_txt = ", ".join(max_flow_res.min_cut_pipes[:5]) or "Ninguno"
        if cap_pct is not None:
            q_adm = f_max * (cap_pct / 100.0)
            self.lbl_fmax_badge.setText(
                f"F_max = {f_max:.4f} m³/s · Tope {cap_pct:.0f}% = {q_adm:.4f} m³/s\n"
                f"Corte mín.: {cut_txt}"
            )
        else:
            self.lbl_fmax_badge.setText(
                f"F_max = {f_max:.4f} m³/s · Sin tope\nCorte mín.: {cut_txt}"
            )

    def read_sim_inputs(self) -> Tuple[str, float, float, float, float, float, str, str]:
        split_rule = theme.ES_TO_SPLIT_RULE.get(
            self.combo_split_rule.currentText(), "proportional"
        )
        source_dist = theme.ES_TO_SOURCE_DIST.get(
            self.combo_source_dist.currentText(), "capacity"
        )
        return (
            self.combo_scenario.currentText(),
            float(self.spin_duration.value()),
            float(self.spin_storm_dur.value()),
            float(self.spin_dt.value()),
            float(self.spin_ingress_pct.value()),
            float(self.spin_dry_flow.value()),
            split_rule,
            source_dist,
        )

    def update_legend(
        self,
        map_mode: str,
        snap: Optional[TimeStepSnapshot],
        peak_all: Dict[str, float],
        ov_all: Dict[str, float],
        dur_total: float,
        cap_pct: Optional[float] = None,
    ) -> None:
        if snap is None:
            return
        counts = [0, 0, 0, 0, 0]
        if map_mode == "overload_minutes":
            self.sec_legend.set_title(f"Sobrecarga acumulada · 0–{dur_total:.0f} min")
            for idx, (rng, _col, desc) in enumerate(OVERLOAD_PERSISTENCE_LEVELS):
                if idx < len(self._legend_text_labels):
                    self._legend_text_labels[idx].setText(f"{rng} · {desc}")
            for pid in snap.pipe_states:
                tier, _, _ = classify_overload_persistence(ov_all.get(pid, 0.0), dur_total)
                counts[tier] += 1
        else:
            title = (
                f"Escala oficial · t = {snap.time_min:.0f} min"
                if map_mode == "instant"
                else f"Pico máximo · 0–{dur_total:.0f} min"
            )
            self.sec_legend.set_title(title)
            short_desc = {"Cercana a capacidad máxima": "Cercana a cap. máx."}
            for idx, (rng, _col, desc) in enumerate(theme.COLOR_SCALE_LEGEND):
                if idx < len(self._legend_text_labels):
                    if idx == 4 and cap_pct is not None:
                        self._legend_text_labels[idx].setText(
                            f">100–{cap_pct:.0f}% · Rebose (tope)"
                        )
                    else:
                        self._legend_text_labels[idx].setText(
                            f"{rng} · {short_desc.get(desc, desc)}"
                        )
            if map_mode == "peak":
                for pid in snap.pipe_states:
                    counts[classify_utilization(peak_all.get(pid, 0.0)).tier_index] += 1
            else:
                for ps in snap.pipe_states.values():
                    counts[ps.category.tier_index] += 1

        for lbl, c in zip(self._legend_count_labels, counts):
            lbl.setText(str(c))

    def set_traversal_text(self, text: str) -> None:
        self.txt_traversal.setPlainText(text)

    def update_structure_strip(
        self, structure_name: str, items: Sequence[str], step_text: str = ""
    ) -> None:
        self.structure_strip.update_items(structure_name, items, step_text)

    def set_animating(self, active: bool) -> None:
        self.btn_anim_traversal.setText("Detener anim." if active else "Animar recorrido")

    def focus_search(self) -> None:
        self.entry_search.setFocus()
        self.entry_search.selectAll()
