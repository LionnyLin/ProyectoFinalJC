"""Ejecución asíncrona de tareas pesadas en hilos Python con puente Qt seguro."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication


class _ResultBridge(QObject):
    """Puente QObject en el hilo GUI para recibir resultados vía QueuedConnection."""

    finished = Signal(int, object)
    failed = Signal(int, object)
    threadExited = Signal(int)


class AsyncTaskRunner(QObject):
    """Administrador de tareas en segundo plano por canal con descarte de respuestas obsoletas.

    Usa ``threading.Thread`` para mantener la segmentación justa del GIL en CPython
    (de modo que el ``QTimer`` del spinner y la UI sigan repintando sin trabarse)
    y entrega los callbacks en el hilo principal mediante ``Qt.QueuedConnection``.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._seq = 0
        self._latest_ids: Dict[str, int] = {}
        self._active: Dict[
            int,
            Tuple[
                str,
                threading.Thread,
                Optional[Callable[[Any], None]],
                Optional[Callable[[Exception], None]],
                Optional[Callable[[], None]],
            ],
        ] = {}

        self._bridge = _ResultBridge(self)
        self._bridge.finished.connect(
            self._on_worker_finished, Qt.ConnectionType.QueuedConnection
        )
        self._bridge.failed.connect(
            self._on_worker_failed, Qt.ConnectionType.QueuedConnection
        )
        self._bridge.threadExited.connect(
            self._on_thread_exited, Qt.ConnectionType.QueuedConnection
        )

    def submit(
        self,
        channel: str,
        fn: Callable[..., Any],
        *args: Any,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_finally: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> int:
        """Lanza `fn(*args, **kwargs)` en un hilo secundario asociado a `channel`."""
        self._seq += 1
        req_id = self._seq
        self._latest_ids[channel] = req_id

        def _runner() -> None:
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self._bridge.failed.emit(req_id, exc)
            else:
                self._bridge.finished.emit(req_id, result)
            finally:
                self._bridge.threadExited.emit(req_id)

        thread = threading.Thread(
            target=_runner,
            name=f"AsyncTask-{channel}-{req_id}",
            daemon=True,
        )
        self._active[req_id] = (channel, thread, on_success, on_error, on_finally)
        thread.start()
        return req_id

    def cancel_channel(self, channel: str) -> None:
        """Invalida cualquier tarea pendiente en `channel`."""
        self._seq += 1
        self._latest_ids[channel] = self._seq

    def is_busy(self, channel: Optional[str] = None) -> bool:
        """Indica si hay tareas vigentes (o activas en general si `channel` es None)."""
        if channel is None:
            return bool(self._active)
        latest = self._latest_ids.get(channel)
        return latest is not None and latest in self._active

    def wait_all(self, timeout_ms: int = 5000) -> bool:
        """Espera hasta `timeout_ms` a que terminen los hilos activos y procesa callbacks."""
        deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
        qapp = QApplication.instance()
        while self._active:
            if qapp is not None:
                qapp.processEvents()
            if not self._active:
                return True
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                return False
            first_entry = next(iter(self._active.values()))
            first_thread = first_entry[1]
            first_thread.join(timeout=min(0.02, max(0.001, remaining_s)))
        if qapp is not None:
            qapp.processEvents()
        return not self._active

    @Slot(int, object)
    def _on_worker_finished(self, req_id: int, result: object) -> None:
        entry = self._active.get(req_id)
        if entry is None:
            return
        channel, _thread, on_success, _on_error, on_finally = entry
        if self._latest_ids.get(channel) != req_id:
            return
        try:
            if on_success is not None:
                on_success(result)
        finally:
            if on_finally is not None:
                on_finally()

    @Slot(int, object)
    def _on_worker_failed(self, req_id: int, exc: object) -> None:
        entry = self._active.get(req_id)
        if entry is None:
            return
        channel, _thread, _on_success, on_error, on_finally = entry
        if self._latest_ids.get(channel) != req_id:
            return
        try:
            if on_error is not None:
                err = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                on_error(err)
        finally:
            if on_finally is not None:
                on_finally()

    @Slot(int)
    def _on_thread_exited(self, req_id: int) -> None:
        self._active.pop(req_id, None)
