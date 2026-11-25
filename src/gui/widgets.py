"""Primitivas reutilizables PySide6 (Capa 2: Widgets con variantes y diseño editorial)."""

from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme

COMMERCIAL_DIAMETERS_IN = [
    "Original",
    '6"',
    '8"',
    '10"',
    '12"',
    '14"',
    '16"',
    '18"',
    '20"',
    '24"',
    '30"',
    '36"',
    '42"',
    '48"',
]


@contextmanager
def blocked_signals(*widgets: QWidget) -> Iterator[None]:
    """Bloquea temporalmente las señales de uno o más widgets durante actualizaciones internas."""
    prev_states = [w.blockSignals(True) for w in widgets]
    try:
        yield
    finally:
        for w, prev in zip(widgets, prev_states):
            w.blockSignals(prev)


def make_separator(
    orientation: str = "h",
    color: str = theme.DOCK_BORDER,
    thickness: int = 1,
    parent: Optional[QWidget] = None,
) -> QFrame:
    """Crea una línea divisoria sólida de 1-3 px en el color del sistema de diseño."""
    line = QFrame(parent)
    line.setStyleSheet(f"background-color: {color}; border: none;")
    if orientation == "v":
        line.setFixedWidth(thickness)
        line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    else:
        line.setFixedHeight(thickness)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return line


