"""Generador reproducible de capturas de pantalla para la documentación técnica.

Produce 24 capturas en `docs/screenshots/` combinando:
- Vistas globales de ventana (1280x740; 900x700 para el modo compacto)
- Recortes enfocados de paneles/widgets para máxima legibilidad en 2 columnas (3.45 in)
- Tarjetas terminales compactas de ejecución real (CSV, CLI y suite de pruebas)

Captura multiplataforma:
- Windows: `PrintWindow` vía ctypes (renderiza aunque la ventana esté tapada).
- Linux/X11: la ventana se re-mapea sin decoración en (0, 0) con la geometría pedida (los gestores de
  ventanas en mosaico ignoran `geometry()` en ventanas gestionadas) y se captura con ImageMagick
  (`import -window <id>`). Requiere ImageMagick y un servidor X (`DISPLAY`).

Uso: `python scripts/capture_doc_screenshots.py [--gui-only]` desde la raíz del repositorio.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SHOT_DIR = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)

IS_WINDOWS = sys.platform.startswith("win")
FULL_SIZE = (1280, 740)
COMPACT_SIZE = (900, 700)


# ── Captura de ventana (Windows: PrintWindow · Linux: ImageMagick) ───────────

def _capture_hwnd(hwnd: int, w: int, h: int) -> Image.Image:
    """Windows: copia la ventana con PrintWindow (PW_RENDERFULLCONTENT) a un bitmap DIB."""
    import ctypes
    from ctypes import wintypes

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd_dc = user32.GetWindowDC(hwnd)
    mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    save_bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mfc_dc, save_bitmap)
    if user32.PrintWindow(hwnd, mfc_dc, 2) == 0:
        user32.PrintWindow(hwnd, mfc_dc, 0)
    bmi = _BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount, bmi.biCompression = w, -h, 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mfc_dc, save_bitmap, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    gdi32.DeleteObject(save_bitmap)
    gdi32.DeleteDC(mfc_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    return img


def _capture_x11(win: tk.Tk) -> Image.Image:
    """Linux/X11: captura la ventana completa con ImageMagick `import -window`."""
    if shutil.which("import") is None:
        raise RuntimeError("Falta ImageMagick (`import`) para capturar en Linux/X11.")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "win.png")
        subprocess.run(["import", "-window", hex(win.winfo_id()), out], check=True, timeout=30)
        return Image.open(out).convert("RGB")


def _pump(win: tk.Misc, seconds: float = 0.0, step: float = 0.05) -> None:
    """Procesa eventos Tk durante `seconds` (o una vez) para que el lienzo y las gráficas terminen de pintar."""
    win.update_idletasks()
    win.update()
    end = time.time() + seconds
    while time.time() < end:
        win.update()
        time.sleep(step)


def _place_window(app: tk.Tk, size) -> None:
    """Fija el tamaño de captura. En Linux re-mapea la ventana sin decoración en (0, 0)."""
    w, h = size
    if IS_WINDOWS:
        app.geometry(f"{w}x{h}+30+20")
        app.lift()
        app.attributes("-topmost", True)
        app.update()
        app.attributes("-topmost", False)
        _pump(app, 0.5)
        return
    app.withdraw()
    app.update()
    app.overrideredirect(True)
    app.geometry(f"{w}x{h}+0+0")
    app.deiconify()
    _pump(app, 2.0)


def _grab_full(win: tk.Tk) -> Image.Image:
    _pump(win, 0.30)
    cv = getattr(win, "network_canvas", None)
    if cv is not None:  # el puntero real puede quedar sobre el mapa y disparar un tooltip espurio
        cv._hide_tooltip()
        win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    if IS_WINDOWS:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        return _capture_hwnd(hwnd, w, h)
    return _capture_x11(win)


# ── Control determinista de la app ────────────────────────────────────────────

def _freeze(app) -> None:
    """Pausa reproducción, animación de recorrido y pulsos para que la captura sea determinista."""
    app._stop_playback()
    app._stop_traversal()
    app.network_canvas.stop_pulse_animation()


def _goto_step(app, target_min: float) -> None:
    """Va al paso más cercano a `target_min` (modo instantáneo, sin reproducción)."""
    _freeze(app)
    app._ensure_instant()
    if not app.result or not app.result.snapshots:
        return
    idx = min(range(len(app.result.snapshots)), key=lambda i: abs(app.result.snapshots[i].time_min - target_min))
    app.go_to_step(idx)
    _pump(app)


def _select(app, kind, entity_id) -> None:
    """Selecciona (o limpia) la entidad del Inspector."""
    app.select_entity(kind, entity_id)
    _pump(app)


def _set_scenario_and_run(app, scenario_id: int, target_min: float = 35.0) -> None:
    """Selecciona el escenario 1..5, simula sin auto-play y se posiciona en `target_min`."""
    app.controls.select_scenario_by_id(scenario_id)
    app.run_simulation(auto_play=False)
    _goto_step(app, target_min)


def _grab_window(app: tk.Tk, filename: str, wait: float = 0.35) -> str:
    _freeze(app)
    _pump(app, wait)
    img = _grab_full(app)
    path = os.path.join(SHOT_DIR, filename)
    img.save(path)
    print(f"Captured {filename} ({img.width}x{img.height})")
    return path


def _grab_widget_crop(app: tk.Tk, widget: tk.Misc, filename: str, wait: float = 0.35) -> str:
    _freeze(app)
    _pump(app, wait)
    full = _grab_full(app)
    left = max(0, widget.winfo_rootx() - app.winfo_rootx())
    top = max(0, widget.winfo_rooty() - app.winfo_rooty())
    right = min(full.width, left + widget.winfo_width())
    bottom = min(full.height, top + widget.winfo_height())
    path = os.path.join(SHOT_DIR, filename)
    full.crop((left, top, right, bottom)).save(path)
    print(f"Captured crop {filename} ({right - left}x{bottom - top})")
    return path


# ── Tarjetas terminal ─────────────────────────────────────────────────────────

_MONO = (
    r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/Library/Fonts/Menlo.ttc",
)
_MONO_BOLD = (
    r"C:\Windows\Fonts\consolab.ttf", "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/Library/Fonts/Menlo.ttc",
)


def _load_font(candidates, size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_terminal_card(title: str, lines: List[str], filename: str) -> str:
    font, title_font = _load_font(_MONO, 14), _load_font(_MONO_BOLD, 15)
    pad_x, pad_y, line_h, w = 18, 16, 20, 880
    h = 44 + len(lines) * line_h + pad_y * 2
    img = Image.new("RGB", (w, h), (22, 27, 34))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (w, 36)], fill=(33, 38, 45))
    for x, col in ((12, (255, 95, 86)), (32, (255, 189, 46)), (52, (39, 201, 63))):
        draw.ellipse([(x, 11), (x + 12, 23)], fill=col)
    draw.text((78, 9), title, font=title_font, fill=(230, 237, 243))
    y = 44
    for line in lines:
        color = (201, 209, 217)
        if "PASSED" in line or "passed" in line or "OK" in line or "Generado" in line or "bytes)" in line:
            color = (126, 231, 135)
        elif line.startswith("$") or line.startswith(">"):
            color = (121, 192, 255)
        draw.text((pad_x, y), line[:98], font=font, fill=color)
        y += line_h
    path = os.path.join(SHOT_DIR, filename)
    img.save(path)
    print(f"Rendered terminal card {filename} ({w}x{h})")
    return path


# ── Captura completa ──────────────────────────────────────────────────────────

def _capture_gui(shots: Dict[str, str], data_path: str) -> None:
    from src.gui import theme as gui_theme
    from src.gui.app import BicentenarioSewerApp

    app = BicentenarioSewerApp(initial_data_path=data_path)
    _place_window(app, FULL_SIZE)
    _freeze(app)
    cv = app.network_canvas

    # 00. Vista general (Esc. 3, t = 35 min)
    _set_scenario_and_run(app, 3, 35.0)
    shots["00_vista_general"] = _grab_window(app, "00_vista_general.png")

    # 01_1. Sub-pasos continuos con PriorityQueue (centro: KPIs, mapa y reproductor)
    shots["01_1_subpasos_transit"] = _grab_widget_crop(app, app._center, "01_1_subpasos_transit.png")

    # 01_2. Almacenamiento finito + rebose superficial (Esc. 5, t = 45 min, Inspector del nodo con más rebose)
    _set_scenario_and_run(app, 5, 45.0)
    snap = app.result.snapshots[app.current_step]
    flood_node = max(snap.node_states.items(), key=lambda kv: kv[1].surface_flooding_m3)[0]
    _select(app, "node", flood_node)
    app.notebook.select(0)
    _goto_step(app, 45.0)
    shots["01_2_almacenamiento_rebose"] = _grab_widget_crop(app, app.notebook, "01_2_almacenamiento_rebose.png")

    # 01_3a. Intervención en vivo (P29 al 80 % en t = 40 min)
    _set_scenario_and_run(app, 3, 40.0)
    _select(app, "pipe", "P29")
    app.inspector_tab.var_obst.set(80.0)
    app.inspector_tab._emit_apply()
    _goto_step(app, 40.0)
    app.notebook.select(0)
    shots["01_3a_intervencion_mapa"] = _grab_widget_crop(app, cv, "01_3a_intervencion_mapa.png")

    # 01_3b. Hidrograma comparativo Antes vs Después
    app.notebook.select(2)
    app.charts_panel.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["01_3b_antes_despues"] = _grab_widget_crop(app, app.charts_panel, "01_3b_antes_despues.png", wait=0.6)
    app._action_restore_all()
    _select(app, None, None)
    app.notebook.select(0)

    # 01_4. Reglas configurables desde la GUI (panel Controles con preset calibrado y reparto igualitario)
    app.controls._split_var.set(gui_theme.SPLIT_RULE_TO_ES["equal"])
    app.controls._source_var.set(gui_theme.SOURCE_DIST_TO_ES["equal"])
    app.controls.apply_preset(2.5, 0.003)
    app.controls.cancel_pending()
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)
    shots["01_4_reglas_gui"] = _grab_widget_crop(app, app.controls, "01_4_reglas_gui.png")

    app.controls._split_var.set(gui_theme.SPLIT_RULE_TO_ES["proportional"])
    app.controls._source_var.set(gui_theme.SOURCE_DIST_TO_ES["capacity"])
    app.controls.apply_preset(100.0, 0.0)
    app.controls.cancel_pending()
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)

    # 02_1a / 02_1b. Animación BFS (Queue) y DFS (Stack) con la Bitácora de recorrido
    app.controls.switch_tab("trav")
    app.controls.set_start_node("9")
    app._action_traversal("BFS", "9", "31", True)
    app.step_traversal_animation(8)
    shots["02_1a_bfs_queue"] = _grab_window(app, "02_1a_bfs_queue.png")
    app._action_traversal("DFS", "9", "31", True)
    app.step_traversal_animation(10)
    shots["02_1b_dfs_stack"] = _grab_window(app, "02_1b_dfs_stack.png")
    app.clear_traversal()
    app.controls.switch_tab("sim")

    # 02_2. Trazado Aguas arriba + Aislar cuenca (nodo K)
    _select(app, "node", "K")
    app._action_toggle_inspector_trace("up")
    app._action_toggle_basin()
    _goto_step(app, 35.0)
    shots["02_2_aguas_arriba_aislar"] = _grab_window(app, "02_2_aguas_arriba_aislar.png")
    app.clear_traversal()
    app._clear_basin()
    _select(app, None, None)

    # 02_3. Detección de nodos desconectados (P29 al 100 % en t = 40 min)
    _select(app, "pipe", "P29")
    app.inspector_tab.var_obst.set(100.0)
    app.inspector_tab._emit_apply()
    _goto_step(app, 40.0)
    shots["02_3_nodos_desconectados"] = _grab_window(app, "02_3_nodos_desconectados.png")
    app._action_restore_all()
    _select(app, None, None)

    # 02_4. Composición por fuente aportante (Nodo 30 en Inspector)
    _set_scenario_and_run(app, 3, 40.0)
    _select(app, "node", "30")
    app.notebook.select(0)
    _goto_step(app, 40.0)
    shots["02_4_composicion_fuentes"] = _grab_widget_crop(app, app.notebook, "02_4_composicion_fuentes.png")
    _select(app, None, None)

    # 02_5. Persistencia de sobrecarga (Tuberías Críticas en Esc. 5, modo Min. Sobrecarga)
    _set_scenario_and_run(app, 5, 45.0)
    app._set_map_mode("overload_minutes")
    app.notebook.select(1)
    shots["02_5_persistencia_sobrecarga"] = _grab_widget_crop(app, app.notebook, "02_5_persistencia_sobrecarga.png")
    app.notebook.select(0)

    # 03_1a/b/c. Tres modos cartográficos en Esc. 5
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    shots["03_1a_modo_instantaneo"] = _grab_window(app, "03_1a_modo_instantaneo.png")
    app._set_map_mode("peak")
    shots["03_1b_modo_pico"] = _grab_window(app, "03_1b_modo_pico.png")
    app._set_map_mode("overload_minutes")
    shots["03_1c_modo_sobrecarga"] = _grab_window(app, "03_1c_modo_sobrecarga.png")

    # 03_2. Lienzo avanzado: zoom en la confluencia 30-D-G-31 con rebose en t = 45 min
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    cv._zoom_at(cv.winfo_width() * 0.38, cv.winfo_height() * 0.65, 1.85)
    shots["03_2_canvas_zoom_rebose"] = _grab_widget_crop(app, cv, "03_2_canvas_zoom_rebose.png")
    cv.reset_view()

    # 03_3a / 03_3b. Gráficas avanzadas (Hidrograma doble eje + Perfil longitudinal)
    _set_scenario_and_run(app, 3, 40.0)
    app.notebook.select(2)
    app.charts_panel.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["03_3a_hidrograma_twinx"] = _grab_widget_crop(app, app.charts_panel, "03_3a_hidrograma_twinx.png", wait=0.6)
    app.charts_panel.set_subtab("profile")
    _goto_step(app, 40.0)
    shots["03_3b_perfil_longitudinal"] = _grab_widget_crop(app, app.charts_panel, "03_3b_perfil_longitudinal.png", wait=0.6)
    app.notebook.select(0)

    # 03_4. Recorrido guiado (Esc. 5, parada 2)
    _set_scenario_and_run(app, 5, 45.0)
    app.tour.toggle()
    _pump(app, 1.0)  # termina la animación de cámara hacia el primer hallazgo
    app.tour.go_to(1)
    _pump(app, 1.2)  # cámara animada hacia el segundo hallazgo
    shots["03_4_recorrido_guiado"] = _grab_window(app, "03_4_recorrido_guiado.png", wait=0.6)
    app.tour.close(reset_view=False)
    cv.reset_view()

    # 03_5a. Comparación de los 5 escenarios
    app.run_comparison()
    app.notebook.select(3)
    try:  # ensancha el panel derecho para que la tabla de 9 columnas se lea completa
        app.paned.sash_place(1, FULL_SIZE[0] - 500, 300)
    except tk.TclError:
        pass
    _pump(app, 0.6)
    shots["03_5a_comparacion_escenarios"] = _grab_window(app, "03_5a_comparacion_escenarios.png", wait=0.6)

    # 03_5b. UI responsiva en modo compacto
    app.notebook.select(0)
    _place_window(app, COMPACT_SIZE)
    _pump(app, 0.8)
    shots["03_5b_ui_compacta"] = _grab_window(app, "03_5b_ui_compacta.png", wait=0.5)

    app._on_close()


def _capture_terminals(shots: Dict[str, str], data_path: str) -> None:
    from src.io.data_loader import export_to_csv_dir, load_dataset

    # 04_1. Carga dual .xlsx + .csv y exportación a CSV
    ds = load_dataset(data_path)
    with tempfile.TemporaryDirectory() as td:
        csv_dir = os.path.join(td, "csv_export")
        export_to_csv_dir(ds, csv_dir)
        csv_lines = [
            "$ python -c \"export_to_csv_dir(load_dataset('DataSetBicentenario.xlsx'), 'csv_export')\"",
            f"Red validada (DAG): {ds.graph.num_nodes} nodos, {ds.graph.num_pipes} tuberias, {len(ds.scenarios)} escenarios",
            "Archivos CSV generados:",
        ] + [
            f"  - {fn:<30} ({os.path.getsize(os.path.join(csv_dir, fn)):>6,} bytes)"
            for fn in sorted(os.listdir(csv_dir))
        ]
    shots["04_1_carga_export_csv"] = _render_terminal_card(
        "4.1 Carga Dual .xlsx + .csv y Exportacion CSV", csv_lines, "04_1_carga_export_csv.png"
    )

    # 04_2. Generación automática por CLI (main.py)
    with tempfile.TemporaryDirectory() as td:
        md_p = os.path.join(td, "REPORTE_ESCENARIOS.md")
        docx_p = os.path.join(td, "REPORTE_ESCENARIOS.docx")
        tech_p = os.path.join(td, "DOCUMENTO_TECNICO.docx")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), "--report", md_p, "--report-docx", docx_p, "--technical-docx", tech_p],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        cli_lines = [
            "$ python main.py --report REPORTE.md --report-docx REPORTE.docx --technical-docx DOC.docx",
            f"Exit code: {proc.returncode} (Generacion pura Python sin Pandoc)",
        ] + (proc.stdout or "").splitlines()[:6] + ["Artefactos generados:"] + [
            f"  - {fn:<35} ({os.path.getsize(os.path.join(td, fn)):>7,} bytes)"
            for fn in sorted(os.listdir(td)) if os.path.isfile(os.path.join(td, fn))
        ]
    shots["04_2_cli_reportes"] = _render_terminal_card(
        "4.2 Generacion Automatica CLI (main.py)", cli_lines, "04_2_cli_reportes.png"
    )

    # 04_3. Suite de pruebas (pytest real)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--no-header", "-p", "no:cacheprovider", "tests"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    out = [l.replace("tests/", "") for l in (proc.stdout + "\n" + proc.stderr).strip().splitlines() if l.strip()]
    summary = out[-1] if out else ""
    n_tests = summary.split(" passed")[0].split()[-1] if " passed" in summary else "?"
    body = [re.sub(r"\s*\[\s*\d+%\]", "", re.sub(r"::Test\w+", "", l)) for l in out if "PASSED" in l or "FAILED" in l or "ERROR" in l]
    shown = body[:11] + ["  ... (pruebas intermedias omitidas) ..."] + body[-7:] + [summary.strip("= ")]
    shots["04_3_tests"] = _render_terminal_card(
        f"4.3 Suite de {n_tests} Pruebas Unitarias (pytest)", ["$ python -m pytest -v"] + shown, "04_3_tests.png"
    )


def capture_all_screenshots() -> Dict[str, str]:
    data_path = os.path.join(ROOT, "data", "DataSetBicentenario.xlsx")
    shots: Dict[str, str] = {}
    _capture_gui(shots, data_path)
    if "--gui-only" not in sys.argv:
        _capture_terminals(shots, data_path)
    return shots


if __name__ == "__main__":
    capture_all_screenshots()
