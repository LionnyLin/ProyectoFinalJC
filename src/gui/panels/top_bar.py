"""Barra superior del Shell en Grafito (#4A4A4A) con acciones responsivas."""

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..icons import build_brand_pixmap
from ..widgets import StyledButton


class TopBar(QFrame):
    """Barra superior institucional con toggles de paneles, recorrido guiado y acciones."""

    toggleLeftRequested = Signal()
    toggleRightRequested = Signal()
    guidedTourRequested = Signal()
    loadExcelRequested = Signal()
    loadCsvRequested = Signal()
    exportCsvRequested = Signal()
    showAssumptionsRequested = Signal()
    generateReportRequested = Signal()

    def __init__(
        self,
        icons: Dict[str, QIcon],
        ui_font: str = "Segoe UI",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self._icons = icons
        self._ui_font = ui_font
        self._last_sig: Optional[Tuple[str, bool, str]] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)

        # Marca + título
        brand_lbl = QLabel(self)
        brand_lbl.setPixmap(
            build_brand_pixmap(theme.SHELL_TEXT, theme.SHELL_TEXT, theme.ACCENT_PRIMARY, 22)
        )
        lay.addWidget(brand_lbl)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 6, 0)
        title_wrap.setSpacing(1)
        self.lbl_title = QLabel("Simulador Hidráulico · Ciudad Bicentenario", self)
        self.lbl_title.setObjectName("AppTitle")
        self.lbl_subtitle = QLabel(
            "Red dirigida de alcantarillado hacia PTAR Punta Canoa (Nodo 31)", self
        )
        self.lbl_subtitle.setObjectName("AppSubtitle")
        title_wrap.addWidget(self.lbl_title)
        title_wrap.addWidget(self.lbl_subtitle)
        lay.addLayout(title_wrap)

        self.btn_toggle_left = StyledButton(
            " Controles",
            variant="dark_primary",
            icon=icons["sliders_ink"],
            icon_size=13,
            font_pt=8,
            pad_x=9,
            pad_y=4,
            parent=self,
        )
        self.btn_toggle_left.clicked.connect(self.toggleLeftRequested.emit)
        lay.addWidget(self.btn_toggle_left)

        self.btn_toggle_right = StyledButton(
            " Análisis",
            variant="dark_primary",
            icon=icons["chart_ink"],
            icon_size=13,
            font_pt=8,
            pad_x=9,
            pad_y=4,
            parent=self,
        )
        self.btn_toggle_right.clicked.connect(self.toggleRightRequested.emit)
        lay.addWidget(self.btn_toggle_right)

        lay.addStretch(1)

        self.btn_guided_tour = StyledButton(
            "Tour Guiado · Esc. 3",
            variant="dark_tour",
            icon=icons.get("tour_light"),
            icon_size=13,
            font_pt=8,
            pad_x=10,
            pad_y=4,
            parent=self,
        )
        self.btn_guided_tour.setToolTip(
            "Abrir recorrido guiado interactivo (4 hallazgos clave del escenario)"
        )
        self.btn_guided_tour.clicked.connect(self.guidedTourRequested.emit)
        lay.addWidget(self.btn_guided_tour)

        self.btn_load_excel = StyledButton(
            "Cargar Excel", variant="dark_secondary", font_pt=8, pad_x=9, pad_y=4, parent=self
        )
        self.btn_load_excel.clicked.connect(self.loadExcelRequested.emit)
        lay.addWidget(self.btn_load_excel)

        self.btn_load_csv = StyledButton(
            "Cargar CSV", variant="dark_secondary", font_pt=8, pad_x=9, pad_y=4, parent=self
        )
        self.btn_load_csv.clicked.connect(self.loadCsvRequested.emit)
        lay.addWidget(self.btn_load_csv)

        self.btn_export_csv = StyledButton(
            "Exportar CSV", variant="dark_secondary", font_pt=8, pad_x=9, pad_y=4, parent=self
        )
        self.btn_export_csv.clicked.connect(self.exportCsvRequested.emit)
        lay.addWidget(self.btn_export_csv)

        self.btn_assumptions = StyledButton(
            "Supuestos", variant="dark_secondary", font_pt=8, pad_x=9, pad_y=4, parent=self
        )
        self.btn_assumptions.clicked.connect(self.showAssumptionsRequested.emit)
        lay.addWidget(self.btn_assumptions)

        self.menu_btn_file = QToolButton(self)
        self.menu_btn_file.setObjectName("FileMenuButton")
        self.menu_btn_file.setText("Archivo y Modelo")
        self.menu_btn_file.setIcon(icons["chevron_light"])
        self.menu_btn_file.setIconSize(QSize(10, 10))
        self.menu_btn_file.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.menu_btn_file.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.menu_btn_file.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn_file.setCursor(Qt.CursorShape.PointingHandCursor)

        file_menu = QMenu(self.menu_btn_file)
        file_menu.setFont(QFont(ui_font, 9))
        act_xlsx = QAction("Cargar Excel (.xlsx)...", file_menu)
        act_xlsx.triggered.connect(self.loadExcelRequested.emit)
        act_csv = QAction("Cargar carpeta CSV...", file_menu)
        act_csv.triggered.connect(self.loadCsvRequested.emit)
        act_exp = QAction("Exportar CSV...", file_menu)
        act_exp.triggered.connect(self.exportCsvRequested.emit)
        act_ass = QAction("Supuestos del modelo", file_menu)
        act_ass.triggered.connect(self.showAssumptionsRequested.emit)
        file_menu.addAction(act_xlsx)
        file_menu.addAction(act_csv)
        file_menu.addAction(act_exp)
        file_menu.addSeparator()
        file_menu.addAction(act_ass)
        self.menu_btn_file.setMenu(file_menu)
        lay.addWidget(self.menu_btn_file)

        self.btn_report = StyledButton(
            "Generar Reporte", variant="dark_primary", font_pt=8, pad_x=11, pad_y=4, parent=self
        )
        self.btn_report.clicked.connect(self.generateReportRequested.emit)
        lay.addWidget(self.btn_report)

    @staticmethod
    def guided_tour_button_label(width: int, scenario_id: int) -> str:
        if width >= 1220:
            return f"Tour Guiado · Esc. {scenario_id}"
        return f"Tour Esc. {scenario_id}"

    def update_tour_label(self, width: int, scenario_id: int) -> None:
        self.btn_guided_tour.setText(self.guided_tour_button_label(width, scenario_id))

    def set_tour_active(self, active: bool) -> None:
        self.btn_guided_tour.set_variant("dark_primary" if active else "dark_tour")

    def set_panel_toggle_states(self, show_left: bool, show_right: bool) -> None:
        self.btn_toggle_left.set_variant("dark_primary" if show_left else "dark_secondary")
        self.btn_toggle_left.setIcon(
            self._icons["sliders_ink"] if show_left else self._icons["sliders_light"]
        )
        self.btn_toggle_right.set_variant("dark_primary" if show_right else "dark_secondary")
        self.btn_toggle_right.setIcon(
            self._icons["chart_ink"] if show_right else self._icons["chart_light"]
        )

    def apply_responsive_mode(self, width: int, scenario_id: int) -> str:
        tb_mode = "wide" if width >= 1220 else ("medium" if width >= 920 else "compact")
        wide_full_bar = width >= 1660
        tour_lbl = self.guided_tour_button_label(width, scenario_id)
        sig = (tb_mode, wide_full_bar, tour_lbl)
        if sig == self._last_sig:
            return tb_mode
        self._last_sig = sig

        self.btn_guided_tour.setText(tour_lbl)

        for b in (
            self.btn_load_excel,
            self.btn_load_csv,
            self.btn_export_csv,
            self.btn_assumptions,
        ):
            b.setVisible(tb_mode == "wide" and wide_full_bar)
        self.menu_btn_file.setVisible(not (tb_mode == "wide" and wide_full_bar))

        if tb_mode == "wide":
            self.lbl_subtitle.setVisible(True)
            self.lbl_title.setText("Simulador Hidráulico · Ciudad Bicentenario")
            self.btn_report.setText("Generar Reporte")
            self.menu_btn_file.setText("Archivo y Modelo")
        elif tb_mode == "medium":
            self.lbl_subtitle.setVisible(False)
            self.lbl_title.setText("Ciudad Bicentenario")
            self.btn_report.setText("Generar Reporte")
            self.menu_btn_file.setText("Archivo y Modelo")
        else:
            self.lbl_subtitle.setVisible(False)
            self.lbl_title.setText("Ciudad Bicentenario")
            self.btn_report.setText("Reporte")
            self.menu_btn_file.setText("Archivo")

        return tb_mode