class StyledButton(QPushButton):
    """Botón estandarizado por variante semántica de tema (`primary`, `dark_secondary`, etc.)."""

    def __init__(
        self,
        text: str = "",
        variant: str = "light_secondary",
        *,
        icon: Optional[QIcon] = None,
        icon_size: int = 12,
        font_pt: int = 9,
        pad_x: Optional[int] = None,
        pad_y: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setDefault(False)
        if icon is not None:
            self.setIcon(icon)
            self.setIconSize(QSize(icon_size, icon_size))
        self._font_pt = font_pt
        self._pad_x = pad_x
        self._pad_y = pad_y
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        if self._pad_y is not None and self._pad_y <= 3:
            self.setProperty("compactPad", "true")
        theme.apply_variant(self, variant)
        f = self.font()
        f.setPointSize(self._font_pt)
        f.setBold("primary" in variant)
        self.setFont(f)

    def variant(self) -> str:
        return self._variant


class PauseOnOpenComboBox(QComboBox):
    """ComboBox que emite `aboutToShowPopup` justo antes de abrir su lista desplegable."""

    aboutToShowPopup = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showPopup(self) -> None:
        self.aboutToShowPopup.emit()
        super().showPopup()


class SectionCard(QFrame):
    """Lámina editorial en vitela (#FFFFE3) con cabecera estructurada y borde grafito."""

    def __init__(
        self,
        title: str,
        *,
        dark_header: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QFrame(self)
        hdr.setObjectName("SectionHeader")
        hdr.setProperty("dark", "true" if dark_header else "false")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 5, 10, 5)
        self._header_label = QLabel(title, hdr)
        self._header_label.setObjectName("SectionHeaderLabel")
        hdr_lay.addWidget(self._header_label)
        outer.addWidget(hdr)

        rule = QFrame(self)
        rule.setObjectName("SectionRule")
        rule.setProperty("dark", "true" if dark_header else "false")
        rule.setFixedHeight(2)
        outer.addWidget(rule)

        body = QWidget(self)
        body.setObjectName("SectionBody")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(10, 8, 10, 8)
        self.body_layout.setSpacing(5)
        outer.addWidget(body)

    def set_title(self, title: str) -> None:
        self._header_label.setText(title)

    def title(self) -> str:
        return self._header_label.text()


class SegmentedControl(QFrame):
    """Selector segmentado plano con estado activo en Azul Pizarra (#6D8196)."""

    selectionChanged = Signal(str)

    def __init__(
        self,
        items: Sequence[Tuple[str, str]],
        *,
        initial_key: Optional[str] = None,
        inactive_variant: str = "dock_secondary",
        font_pt: int = 8,
        pad_x: int = 9,
        pad_y: int = 3,
        spacing: int = 1,
        framed: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if framed:
            self.setObjectName("SegmentedFrame")
        self._inactive_variant = inactive_variant
        self._font_pt = font_pt
        self._pad_x = pad_x
        self._pad_y = pad_y
        self._buttons: Dict[str, StyledButton] = {}
        self._current_key: str = initial_key or (items[0][0] if items else "")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(1 if framed else 0, 1 if framed else 0, 1 if framed else 0, 1 if framed else 0)
        lay.setSpacing(spacing)

        for key, label in items:
            btn = StyledButton(
                label,
                variant="primary" if key == self._current_key else inactive_variant,
                font_pt=font_pt,
                pad_x=pad_x,
                pad_y=pad_y,
                parent=self,
            )
            btn.clicked.connect(lambda _checked=False, k=key: self._on_btn_clicked(k))
            lay.addWidget(btn)
            self._buttons[key] = btn

    def _on_btn_clicked(self, key: str) -> None:
        if key == self._current_key:
            return
        self.set_current(key)
        self.selectionChanged.emit(key)

    def set_current(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._current_key = key
        for k, btn in self._buttons.items():
            btn.set_variant("primary" if k == key else self._inactive_variant)

    def set_labels(self, labels: Dict[str, str], pad_x: Optional[int] = None) -> None:
        for k, text in labels.items():
            btn = self._buttons.get(k)
            if btn is not None:
                btn.setText(text)
                if pad_x is not None and pad_x <= 6:
                    btn.setProperty("compactPad", "true")
                    theme.apply_variant(btn, btn.variant())

    def current_key(self) -> str:
        return self._current_key

    def button(self, key: str) -> Optional[StyledButton]:
        return self._buttons.get(key)


class KpiCard(QFrame):
    """Tarjeta métrica de telemetría en papel vitela (#FFFFE3) con filete pizarra."""

    def __init__(self, caption: str, initial_value: str = "-", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top_rule = QFrame(self)
        top_rule.setObjectName("KpiTopRule")
        top_rule.setFixedHeight(2)
        lay.addWidget(top_rule)

        inner = QVBoxLayout()
        inner.setContentsMargins(8, 4, 8, 5)
        inner.setSpacing(1)
        self._caption_lbl = QLabel(caption, self)
        self._caption_lbl.setObjectName("KpiCaption")
        self._value_lbl = QLabel(initial_value, self)
        self._value_lbl.setObjectName("KpiValue")
        inner.addWidget(self._caption_lbl)
        inner.addWidget(self._value_lbl)
        lay.addLayout(inner)

    def set_caption(self, text: str) -> None:
        self._caption_lbl.setText(text)

    def set_value(self, text: str, color_hex: Optional[str] = None) -> None:
        self._value_lbl.setText(text)
        col = color_hex or theme.INK_PRIMARY
        self._value_lbl.setStyleSheet(f"color: {col};")

    def value_text(self) -> str:
        return self._value_lbl.text()


class StructureStrip(QFrame):
    """Tira visual de nodos activos en Cola (Queue) o Pila (Stack) para recorridos."""

    def __init__(self, mono_font: str = "Consolas", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mono_font = mono_font
        self.setStyleSheet(
            f"QFrame#StructureStrip {{ background-color: {theme.PAPER_SUBTLE}; "
            f"border: 1px solid {theme.DOCK_BORDER}; }}"
        )
        self.setObjectName("StructureStrip")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 5)
        lay.setSpacing(3)

        self._header_lbl = QLabel("Cola (Queue) · FRENTE → FINAL", self)
        self._header_lbl.setFont(QFont(mono_font, 7, QFont.Weight.Bold))
        self._header_lbl.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        lay.addWidget(self._header_lbl)

        self._cells_host = QWidget(self)
        self._cells_host.setStyleSheet("background: transparent;")
        self._cells_layout = QHBoxLayout(self._cells_host)
        self._cells_layout.setContentsMargins(0, 0, 0, 0)
        self._cells_layout.setSpacing(3)
        lay.addWidget(self._cells_host)

        self.update_items("Queue", [])

    def update_items(self, structure_name: str, items: Sequence[str], step_text: str = "") -> None:
        while self._cells_layout.count():
            child = self._cells_layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()

        hdr = "Pila (Stack) · TOPE ↑" if structure_name == "Stack" else "Cola (Queue) · FRENTE → FINAL"
        if step_text:
            hdr = f"{hdr}  [{step_text}]"
        self._header_lbl.setText(hdr)

        if not items:
            lbl = QLabel("(vacía)", self._cells_host)
            lbl.setFont(QFont(self._mono_font, 7))
            lbl.setStyleSheet(
                f"background-color: {theme.PAPER_BG}; color: {theme.INK_MUTED}; "
                f"border: 1px solid {theme.PAPER_BORDER}; padding: 2px 6px;"
            )
            self._cells_layout.addWidget(lbl)
            self._cells_layout.addStretch(1)
            return

        max_cells = 6
        for idx, val in enumerate(items[:max_cells]):
            is_head = idx == 0
            bg = theme.ACCENT_PRIMARY if is_head else theme.PAPER_BG
            fg = theme.ACCENT_INK if is_head else theme.INK_PRIMARY
            cell = QLabel(str(val), self._cells_host)
            cell.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
            cell.setStyleSheet(
                f"background-color: {bg}; color: {fg}; "
                f"border: 1px solid {theme.DOCK_BORDER}; padding: 2px 5px;"
            )
            self._cells_layout.addWidget(cell)

        if len(items) > max_cells:
            extra = QLabel(f"+{len(items) - max_cells}", self._cells_host)
            extra.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
            extra.setStyleSheet(
                f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; "
                f"border: 1px solid {theme.DOCK_BORDER}; padding: 2px 4px;"
            )
            self._cells_layout.addWidget(extra)

        self._cells_layout.addStretch(1)


class SourceBarWidget(QWidget):
    """Barra proporcional apilada de composición por fuente aportante."""

    _TONES = [
        "#4A4A4A",
        "#6D8196",
        "#5A6570",
        "#9BA5B0",
        "#CBCBCB",
        "#7D8E9F",
        "#3A3A3A",
        "#B3B8BE",
    ]

    def __init__(self, mono_font: str = "Consolas", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mono_font = mono_font
        self._shares: List[Tuple[str, float]] = []
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_shares(self, shares: Sequence[Tuple[str, float]]) -> None:
        self._shares = list(shares)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())
        painter.fillRect(QRectF(0, 0, w, h), QColor(theme.PAPER_BG))

        font = QFont(self._mono_font)
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)

        if not self._shares:
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(theme.INK_MUTED))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Sin mezcla activa")
        else:
            x_cur = 0.0
            n = len(self._shares)
            for idx, (src_id, frac) in enumerate(self._shares):
                seg_w = (w - x_cur) if idx == n - 1 else (w * frac)
                if seg_w < 1.0:
                    continue
                tone = self._TONES[idx % len(self._TONES)]
                rect = QRectF(x_cur, 0.0, seg_w, h)
                painter.fillRect(rect, QColor(tone))
                if idx < n - 1:
                    painter.setPen(QPen(QColor(theme.PAPER_BG), 1.5))
                    painter.drawLine(int(round(x_cur + seg_w)), 0, int(round(x_cur + seg_w)), int(h))
                if seg_w >= 34.0:
                    txt_col = theme.INK_PRIMARY if tone in ("#CBCBCB", "#B3B8BE") else theme.PAPER_BG
                    painter.setPen(QColor(txt_col))
                    painter.drawText(
                        rect,
                        Qt.AlignmentFlag.AlignCenter,
                        f"F{src_id} {frac * 100.0:.0f}%",
                    )
                x_cur += seg_w

        painter.setPen(QPen(QColor(theme.DOCK_BORDER), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, max(1.0, w - 1.0), max(1.0, h - 1.0)))
        painter.end()


class LoadingSpinner(QWidget):
    """Indicador circular animado estilo Lámina Cartográfica."""

    def __init__(
        self,
        size: int = 34,
        stroke: float = 3.2,
        accent_color: str = theme.ACCENT_PRIMARY,
        track_color: str = theme.PAPER_BORDER,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._size = max(16, int(size))
        self._stroke = float(stroke)
        self._accent = QColor(accent_color)
        self._track = QColor(track_color)
        self._angle = 0
        self.setFixedSize(self._size, self._size)

        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._advance)

    def _advance(self) -> None:
        self._angle = (self._angle - 18) % 360
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pad = self._stroke / 2.0 + 2.0
        rect = QRectF(pad, pad, self.width() - 2.0 * pad, self.height() - 2.0 * pad)

        track_pen = QPen(self._track, self._stroke)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        arc_pen = QPen(self._accent, self._stroke)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        p.drawArc(rect, self._angle * 16, 115 * 16)
        p.end()


class LoadingOverlay(QFrame):
    """Superposición translúcida con spinner centrado y etiqueta de progreso."""

    def __init__(self, parent: QWidget, ui_font: str = "Segoe UI") -> None:
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = QFrame(self)
        self._card.setObjectName("LoadingOverlayCard")
        self._card.setStyleSheet(
            f"#LoadingOverlayCard {{ background-color: {theme.PAPER_BG}; "
            f"border: 1px solid {theme.PAPER_RULE}; }}"
        )
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(20, 14, 20, 14)
        card_lay.setSpacing(9)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.spinner = LoadingSpinner(size=34, stroke=3.2, parent=self._card)
        card_lay.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)

        self.lbl_message = QLabel("Generando gráficas...", self._card)
        self.lbl_message.setFont(QFont(ui_font, 8, QFont.Weight.Bold))
        self.lbl_message.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.lbl_message)

        root_lay.addWidget(self._card, 0, Qt.AlignmentFlag.AlignCenter)

        parent.installEventFilter(self)
        self.setGeometry(parent.rect())

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self.setGeometry(watched.rect())
            if self.isVisible():
                self.raise_()
        return super().eventFilter(watched, event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 227, 214))
        p.end()

    def start(self, message: str = "Generando gráficas...") -> None:
        self.lbl_message.setText(message)
        pw = self.parentWidget()
        if pw is not None:
            self.setGeometry(pw.rect())
        self.setVisible(True)
        self.raise_()
        self.spinner.start()

    def stop(self) -> None:
        self.spinner.stop()
        self.setVisible(False)

    def set_active(self, active: bool, message: str = "Generando gráficas...") -> None:
        if active:
            self.start(message)
        else:
            self.stop()
