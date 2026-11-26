"""Orquestador principal PySide6 — Lámina Cartográfica de Archivo Hidráulico (Capa 4)."""

from dataclasses import replace
import math
import os
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QFont, QFontMetrics, QKeySequence, QPalette, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.algorithms import (
    bfs_anim_frames,
    build_route_to_sink,
    compute_source_attribution,
    dfs_anim_frames,
    find_isolated_from_sinks,
    ford_fulkerson_max_flow,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from src.data_structures import PipeEdge
from src.io.data_loader import (
    DataLoadError,
    NetworkDataset,
    PrecipitationScenario,
    export_to_csv_dir,
    load_dataset,
)
from src.simulation import (
    PipeIntervention,
    SewerSimulationEngine,
    SimulationConfig,
    TimeStepSnapshot,
    compare_all_scenarios,
    compute_fmax_calibrated_ingress,
    estimate_fmax_scenarios,
    generate_docx_report,
    generate_markdown_report,
    resolve_pipe_hydraulics,
)
from . import theme
from .icons import build_icon_set
from .panels import (
    CenterPanel,
    ComparisonPanel,
    ControlsPanel,
    CriticalPipesPanel,
    InspectorPanel,
    MaxFlowPanel,
    TopBar,
    build_tour_stops,
    parse_diameter_override,
)
from .state import AppState
from .widgets import blocked_signals, make_separator
from .workers import AsyncTaskRunner


def ensure_qapplication() -> QApplication:
    """Garantiza una única instancia de QApplication configurada con Fusion, fuentes y QSS."""
    theme.enable_dpi_awareness()
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    assert isinstance(app, QApplication)

    if not app.property("_bicentenario_configured"):
        app.setStyle("Fusion")
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor(theme.ACCENT_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.ACCENT_INK))
        if hasattr(QPalette.ColorRole, "Accent"):
            pal.setColor(QPalette.ColorRole.Accent, QColor(theme.ACCENT_PRIMARY))
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.PAPER_BG))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.INK_PRIMARY))
        app.setPalette(pal)
        ui_font, mono_font, display_font, _ = theme.resolve_fonts()
        app.setFont(QFont(ui_font, 9))
        app.setStyleSheet(theme.build_stylesheet(ui_font, mono_font, display_font))
        app.setProperty("_bicentenario_configured", True)
        app.setProperty("_ui_font", ui_font)
        app.setProperty("_mono_font", mono_font)
        app.setProperty("_display_font", display_font)

    return app


