"""Componentes reutilizables de interfaz gráfica para el simulador."""

import tkinter as tk
from typing import Callable, Dict, List, Optional, Sequence

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


class _ScenarioMenuButton(tk.Menubutton):
    """Selector desplegable basado en tk.Menubutton + tk.Menu (inmune al popdown y selección en blanco de clam)."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        textvariable: tk.StringVar,
        on_select: Callable[[], None],
        on_before_open: Optional[Callable[[], None]] = None,
        values: Sequence[str] = (),
        width: Optional[int] = None,
        padx: int = 8,
        pady: int = 5,
        ui_font: str = "Segoe UI",
    ) -> None:
        kw: Dict[str, object] = {
            "textvariable": textvariable,
            "indicatoron": True,
            "anchor": "w",
            "justify": "left",
            "bg": theme.PAPER_BG,
            "fg": theme.INK_PRIMARY,
            "activebackground": theme.PAPER_SUBTLE,
            "activeforeground": theme.INK_PRIMARY,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 1,
            "highlightbackground": theme.DOCK_BORDER,
            "highlightcolor": theme.ACCENT_PRIMARY,
            "padx": padx,
            "pady": pady,
            "font": (ui_font, 9),
            "cursor": "hand2",
        }
        if width is not None:
            kw["width"] = width
        super().__init__(master, **kw)
        self._var = textvariable
        self._on_select = on_select
        self._on_before_open = on_before_open
        self._values: List[str] = []
        self._menu = tk.Menu(
            self,
            tearoff=0,
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            activebackground=theme.ACCENT_PRIMARY,
            activeforeground=theme.ACCENT_INK,
            selectcolor=theme.ACCENT_PRIMARY,
            font=(ui_font, 9),
            postcommand=self._handle_postcommand,
        )
        self.configure(menu=self._menu)
        if values:
            self.set_values(values)
        self.bind("<ButtonPress-1>", lambda _e: self._handle_postcommand(), add="+")
        self.bind("<<ComboboxSelected>>", lambda _e: self._on_select(), add="+")

    def _handle_postcommand(self) -> None:
        if self._on_before_open is not None:
            self._on_before_open()

    def set_values(self, values: Sequence[str]) -> None:
        self._values = list(values)
        self._menu.delete(0, tk.END)
        for val in self._values:
            self._menu.add_radiobutton(
                label=val,
                variable=self._var,
                value=val,
                command=self._on_select,
            )

    def __getitem__(self, key: str):
        if key == "values":
            return tuple(self._values)
        return super().__getitem__(key)

    def __setitem__(self, key: str, value) -> None:
        if key == "values":
            self.set_values(value)
        else:
            super().__setitem__(key, value)
