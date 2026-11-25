"""Panel derecho — Pestaña Comparación de Escenarios (tabla + gráficas comparativas)."""

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.simulation import ScenarioSummary
from .. import theme
from ..widgets import LoadingOverlay, StyledButton, make_separator
from .charts_panel import ComparisonChartsPanel


class ComparisonPanel(QWidget):
    """Construye y actualiza la pestaña Comparación entre los 5 escenarios."""

    compareRequested = Signal()
    scenarioActivated = Signal(int)

    def __init__(
        self,
        dpi: int = 96,
        ui_font: str = "Segoe UI",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ui_font = ui_font

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        comp_top = QFrame(self)
        comp_top.setObjectName("CompTopBar")
        ct_lay = QHBoxLayout(comp_top)
        ct_lay.setContentsMargins(8, 6, 8, 6)
        ct_lay.setSpacing(8)

        self.btn_compare = StyledButton(
            "Recalcular 5 Escenarios",
            variant="light_secondary",
            font_pt=8,
            pad_x=10,
            pad_y=4,
            parent=comp_top,
        )
        self.btn_compare.clicked.connect(self.compareRequested.emit)
        ct_lay.addWidget(self.btn_compare)

        ct_lay.addStretch(1)

        self.lbl_comp_hint = QLabel("Doble clic activa escenario", comp_top)
        self.lbl_comp_hint.setFont(QFont(ui_font, 8))
        self.lbl_comp_hint.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        ct_lay.addWidget(self.lbl_comp_hint)

        lay.addWidget(comp_top)
        lay.addWidget(make_separator("h", theme.DOCK_BORDER, 1, self))

        fm = QFontMetrics(QFont(ui_font, 9))
        self._col_specs: List[Tuple[str, Qt.AlignmentFlag, int]] = [
            ("Escenario", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, max(155, fm.horizontalAdvance("E3 Lluvia moderada") + 24)),
            ("mm/h", Qt.AlignmentFlag.AlignCenter, max(52, fm.horizontalAdvance("mm/h") + 18)),
            ("Máx %", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(68, fm.horizontalAdvance("1000.0%") + 18)),
            ("Crítica", Qt.AlignmentFlag.AlignCenter, max(56, fm.horizontalAdvance("Crítica") + 18)),
            (">75–100%", Qt.AlignmentFlag.AlignCenter, max(74, fm.horizontalAdvance(">75–100%") + 18)),
            (">100%", Qt.AlignmentFlag.AlignCenter, max(62, fm.horizontalAdvance(">100%") + 18)),
            ("Pico PTAR", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(80, fm.horizontalAdvance("Pico PTAR") + 18)),
            ("Rebose (m³)", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, max(92, fm.horizontalAdvance("Rebose (m³)") + 18)),
        ]

        table_wrap = QWidget(self)
        table_wrap.setObjectName("CompTableWrap")
        tw_lay = QVBoxLayout(table_wrap)
        tw_lay.setContentsMargins(6, 4, 6, 4)

        self.table = QTableWidget(0, len(self._col_specs), table_wrap)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalHeaderLabels([h for h, _, _ in self._col_specs])

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        self.table.setFixedHeight(168)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        tw_lay.addWidget(self.table)
        lay.addWidget(table_wrap)

        self.charts = ComparisonChartsPanel(dpi=dpi, ui_font=ui_font, parent=self)
        lay.addWidget(self.charts, 1)

        self.loading_overlay = LoadingOverlay(self, ui_font=ui_font)
        self._resize_columns()

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(sid, int):
            self.scenarioActivated.emit(sid)

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

    def mark_dirty(self, has_comparisons: bool) -> None:
        if has_comparisons:
            self.btn_compare.setText("Recalcular 5 Escenarios *")
            self.btn_compare.set_variant("primary")
            self.lbl_comp_hint.setText("Parámetros modificados · Recalcular")
            self.lbl_comp_hint.setStyleSheet(
                f"color: {theme.STATUS_WARN_LIGHT}; background: transparent;"
            )

    def mark_clean(self, elapsed_ms: float) -> None:
        self.btn_compare.setText("Recalcular 5 Escenarios")
        self.btn_compare.set_variant("light_secondary")
        self.lbl_comp_hint.setText(f"Al día ({elapsed_ms:.0f} ms) · Doble clic activa")
        self.lbl_comp_hint.setStyleSheet(
            f"color: {theme.INK_MUTED}; background: transparent;"
        )

    def reset_hint(self) -> None:
        self.lbl_comp_hint.setText("Doble clic para activar escenario")
        self.lbl_comp_hint.setStyleSheet(
            f"color: {theme.INK_MUTED}; background: transparent;"
        )

    def set_hint_visible(self, visible: bool) -> None:
        self.lbl_comp_hint.setVisible(visible)

    def set_loading(
        self,
        active: bool,
        message: str = "Simulando 5 escenarios y generando gráficas...",
    ) -> None:
        self.btn_compare.setEnabled(not active)
        if active:
            self.lbl_comp_hint.setText("Calculando en segundo plano...")
            self.lbl_comp_hint.setStyleSheet(
                f"color: {theme.ACCENT_TEXT_ON_LIGHT}; background: transparent;"
            )
            self.loading_overlay.start(message)
        else:
            self.loading_overlay.stop()

    def stop_timers(self) -> None:
        self.loading_overlay.stop()
        self.charts.stop_timers()

    def clear_table(self) -> None:
        self.table.setRowCount(0)

    def populate(self, summaries: List[ScenarioSummary]) -> None:
        self.table.setRowCount(len(summaries))
        for row_i, s in enumerate(summaries):
            cond = theme.translate_scenario_name(s.condition, compact=False)
            vals = (
                f"E{s.scenario_id} {cond}",
                f"{s.intensity_mm_h:.0f}",
                f"{s.max_utilization_pct:.1f}%",
                s.most_critical_pipe,
                str(s.num_near_capacity_pipes),
                str(s.num_overloaded_pipes),
                f"{s.peak_sink_discharge_m3s:.4f}",
                f"{s.total_surface_flooding_m3:,.1f}",
            )
            for col_i, (val, (_, align, _)) in enumerate(zip(vals, self._col_specs)):
                item = QTableWidgetItem(val)
                item.setTextAlignment(align)
                if col_i == 0:
                    item.setData(Qt.ItemDataRole.UserRole, s.scenario_id)
                self.table.setItem(row_i, col_i, item)
        self._resize_columns()
        self.charts.update_comparison(summaries)
