"""Panel derecho — Pestaña Tuberías Críticas (filtros excluyentes y tabla reactiva)."""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.algorithms import rank_critical_pipes
from src.io.data_loader import NetworkDataset
from src.simulation import SimulationResult, TimeStepSnapshot
from .. import theme
from ..widgets import make_separator


class CriticalPipesPanel(QWidget):
    """Tabla ordenada de tuberías con filtros excluyentes de utilización."""

    filterChanged = Signal(str)
    pipeSelected = Signal(str)
    pipeActivated = Signal(str)

    def __init__(
        self,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._suppress_select: bool = False
        self._compact_mode: Optional[bool] = None
        self._row_pipe_ids: List[str] = []
        self._pipe_row_map: Dict[str, int] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        filter_bar = QFrame(self)
        filter_bar.setObjectName("FilterBar")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(8, 5, 8, 5)
        fb_lay.setSpacing(6)

        self._btn_group = QButtonGroup(self)
        self._radios: Dict[str, QRadioButton] = {}
        for text, val in [
            ("Todas", "all"),
            ("Resto (≤75%)", "rest"),
            ("Críticas (>75–100%)", "critical"),
            ("Sobrec. (>100%)", "overloaded"),
        ]:
            rb = QRadioButton(text, filter_bar)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setChecked(val == "all")
            rb.toggled.connect(lambda checked, v=val: self._on_radio_toggled(v, checked))
            self._btn_group.addButton(rb)
            self._radios[val] = rb
            fb_lay.addWidget(rb)

        fb_lay.addStretch(1)
        self.lbl_crit_count = QLabel("", filter_bar)
        self.lbl_crit_count.setFont(QFont(mono_font, 8, QFont.Weight.Bold))
        self.lbl_crit_count.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        fb_lay.addWidget(self.lbl_crit_count)
        lay.addWidget(filter_bar)
        lay.addWidget(make_separator("h", theme.DOCK_BORDER, 1, self))

        table_wrap = QWidget(self)
        tw_lay = QVBoxLayout(table_wrap)
        tw_lay.setContentsMargins(0, 0, 0, 0)
        tw_lay.setSpacing(0)

        self.table = QTableWidget(0, 7, table_wrap)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setShowGrid(False)
        self.table.setHorizontalHeaderLabels(
            ["#", "Tub.", "Tramo", "Q (m³/s)", "Qmax", "% Util", "Estado"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        tw_lay.addWidget(self.table, 1)

        self.lbl_empty = QLabel("", table_wrap)
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setWordWrap(True)
        self.lbl_empty.setFont(QFont(ui_font, 9))
        self.lbl_empty.setStyleSheet(
            f"background-color: {theme.PAPER_BG}; color: {theme.INK_MUTED}; padding: 16px;"
        )
        self.lbl_empty.setVisible(False)
        tw_lay.addWidget(self.lbl_empty, 1)

        lay.addWidget(table_wrap, 1)
        self._apply_column_layout(400)

    def _on_radio_toggled(self, value: str, checked: bool) -> None:
        if checked:
            self.filterChanged.emit(value)

    def current_filter(self) -> str:
        for val, rb in self._radios.items():
            if rb.isChecked():
                return val
        return "all"

    def set_filter(self, flt: str) -> None:
        rb = self._radios.get(flt)
        if rb is not None:
            rb.setChecked(True)

    def _on_selection_changed(self) -> None:
        if self._suppress_select:
            return
        pid = self.selected_pipe_id()
        if pid is not None:
            self.pipeSelected.emit(pid)

    def _on_double_click(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._row_pipe_ids):
            self.pipeActivated.emit(self._row_pipe_ids[row])

    def selected_pipe_id(self) -> Optional[str]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self._row_pipe_ids):
            return self._row_pipe_ids[row]
        return None

    def select_pipe(self, pipe_id: Optional[str], *, scroll_into_view: bool = True) -> None:
        self._suppress_select = True
        try:
            if pipe_id is None or pipe_id not in self._pipe_row_map:
                self.table.clearSelection()
                return
            row = self._pipe_row_map[pipe_id]
            if self.selected_pipe_id() != pipe_id:
                self.table.selectRow(row)
            if scroll_into_view:
                item = self.table.item(row, 0)
                if item is not None:
                    self.table.scrollToItem(item)
        finally:
            self._suppress_select = False

    def clear_selection(self) -> None:
        self.select_pipe(None)

    def row_pipe_ids(self) -> List[str]:
        return list(self._row_pipe_ids)

    def row_utilization_text(self, pipe_id: str) -> str:
        row = self._pipe_row_map.get(pipe_id)
        if row is None:
            return ""
        item = self.table.item(row, 5)
        return item.text() if item is not None else ""

    def refresh(
        self,
        *,
        dataset: Optional[NetworkDataset],
        result: Optional[SimulationResult],
        snap: Optional[TimeStepSnapshot],
        selected_pipe_id: Optional[str],
        is_playing: bool,
    ) -> None:
        self._suppress_select = True
        try:
            if dataset is None or result is None or snap is None:
                self.table.setRowCount(0)
                self._row_pipe_ids.clear()
                self._pipe_row_map.clear()
                self.lbl_crit_count.setText("")
                self.lbl_empty.setVisible(False)
                self.table.setVisible(True)
                return

            flows = {pid: ps.flow_m3s for pid, ps in snap.pipe_states.items()}
            utils = {pid: ps.utilization_pct for pid, ps in snap.pipe_states.items()}
            demands = {pid: ps.demand_ratio_pct for pid, ps in snap.pipe_states.items()}
            excesses = {pid: ps.excess_flow_m3s for pid, ps in snap.pipe_states.items()}
            qmax_overrides = {
                pid: ps.effective_q_max_m3s
                for pid, ps in snap.pipe_states.items()
                if ps.effective_q_max_m3s is not None
            }

            flt = self.current_filter()
            if flt == "rest":
                min_u, max_u, exc_min = 0.0, 75.0, False
            elif flt == "critical":
                min_u, max_u, exc_min = 75.0, 100.0, True
            elif flt == "overloaded":
                min_u, max_u, exc_min = 100.0, None, True
            else:
                min_u, max_u, exc_min = 0.0, None, False

            ranked = rank_critical_pipes(
                dataset.graph,
                flows,
                utils,
                min_utilization_pct=min_u,
                max_utilization_pct=max_u,
                exclusive_min=exc_min,
                pipe_qmax_overrides=qmax_overrides,
                pipe_demand_ratios_pct=demands,
                pipe_excess_flows_m3s=excesses,
            )
            self.lbl_crit_count.setText(f"{len(ranked)} reg.")

            short_estado = {
                "Baja utilización": "Baja",
                "Utilización moderada": "Moderada",
                "Utilización alta": "Alta",
                "Cercana a la capacidad máxima": "Cercana máx.",
                "Capacidad excedida": "Cap. excedida",
            }
            wide_estado = {
                "Baja utilización": "Baja util.",
                "Utilización moderada": "Moderada",
                "Utilización alta": "Alta",
                "Cercana a la capacidad máxima": "Cercana máx.",
                "Capacidad excedida": "Cap. excedida",
            }
            compact = bool(self._compact_mode)
            desired_ids = [rec.pipe_id for rec in ranked]

            def _row_cells(rec):
                if rec.q_max_m3s <= 1e-12:
                    estado_txt = "Cerrada 100%"
                    util_txt = "0.0%"
                else:
                    estado_txt = (
                        short_estado.get(rec.category.label, rec.category.label)
                        if compact
                        else wide_estado.get(rec.category.label, rec.category.label)
                    )
                    util_txt = (
                        f"{rec.utilization_pct:.1f}% ({rec.utilization_pct / 100.0:.1f}×)"
                        if rec.utilization_pct > 100.5
                        else f"{rec.utilization_pct:.1f}%"
                    )
                return (
                    str(rec.rank),
                    rec.pipe_id,
                    f"{rec.from_node}→{rec.to_node}",
                    f"{rec.flow_m3s:.4f}",
                    f"{rec.q_max_m3s:.4f}",
                    util_txt,
                    estado_txt,
                )

            aligns = (
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )

            if self._row_pipe_ids != desired_ids:
                self.table.setRowCount(len(ranked))
                self._row_pipe_ids = desired_ids
                self._pipe_row_map = {pid: i for i, pid in enumerate(desired_ids)}
                for row_i, rec in enumerate(ranked):
                    vals = _row_cells(rec)
                    for col_i, (val, align) in enumerate(zip(vals, aligns)):
                        item = QTableWidgetItem(val)
                        item.setTextAlignment(align)
                        if col_i == 0:
                            item.setData(Qt.ItemDataRole.UserRole, rec.pipe_id)
                        self.table.setItem(row_i, col_i, item)
            else:
                for row_i, rec in enumerate(ranked):
                    vals = _row_cells(rec)
                    for col_i, val in enumerate(vals):
                        item = self.table.item(row_i, col_i)
                        if item is not None and item.text() != val:
                            item.setText(val)

            if not ranked:
                if flt == "overloaded":
                    msg = "Ninguna tubería supera el 100% en este instante."
                elif flt == "critical":
                    msg = "Ninguna tubería está en >75–100% en este instante."
                elif flt == "rest":
                    msg = "Ninguna tubería está en ≤75% en este instante."
                else:
                    msg = "Sin tuberías para mostrar."
                self.lbl_empty.setText(msg)
                self.table.setVisible(False)
                self.lbl_empty.setVisible(True)
            else:
                self.lbl_empty.setVisible(False)
                self.table.setVisible(True)
                if selected_pipe_id and selected_pipe_id in self._pipe_row_map:
                    row = self._pipe_row_map[selected_pipe_id]
                    if self.selected_pipe_id() != selected_pipe_id:
                        self.table.selectRow(row)
                    if not is_playing:
                        item = self.table.item(row, 0)
                        if item is not None:
                            self.table.scrollToItem(item)
        finally:
            self._suppress_select = False

    def _apply_column_layout(self, width: int) -> None:
        w = max(220, width - 8)
        compact = w < 365
        if compact != self._compact_mode:
            self._compact_mode = compact
            if compact:
                self.table.setHorizontalHeaderLabels(
                    ["#", "Tub.", "Tramo", "Q", "Qmax", "%", "Estado"]
                )
            else:
                self.table.setHorizontalHeaderLabels(
                    ["#", "Tub.", "Tramo", "Q (m³/s)", "Qmax", "% Util", "Estado"]
                )

        if compact:
            weights = [
                (0.06, 22),
                (0.10, 34),
                (0.15, 46),
                (0.14, 44),
                (0.14, 44),
                (0.16, 48),
                (0.25, 76),
            ]
        else:
            weights = [
                (0.06, 26),
                (0.10, 38),
                (0.14, 50),
                (0.15, 54),
                (0.14, 52),
                (0.15, 52),
                (0.26, 98),
            ]
        for col_i, (ratio, min_w) in enumerate(weights):
            self.table.setColumnWidth(col_i, max(min_w, int(w * ratio)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_column_layout(self.width())
