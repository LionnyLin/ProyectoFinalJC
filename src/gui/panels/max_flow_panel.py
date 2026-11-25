"""Panel derecho — Pestaña Flujo Máximo (Ford-Fulkerson) y Estimaciones por % de F_max."""

import os
from typing import List, Optional, Tuple

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from ..mpl_canvas import ResponsiveFigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from src.algorithms.max_flow import MaxFlowResult
from src.simulation import MaxFlowEstimationRow
from .. import theme
from ..widgets import LoadingOverlay, StyledButton, make_separator
from .charts_panel import _apply_axis_style, _fmt_vol_compact, _safe_tight_layout, _sync_figure_size


class MaxFlowPanel(QWidget):
    """Pestaña analítica del algoritmo Ford-Fulkerson y simulaciones de saturación por % de F_max.

    Estructura: barra de acciones fija arriba + contenido desplazable como una sola lámina
    (resumen, tabla a altura completa y gráficas), de modo que el scroll es el de la pestaña
    entera y no un scroll anidado dentro de la tabla.
    """

    ROW_HEIGHT = 22
    CHARTS_MIN_HEIGHT = 520

    recalculateRequested = Signal()
    highlightMinCutRequested = Signal()
    targetFmaxActivated = Signal(float)

    def __init__(
        self,
        dpi: int = 96,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        display_font: str = "Inter",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._dpi = max(72, int(dpi))
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._last_ff_res: Optional[MaxFlowResult] = None
        self._last_rows: List[MaxFlowEstimationRow] = []
        self._last_cap_pct: Optional[float] = 120.0
        self._last_drawn_size: Tuple[int, int] = (0, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barra superior de acciones
        top_bar = QFrame(self)
        top_bar.setObjectName("CompTopBar")
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(8, 6, 8, 6)
        tb_lay.setSpacing(6)

        self.btn_recalc = StyledButton(
            "Recalcular Estimaciones",
            variant="light_secondary",
            font_pt=8,
            pad_x=9,
            pad_y=4,
            parent=top_bar,
        )
        self.btn_recalc.clicked.connect(self.recalculateRequested.emit)
        tb_lay.addWidget(self.btn_recalc)

        self.btn_highlight_cut = StyledButton(
            "Ver Corte Mín.",
            variant="light_secondary",
            font_pt=8,
            pad_x=8,
            pad_y=4,
            parent=top_bar,
        )
        self.btn_highlight_cut.clicked.connect(self.highlightMinCutRequested.emit)
        tb_lay.addWidget(self.btn_highlight_cut)

        tb_lay.addStretch(1)

        self.lbl_hint = QLabel("Doble clic simula % F_max", top_bar)
        self.lbl_hint.setFont(QFont(ui_font, 8))
        self.lbl_hint.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        tb_lay.addWidget(self.lbl_hint)

        lay.addWidget(top_bar)
        lay.addWidget(make_separator("h", theme.DOCK_BORDER, 1, self))

        # Contenido desplazable: todo lo que está bajo la barra de acciones
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("MaxFlowScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            f"QScrollArea#MaxFlowScroll, QWidget#MaxFlowContent {{ background-color: {theme.PAPER_BG}; }}"
        )
        content = QWidget(self.scroll_area)
        content.setObjectName("MaxFlowContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.scroll_area.setWidget(content)
        lay.addWidget(self.scroll_area, 1)

        # Tarjeta resumen Ford-Fulkerson
        summary_card = QFrame(content)
        summary_card.setObjectName("InspectorSubCard")
        sc_lay = QVBoxLayout(summary_card)
        sc_lay.setContentsMargins(8, 5, 8, 5)
        sc_lay.setSpacing(2)

        lbl_sc_title = QLabel("Flujo Máximo del Sistema · Ford-Fulkerson (Edmonds-Karp)", summary_card)
        lbl_sc_title.setFont(QFont(display_font, 8, QFont.Weight.Bold))
        lbl_sc_title.setWordWrap(True)
        lbl_sc_title.setStyleSheet(f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;")
        sc_lay.addWidget(lbl_sc_title)

        self.lbl_ff_summary = QLabel(
            "Presione 'Recalcular Estimaciones' o abra esta pestaña para auditar F_max y el tope de rebose.",
            summary_card,
        )
        self.lbl_ff_summary.setWordWrap(True)
        self.lbl_ff_summary.setFont(QFont(mono_font, 7))
        self.lbl_ff_summary.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        sc_lay.addWidget(self.lbl_ff_summary)

        body.addWidget(summary_card)
        body.addWidget(make_separator("h", theme.DOCK_BORDER, 1, content))

        fm = QFontMetrics(QFont(ui_font, 8))
        self._col_specs: List[Tuple[str, Qt.AlignmentFlag, int]] = [
            ("% F_max", Qt.AlignmentFlag.AlignCenter, max(60, fm.horizontalAdvance("% F_max") + 16)),
            ("Q req", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(58, fm.horizontalAdvance("0.0000") + 14)),
            ("Q adm", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(58, fm.horizontalAdvance("0.0000") + 14)),
            ("Uso Sis.", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(62, fm.horizontalAdvance("120.0%") + 14)),
            ("Máx Tub.", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(62, fm.horizontalAdvance("120.0%") + 14)),
            (">100%", Qt.AlignmentFlag.AlignCenter, max(46, fm.horizontalAdvance(">100%") + 14)),
            ("Rebose m³", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(76, fm.horizontalAdvance("Rebose m³") + 14)),
            ("Estado", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, max(112, fm.horizontalAdvance("Rebose total (tope)") + 14)),
        ]

        table_wrap = QWidget(content)
        table_wrap.setObjectName("CompTableWrap")
        tw_lay = QVBoxLayout(table_wrap)
        tw_lay.setContentsMargins(6, 4, 6, 4)

        self.table = QTableWidget(0, len(self._col_specs), table_wrap)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalHeaderLabels([h for h, _, _ in self._col_specs])

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        tw_lay.addWidget(self.table)
        body.addWidget(table_wrap)
        self.table.installEventFilter(self)
        self._fit_table_height()

        # Gráfica Matplotlib 2x1
        charts_host = QWidget(content)
        charts_host.setObjectName("ChartsHost")
        ch_lay = QVBoxLayout(charts_host)
        ch_lay.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(4.0, 4.2), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_usage = self.figure.add_subplot(211)
        self.ax_flood = self.figure.add_subplot(212)
        self.canvas = ResponsiveFigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setMinimumSize(220, self.CHARTS_MIN_HEIGHT)
        self.canvas.installEventFilter(self)
        ch_lay.addWidget(self.canvas, 1)
        body.addWidget(charts_host, 1)

        self.loading_overlay = LoadingOverlay(self, ui_font=ui_font)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(110)
        self._resize_timer.timeout.connect(self._reflow)
        self.canvas.resizeSettled.connect(self._reflow)

        self._resize_columns()
        self._draw_empty()

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        pct = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(pct, (int, float)):
            self.targetFmaxActivated.emit(float(pct))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # La aparición del scroll vertical cambia el ancho de la tabla sin redimensionar el panel.
        if obj is self.table and event.type() == QEvent.Type.Resize:
            self._resize_columns()
        # Matplotlib acepta la rueda del ratón; la redirigimos para desplazar toda la pestaña.
        elif obj is self.canvas and event.type() == QEvent.Type.Wheel:
            QApplication.sendEvent(self.scroll_area.verticalScrollBar(), event)
            return True
        return super().eventFilter(obj, event)

    def _fit_table_height(self) -> None:
        """Ajusta la tabla a la altura exacta de sus filas: el scroll lo lleva la pestaña completa."""
        rows = max(1, self.table.rowCount())
        hdr_h = self.table.horizontalHeader().sizeHint().height()
        hbar = self.table.horizontalScrollBar()
        hbar_h = hbar.sizeHint().height() if hbar.isVisible() else 0
        frame = self.table.frameWidth() * 2
        self.table.setFixedHeight(hdr_h + rows * self.ROW_HEIGHT + hbar_h + frame + 2)

    def _resize_columns(self) -> None:
        avail_w = max(220, self.table.viewport().width())
        total_min = sum(min_w for _, _, min_w in self._col_specs)
        extra = max(0, avail_w - total_min)
        for col_i, (_, _, min_w) in enumerate(self._col_specs):
            share = int(extra * (min_w / total_min)) if extra > 0 else 0
            self.table.setColumnWidth(col_i, min_w + share)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_columns()
        if not self.canvas.is_resizing() and self.width() >= 180 and self.height() >= 180:
            self._resize_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        if self.canvas.is_resizing():
            return  # se reintenta en canvas.resizeSettled
        cw = self.canvas.width()
        ch = self.canvas.height()
        if cw < 180 or ch < 180:
            return
        lw, lh = self._last_drawn_size
        if abs(cw - lw) <= 8 and abs(ch - lh) <= 8:
            return
        if self._last_rows:
            self._redraw_charts()
        else:
            self._draw_empty()

    def stop_timers(self) -> None:
        self.loading_overlay.stop()
        if self._resize_timer.isActive():
            self._resize_timer.stop()

    def set_hint_visible(self, visible: bool) -> None:
        self.lbl_hint.setVisible(visible)

    def mark_dirty(self, has_data: bool) -> None:
        if has_data:
            self.btn_recalc.setText("Recalcular Estimaciones *")
            self.btn_recalc.set_variant("primary")
            self.lbl_hint.setText("Parámetros modificados · Recalcular")
            self.lbl_hint.setStyleSheet(
                f"color: {theme.STATUS_WARN_LIGHT}; background: transparent;"
            )

    def mark_clean(self, elapsed_ms: float) -> None:
        self.btn_recalc.setText("Recalcular Estimaciones")
        self.btn_recalc.set_variant("light_secondary")
        self.lbl_hint.setText(f"Al día ({elapsed_ms:.0f} ms) · Doble clic simula")
        self.lbl_hint.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")

    def reset_hint(self) -> None:
        self.lbl_hint.setText("Doble clic simula % F_max")
        self.lbl_hint.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")

    def set_loading(
        self,
        active: bool,
        message: str = "Ejecutando Ford-Fulkerson y simulando curvas de saturación...",
    ) -> None:
        self.btn_recalc.setEnabled(not active)
        if active:
            self.lbl_hint.setText("Calculando en segundo plano...")
            self.lbl_hint.setStyleSheet(
                f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;"
            )
            self.loading_overlay.start(message)
        else:
            self.loading_overlay.stop()

    def clear_table(self) -> None:
        self.table.setRowCount(0)
        self._fit_table_height()
        self._last_ff_res = None
        self._last_rows = []
        self._draw_empty()

    def populate(
        self,
        ff_res: Optional[MaxFlowResult],
        rows: List[MaxFlowEstimationRow],
        cap_pct: Optional[float],
    ) -> None:
        self._last_ff_res = ff_res
        self._last_rows = list(rows)
        self._last_cap_pct = cap_pct

        if ff_res is not None:
            cut_str = ", ".join(ff_res.min_cut_pipes) or "Ninguno"
            if cap_pct is not None:
                tot_src_cap = (
                    rows[-1].result.total_source_capacity_m3s if rows else 0.0
                )
                if tot_src_cap > 0.0:
                    q_src_max = tot_src_cap * (cap_pct / 100.0)
                    cap_txt = f"Tope {cap_pct:.0f}% · Entr. ≤ {q_src_max:.4f} m³/s"
                else:
                    cap_txt = f"Tope {cap_pct:.0f}%"
            else:
                cap_txt = "Sin tope artificial"
            self.lbl_ff_summary.setText(
                f"F_max = {ff_res.max_flow_m3s:.5f} m³/s  ·  {cap_txt}  ·  {ff_res.iterations} rutas BFS\n"
                f"Corte mínimo ({len(ff_res.min_cut_pipes)} tramos = {ff_res.min_cut_capacity_m3s:.5f} m³/s): {cut_str}"
            )

        self.table.setRowCount(len(rows))
        for row_i, r in enumerate(rows):
            vals = (
                f"{r.target_fmax_pct:.0f}%",
                f"{r.requested_flow_m3s:.4f}",
                f"{r.admitted_flow_m3s:.4f}",
                f"{r.system_utilization_pct:.1f}%",
                f"{r.max_pipe_utilization_pct:.1f}%",
                str(r.num_overloaded_pipes),
                f"{r.total_surface_flooding_m3:,.1f}",
                r.state_label,
            )
            for col_i, (val, (_, align, _)) in enumerate(zip(vals, self._col_specs)):
                item = QTableWidgetItem(val)
                item.setTextAlignment(align)
                if col_i == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r.target_fmax_pct)
                self.table.setItem(row_i, col_i, item)
        self._resize_columns()
        self._fit_table_height()
        self._redraw_charts()

    def _draw_empty(self) -> None:
        _sync_figure_size(self.canvas, self.figure)
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(theme.PAPER_ALT_ROW)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(theme.PAPER_BORDER)
        ax.text(
            0.5,
            0.5,
            "Presione 'Recalcular Estimaciones'\npara generar la curva de saturación Ford-Fulkerson.",
            ha="center",
            va="center",
            color=theme.INK_MUTED,
            fontsize=8.5,
            transform=ax.transAxes,
        )
        self._last_drawn_size = (self.canvas.width(), self.canvas.height())
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()

    def _redraw_charts(self) -> None:
        if not self._last_rows:
            self._draw_empty()
            return

        _sync_figure_size(self.canvas, self.figure)
        self.figure.clear()
        self.ax_usage = self.figure.add_subplot(211)
        self.ax_flood = self.figure.add_subplot(212)
        _apply_axis_style(self.ax_usage)
        _apply_axis_style(self.ax_flood)

        xs = [r.target_fmax_pct for r in self._last_rows]
        sys_u = [r.system_utilization_pct for r in self._last_rows]
        pipe_u = [r.max_pipe_utilization_pct for r in self._last_rows]
        floods = [r.total_surface_flooding_m3 for r in self._last_rows]
        ptar_eff = [r.ptar_fmax_efficiency_pct for r in self._last_rows]

        cap = self._last_cap_pct
        self.ax_usage.plot(
            xs, sys_u, marker="o", markersize=3.8, color="#1D4ED8", linewidth=2.1, label="Uso Sistema (% F_max)"
        )
        self.ax_usage.plot(
            xs, pipe_u, marker="s", markersize=3.4, linestyle="--", color="#EA580C", linewidth=1.6, label="Máx. Tubería (%)"
        )
        self.ax_usage.axvline(100.0, color="#6B7280", linestyle=":", linewidth=1.1, label="100% F_max")
        if cap is not None:
            self.ax_usage.axhline(
                cap, color="#991B1B", linestyle="--", linewidth=1.4, label=f"Tope rebose {cap:.0f}%"
            )
            if max(xs) >= cap:
                self.ax_usage.axvspan(cap, max(xs) * 1.04, color="#DC2626", alpha=0.06, zorder=0)

        top_y = max(sys_u + pipe_u + ([cap] if cap is not None else []) + [115.0])
        self.ax_usage.set_ylim(0.0, top_y * 1.18)
        self.ax_usage.set_xlim(min(xs), max(xs) * 1.03)
        self.ax_usage.set_ylabel("% Uso", color=theme.INK_SECONDARY, fontsize=7.3)
        self.ax_usage.set_title(
            "Curva de Saturación por Flujo Máximo (Ford-Fulkerson)",
            color=theme.INK_PRIMARY,
            fontsize=8.3,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=3,
        )
        self.ax_usage.legend(
            loc="lower right",
            fontsize=5.9,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.92,
            borderpad=0.20,
            labelcolor=theme.INK_PRIMARY,
        )

        l1 = self.ax_flood.plot(
            xs, floods, marker="o", markersize=3.5, color="#DC2626", linewidth=1.9, label="Rebose (m³)"
        )
        self.ax_flood.fill_between(xs, 0.0, floods, color="#DC2626", alpha=0.10)
        self.ax_flood.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _fmt_vol_compact(v)))
        self.ax_flood.set_ylabel("Rebose (m³)", color="#DC2626", fontsize=7.3)
        self.ax_flood.set_xlabel("Demanda de entrada (% de F_max)", color=theme.INK_SECONDARY, fontsize=7.3)

        ax_eff = self.ax_flood.twinx()
        ax_eff.tick_params(colors="#0F766E", labelsize=7.0)
        l2 = ax_eff.plot(
            xs, ptar_eff, marker="^", markersize=3.5, linestyle="-.", color="#0F766E", linewidth=1.6, label="PTAR / F_max (%)"
        )
        ax_eff.set_ylabel("PTAR / F_max (%)", color="#0F766E", fontsize=7.0)
        ax_eff.set_ylim(0.0, max(110.0, max(ptar_eff, default=100.0) * 1.18))

        max_f = max(floods, default=10.0)
        self.ax_flood.set_ylim(0.0, max(10.0, max_f * 1.24))
        self.ax_flood.set_xlim(min(xs), max(xs) * 1.03)
        self.ax_flood.set_title(
            "Rebose Acumulado vs. Eficiencia PTAR 31",
            color=theme.INK_PRIMARY,
            fontsize=8.3,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=3,
        )
        lines = l1 + l2
        self.ax_flood.legend(
            lines,
            [ln.get_label() for ln in lines],
            loc="upper left",
            fontsize=5.9,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.92,
            borderpad=0.20,
            labelcolor=theme.INK_PRIMARY,
        )

        self._last_drawn_size = (self.canvas.width(), self.canvas.height())
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()
