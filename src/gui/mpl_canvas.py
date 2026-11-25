"""Canvas Matplotlib con redimensionado diferido para paneles con gráficas.

`FigureCanvasQTAgg` re-renderiza la figura completa (Agg) en cada `resizeEvent`. Al arrastrar
un divisor llegan decenas de eventos por segundo y cada render cuesta 80–250 ms, lo que congela
la interfaz. `ResponsiveFigureCanvas` separa las dos fases:

1. Durante el arrastre: se pinta la última imagen renderizada, estirada al nuevo tamaño (~1 ms).
2. Cuando el tamaño deja de cambiar (`settle_ms`): se aplica el tamaño real a la figura, se
   emite `resizeSettled` para que el panel recalcule su layout y se hace un único render.
"""

import os
from typing import Optional

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QResizeEvent
from PySide6.QtWidgets import QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import to_hex
from matplotlib.figure import Figure


class ResponsiveFigureCanvas(FigureCanvasQTAgg):
    """FigureCanvasQTAgg que no re-renderiza mientras el widget se redimensiona de forma continua."""

    resizeSettled = Signal()

    def __init__(self, figure: Figure, settle_ms: int = 140) -> None:
        super().__init__(figure)
        self._resize_pending = False
        self._preview: Optional[QImage] = None
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(settle_ms)
        self._settle_timer.timeout.connect(self._apply_pending_resize)

    def is_resizing(self) -> bool:
        return self._resize_pending

    # --- Fase 1: arrastre ----------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        # Sin nada en pantalla (oculto o aún sin render) no hay lag que evitar: ruta normal.
        if not self.isVisible() or not hasattr(self, "renderer"):
            super().resizeEvent(event)
            return
        if not self._resize_pending:
            self._preview = self._snapshot()
            self._resize_pending = True
        QWidget.resizeEvent(self, event)
        self._settle_timer.start()
        self.update()

    def paintEvent(self, event) -> None:
        if self._resize_pending and self._preview is not None:
            painter = QPainter(self)
            try:
                painter.fillRect(self.rect(), QColor(to_hex(self.figure.get_facecolor())))
                painter.drawImage(QRectF(self.rect()), self._preview)
            finally:
                painter.end()
            return
        super().paintEvent(event)

    def _snapshot(self) -> Optional[QImage]:
        try:
            buf = self.renderer.buffer_rgba()
            h, w = int(self.renderer.height), int(self.renderer.width)
            img = QImage(bytes(buf), w, h, QImage.Format.Format_RGBA8888).copy()
            img.setDevicePixelRatio(self.device_pixel_ratio)
            return img
        except Exception:
            return None

    # --- Fase 2: tamaño estable ------------------------------------------------------------

    def _apply_pending_resize(self) -> None:
        if not self._resize_pending:
            return
        self._resize_pending = False
        self._preview = None
        size = self.size()
        # Ajusta figure.set_size_inches y deja un draw_idle pendiente (aún no renderiza).
        super().resizeEvent(QResizeEvent(size, size))
        # El panel rehace su layout de forma síncrona; su draw_idle se fusiona con el anterior.
        self.resizeSettled.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._resize_pending:
            QTimer.singleShot(0, self._apply_pending_resize)