class BicentenarioSewerApp(QMainWindow):
    """Ventana principal de composición modular para simulación y análisis de la red."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        qapp = ensure_qapplication()
        super().__init__()

        self.ui_font = str(qapp.property("_ui_font") or "Segoe UI")
        self.mono_font = str(qapp.property("_mono_font") or "Consolas")
        self.display_font = str(qapp.property("_display_font") or "Inter")
        self._dpi_scale = self._resolve_dpi_scale(qapp)
        self._mpl_dpi = min(116, max(96, int(round(96.0 * min(1.20, self._dpi_scale)))))

        self.state = AppState()
        self._scenario_display_map: Dict[str, object] = {}
        self._insp_tab_dirty: bool = False
        self._crit_tab_dirty: bool = False
        self._charts_tab_dirty: bool = False
        self._right_tabs_compact: Optional[str] = None
        self._auto_collapsed_right: bool = False

        self._icons = build_icon_set(
            fg_dark=theme.SHELL_TEXT,
            fg_light=theme.INK_PRIMARY,
            fg_on_accent=theme.ACCENT_INK,
            accent_color=theme.ACCENT_PRIMARY,
        )

        self.setWindowTitle("Red de Alcantarillado Ciudad Bicentenario · Simulador Hidráulico")
        self.setWindowIcon(self._icons["brand_network"])
        self._configure_initial_geometry(qapp)

        self._play_timer = QTimer(self)
        self._play_timer.setSingleShot(True)
        self._play_timer.timeout.connect(self._schedule_next_frame)

        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._step_traversal_anim)

        self._traversal_handoff_timer = QTimer(self)
        self._traversal_handoff_timer.setSingleShot(True)
        self._traversal_handoff_timer.setInterval(420)
        self._traversal_handoff_timer.timeout.connect(
            self._promote_finished_traversal_to_live_route
        )
        self._pending_traversal_highlights: Optional[
            Tuple[Set[str], Set[str], List[str]]
        ] = None

        self._task_runner = AsyncTaskRunner(self)

        self._deferred_charts_timer = QTimer(self)
        self._deferred_charts_timer.setSingleShot(True)
        self._deferred_charts_timer.setInterval(15)
        self._deferred_charts_timer.timeout.connect(self._run_deferred_temporal_charts)

        self._deferred_compare_timer = QTimer(self)
        self._deferred_compare_timer.setSingleShot(True)
        self._deferred_compare_timer.setInterval(15)
        self._deferred_compare_timer.timeout.connect(self._launch_pending_comparison)
        self._pending_compare_job = None

        self._deferred_fmax_timer = QTimer(self)
        self._deferred_fmax_timer.setSingleShot(True)
        self._deferred_fmax_timer.setInterval(15)
        self._deferred_fmax_timer.timeout.connect(self._launch_pending_max_flow)
        self._pending_fmax_job = None

        self._build_layout()
        self._connect_signals()
        self._bind_shortcuts()

        default_path = initial_data_path or self._find_default_dataset()
        if default_path and self._load_path(default_path, silent_error=False):
            self.run_simulation()

        self._apply_responsive_layout(self.width(), self.height())

    @staticmethod
    def _resolve_dpi_scale(qapp: QApplication) -> float:
        screen = qapp.primaryScreen()
        if screen is not None:
            dpi = float(screen.logicalDotsPerInch())
            if dpi > 0.0:
                return max(1.0, min(3.0, dpi / 96.0))
        return 1.0

    def _configure_initial_geometry(self, qapp: QApplication) -> None:
        if qapp.platformName() == "offscreen":
            init_w, init_h = 1280, 800
            pos_x, pos_y = 20, 20
        else:
            screen = qapp.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                sw, sh = max(800, geo.width()), max(600, geo.height())
                ox, oy = geo.x(), geo.y()
            else:
                sw, sh = 1440, 900
                ox, oy = 0, 0
            init_w = max(860, min(int(round(1440 * min(1.15, self._dpi_scale))), int(sw * 0.92)))
            init_h = max(580, min(int(round(880 * min(1.15, self._dpi_scale))), int(sh * 0.88)))
            pos_x = ox + max(0, (sw - init_w) // 2)
            pos_y = oy + max(0, (sh - init_h) // 2)
        self.setMinimumSize(780, 540)
        self.setGeometry(pos_x, pos_y, init_w, init_h)

    @staticmethod
    def _find_default_dataset() -> Optional[str]:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        xlsx = os.path.join(base, "data", "DataSetBicentenario.xlsx")
        if os.path.isfile(xlsx):
            return xlsx
        csv_dir = os.path.join(base, "data", "csv")
        if os.path.isdir(csv_dir):
            return csv_dir
        return None

    def _build_layout(self) -> None:
        central = QWidget(self)
        central.setObjectName("MainCentral")
        self.setCentralWidget(central)

        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # 1. Barra superior institucional
        self.top_bar = TopBar(self._icons, ui_font=self.ui_font, parent=central)
        root_lay.addWidget(self.top_bar)

        accent_top = QFrame(central)
        accent_top.setObjectName("TopBarAccent")
        accent_top.setFixedHeight(3)
        root_lay.addWidget(accent_top)

        # 2. Área principal de 3 columnas redimensionables
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.main_splitter.setObjectName("MainSplitter")
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setChildrenCollapsible(False)

        self.controls_panel = ControlsPanel(
            self._icons,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            parent=self.main_splitter,
        )
        self.controls_panel.setMinimumWidth(264)

        self.center_panel = CenterPanel(
            self._icons,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            display_font=self.display_font,
            dpi_scale=self._dpi_scale,
            parent=self.main_splitter,
        )
        self.center_panel.setMinimumWidth(310)
        self.network_canvas = self.center_panel.network_canvas
        self.basin_3d = self.center_panel.basin_3d

        self.right_panel = QFrame(self.main_splitter)
        self.right_panel.setObjectName("RightPanel")
        self.right_panel.setMinimumWidth(285)
        rp_lay = QVBoxLayout(self.right_panel)
        rp_lay.setContentsMargins(8, 8, 8, 8)

        sheet_frame = QFrame(self.right_panel)
        sheet_frame.setObjectName("RightSheetFrame")
        sf_lay = QVBoxLayout(sheet_frame)
        sf_lay.setContentsMargins(0, 0, 0, 0)

        self.right_tabs = QTabWidget(sheet_frame)
        self.right_tabs.setObjectName("RightTabs")
        # Sin flechas de desplazamiento: las pestañas se compactan o se eliden para caber siempre.
        self.right_tabs.setUsesScrollButtons(False)
        self.right_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.right_tabs.tabBar().setExpanding(False)

        self.inspector_panel = InspectorPanel(
            self._icons,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            display_font=self.display_font,
            parent=self.right_tabs,
        )
        self.critical_panel = CriticalPipesPanel(
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            parent=self.right_tabs,
        )
        self.temporal_charts = (
            __import__("src.gui.panels.charts_panel", fromlist=["TemporalChartsPanel"]).TemporalChartsPanel(
                dpi=self._mpl_dpi,
                ui_font=self.ui_font,
                mono_font=self.mono_font,
                parent=self.right_tabs,
            )
        )
        self.comparison_panel = ComparisonPanel(
            dpi=self._mpl_dpi,
            ui_font=self.ui_font,
            parent=self.right_tabs,
        )
        self.comparison_charts = self.comparison_panel.charts
        self.max_flow_panel = MaxFlowPanel(
            dpi=self._mpl_dpi,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            display_font=self.display_font,
            parent=self.right_tabs,
        )

        self.right_tabs.addTab(self.inspector_panel, "Inspector")
        self.right_tabs.addTab(self.critical_panel, "Tuberías Críticas")
        self.right_tabs.addTab(self.temporal_charts, "Evolución")
        self.right_tabs.addTab(self.comparison_panel, "Comparación")
        self.right_tabs.addTab(self.max_flow_panel, "Flujo Máx.")

        sf_lay.addWidget(self.right_tabs)
        rp_lay.addWidget(sheet_frame)
        # Al arrastrar el splitter el panel cambia de ancho sin redimensionar la ventana.
        self.right_panel.installEventFilter(self)

        self.main_splitter.addWidget(self.controls_panel)
        self.main_splitter.addWidget(self.center_panel)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        root_lay.addWidget(self.main_splitter, 1)

        # 3. Barra de estado inferior en grafito (#4A4A4A)
        accent_bot = QFrame(central)
        accent_bot.setObjectName("StatusBarAccent")
        accent_bot.setFixedHeight(2)
        root_lay.addWidget(accent_bot)

        status_frame = QFrame(central)
        status_frame.setObjectName("StatusBarFrame")
        status_frame.setFixedHeight(27)
        st_lay = QHBoxLayout(status_frame)
        st_lay.setContentsMargins(12, 2, 12, 2)

        self.lbl_status = QLabel("Listo.", status_frame)
        self.lbl_status.setObjectName("StatusLabel")
        st_lay.addWidget(self.lbl_status, 1)

        self.lbl_shortcuts_hint = QLabel(
            "Espacio: Reproducir/Pausar  ·  ←/→: Paso  ·  Ctrl+F: Buscar  ·  Esc: Limpiar",
            status_frame,
        )
        self.lbl_shortcuts_hint.setObjectName("ShortcutsHintLabel")
        st_lay.addWidget(self.lbl_shortcuts_hint)
        root_lay.addWidget(status_frame)

        self.top_bar.set_panel_toggle_states(self.state.show_left, self.state.show_right)

    def _connect_signals(self) -> None:
        # Barra superior
        self.top_bar.toggleLeftRequested.connect(self.toggle_left_panel)
        self.top_bar.toggleRightRequested.connect(self.toggle_right_panel)
        self.top_bar.guidedTourRequested.connect(self.toggle_guided_tour)
        self.top_bar.loadExcelRequested.connect(self._action_load_excel)
        self.top_bar.loadCsvRequested.connect(self._action_load_csv)
        self.top_bar.exportCsvRequested.connect(self._action_export_csv)
        self.top_bar.showAssumptionsRequested.connect(self._action_show_assumptions)
        self.top_bar.generateReportRequested.connect(self._action_generate_report)

        # Panel izquierdo
        self.controls_panel.railTabChanged.connect(self._on_rail_tab_changed)
        self.controls_panel.aboutToOpenSelector.connect(self.pause)
        self.controls_panel.scenarioChanged.connect(self._on_scenario_changed)
        self.controls_panel.paramsChanged.connect(self._on_params_changed)
        self.controls_panel.executeSimulationRequested.connect(self._on_execute_sim_clicked)
        self.controls_panel.calibrateFmaxRequested.connect(self._action_calibrate_fmax)
        self.controls_panel.demandTargetChanged.connect(self._on_demand_target_changed)
        self.controls_panel.maxFlowHighlightRequested.connect(self._action_highlight_ford_fulkerson)
        self.controls_panel.searchRequested.connect(self._action_search)
        self.controls_panel.traversalRequested.connect(self._run_traversal)
        self.controls_panel.toggleTraversalAnimRequested.connect(self._action_toggle_traversal_anim)
        self.controls_panel.traceRequested.connect(self._run_trace)
        self.controls_panel.clearHighlightsRequested.connect(self._clear_highlights)

        # Panel central + Canvas + Tour
        self.center_panel.labelsToggled.connect(self._toggle_labels)
        self.center_panel.mapModeChanged.connect(self._set_map_mode)
        self.center_panel.viewModeChanged.connect(self._set_view_mode)
        self.center_panel.resetRequested.connect(self._player_reset)
        self.center_panel.stepRequested.connect(self._player_step)
        self.center_panel.playPauseRequested.connect(self.toggle_play_pause)
        self.center_panel.speedChanged.connect(self._on_speed_change)
        self.center_panel.sliderMoved.connect(self._on_slider_move)
        self.network_canvas.pipeSelected.connect(self._on_pipe_selected)
        self.network_canvas.nodeSelected.connect(self._on_node_selected)
        self.basin_3d.pipeSelected.connect(self._on_3d_pipe_selected)
        self.basin_3d.nodeSelected.connect(self._on_3d_node_selected)
        self.center_panel.tour_card.previousRequested.connect(
            lambda: self._go_tour_stop(self.state.tour_step - 1)
        )
        self.center_panel.tour_card.nextRequested.connect(
            lambda: self._go_tour_stop(self.state.tour_step + 1)
        )
        self.center_panel.tour_card.closeRequested.connect(self._close_guided_tour)

        # Panel derecho
        self.right_tabs.currentChanged.connect(self._on_tab_changed)
        self.inspector_panel.focusSelectedRequested.connect(self._action_focus_selected)
        self.inspector_panel.toggleBasinIsolationRequested.connect(
            self._action_toggle_basin_isolation
        )
        self.inspector_panel.toggleNodeTraceRequested.connect(self._action_toggle_inspector_trace)
        self.inspector_panel.applyInterventionRequested.connect(self._action_apply_intervention)
        self.inspector_panel.restorePipeRequested.connect(self._action_restore_pipe)
        self.inspector_panel.restoreAllRequested.connect(self._action_restore_all_interventions)
        self.inspector_panel.pipe3dToggled.connect(lambda _exp: self._update_pipe_inspector_3d())

        self.critical_panel.filterChanged.connect(lambda _f: self._refresh_critical_table())
        self.critical_panel.pipeSelected.connect(self._on_critical_pipe_selected)
        self.critical_panel.pipeActivated.connect(self.network_canvas.focus_pipe)

        self.comparison_panel.compareRequested.connect(self._action_compare_scenarios)
        self.comparison_panel.scenarioActivated.connect(self._on_comparison_scenario_activated)

        self.max_flow_panel.recalculateRequested.connect(
            self._action_compute_max_flow_estimations
        )
        self.max_flow_panel.highlightMinCutRequested.connect(
            self._action_highlight_ford_fulkerson
        )
        self.max_flow_panel.targetFmaxActivated.connect(
            self._action_simulate_target_fmax
        )

    def _bind_shortcuts(self) -> None:
        self._shortcuts = [
            QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._shortcut_play_pause),
            QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._shortcut_step(-1)),
            QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._shortcut_step(1)),
            QShortcut(QKeySequence(Qt.Key.Key_Home), self, self._shortcut_home),
            QShortcut(QKeySequence("Ctrl+F"), self, self._shortcut_focus_search),
            QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._shortcut_escape),
        ]
        for sc in self._shortcuts:
            sc.setContext(Qt.ShortcutContext.WindowShortcut)

    def _is_typing_widget(self) -> bool:
        w = QApplication.focusWidget()
        if w is None:
            return False
        if isinstance(w, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)):
            return True
        if isinstance(w, QComboBox) and w.isEditable():
            return True
        return False

    def _shortcut_play_pause(self) -> None:
        if not self._is_typing_widget():
            self.toggle_play_pause()

    def _shortcut_step(self, delta: int) -> None:
        if not self._is_typing_widget():
            self._player_step(delta)

    def _shortcut_home(self) -> None:
        if not self._is_typing_widget():
            self._player_reset()

    def _shortcut_focus_search(self) -> None:
        if not self.state.show_left:
            self.toggle_left_panel()
        self.controls_panel.switch_rail_tab("trav")
        self.state.rail_tab = "trav"
        self.controls_panel.focus_search()

    def _shortcut_escape(self) -> None:
        if self.state.tour_active:
            self._close_guided_tour()
        self._clear_highlights()
        self.state.selected_pipe_id = None
        self.state.selected_node_id = None
        self.state.basin_isolated = False
        self.network_canvas.set_basin_focus(None, None)
        self.network_canvas.select_pipe(None)
        self.network_canvas.select_node(None)
        if self.state.view_mode == "3d":
            self.basin_3d.set_basin_focus(None, None)
            self.basin_3d.select_pipe(None)
            self.basin_3d.select_node(None)
        self._crit_tab_dirty = True
        self._charts_tab_dirty = True
        self.critical_panel.clear_selection()
        if (
            self.right_tabs.currentIndex() == 2
            and self.state.result is not None
            and self.state.result.snapshots
        ):
            self._charts_tab_dirty = False
            self._push_temporal_charts(throttle_draw=False)
        self._refresh_inspector()

    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _on_rail_tab_changed(self, tab_id: str) -> None:
        self.state.rail_tab = tab_id

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        if width < 200 or height < 200:
            return
        new_tier = (
            "wide"
            if width >= theme.BREAKPOINT_MEDIUM
            else ("medium" if width >= theme.BREAKPOINT_COMPACT else "compact")
        )
        tier_changed = new_tier != self.state.layout_tier
        self.state.layout_tier = new_tier

        sc = self._selected_scenario_obj()
        sid = (
            sc.scenario_id
            if sc is not None
            else (self.state.result.config.scenario_id if self.state.result else 3)
        )
        self.state.topbar_mode = self.top_bar.apply_responsive_mode(width, sid)
        self.lbl_shortcuts_hint.setVisible(width >= 980)

        if tier_changed:
            if new_tier == "compact" and self.state.show_left and self.state.show_right:
                self.state.show_right = False
                self._auto_collapsed_right = True
            elif new_tier != "compact" and self._auto_collapsed_right and not self.state.show_right:
                self.state.show_right = True
                self._auto_collapsed_right = False
            self._sync_panes()
            self.top_bar.set_panel_toggle_states(self.state.show_left, self.state.show_right)

        self._clamp_splitter_sizes(width)
        self._update_right_panel_responsive()

    def _sync_panes(self) -> None:
        self.controls_panel.setVisible(self.state.show_left)
        self.right_panel.setVisible(self.state.show_right)
        tier = self.state.layout_tier or "wide"
        self.controls_panel.setMinimumWidth(288 if tier == "wide" else 276)
        self.center_panel.setMinimumWidth(420 if tier == "wide" else 310)
        self.right_panel.setMinimumWidth(340 if tier == "wide" else 285)

    def _clamp_splitter_sizes(self, total_w: int) -> None:
        if total_w < 400:
            return
        if self.state.show_left and self.state.show_right:
            if total_w >= theme.BREAKPOINT_MEDIUM:
                left_w = min(int(round(312 * self._dpi_scale)), max(288, int(total_w * 0.22)))
                right_w = min(int(round(440 * self._dpi_scale)), max(360, int(total_w * 0.30)))
            else:
                left_w = min(286, max(276, int(total_w * 0.26)))
                right_w = min(344, max(296, int(total_w * 0.31)))
            center_w = max(310, total_w - left_w - right_w)
            self.main_splitter.setSizes([left_w, center_w, right_w])
        elif self.state.show_left:
            left_w = min(int(round(312 * self._dpi_scale)), max(284, int(total_w * 0.28)))
            self.main_splitter.setSizes([left_w, max(310, total_w - left_w), 0])
        elif self.state.show_right:
            right_w = min(int(round(420 * self._dpi_scale)), max(324, int(total_w * 0.39)))
            self.main_splitter.setSizes([0, max(310, total_w - right_w), right_w])
        else:
            self.main_splitter.setSizes([0, total_w, 0])

    _RIGHT_TAB_LABELS_FULL = ("Inspector", "Tuberías Críticas", "Evolución", "Comparación", "Flujo Máx.")
    _RIGHT_TAB_LABELS_COMPACT = ("Inspector", "Críticas", "Evolución", "Comparar", "F_max")

    # (padding horizontal px, tamaño pt, negrita) por nivel; debe coincidir con el QSS de RightTabs.
    _RIGHT_TAB_TIERS = {"false": (10, 9, True), "true": (6, 8, True), "tight": (4, 7, False)}

    def _tabs_required_width(self, labels: Tuple[str, ...], tier: str) -> int:
        pad_x, pt, bold = self._RIGHT_TAB_TIERS[tier]
        fm = QFontMetrics(QFont(self.ui_font, pt, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        per_tab_chrome = pad_x * 2 + 2 + 2  # padding + bordes + margin-right
        return sum(fm.horizontalAdvance(t) + per_tab_chrome for t in labels) + 12

    def _update_right_panel_responsive(self) -> None:
        rw = self.right_panel.width()
        if rw <= 0:
            return
        if rw >= self._tabs_required_width(self._RIGHT_TAB_LABELS_FULL, "false"):
            tier = "false"
        elif rw >= self._tabs_required_width(self._RIGHT_TAB_LABELS_COMPACT, "true"):
            tier = "true"
        else:
            tier = "tight"
        if tier != self._right_tabs_compact:
            self._right_tabs_compact = tier
            self.right_tabs.setProperty("compactTabs", tier)
            bar = self.right_tabs.tabBar()
            st = self.right_tabs.style()
            if st is not None:
                st.unpolish(self.right_tabs)
                st.polish(self.right_tabs)
                st.unpolish(bar)
                st.polish(bar)
            # La fuente se fija en el widget (no en QSS) para que el cálculo de ancho de cada
            # pestaña y el dibujo usen la misma métrica; el cambio de fuente recalcula el layout.
            pad_x, pt, bold = self._RIGHT_TAB_TIERS[tier]
            bar.setFont(QFont(self.ui_font, pt, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            labels = self._RIGHT_TAB_LABELS_FULL if tier == "false" else self._RIGHT_TAB_LABELS_COMPACT
            for idx, txt in enumerate(labels):
                self.right_tabs.setTabText(idx, txt)
        self.comparison_panel.set_hint_visible(rw >= 365)
        self.max_flow_panel.set_hint_visible(rw >= 365)

    def toggle_left_panel(self) -> None:
        self.state.show_left = not self.state.show_left
        if self.state.show_left and self.state.layout_tier == "compact":
            self.state.show_right = False
        self._sync_panes()
        self.top_bar.set_panel_toggle_states(self.state.show_left, self.state.show_right)
        self._clamp_splitter_sizes(self.width())
        self._update_right_panel_responsive()

    def toggle_right_panel(self) -> None:
        self._auto_collapsed_right = False
        self.state.show_right = not self.state.show_right
        if self.state.show_right and self.state.layout_tier == "compact":
            self.state.show_left = False
        self._sync_panes()
        self.top_bar.set_panel_toggle_states(self.state.show_left, self.state.show_right)
        self._clamp_splitter_sizes(self.width())
        self._update_right_panel_responsive()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is getattr(self, "right_panel", None) and event.type() == QEvent.Type.Resize:
            self._update_right_panel_responsive()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(self.width(), self.height())

    # ------------------------------------------------------------------
    # Carga de dataset y configuración
    # ------------------------------------------------------------------

    def _load_path(self, path: str, silent_error: bool = False) -> bool:
        try:
            dataset = load_dataset(path)
        except DataLoadError as exc:
            if not silent_error:
                QMessageBox.critical(self, "Error de validación de datos", str(exc))
            self._set_status(f"Error al cargar: {exc}")
            return False
        except Exception as exc:
            if not silent_error:
                QMessageBox.critical(self, "Error inesperado", str(exc))
            self._set_status(f"Error inesperado: {exc}")
            return False

        self.pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._close_guided_tour()
        self._task_runner.cancel_channel("comparison")
        self._task_runner.cancel_channel("max_flow")
        self._task_runner.cancel_channel("report")
        if self._deferred_charts_timer.isActive():
            self._deferred_charts_timer.stop()
        if self._deferred_compare_timer.isActive():
            self._deferred_compare_timer.stop()
        if self._deferred_fmax_timer.isActive():
            self._deferred_fmax_timer.stop()
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        self._pending_compare_job = None
        self._pending_fmax_job = None
        self._pending_traversal_highlights = None
        self.comparison_panel.set_loading(False)
        self.max_flow_panel.set_loading(False)
        self.temporal_charts.set_loading(False)

        n_nodes, n_pipes, _n_src, _n_snk, total_len = dataset.graph.summary()
        summary_text = (
            f"{n_nodes} nodos · {n_pipes} tuberías · {total_len:,.1f} m ({os.path.basename(path)})"
        )
        engine = SewerSimulationEngine(dataset.graph, dataset.basin)
        self.state.reset_for_dataset(dataset, engine, summary_text)
        self.state.max_flow_result = ford_fulkerson_max_flow(dataset.graph)
        self.controls_panel.update_fmax_summary(
            self.state.max_flow_result, self.controls_panel.read_util_cap_pct()
        )

        self.comparison_panel.clear_table()
        self.comparison_charts.update_comparison([])
        self.comparison_panel.reset_hint()
        self.max_flow_panel.clear_table()
        self.max_flow_panel.reset_hint()
        self.network_canvas.set_graph(dataset.graph)
        self.basin_3d.set_graph(dataset.graph)

        scen_labels = []
        self._scenario_display_map.clear()
        for s in dataset.scenarios:
            es_lbl = theme.format_scenario_display(s.scenario_id, s.condition, s.intensity_mm_h)
            scen_labels.append(es_lbl)
            self._scenario_display_map[es_lbl] = s
            self._scenario_display_map[s.display_name] = s
        extra_sc = PrecipitationScenario(
            scenario_id=0, intensity_mm_h=0.0, condition="Calibrado F_max"
        )
        extra_lbl = self.controls_panel.EXTRA_FMAX_SCENARIO_LABEL
        scen_labels.append(extra_lbl)
        self._scenario_display_map[extra_lbl] = extra_sc
        init_idx = 2 if len(dataset.scenarios) >= 3 else 0
        self.controls_panel.set_scenarios(scen_labels, init_idx)

        nids = dataset.graph.node_ids()
        srcs = dataset.graph.source_ids()
        snks = dataset.graph.sink_ids()
        self.controls_panel.set_node_choices(
            nids,
            srcs[0] if srcs else "6",
            snks[0] if snks else "31",
        )
        sc = self._selected_scenario_obj()
        if sc is not None:
            self.top_bar.update_tour_label(self.width(), sc.scenario_id)

        self._set_status(f"Red cargada: {summary_text}")
        self.controls_panel.update_structure_strip("Queue", [])
        self._refresh_inspector()
        return True

    def _selected_scenario_obj(self):
        if self.state.dataset is None:
            return None
        selected = self.controls_panel.combo_scenario.currentText()
        if selected in self._scenario_display_map:
            return self._scenario_display_map[selected]
        for sc in self.state.dataset.scenarios:
            if sc.display_name == selected:
                return sc
        return self.state.dataset.scenarios[0] if self.state.dataset.scenarios else None

    def _build_sim_config(self) -> SimulationConfig:
        assert self.state.dataset is not None
        sc = self._selected_scenario_obj()
        assert sc is not None
        _, duration, storm_dur, dt, ingress, dry_flow, split_rule, source_dist = (
            self.controls_panel.read_sim_inputs()
        )
        util_cap_pct = self.controls_panel.read_util_cap_pct()
        for val, name in (
            (duration, "Duración simulación"),
            (storm_dur, "Duración lluvia"),
            (dt, "Paso temporal Δt"),
            (ingress, "Ingreso pluvial (%)"),
            (dry_flow, "Caudal sanitario"),
            (util_cap_pct, "Tope físico uso (%)"),
        ):
            if not math.isfinite(val):
                raise ValueError(f"{name} debe ser un número finito.")
        if duration <= 0.0 or duration > 1440.0:
            raise ValueError("Duración simulación debe estar entre > 0 y 1440 min.")
        if storm_dur < 0.0 or storm_dur > 1440.0:
            raise ValueError("Duración lluvia debe estar entre 0 y 1440 min.")
        if dt <= 0.0 or dt > 60.0:
            raise ValueError("Paso temporal Δt debe estar entre > 0 y 60 min.")
        if ingress <= 0.0 or ingress > 100.0:
            raise ValueError("Ingreso pluvial (%) debe estar entre > 0 y 100 %.")
        if dry_flow < 0.0 or dry_flow > 10.0:
            raise ValueError("Caudal sanitario debe estar entre 0 y 10 m³/s.")
        if util_cap_pct < 100.0 or util_cap_pct > 300.0:
            raise ValueError("Tope físico uso (%) debe estar entre 100 % y 300 %.")

        return SimulationConfig(
            scenario_id=sc.scenario_id,
            scenario_name=sc.condition,
            intensity_mm_h=sc.intensity_mm_h,
            duration_min=max(5.0, duration),
            storm_duration_min=max(0.0, storm_dur),
            dt_min=max(0.25, dt),
            ingress_factor=max(0.001, min(1.0, ingress / 100.0)),
            dry_weather_flow_per_source_m3s=max(0.0, dry_flow),
            split_rule=split_rule,
            source_distribution=source_dist,
            max_physical_utilization_pct=util_cap_pct,
            use_ford_fulkerson_admission=True,
            admission_mode="source_local",
            target_fmax_pct=self.state.active_target_fmax_pct,
            interventions=dict(self.state.interventions),
        )

    def _mark_comparisons_dirty(self) -> None:
        self.state.comparisons_dirty = True
        self.comparison_panel.mark_dirty(bool(self.state.comparisons))
        self.state.max_flow_dirty = True
        self.max_flow_panel.mark_dirty(bool(self.state.max_flow_estimations))

    def _show_extra_fmax_banner(self) -> None:
        ff_res = self.state.max_flow_result
        if ff_res is None or self.state.dataset is None:
            return
        f_max = ff_res.max_flow_m3s
        cap_pct = self.controls_panel.read_util_cap_pct()
        cut_txt = ", ".join(ff_res.min_cut_pipes[:6]) or "Ninguno"
        self.network_canvas.set_banner(
            f"Escenario Extra · F_max = {f_max:.4f} m³/s",
            (
                f"• Tope físico de uso: {cap_pct:.0f}% (ref. {f_max * (cap_pct / 100.0):.4f} m³/s)\n"
                f"• Corte mínimo ({len(ff_res.min_cut_pipes)} tramos): {cut_txt}"
            ),
        )

    def _on_scenario_changed(self) -> None:
        if self.controls_panel.demand_mode() == "fmax":
            self.state.active_target_fmax_pct = self.controls_panel.read_target_fmax_pct()
            self._on_simulation_option_changed(mark_comp=False)
            self._show_extra_fmax_banner()
        else:
            self.state.active_target_fmax_pct = None
            self.network_canvas.clear_banner()
            self._on_simulation_option_changed(mark_comp=False)

    def _on_execute_sim_clicked(self) -> None:
        self.state.active_target_fmax_pct = self.controls_panel.read_target_fmax_pct()
        self.run_simulation(preserve_previous=False, auto_play=True)

    def _on_demand_target_changed(self, target_pct: Optional[float]) -> None:
        """Cambio de modo de demanda o de % objetivo: se trata como un parámetro más."""
        self.state.active_target_fmax_pct = (
            None if target_pct is None else max(0.0, min(300.0, float(target_pct)))
        )
        self.run_simulation(preserve_previous=False)

    def _on_params_changed(self) -> None:
        self._mark_comparisons_dirty()
        if self.state.dataset is None or self.state.engine is None:
            return
        try:
            self._build_sim_config()
        except ValueError:
            return
        self._on_simulation_option_changed(mark_comp=True)

    def _on_simulation_option_changed(self, mark_comp: bool = True) -> None:
        if mark_comp:
            self._mark_comparisons_dirty()
        self.run_simulation(preserve_previous=False)

    def run_simulation(self, preserve_previous: bool = False, auto_play: bool = False) -> None:
        if self.state.dataset is None or self.state.engine is None:
            return
        self.controls_panel.cancel_pending_param_rerun()
        self.pause()
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            QMessageBox.critical(
                self, "Parámetros inválidos", f"Revise los parámetros numéricos: {exc}"
            )
            return

        prev_scenario_id = (
            self.state.result.config.scenario_id if self.state.result is not None else None
        )
        base_cfg = replace(cfg, interventions={})

        if self.state.interventions:
            if (
                self.state.baseline_result is not None
                and replace(self.state.baseline_result.config, interventions={}) == base_cfg
            ):
                pass
            elif (
                self.state.result is not None
                and not self.state.result.config.interventions
                and replace(self.state.result.config, interventions={}) == base_cfg
            ):
                self.state.baseline_result = self.state.result
            else:
                self.state.baseline_result = self.state.engine.run(base_cfg)
            self.state.previous_result = self.state.baseline_result
        else:
            self.state.previous_result = None

        self.state.result = self.state.engine.run(cfg)
        self.state.max_flow_result = self.state.result.max_flow_result
        self.controls_panel.update_fmax_summary(
            self.state.max_flow_result, cfg.max_physical_utilization_pct
        )
        if not self.state.interventions:
            self.state.baseline_result = self.state.result
        self.state.last_attr_key = None

        n_snaps = len(self.state.result.snapshots)
        if auto_play and self.state.map_mode != "instant":
            self.state.map_mode = "instant"
            self.center_panel.set_map_mode_active("instant")

        peak_all, ov_all, dur_total = self.state.global_stress_maps()
        self.network_canvas.set_map_mode(
            self.state.map_mode,
            peak_util=peak_all,
            overload_minutes=ov_all,
            total_duration_min=dur_total,
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_map_mode(
                self.state.map_mode,
                peak_util=peak_all,
                overload_minutes=ov_all,
                total_duration_min=dur_total,
            )
        end_min = (
            self.state.result.snapshots[-1].time_min
            if self.state.result.snapshots
            else cfg.duration_min
        )
        self.center_panel.set_slider_range(max(0, n_snaps - 1), end_min)
        self.top_bar.update_tour_label(self.width(), cfg.scenario_id)

        self._set_step(0)
        if auto_play:
            if self.state.tour_active:
                self._close_guided_tour(reset_view=True)
            if n_snaps > 1:
                self._player_play()
        elif self.state.tour_active:
            scenario_changed = prev_scenario_id is not None and prev_scenario_id != cfg.scenario_id
            self._go_tour_stop(
                0 if scenario_changed else self.state.tour_step,
                animate_cam=scenario_changed,
            )

        self._set_status(
            f"{self.state.dataset_summary_text}  ·  Escenario {cfg.scenario_id} ({cfg.intensity_mm_h:.0f} mm/h) "
            f"en {self.state.result.execution_time_ms:.1f} ms ({n_snaps} instantes)"
        )

    # ------------------------------------------------------------------
    # Reproducción y sincronización de paso
    # ------------------------------------------------------------------

    def _set_step(self, step_idx: int) -> None:
        if self.state.result is None or not self.state.result.snapshots:
            return
        step_idx = max(0, min(len(self.state.result.snapshots) - 1, step_idx))
        self.state.current_step = step_idx
        snap = self.state.result.snapshots[step_idx]

        self.center_panel.set_slider_value(step_idx)

        peak_all, ov_all, dur_total = self.state.global_stress_maps()
        self.network_canvas.set_stress_maps(
            peak_util=peak_all,
            overload_minutes=ov_all,
            total_duration_min=dur_total,
        )
        canvas_snap = (
            snap if self.state.map_mode == "instant" else self.state.result.snapshots[-1]
        )
        self.network_canvas.set_snapshot(canvas_snap)
        if self.state.view_mode == "3d":
            self._sync_basin_3d_step(canvas_snap, peak_all, ov_all, dur_total)
        self.center_panel.update_telemetry(
            map_mode=self.state.map_mode,
            result=self.state.result,
            snap=snap,
            peak_all=peak_all,
            ov_all=ov_all,
            dur_total=dur_total,
        )
        self.controls_panel.update_legend(
            self.state.map_mode,
            snap,
            peak_all,
            ov_all,
            dur_total,
            cap_pct=self.state.result.utilization_cap_pct,
        )

        active_tab = self.right_tabs.currentIndex()
        if active_tab == 1:
            self._crit_tab_dirty = False
            self._refresh_critical_table()
        else:
            self._crit_tab_dirty = True

        if active_tab == 0 or not self.state.is_playing:
            self._insp_tab_dirty = False
            self._refresh_inspector()
        else:
            self._insp_tab_dirty = True

        if active_tab == 2:
            self._charts_tab_dirty = False
            self._push_temporal_charts(throttle_draw=self.state.is_playing)
        else:
            self._charts_tab_dirty = True

    def _handoff_active_traversal_if_any(self) -> None:
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        if self.state.is_animating_traversal or self.network_canvas._traversal_frame is not None:
            self._stop_traversal_anim(clear_canvas=False)
            self._promote_finished_traversal_to_live_route()

    def _on_slider_move(self, step: int) -> None:
        if step == self.state.current_step:
            return
        self.pause()
        self._handoff_active_traversal_if_any()
        if self.state.map_mode != "instant":
            self.state.map_mode = "instant"
            self.center_panel.set_map_mode_active("instant")
            self.network_canvas._map_mode = "instant"
        self._set_step(step)

    def _on_speed_change(self, speed_label: str) -> None:
        self.state.speed_label = speed_label
        if self.state.is_playing:
            self.network_canvas.set_playing(True, self.state.speed_factor())

    def toggle_play_pause(self) -> None:
        if self.state.is_playing:
            self.pause()
        else:
            self._player_play()

    def _player_play(self) -> None:
        if self.state.result is None or len(self.state.result.snapshots) <= 1:
            return
        if self._play_timer.isActive():
            self._play_timer.stop()
        if self.state.tour_active:
            self._close_guided_tour(reset_view=True)
        if self.state.map_mode != "instant":
            self._set_map_mode("instant")
        self._handoff_active_traversal_if_any()
        if self.state.current_step >= len(self.state.result.snapshots) - 1:
            self._set_step(0)
        self.state.is_playing = True
        self.center_panel.set_playing_state(True)
        self.network_canvas.set_playing(True, self.state.speed_factor())
        self._play_timer.start(self.state.frame_delay_ms())

    def pause(self) -> None:
        was_playing = self.state.is_playing
        self.state.is_playing = False
        if self._play_timer.isActive():
            self._play_timer.stop()
        self.network_canvas.set_playing(False)
        self.center_panel.set_playing_state(False)
        if was_playing and self.state.result is not None and self.state.result.snapshots:
            active_tab = self.right_tabs.currentIndex()
            if active_tab == 2:
                self._push_temporal_charts(throttle_draw=False)
            elif active_tab == 0 and self._insp_tab_dirty:
                self._insp_tab_dirty = False
                self._refresh_inspector()

    def _player_reset(self) -> None:
        self.pause()
        self._handoff_active_traversal_if_any()
        if self.state.map_mode != "instant":
            self.state.map_mode = "instant"
            self.center_panel.set_map_mode_active("instant")
            self.network_canvas._map_mode = "instant"
        self._set_step(0)

    def _player_step(self, delta: int) -> None:
        self.pause()
        self._handoff_active_traversal_if_any()
        if self.state.map_mode != "instant":
            self.state.map_mode = "instant"
            self.center_panel.set_map_mode_active("instant")
            self.network_canvas._map_mode = "instant"
        self._set_step(self.state.current_step + delta)

    def _schedule_next_frame(self) -> None:
        if not self.state.is_playing or self.state.result is None:
            return
        if self.state.current_step >= len(self.state.result.snapshots) - 1:
            self.pause()
            return
        self._set_step(self.state.current_step + 1)
        if self.state.is_playing:
            self._play_timer.start(self.state.frame_delay_ms())

    def _toggle_labels(self, show_ids: bool, show_util: bool) -> None:
        self.network_canvas.show_pipe_labels = show_ids
        self.network_canvas.show_util_labels = show_util
        self.network_canvas.redraw()
        if self.state.view_mode == "3d":
            self.basin_3d.set_labels_visible(show_ids, show_util)

    def _set_view_mode(self, mode: str) -> None:
        norm = "3d" if mode == "3d" else "2d"
        if norm == self.state.view_mode:
            return
        if norm == "3d" and self.state.tour_active:
            self._close_guided_tour(reset_view=False)
        self.state.view_mode = norm
        self.center_panel.set_view_mode_active(norm)
        if norm == "3d":
            self._sync_basin_3d_full()
        else:
            self.basin_3d.close_overlays()

    def _sync_basin_3d_step(
        self,
        canvas_snap: TimeStepSnapshot,
        peak_all: Dict[str, float],
        ov_all: Dict[str, float],
        dur_total: float,
    ) -> None:
        self.basin_3d.set_stress_maps(
            peak_util=peak_all,
            overload_minutes=ov_all,
            total_duration_min=dur_total,
        )
        self.basin_3d.set_snapshot(canvas_snap, self.state.result)

    def _sync_basin_3d_full(self) -> None:
        self.basin_3d.set_labels_visible(
            self.network_canvas.show_pipe_labels,
            self.network_canvas.show_util_labels,
        )
        self.basin_3d.set_interventions(
            self.state.interventions,
            self.state.isolated_nodes,
            self.state.isolated_pipes,
        )
        if self.state.basin_isolated:
            self.basin_3d.set_basin_focus(
                self.network_canvas._basin_nodes,
                self.network_canvas._basin_pipes,
            )
        else:
            self.basin_3d.set_basin_focus(None, None)
        self.basin_3d.set_highlights(
            self.network_canvas.highlight_pipe_ids,
            self.network_canvas.highlight_node_ids,
        )
        if self.state.selected_pipe_id:
            self.basin_3d.select_pipe(self.state.selected_pipe_id)
        elif self.state.selected_node_id:
            self.basin_3d.select_node(self.state.selected_node_id)
        else:
            self.basin_3d.select_pipe(None)

        if self.state.result is not None and self.state.result.snapshots:
            peak_all, ov_all, dur_total = self.state.global_stress_maps()
            snap_cur = self.state.result.snapshots[self.state.current_step]
            canvas_snap = (
                snap_cur
                if self.state.map_mode == "instant"
                else self.state.result.snapshots[-1]
            )
            self.basin_3d.set_map_mode(
                self.state.map_mode,
                peak_util=peak_all,
                overload_minutes=ov_all,
                total_duration_min=dur_total,
            )
            self.basin_3d.set_snapshot(canvas_snap, self.state.result)
        else:
            self.basin_3d.set_map_mode(self.state.map_mode)

    def _on_3d_pipe_selected(self, pipe_id: str) -> None:
        self.network_canvas.select_pipe(pipe_id)
        self._on_pipe_selected(pipe_id)

    def _on_3d_node_selected(self, node_id: str) -> None:
        self.network_canvas.select_node(node_id)
        self._on_node_selected(node_id)

    def _update_pipe_inspector_3d(self) -> None:
        if (
            self.state.dataset is None
            or not self.state.selected_pipe_id
            or not self.inspector_panel.is_pipe_3d_expanded()
        ):
            return
        edge = self.state.dataset.graph.get_pipe(self.state.selected_pipe_id)
        if edge is None:
            return
        snap = self.state.current_snapshot()
        ps = snap.pipe_states.get(edge.pipe_id) if snap is not None else None
        upstream_ns = snap.node_states.get(edge.from_node) if snap is not None else None
        inv = self.state.interventions.get(edge.pipe_id)
        max_storage = (
            self.state.result.config.max_manhole_storage_m3
            if self.state.result is not None
            else 4.0
        )
        self.inspector_panel.update_pipe_3d(
            edge,
            ps,
            upstream_ns,
            inv,
            max_manhole_storage_m3=max_storage,
        )

    def _set_map_mode(self, mode: str) -> None:
        if mode not in ("instant", "peak", "overload_minutes"):
            return
        if mode in ("peak", "overload_minutes"):
            self.pause()
        self.state.map_mode = mode
        self.center_panel.set_map_mode_active(mode)
        if self.state.result is not None and self.state.result.snapshots:
            peak_all, ov_all, dur_total = self.state.global_stress_maps()
            snap_cur = self.state.result.snapshots[self.state.current_step]
            canvas_snap = snap_cur if mode == "instant" else self.state.result.snapshots[-1]
            self.network_canvas.snapshot = canvas_snap
            self.network_canvas.set_map_mode(
                mode,
                peak_util=peak_all,
                overload_minutes=ov_all,
                total_duration_min=dur_total,
            )
            if self.state.view_mode == "3d":
                self.basin_3d.set_map_mode(
                    mode,
                    peak_util=peak_all,
                    overload_minutes=ov_all,
                    total_duration_min=dur_total,
                )
                self.basin_3d.set_snapshot(canvas_snap, self.state.result)
            self.center_panel.update_telemetry(
                map_mode=mode,
                result=self.state.result,
                snap=snap_cur,
                peak_all=peak_all,
                ov_all=ov_all,
                dur_total=dur_total,
            )
            self.controls_panel.update_legend(
                mode,
                snap_cur,
                peak_all,
                ov_all,
                dur_total,
                cap_pct=self.state.result.utilization_cap_pct,
            )
        else:
            self.network_canvas.set_map_mode(mode)
            if self.state.view_mode == "3d":
                self.basin_3d.set_map_mode(mode)

    # ------------------------------------------------------------------
    # Selección, Inspector, Intervenciones y Críticas
    # ------------------------------------------------------------------

    def _on_pipe_selected(self, pipe_id: str) -> None:
        self.state.selected_pipe_id = pipe_id
        self.state.selected_node_id = None
        if self.state.view_mode == "3d":
            self.basin_3d.select_pipe(pipe_id)
        if self.state.inspector_trace_state is not None:
            self.state.inspector_trace_state = None
        if self.state.dataset is not None:
            edge = self.state.dataset.graph.get_pipe(pipe_id)
            self.inspector_panel.sync_intervention_controls(
                edge, self.state.interventions.get(pipe_id)
            )
        if self.state.basin_isolated:
            self._apply_basin_isolation()
        if self.right_tabs.currentIndex() == 1:
            self.critical_panel.select_pipe(pipe_id, scroll_into_view=not self.state.is_playing)
        else:
            self._crit_tab_dirty = True
        self._refresh_inspector()
        if self.state.result is not None:
            if self.right_tabs.currentIndex() == 2:
                self._charts_tab_dirty = False
                self._push_temporal_charts(throttle_draw=False)
            else:
                self._charts_tab_dirty = True

    def _on_node_selected(self, node_id: str) -> None:
        if (
            self.state.inspector_trace_state is not None
            and self.state.inspector_trace_state[0] != node_id
        ):
            self.state.inspector_trace_state = None
        self.state.selected_node_id = node_id
        self.state.selected_pipe_id = None
        if self.state.view_mode == "3d":
            self.basin_3d.select_node(node_id)
        self.controls_panel.combo_bfs_start.setCurrentText(node_id)
        if self.state.basin_isolated:
            self._apply_basin_isolation()
        self._crit_tab_dirty = True
        self.critical_panel.clear_selection()
        self._refresh_inspector()
        if self.state.result is not None:
            if self.right_tabs.currentIndex() == 2:
                self._charts_tab_dirty = False
                self._push_temporal_charts(throttle_draw=False)
            else:
                self._charts_tab_dirty = True

    def _on_critical_pipe_selected(self, pipe_id: str) -> None:
        if pipe_id == self.state.selected_pipe_id:
            return
        self.network_canvas.select_pipe(pipe_id)
        self._on_pipe_selected(pipe_id)

    def _action_focus_selected(self) -> None:
        if self.state.selected_pipe_id:
            self.network_canvas.focus_pipe(self.state.selected_pipe_id)
        elif self.state.selected_node_id:
            self.network_canvas.focus_node(self.state.selected_node_id)

    def _action_toggle_basin_isolation(self) -> None:
        if self.state.dataset is None or (
            not self.state.selected_pipe_id and not self.state.selected_node_id
        ):
            QMessageBox.information(
                self, "Sin selección", "Seleccione primero un nodo o tubería del grafo."
            )
            return
        if self.state.tour_active:
            self._close_guided_tour()
        self.state.basin_isolated = not self.state.basin_isolated
        self._apply_basin_isolation()
        self._refresh_inspector()

    def _apply_basin_isolation(self) -> None:
        if not self.state.basin_isolated or self.state.dataset is None:
            self.network_canvas.set_basin_focus(None, None)
            if self.state.view_mode == "3d":
                self.basin_3d.set_basin_focus(None, None)
            return
        g = self.state.dataset.graph
        focus_nodes: Set[str] = set()
        focus_pipes: Set[str] = set()

        if self.state.selected_pipe_id and g.has_pipe(self.state.selected_pipe_id):
            edge = g.get_pipe(self.state.selected_pipe_id)
            assert edge is not None
            up_n, up_p = trace_upstream(g, edge.from_node)
            dn_n, dn_p = trace_downstream(g, edge.to_node)
            focus_nodes = set(up_n) | set(dn_n)
            focus_pipes = (
                {p.pipe_id for p in up_p} | {p.pipe_id for p in dn_p} | {edge.pipe_id}
            )
        elif self.state.selected_node_id and g.has_node(self.state.selected_node_id):
            up_n, up_p = trace_upstream(g, self.state.selected_node_id)
            dn_n, dn_p = trace_downstream(g, self.state.selected_node_id)
            focus_nodes = set(up_n) | set(dn_n)
            focus_pipes = {p.pipe_id for p in up_p} | {p.pipe_id for p in dn_p}
        else:
            self.state.basin_isolated = False
            self.network_canvas.set_basin_focus(None, None)
            return

        self.network_canvas.set_basin_focus(focus_nodes, focus_pipes)
        if self.state.view_mode == "3d":
            self.basin_3d.set_basin_focus(focus_nodes, focus_pipes)
        self._set_status(
            f"Cuenca aislada: {len(focus_nodes)} nodo(s) y {len(focus_pipes)} tramo(s) activos hacia PTAR 31."
        )

    def _sync_isolation_and_canvas(self) -> None:
        if self.state.dataset is None:
            return
        blocked = {pid for pid, inv in self.state.interventions.items() if inv.is_closed}
        self.state.isolated_nodes, self.state.isolated_pipes = find_isolated_from_sinks(
            self.state.dataset.graph, blocked
        )
        self.network_canvas.set_interventions(
            self.state.interventions,
            self.state.isolated_nodes,
            self.state.isolated_pipes,
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_interventions(
                self.state.interventions,
                self.state.isolated_nodes,
                self.state.isolated_pipes,
            )
        self._mark_comparisons_dirty()

    def _action_apply_intervention(self, obst_pct: float, diam_raw: str) -> None:
        if self.state.dataset is None or not self.state.selected_pipe_id:
            return
        edge = self.state.dataset.graph.get_pipe(self.state.selected_pipe_id)
        if edge is None:
            return
        try:
            obst = float(obst_pct)
            if not math.isfinite(obst) or obst < 0.0 or obst > 100.0:
                raise ValueError("La obstrucción debe estar entre 0 % y 100 %.")
            diam_override = parse_diameter_override(diam_raw, edge.diameter_in)
        except Exception as exc:
            QMessageBox.warning(self, "Intervención inválida", str(exc))
            return

        if obst <= 1e-6 and diam_override is None:
            self.state.interventions.pop(edge.pipe_id, None)
        else:
            self.state.interventions[edge.pipe_id] = PipeIntervention(
                pipe_id=edge.pipe_id,
                obstruction_pct=obst,
                diameter_in_override=diam_override,
            )

        self.inspector_panel.sync_intervention_controls(
            edge, self.state.interventions.get(edge.pipe_id)
        )
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)
        if self.state.isolated_nodes:
            self._set_status(
                f"Cirugía en {edge.pipe_id}: {len(self.state.isolated_nodes)} nodo(s) aislados de la PTAR 31."
            )

    def _action_restore_pipe(self) -> None:
        pid = self.state.selected_pipe_id
        if not pid or pid not in self.state.interventions:
            return
        self.state.interventions.pop(pid, None)
        if self.state.dataset is not None:
            self.inspector_panel.sync_intervention_controls(
                self.state.dataset.graph.get_pipe(pid), None
            )
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)

    def _action_restore_all_interventions(self) -> None:
        if not self.state.interventions:
            return
        self.state.interventions.clear()
        if self.state.dataset is not None and self.state.selected_pipe_id:
            self.inspector_panel.sync_intervention_controls(
                self.state.dataset.graph.get_pipe(self.state.selected_pipe_id), None
            )
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)

    def _action_toggle_inspector_trace(self, direction: str) -> None:
        if self.state.dataset is None or not self.state.selected_node_id:
            return
        if self.state.inspector_trace_state == (self.state.selected_node_id, direction):
            self.state.inspector_trace_state = None
            self.network_canvas.set_highlights(set(), set())
            if self.state.view_mode == "3d":
                self.basin_3d.set_highlights(set(), set())
            self._refresh_inspector()
            self._set_status("Vista de red restaurada.")
            return
        self.controls_panel.combo_bfs_start.setCurrentText(self.state.selected_node_id)
        self._run_trace(direction)
        self.state.inspector_trace_state = (self.state.selected_node_id, direction)
        self._refresh_inspector()

    def _refresh_inspector(self) -> None:
        sel_kind = (
            "pipe"
            if self.state.selected_pipe_id
            else ("node" if self.state.selected_node_id else "none")
        )
        trace_dir = None
        if (
            sel_kind == "node"
            and self.state.inspector_trace_state is not None
            and self.state.inspector_trace_state[0] == self.state.selected_node_id
        ):
            trace_dir = self.state.inspector_trace_state[1]

        self.inspector_panel.sync_action_bars(
            sel_kind=sel_kind,
            n_interventions=len(self.state.interventions),
            basin_isolated=self.state.basin_isolated,
            trace_dir=trace_dir,
        )

        if sel_kind != "none" and self.state.dataset is not None:
            self._refresh_source_attribution_panel()

        snap = self.state.current_snapshot()
        self.inspector_panel.render_details(
            dataset=self.state.dataset,
            result=self.state.result,
            snap=snap,
            selected_pipe_id=self.state.selected_pipe_id,
            selected_node_id=self.state.selected_node_id,
            interventions=self.state.interventions,
            isolated_nodes=self.state.isolated_nodes,
            isolated_pipes=self.state.isolated_pipes,
        )
        self._update_pipe_inspector_3d()

    def _refresh_source_attribution_panel(self) -> None:
        if self.state.dataset is None or (
            not self.state.selected_pipe_id and not self.state.selected_node_id
        ):
            return
        g = self.state.dataset.graph
        snap = self.state.current_snapshot()
        qmax_over = (
            {
                pid: ps.effective_q_max_m3s
                for pid, ps in snap.pipe_states.items()
                if ps.effective_q_max_m3s is not None
            }
            if snap is not None
            else None
        )
        _, _, _, _, _, _, split_rule, source_dist = self.controls_panel.read_sim_inputs()
        entity_kind = "pipe" if self.state.selected_pipe_id else "node"
        entity_id = self.state.selected_pipe_id or self.state.selected_node_id or ""
        attr_key = (
            id(g),
            id(snap),
            split_rule,
            source_dist,
            entity_kind,
            entity_id,
            tuple(sorted(self.state.interventions.items(), key=lambda kv: kv[0])),
        )
        if attr_key == self.state.last_attr_key:
            return
        self.state.last_attr_key = attr_key

        attr = compute_source_attribution(
            g,
            snapshot=snap,
            split_rule=split_rule,
            pipe_qmax_overrides=qmax_over,
            source_distribution=source_dist,
        )
        self.state.source_attribution = attr
        if entity_kind == "pipe":
            shares = attr.pipe_shares.get(entity_id, [])
            ent_lbl = f"Tramo {entity_id}"
        else:
            shares = attr.node_shares.get(entity_id, [])
            ent_lbl = f"PTAR {entity_id}" if entity_id == "31" else f"Pozo {entity_id}"
        self.inspector_panel.update_source_attribution(ent_lbl, shares, split_rule)

    def _refresh_critical_table(self) -> None:
        snap = self.state.current_snapshot()
        self.critical_panel.refresh(
            dataset=self.state.dataset,
            result=self.state.result,
            snap=snap,
            selected_pipe_id=self.state.selected_pipe_id,
            is_playing=self.state.is_playing,
        )

    # ------------------------------------------------------------------
    # Gráficas temporales, Comparación y Pestañas
    # ------------------------------------------------------------------

    def _resolve_active_route(self) -> List[PipeEdge]:
        if self.state.dataset is None:
            return []
        g = self.state.dataset.graph
        if self.state.active_route_pipes:
            return list(self.state.active_route_pipes)
        if self.state.selected_pipe_id and g.has_pipe(self.state.selected_pipe_id):
            return build_route_to_sink(g, pipe_id=self.state.selected_pipe_id, sink_id="31")
        if self.state.selected_node_id and g.has_node(self.state.selected_node_id):
            return build_route_to_sink(g, node_id=self.state.selected_node_id, sink_id="31")
        if self.state.result is not None and self.state.result.peak_pipe_utilization:
            top_pid, top_u = max(
                self.state.result.peak_pipe_utilization.items(),
                key=lambda kv: (kv[1], self.state.result.peak_pipe_demand_ratio.get(kv[0], 0.0)),
            )
            if top_u > 1e-6 and g.has_pipe(top_pid):
                return build_route_to_sink(g, pipe_id=top_pid, sink_id="31")
        if g.has_pipe("P25"):
            return build_route_to_sink(g, pipe_id="P25", sink_id="31")
        if g.has_pipe("P31"):
            return build_route_to_sink(g, pipe_id="P31", sink_id="31")
        srcs = g.source_ids()
        if srcs:
            return build_route_to_sink(g, node_id=srcs[0], sink_id="31")
        return []

    def _push_temporal_charts(self, throttle_draw: bool = False) -> None:
        if self.state.result is None or not self.state.result.snapshots:
            return
        step_idx = max(0, min(len(self.state.result.snapshots) - 1, self.state.current_step))
        snap = self.state.result.snapshots[step_idx]
        self.temporal_charts.update_plots(
            self.state.result,
            self.state.selected_pipe_id,
            snap.time_min,
            previous_result=self.state.previous_result,
            route_pipes=self._resolve_active_route(),
            current_step_index=step_idx,
            diameter_overrides=self.state.diameter_overrides_map(),
            interventions=dict(self.state.interventions),
            throttle_draw=throttle_draw,
        )

    def _run_deferred_temporal_charts(self) -> None:
        try:
            if self.state.result is not None and self.state.result.snapshots:
                if self.right_tabs.currentIndex() != 2:
                    self._charts_tab_dirty = True
                    return
                self._push_temporal_charts(throttle_draw=False)
                qapp = QApplication.instance()
                if qapp is not None:
                    qapp.processEvents()
        finally:
            self.temporal_charts.set_loading(False)

    def _on_tab_changed(self, idx: int) -> None:
        if self.state.dataset is None:
            return
        if idx == 0 and self._insp_tab_dirty:
            self._insp_tab_dirty = False
            self._refresh_inspector()
        elif idx == 1 and self._crit_tab_dirty:
            self._crit_tab_dirty = False
            self._refresh_critical_table()
        elif idx == 2 and self._charts_tab_dirty and self.state.result is not None:
            self._charts_tab_dirty = False
            self.temporal_charts.set_loading(True, "Generando gráficas...")
            self._deferred_charts_timer.start()
        elif idx == 3 and (not self.state.comparisons or self.state.comparisons_dirty):
            if not self.is_comparison_running():
                self._action_compare_scenarios()
        elif idx == 4 and (not self.state.max_flow_estimations or self.state.max_flow_dirty):
            if not self.is_max_flow_running():
                self._action_compute_max_flow_estimations()

    def is_comparison_running(self) -> bool:
        """Indica si hay una comparación diferida o ejecutándose en segundo plano."""
        return self._deferred_compare_timer.isActive() or self._task_runner.is_busy("comparison")

    def is_max_flow_running(self) -> bool:
        """Indica si hay una estimación Ford-Fulkerson diferida o en segundo plano."""
        return self._deferred_fmax_timer.isActive() or self._task_runner.is_busy("max_flow")

    def _action_compare_scenarios(self) -> None:
        if self.state.dataset is None:
            return
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            QMessageBox.critical(
                self, "Parámetros inválidos", f"Revise los parámetros numéricos: {exc}"
            )
            return

        dataset = self.state.dataset
        cfg_copy = replace(cfg, interventions=dict(cfg.interventions))
        self._task_runner.cancel_channel("comparison")
        self._pending_compare_job = (dataset, cfg_copy)
        self.comparison_panel.set_loading(
            True, "Simulando 5 escenarios y generando gráficas..."
        )
        self._set_status("Calculando comparación de los 5 escenarios...")
        # Diferimos 15 ms el arranque del hilo para que Qt pinte primero la pestaña y el spinner.
        self._deferred_compare_timer.start()

    def _launch_pending_comparison(self) -> None:
        job = self._pending_compare_job
        self._pending_compare_job = None
        if job is None or self.state.dataset is None:
            return
        dataset, cfg_copy = job
        if self.state.dataset is not dataset:
            return

        def _compute_task() -> Tuple[list, float]:
            t_start = time.perf_counter()
            summaries = compare_all_scenarios(dataset, cfg_copy)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return summaries, elapsed_ms

        def _on_done(payload: Tuple[list, float]) -> None:
            if self.state.dataset is not dataset:
                return
            summaries, elapsed_ms = payload
            try:
                still_fresh = self._build_sim_config() == cfg_copy
            except Exception:
                still_fresh = False
            self.state.comparisons = summaries
            self.state.comparisons_dirty = not still_fresh
            if still_fresh:
                self.comparison_panel.mark_clean(elapsed_ms)
            else:
                self.comparison_panel.mark_dirty(True)
            self.comparison_panel.populate(summaries)
            self._set_status(
                f"Comparación de los 5 escenarios recalculada en {elapsed_ms:.0f} ms."
            )

        def _on_err(exc: Exception) -> None:
            self.comparison_panel.reset_hint()
            QMessageBox.critical(
                self,
                "Error al comparar escenarios",
                f"No se pudo completar la comparación:\n{exc}",
            )
            self._set_status("Error al recalcular comparación.")

        self._task_runner.submit(
            "comparison",
            _compute_task,
            on_success=_on_done,
            on_error=_on_err,
            on_finally=lambda: self.comparison_panel.set_loading(False),
        )

    def _action_compute_max_flow_estimations(self) -> None:
        if self.state.dataset is None:
            return
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            QMessageBox.critical(
                self, "Parámetros inválidos", f"Revise los parámetros numéricos: {exc}"
            )
            return

        dataset = self.state.dataset
        cfg_copy = replace(cfg, target_fmax_pct=None, interventions=dict(cfg.interventions))
        self._task_runner.cancel_channel("max_flow")
        self._pending_fmax_job = (dataset, cfg_copy)
        self.max_flow_panel.set_loading(
            True, "Calculando flujo máximo Ford-Fulkerson y curvas de saturación..."
        )
        self._set_status("Calculando estimaciones Ford-Fulkerson por % de F_max...")
        self._deferred_fmax_timer.start()

    def _launch_pending_max_flow(self) -> None:
        job = self._pending_fmax_job
        self._pending_fmax_job = None
        if job is None or self.state.dataset is None:
            return
        dataset, cfg_copy = job
        if self.state.dataset is not dataset:
            return

        def _compute_task() -> Tuple[object, list, float]:
            t_start = time.perf_counter()
            ff_res, rows = estimate_fmax_scenarios(dataset, cfg_copy)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return ff_res, rows, elapsed_ms

        def _on_done(payload: Tuple[object, list, float]) -> None:
            if self.state.dataset is not dataset:
                return
            ff_res, rows, elapsed_ms = payload
            try:
                cur_cfg = replace(self._build_sim_config(), target_fmax_pct=None)
                still_fresh = cur_cfg == cfg_copy
            except Exception:
                still_fresh = False
            self.state.max_flow_result = ff_res
            self.state.max_flow_estimations = rows
            self.state.max_flow_dirty = not still_fresh
            if still_fresh:
                self.max_flow_panel.mark_clean(elapsed_ms)
            else:
                self.max_flow_panel.mark_dirty(True)
            self.max_flow_panel.populate(
                ff_res, rows, cfg_copy.max_physical_utilization_pct
            )
            self.controls_panel.update_fmax_summary(
                ff_res, cfg_copy.max_physical_utilization_pct
            )
            self._set_status(
                f"Estimaciones Ford-Fulkerson actualizadas (F_max = {ff_res.max_flow_m3s:.4f} m³/s) en {elapsed_ms:.0f} ms."
            )

        def _on_err(exc: Exception) -> None:
            self.max_flow_panel.reset_hint()
            QMessageBox.critical(
                self,
                "Error en análisis Ford-Fulkerson",
                f"No se pudo completar el cálculo de flujo máximo:\n{exc}",
            )
            self._set_status("Error al calcular estimaciones Ford-Fulkerson.")

        self._task_runner.submit(
            "max_flow",
            _compute_task,
            on_success=_on_done,
            on_error=_on_err,
            on_finally=lambda: self.max_flow_panel.set_loading(False),
        )

    def _action_calibrate_fmax(self) -> None:
        if self.state.dataset is None:
            return
        g = self.state.dataset.graph
        eff_caps = {
            p.pipe_id: resolve_pipe_hydraulics(p, self.state.interventions.get(p.pipe_id))[0]
            for p in g.pipes()
        }
        ff_res = ford_fulkerson_max_flow(g, pipe_capacities=eff_caps)
        f_ing = compute_fmax_calibrated_ingress(
            ff_res.max_flow_m3s,
            self.state.dataset.basin.runoff_coefficient_c,
            self.state.dataset.basin.area_ha,
            reference_intensity_mm_h=30.0,
        )
        self.state.active_target_fmax_pct = None
        self.controls_panel.set_demand_target(None)
        self.controls_panel.apply_preset(f_ing * 100.0, 0.0)
        self._set_status(
            f"Calibrado a F_max = {ff_res.max_flow_m3s:.4f} m³/s (ingreso = {f_ing * 100.0:.2f}% para E3 = 100%)."
        )

    def _action_simulate_target_fmax(self, target_pct: float) -> None:
        if self.state.dataset is None:
            return
        pct = max(0.0, min(300.0, float(target_pct)))
        self.controls_panel.set_demand_target(pct)
        self.state.active_target_fmax_pct = pct
        self.run_simulation(preserve_previous=False, auto_play=True)
        self._show_extra_fmax_banner()

    def _action_highlight_ford_fulkerson(self) -> None:
        if self.state.dataset is None:
            return
        g = self.state.dataset.graph
        eff_caps = {
            p.pipe_id: resolve_pipe_hydraulics(p, self.state.interventions.get(p.pipe_id))[0]
            for p in g.pipes()
        }
        ff_res = ford_fulkerson_max_flow(g, pipe_capacities=eff_caps)
        self.state.max_flow_result = ff_res
        self.controls_panel.update_fmax_summary(
            ff_res, self.controls_panel.read_util_cap_pct()
        )
        self._stop_traversal_anim(clear_canvas=False)
        self._deactivate_focus_filters_for_traversal()

        sat_pipes = {
            pid
            for pid, sat in ff_res.edge_saturation_pct.items()
            if sat >= 99.9 and ff_res.edge_capacities.get(pid, 0.0) > 1e-12
        }
        cut_pipes = set(ff_res.min_cut_pipes)
        hl_pipes = cut_pipes | sat_pipes
        hl_nodes: Set[str] = set()
        for pid in cut_pipes:
            edge = g.get_pipe(pid)
            if edge is not None:
                hl_nodes.update((edge.from_node, edge.to_node))
        ordered_ff = list(ff_res.min_cut_pipes) + [
            pid for pid in sorted(sat_pipes) if pid not in cut_pipes
        ]
        self.network_canvas.set_highlights(
            hl_pipes, hl_nodes, ordered_route_pipes=ordered_ff
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_highlights(hl_pipes, hl_nodes)
        cut_str = ", ".join(ff_res.min_cut_pipes) or "Ninguno"
        self.network_canvas.set_banner(
            f"Ford-Fulkerson · F_max = {ff_res.max_flow_m3s:.4f} m³/s",
            (
                f"• Corte mínimo ({len(ff_res.min_cut_pipes)} tramos: {cut_str}): "
                f"cuello de botella global cuya capacidad ({ff_res.min_cut_capacity_m3s:.4f} m³/s) "
                f"limita el flujo hacia PTAR 31.\n"
                f"• Tramos resaltados ({len(sat_pipes)} saturados al 100%): "
                f"tuberías que alcanzan su capacidad máxima en la ruta óptima."
            ),
        )

        self.controls_panel.update_structure_strip(
            "Queue",
            ff_res.min_cut_pipes,
            f"F_max {ff_res.max_flow_m3s:.4f}",
        )
        lines = [
            f"[Ford-Fulkerson (Edmonds-Karp)] F_max = {ff_res.max_flow_m3s:.5f} m³/s ({ff_res.iterations} rutas)",
            f"Corte mínimo ({len(ff_res.min_cut_pipes)} tramos = {ff_res.min_cut_capacity_m3s:.5f} m³/s): {', '.join(ff_res.min_cut_pipes) or 'Ninguno'}",
            f"Tramos saturados (100%): {', '.join(sorted(sat_pipes)) or 'Ninguno'}",
        ]
        for step in ff_res.augmenting_paths[:6]:
            lines.append(
                f"  #{step.iteration}: {'→'.join(step.nodes)} (+{step.bottleneck_m3s:.4f} ⇒ {step.cumulative_flow_m3s:.4f})"
            )
        if len(ff_res.augmenting_paths) > 6:
            lines.append(f"  ... (+{len(ff_res.augmenting_paths) - 6} caminos aumentantes)")
        self.controls_panel.set_traversal_text("\n".join(lines))
        self._set_status(
            f"Ford-Fulkerson: F_max = {ff_res.max_flow_m3s:.4f} m³/s · Corte mín.: {', '.join(ff_res.min_cut_pipes) or '-'}."
        )

    def wait_for_background_tasks(self, timeout_ms: int = 5000) -> bool:
        """Espera a que finalicen las tareas en segundo plano y el render diferido."""
        if self._deferred_charts_timer.isActive():
            self._deferred_charts_timer.stop()
            self._run_deferred_temporal_charts()
        if self._deferred_compare_timer.isActive():
            self._deferred_compare_timer.stop()
            self._launch_pending_comparison()
        if self._deferred_fmax_timer.isActive():
            self._deferred_fmax_timer.stop()
            self._launch_pending_max_flow()
        return self._task_runner.wait_all(timeout_ms)

    def _on_comparison_scenario_activated(self, sid: int) -> None:
        if self.state.dataset is None:
            return
        for sc in self.state.dataset.scenarios:
            if sc.scenario_id == sid:
                self.controls_panel.set_scenario_text(
                    theme.format_scenario_display(
                        sc.scenario_id, sc.condition, sc.intensity_mm_h
                    )
                )
                self.run_simulation()
                return

    # ------------------------------------------------------------------
    # Búsqueda y recorridos BFS / DFS / Aguas arriba & abajo
    # ------------------------------------------------------------------

    def _deactivate_focus_filters_for_traversal(self) -> None:
        if self.state.tour_active:
            self._close_guided_tour(reset_view=False)
        if self.state.basin_isolated:
            self.state.basin_isolated = False
            self.network_canvas.set_basin_focus(None, None)

    def _action_search(self, raw_query: str) -> None:
        if self.state.dataset is None:
            return
        q = raw_query.strip()
        if not q:
            return
        nodes, pipes = search_entities(self.state.dataset.graph, q)
        if not nodes and not pipes:
            QMessageBox.information(
                self, "Sin resultados", f"No se encontró nodo o tubería para '{q}'."
            )
            return

        self.state.inspector_trace_state = None
        self._stop_traversal_anim(clear_canvas=False)
        self._deactivate_focus_filters_for_traversal()
        exact_pipe = self.state.dataset.graph.get_pipe(q.upper()) or self.state.dataset.graph.get_pipe(q)
        exact_node = self.state.dataset.graph.get_node(q.upper()) or self.state.dataset.graph.get_node(q)
        if exact_pipe is not None:
            self.network_canvas.select_pipe(exact_pipe.pipe_id)
            self._on_pipe_selected(exact_pipe.pipe_id)
            self.network_canvas.focus_pipe(exact_pipe.pipe_id)
        elif exact_node is not None:
            self.network_canvas.select_node(exact_node.node_id)
            self._on_node_selected(exact_node.node_id)
            self.network_canvas.focus_node(exact_node.node_id)
        elif pipes:
            self.network_canvas.select_pipe(pipes[0].pipe_id)
            self._on_pipe_selected(pipes[0].pipe_id)
            self.network_canvas.focus_pipe(pipes[0].pipe_id)
        elif nodes:
            self.network_canvas.select_node(nodes[0].node_id)
            self._on_node_selected(nodes[0].node_id)
            self.network_canvas.focus_node(nodes[0].node_id)

        self.network_canvas.set_highlights(
            pipe_ids={p.pipe_id for p in pipes},
            node_ids={n.node_id for n in nodes},
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_highlights(
                pipe_ids={p.pipe_id for p in pipes},
                node_ids={n.node_id for n in nodes},
            )
        self.controls_panel.set_traversal_text(
            f"[Búsqueda '{q}']\n"
            f"Nodos ({len(nodes)}): {', '.join(n.node_id for n in nodes[:12]) or '-'}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes[:12]) or '-'}"
        )
        self._set_status(f"Búsqueda '{q}': {len(nodes)} nodo(s), {len(pipes)} tubería(s).")

    def _run_traversal(self, alg: str) -> None:
        if self.state.dataset is None:
            return
        self.state.inspector_trace_state = None
        self._stop_traversal_anim(clear_canvas=True)
        self._deactivate_focus_filters_for_traversal()
        self.state.last_traversal_alg = alg
        start = self.controls_panel.combo_bfs_start.currentText().strip()
        target = self.controls_panel.combo_bfs_target.currentText().strip() or None
        try:
            res, frames = (
                bfs_anim_frames(self.state.dataset.graph, start, target)
                if alg == "BFS"
                else dfs_anim_frames(self.state.dataset.graph, start, target)
            )
        except KeyError as exc:
            QMessageBox.warning(self, "Nodo inválido", str(exc))
            return

        if res.path_pipes:
            hl_pipes = {p.pipe_id for p in res.path_pipes}
            hl_nodes = set(res.path_nodes)
            self.state.active_route_pipes = list(res.path_pipes)
            ordered_pipes = [p.pipe_id for p in res.path_pipes]
        else:
            hl_pipes = {p.pipe_id for p in res.traversed_edges}
            hl_nodes = set(res.visited_order)
            self.state.active_route_pipes = []
            ordered_pipes = [p.pipe_id for p in res.traversed_edges]

        self.network_canvas.set_highlights(
            hl_pipes, hl_nodes, ordered_route_pipes=ordered_pipes
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_highlights(hl_pipes, hl_nodes)
        if frames:
            mid_fr = frames[min(1, len(frames) - 1)]
            self.controls_panel.update_structure_strip(
                mid_fr.structure_name,
                mid_fr.structure_items,
                f"muestra {res.algorithm}",
            )

        lines = [
            f"[{res.algorithm}] {start} → {target or 'toda la red'}",
            f"Visitados ({len(res.visited_order)}): {' → '.join(res.visited_order[:14])}"
            + (" ..." if len(res.visited_order) > 14 else ""),
        ]
        if target:
            if res.target_reached:
                lines.append(
                    f"Ruta ({len(res.path_pipes)} tramos): {' → '.join(res.path_nodes)}"
                )
                lines.append(f"Tuberías: {', '.join(p.pipe_id for p in res.path_pipes)}")
                total_t = sum(p.transit_time_min for p in res.path_pipes)
                lines.append(f"Tránsito acumulado: {total_t:.1f} min")
            else:
                lines.append(f"Sin camino dirigido desde {start} hasta {target}.")

        self.controls_panel.set_traversal_text("\n".join(lines))
        self._refresh_inspector()
        if self.state.result is not None and self.state.result.snapshots:
            if self.right_tabs.currentIndex() == 2:
                self._charts_tab_dirty = False
                self._push_temporal_charts(throttle_draw=False)
            else:
                self._charts_tab_dirty = True

    def _action_toggle_traversal_anim(self) -> None:
        if self.state.dataset is None:
            return
        if self.state.is_animating_traversal:
            self._stop_traversal_anim(clear_canvas=False)
            return

        self.pause()
        self._deactivate_focus_filters_for_traversal()
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        start = self.controls_panel.combo_bfs_start.currentText().strip()
        target = self.controls_panel.combo_bfs_target.currentText().strip() or None
        alg = self.state.last_traversal_alg
        try:
            res, frames = (
                bfs_anim_frames(self.state.dataset.graph, start, target)
                if alg == "BFS"
                else dfs_anim_frames(self.state.dataset.graph, start, target)
            )
        except KeyError as exc:
            QMessageBox.warning(self, "Nodo inválido", str(exc))
            return

        if res.path_pipes:
            self.state.active_route_pipes = list(res.path_pipes)
            ordered_pipes = [p.pipe_id for p in res.path_pipes]
            self._pending_traversal_highlights = (
                {p.pipe_id for p in res.path_pipes},
                set(res.path_nodes),
                ordered_pipes,
            )
        else:
            ordered_pipes = [p.pipe_id for p in res.traversed_edges]
            self._pending_traversal_highlights = (
                {p.pipe_id for p in res.traversed_edges},
                set(res.visited_order),
                ordered_pipes,
            )
        self.state.anim_frames = frames
        self.state.anim_idx = 0
        self.state.is_animating_traversal = True
        self.controls_panel.set_animating(True)
        self._step_traversal_anim()

    def _step_traversal_anim(self) -> None:
        if not self.state.is_animating_traversal or not self.state.anim_frames:
            self._stop_traversal_anim(clear_canvas=False)
            return

        fr = self.state.anim_frames[self.state.anim_idx]
        self.network_canvas.set_traversal_frame(fr)
        self.controls_panel.update_structure_strip(
            fr.structure_name,
            fr.structure_items,
            f"{fr.step_index + 1}/{fr.total_steps}",
        )
        self.controls_panel.set_traversal_text(
            f"[{fr.algorithm} · Paso {fr.step_index + 1}/{fr.total_steps}]\n"
            f"{fr.note}\n"
            f"{fr.structure_name}: {', '.join(fr.structure_items[:10]) or '(vacía)'}"
        )

        self.state.anim_idx += 1
        if self.state.anim_idx >= len(self.state.anim_frames):
            self.state.is_animating_traversal = False
            self.controls_panel.set_animating(False)
            self._set_status(
                f"Recorrido {fr.algorithm} completado · Transicionando ruta a flujo hidráulico en vivo..."
            )
            self._traversal_handoff_timer.start()
            return
        delay = 560 if fr.algorithm == "BFS" else 340
        self._anim_timer.start(delay)

    def _promote_finished_traversal_to_live_route(self) -> None:
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        fr = self.network_canvas._traversal_frame
        if fr is None:
            return
        pending = self._pending_traversal_highlights
        self._pending_traversal_highlights = None
        if pending is not None:
            hl_pipes, hl_nodes, ordered_pipes = pending
        else:
            ordered_pipes = [p.pipe_id for p in self.state.active_route_pipes]
            hl_pipes = (
                set(ordered_pipes)
                if ordered_pipes
                else (set(fr.active_edges) or set(fr.visited_edges))
            )
            hl_nodes = set(fr.active_nodes) or set(fr.visited_nodes)
        self.network_canvas.promote_traversal_to_highlights(
            hl_pipes, hl_nodes, ordered_route_pipes=ordered_pipes
        )
        if self.state.result is not None and self.state.result.snapshots:
            if self.right_tabs.currentIndex() == 2:
                self._charts_tab_dirty = False
                self._push_temporal_charts(throttle_draw=False)
            else:
                self._charts_tab_dirty = True
            self._set_status(
                f"Ruta {fr.algorithm} activa en vivo ({len(hl_pipes)} tramos). Presione Reproducir para ver el flujo."
            )

    def _stop_traversal_anim(self, clear_canvas: bool = True) -> None:
        self.state.is_animating_traversal = False
        if self._anim_timer.isActive():
            self._anim_timer.stop()
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        self.controls_panel.set_animating(False)
        if clear_canvas:
            self._pending_traversal_highlights = None
            self.network_canvas.set_traversal_frame(None)

    def _run_trace(self, direction: str) -> None:
        if self.state.dataset is None:
            return
        self._stop_traversal_anim(clear_canvas=True)
        self._deactivate_focus_filters_for_traversal()
        nid = self.controls_panel.combo_bfs_start.currentText().strip()
        try:
            nodes, pipes = (
                trace_downstream(self.state.dataset.graph, nid)
                if direction == "down"
                else trace_upstream(self.state.dataset.graph, nid)
            )
        except KeyError as exc:
            QMessageBox.warning(self, "Nodo inválido", str(exc))
            return
        self.network_canvas.set_highlights(
            {p.pipe_id for p in pipes},
            set(nodes),
            ordered_route_pipes=[p.pipe_id for p in pipes],
        )
        if self.state.view_mode == "3d":
            self.basin_3d.set_highlights({p.pipe_id for p in pipes}, set(nodes))
        label = "Aguas abajo" if direction == "down" else "Aguas arriba"
        self.controls_panel.set_traversal_text(
            f"[{label} desde {nid}]\n"
            f"Nodos ({len(nodes)}): {', '.join(nodes)}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes)}"
        )
        self._set_status(
            f"{label} desde {nid}: {len(nodes)} nodo(s), {len(pipes)} tubería(s)."
        )

    def _clear_highlights(self) -> None:
        self.state.inspector_trace_state = None
        self._stop_traversal_anim(clear_canvas=True)
        self._pending_traversal_highlights = None
        self.state.active_route_pipes = []
        self.state.basin_isolated = False
        self.network_canvas.set_basin_focus(None, None)
        self.network_canvas.set_highlights(set(), set())
        if self.state.view_mode == "3d":
            self.basin_3d.set_basin_focus(None, None)
            self.basin_3d.set_highlights(set(), set())
        self.controls_panel.update_structure_strip("Queue", [])
        self.controls_panel.set_traversal_text("")
        self._charts_tab_dirty = True
        if (
            self.right_tabs.currentIndex() == 2
            and self.state.result is not None
            and self.state.result.snapshots
        ):
            self._charts_tab_dirty = False
            self._push_temporal_charts(throttle_draw=False)
        self._refresh_inspector()

    # ------------------------------------------------------------------
    # Guía de Sustentación (4 Hallazgos por escenario)
    # ------------------------------------------------------------------

    def toggle_guided_tour(self) -> None:
        if self.state.dataset is None or self.state.result is None:
            return
        if self.state.tour_active:
            self._close_guided_tour()
        else:
            if self.state.view_mode == "3d":
                self._set_view_mode("2d")
            if self.state.basin_isolated:
                self.state.basin_isolated = False
                self._apply_basin_isolation()
                self._refresh_inspector()
            if self.state.map_mode != "instant":
                self._set_map_mode("instant")
            self.state.tour_active = True
            self.top_bar.set_tour_active(True)
            self._go_tour_stop(0, animate_cam=True)

    def _go_tour_stop(self, stop_idx: int, animate_cam: bool = True) -> None:
        if self.state.result is None or not self.state.result.snapshots:
            return
        stops = build_tour_stops(
            self.state.dataset, self.state.result, self._selected_scenario_obj()
        )
        if not stops:
            return
        if stop_idx >= len(stops):
            self._close_guided_tour()
            return
        stop_idx = max(0, stop_idx)
        self.state.tour_step = stop_idx
        stop = stops[stop_idx]

        self.pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._set_step(stop.step_idx)

        self.network_canvas.set_tour_focus(stop.nodes, stop.pipes)
        cfg = self.state.result.config
        t_real = self.state.result.snapshots[self.state.current_step].time_min
        self.center_panel.tour_card.show_stop(cfg, stop_idx, len(stops), stop, t_real)
        self.network_canvas.reposition_tour_card()

        if animate_cam:
            cw = self.network_canvas.width()
            card_w = self.center_panel.tour_card.width()
            self.network_canvas.animate_focus_region(
                stop.nodes,
                stop.pipes,
                left_reserve_px=(card_w + 20) if cw >= 520 else 0,
            )

        scen_es = theme.translate_scenario_name(cfg.scenario_name, compact=False)
        self._set_status(
            f"Guía Esc. {cfg.scenario_id} ({scen_es}) · Parada {stop_idx + 1}/{len(stops)}: {stop.title}"
        )

    def _close_guided_tour(self, reset_view: bool = True) -> None:
        if not self.state.tour_active:
            return
        self.state.tour_active = False
        self.center_panel.tour_card.hide()
        self.top_bar.set_tour_active(False)
        self.network_canvas.set_tour_focus(None, None)
        if reset_view:
            self.network_canvas.animate_reset_view()
        self._set_status("Guía de Sustentación cerrada · Encuadre general restaurado.")

    # ------------------------------------------------------------------
    # Diálogos de archivo y exportación
    # ------------------------------------------------------------------

    def _action_load_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo Excel de la red",
            "",
            "Archivos Excel (*.xlsx);;Todos los archivos (*)",
        )
        if path and self._load_path(path):
            self.run_simulation()

    def _action_load_csv(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta con archivos CSV")
        if path and self._load_path(path):
            self.run_simulation()

    def _action_export_csv(self) -> None:
        if self.state.dataset is None:
            QMessageBox.warning(self, "Sin datos", "Primero cargue un conjunto de datos.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino para CSV")
        if out_dir:
            try:
                export_to_csv_dir(self.state.dataset, out_dir)
                QMessageBox.information(
                    self, "Exportación completada", f"Archivos CSV exportados en:\n{out_dir}"
                )
            except Exception as exc:
                QMessageBox.critical(
                    self, "Error al exportar CSV", f"No se pudieron exportar los archivos CSV:\n{exc}"
                )

    def _action_generate_report(self) -> None:
        if self.state.dataset is None or self.state.result is None:
            QMessageBox.warning(self, "Sin simulación", "Ejecute primero una simulación.")
            return
        if self._task_runner.is_busy("report"):
            return
        default_name = f"reporte_escenario_{self.state.result.config.scenario_id}.docx"
        out_file, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte de simulación",
            default_name,
            "Documento Word (2 columnas) (*.docx);;Markdown + CSV (*.md)",
        )
        if not out_file:
            return

        dataset = self.state.dataset
        result = self.state.result
        existing_comps = list(self.state.comparisons)
        need_recomp = not existing_comps or self.state.comparisons_dirty
        self.top_bar.btn_report.setEnabled(False)
        self._set_status("Generando reporte en segundo plano...")

        def _report_task() -> Tuple[list, str, str, str]:
            comps = (
                compare_all_scenarios(dataset, result.config)
                if need_recomp
                else existing_comps
            )
            if out_file.lower().endswith(".docx"):
                try:
                    written = generate_docx_report(dataset, result, comps, out_file)
                    return comps, "docx", written, ""
                except Exception as exc:
                    fallback = os.path.splitext(out_file)[0] + ".md"
                    written = generate_markdown_report(dataset, result, comps, fallback)
                    return comps, "fallback_md", written, str(exc)
            written = generate_markdown_report(dataset, result, comps, out_file)
            return comps, "md", written, ""

        def _on_report_done(payload: Tuple[list, str, str, str]) -> None:
            comps, mode, written, err_msg = payload
            if self.state.dataset is dataset and need_recomp:
                self.state.comparisons = comps
                self.state.comparisons_dirty = False
                self.comparison_panel.reset_hint()
                self.comparison_panel.populate(comps)
            if mode == "docx":
                self._set_status(f"Reporte Word generado: {written}")
                QMessageBox.information(
                    self,
                    "Reporte Word generado",
                    f"Documento .docx a dos columnas (OMML 8.5 pt) generado en:\n{written}",
                )
            elif mode == "fallback_md":
                self._set_status(f"Respaldo Markdown generado: {written}")
                QMessageBox.warning(
                    self,
                    "Respaldo Markdown generado",
                    f"No se pudo generar .docx ({err_msg}).\nSe exportó respaldo Markdown/CSV en:\n{written}",
                )
            else:
                self._set_status(f"Reporte generado: {written}")
                QMessageBox.information(
                    self, "Reporte generado", f"Reporte y tabla CSV generados en:\n{written}"
                )

        def _on_report_err(exc: Exception) -> None:
            self._set_status("Error al generar reporte.")
            QMessageBox.critical(
                self, "Error al exportar reporte", f"No se pudo generar el reporte:\n{exc}"
            )

        self._task_runner.submit(
            "report",
            _report_task,
            on_success=_on_report_done,
            on_error=_on_report_err,
            on_finally=lambda: self.top_bar.btn_report.setEnabled(True),
        )

    def _action_show_assumptions(self) -> None:
        msg = (
            "Supuestos del Modelo Computacional (Ciudad Bicentenario):\n\n"
            "1. Grafo Dirigido Propio: 46 vértices (8 fuentes, 37 pozos, 1 sumidero PTAR 31) y 59 aristas.\n"
            "2. Flujo Máximo (Ford-Fulkerson / Edmonds-Karp): F_max = 0.3591 m³/s (corte mínimo: P28, P3, P43, P53).\n"
            "3. Admisión Local en Fuentes y Tope Físico por Rebose (120% configurable): cada fuente admite hasta (tope/100)·Q_max,fuente (0.5943 m³/s en conjunto al 120%), permitiendo que las tuberías fuente también se llenen hasta su tope mientras el % de uso del sistema se mide contra F_max y el exceso rebosa.\n"
            "4. Tiempo de Tránsito Continuo: t_i = L_i / V_i con sub-paso hidráulico interno (≤10 s) y cola de prioridad de eventos.\n"
            "5. Pozos Finitos y Conservación de Masa: cada pozo retiene hasta 4.0 m³ antes de derivar el excedente a rebose superficial en vía (~10⁻⁹ m³)."
        )
        QMessageBox.information(self, "Supuestos del Modelo", msg)

    # ------------------------------------------------------------------
    # Cierre limpio
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self.pause()
        self._stop_traversal_anim(clear_canvas=False)
        self.controls_panel.cancel_pending_param_rerun()
        if self._deferred_charts_timer.isActive():
            self._deferred_charts_timer.stop()
        if self._deferred_compare_timer.isActive():
            self._deferred_compare_timer.stop()
        if self._deferred_fmax_timer.isActive():
            self._deferred_fmax_timer.stop()
        if self._traversal_handoff_timer.isActive():
            self._traversal_handoff_timer.stop()
        self._pending_compare_job = None
        self._pending_fmax_job = None
        self._pending_traversal_highlights = None
        self._task_runner.cancel_channel("comparison")
        self._task_runner.cancel_channel("max_flow")
        self._task_runner.cancel_channel("report")
        self._task_runner.wait_all(3000)
        self.network_canvas.close_overlays()
        self.basin_3d.close_overlays()
        self.temporal_charts.stop_timers()
        self.comparison_panel.stop_timers()
        self.max_flow_panel.stop_timers()
        super().closeEvent(event)


def launch_gui(initial_data_path: Optional[str] = None) -> int:
    """Inicializa la aplicación PySide6, muestra la ventana principal y ejecuta el bucle Qt."""
    qapp = ensure_qapplication()
    window = BicentenarioSewerApp(initial_data_path=initial_data_path)
    window.show()
    return qapp.exec()
