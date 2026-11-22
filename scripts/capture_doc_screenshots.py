"""Generador reproducible de capturas de pantalla para la documentación técnica.

Produce 24 capturas en `docs/screenshots/` combinando:
- Vistas globales de ventana (1280x740)
- Recortes enfocados de paneles/widgets para máxima legibilidad en 2 columnas (3.45 in)
- Tarjetas terminales compactas de ejecución real (CSV, CLI y 41 pruebas unitarias)
"""

import ctypes
from ctypes import wintypes
import os
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


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _capture_hwnd(hwnd: int, w: int, h: int) -> Image.Image:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    hwnd_dc = user32.GetWindowDC(hwnd)
    mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    save_bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mfc_dc, save_bitmap)

    res = user32.PrintWindow(hwnd, mfc_dc, 2)
    if res == 0:
        user32.PrintWindow(hwnd, mfc_dc, 0)

    bmi = _BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mfc_dc, save_bitmap, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)

    gdi32.DeleteObject(save_bitmap)
    gdi32.DeleteDC(mfc_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    return img


def _pause_app_playback(app) -> None:
    if hasattr(app, "is_playing"):
        app.is_playing = False
    if hasattr(app, "_play_after_id") and app._play_after_id is not None:
        try:
            app.after_cancel(app._play_after_id)
        except Exception:
            pass
        app._play_after_id = None
    if hasattr(app, "_pulse_after_id") and app._pulse_after_id is not None:
        try:
            app.after_cancel(app._pulse_after_id)
        except Exception:
            pass
        app._pulse_after_id = None


def _goto_step(app, target_min: float) -> None:
    _pause_app_playback(app)
    if hasattr(app, "pause"):
        app.pause()
    if not app.result or not app.result.snapshots:
        return
    best_i = 0
    best_d = 1e9
    for idx, snap in enumerate(app.result.snapshots):
        d = abs(snap.time_min - target_min)
        if d < best_d:
            best_d = d
            best_i = idx
    app._set_step(best_i)
    app.update_idletasks()
    app.update()


def _set_scenario_and_run(app, scenario_idx_0_based: int, target_min: float = 35.0) -> None:
    from src.gui import theme as gui_theme

    if app.dataset and 0 <= scenario_idx_0_based < len(app.dataset.scenarios):
        sc = app.dataset.scenarios[scenario_idx_0_based]
        app.var_scenario.set(
            gui_theme.format_scenario_display(sc.scenario_id, sc.condition, sc.intensity_mm_h)
        )
    if hasattr(app, "run_simulation"):
        app.run_simulation(auto_play=False)
    _goto_step(app, target_min)


def _grab_window(win: tk.Tk, filename: str, wait: float = 0.30) -> str:
    win.update_idletasks()
    win.update()
    time.sleep(wait)
    win.update()
    w = win.winfo_width()
    h = win.winfo_height()
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
    path = os.path.join(SHOT_DIR, filename)
    _capture_hwnd(hwnd, w, h).save(path)
    print(f"Captured {filename} ({w}x{h})")
    return path


def _grab_widget_crop(win: tk.Tk, widget: tk.Misc, filename: str, wait: float = 0.30) -> str:
    win.update_idletasks()
    win.update()
    time.sleep(wait)
    win.update()
    ww = win.winfo_width()
    wh = win.winfo_height()
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
    full_img = _capture_hwnd(hwnd, ww, wh)

    rect = _RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    cx_off = win.winfo_rootx() - rect.left
    cy_off = win.winfo_rooty() - rect.top

    wx = widget.winfo_rootx() - win.winfo_rootx()
    wy = widget.winfo_rooty() - win.winfo_rooty()
    cw = widget.winfo_width()
    ch = widget.winfo_height()

    left = max(0, cx_off + wx)
    top = max(0, cy_off + wy)
    right = min(ww, left + cw)
    bottom = min(wh, top + ch)
    path = os.path.join(SHOT_DIR, filename)
    full_img.crop((left, top, right, bottom)).save(path)
    print(f"Captured crop {filename} ({right - left}x{bottom - top})")
    return path


def _render_terminal_card(title: str, lines: List[str], filename: str) -> str:
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 14)
        title_font = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
        title_font = font

    pad_x, pad_y = 18, 16
    line_h = 20
    w = 880
    h = 44 + len(lines) * line_h + pad_y * 2

    img = Image.new("RGB", (w, h), (22, 27, 34))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (w, 36)], fill=(33, 38, 45))
    draw.ellipse([(12, 11), (24, 23)], fill=(255, 95, 86))
    draw.ellipse([(32, 11), (44, 23)], fill=(255, 189, 46))
    draw.ellipse([(52, 11), (64, 23)], fill=(39, 201, 63))
    draw.text((78, 9), title, font=title_font, fill=(230, 237, 243))

    y = 44
    for line in lines:
        color = (201, 209, 217)
        if line.endswith("... ok") or "OK" in line or "passed" in line or "Generado" in line or "bytes)" in line:
            color = (126, 231, 135)
        elif line.startswith("$") or line.startswith(">"):
            color = (121, 192, 255)
        draw.text((pad_x, y), line[:98], font=font, fill=color)
        y += line_h

    path = os.path.join(SHOT_DIR, filename)
    img.save(path)
    print(f"Rendered terminal card {filename} ({w}x{h})")
    return path


def capture_all_screenshots() -> Dict[str, str]:
    from src.gui.app import BicentenarioSewerApp
    from src.io.data_loader import export_to_csv_dir, load_dataset

    data_path = os.path.join(ROOT, "data", "DataSetBicentenario.xlsx")
    app = BicentenarioSewerApp(initial_data_path=data_path)
    app.geometry("1280x740+30+20")
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    app.attributes("-topmost", False)
    time.sleep(0.45)
    _pause_app_playback(app)

    shots: Dict[str, str] = {}

    # 00. Vista general sistema (Esc. 3, t = 35 min)
    _set_scenario_and_run(app, 2, target_min=35.0)
    shots["00_vista_general"] = _grab_window(app, "00_vista_general.png")

    # 01_1. Sub-pasos continuos con PriorityQueue (Esc. 3, t = 35 min)
    shots["01_1_subpasos_transit"] = _grab_widget_crop(app, app.center_panel, "01_1_subpasos_transit.png")

    # 01_2. Almacenamiento finito 4.0 m3 + rebose superficial (Esc. 5, t = 45 min)
    _set_scenario_and_run(app, 4, target_min=45.0)
    snap = app.result.snapshots[app.current_step]
    flood_node = max(snap.node_states.items(), key=lambda kv: kv[1].surface_flooding_m3)[0]
    app._on_node_selected(flood_node)
    app.notebook.select(0)
    _goto_step(app, 45.0)
    shots["01_2_almacenamiento_rebose"] = _grab_widget_crop(app, app.right_panel, "01_2_almacenamiento_rebose.png")

    # 01_3a. Intervención en vivo (P29 al 80 % en t = 40 min)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app._on_pipe_selected("P29")
    app.var_obstruction_pct.set(80.0)
    app._action_apply_intervention()
    _goto_step(app, 40.0)
    app.notebook.select(0)
    shots["01_3a_intervencion_mapa"] = _grab_widget_crop(app, app.network_canvas, "01_3a_intervencion_mapa.png")

    # 01_3b. Hidrograma comparativo Antes vs Después
    app.notebook.select(2)
    app.temporal_charts.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["01_3b_antes_despues"] = _grab_widget_crop(app, app.temporal_charts, "01_3b_antes_despues.png", wait=0.40)

    app._action_restore_all_interventions()
    app.notebook.select(0)

    # 01_4. Reglas configurables desde la GUI (recorte panel Controles)
    from src.gui import theme as gui_theme
    app.var_split_rule_es.set(gui_theme.SPLIT_RULE_TO_ES["equal"])
    app.var_source_dist_es.set(gui_theme.SOURCE_DIST_TO_ES["equal"])
    app._apply_preset(2.5, 0.003)
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)
    shots["01_4_reglas_gui"] = _grab_widget_crop(app, app.left_panel, "01_4_reglas_gui.png")

    app._apply_preset(100.0, 0.0)
    app.var_split_rule_es.set(gui_theme.SPLIT_RULE_TO_ES["proportional"])
    app.var_source_dist_es.set(gui_theme.SOURCE_DIST_TO_ES["capacity"])
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)

    # 02_1a & 02_1b. Animación BFS (Queue) y DFS (Stack)
    app._switch_rail_tab("trav")
    app._run_traversal("BFS")
    for _ in range(8):
        app._step_traversal_anim()
    shots["02_1a_bfs_queue"] = _grab_window(app, "02_1a_bfs_queue.png")

    app._run_traversal("DFS")
    for _ in range(10):
        app._step_traversal_anim()
    shots["02_1b_dfs_stack"] = _grab_window(app, "02_1b_dfs_stack.png")

    app._stop_traversal_anim(clear_canvas=True)
    app._switch_rail_tab("sim")

    # 02_2. Trazado Aguas arriba + Aislar cuenca
    app._on_node_selected("K")
    app._action_toggle_inspector_trace("upstream")
    app._action_toggle_basin_isolation()
    _goto_step(app, 35.0)
    shots["02_2_aguas_arriba_aislar"] = _grab_window(app, "02_2_aguas_arriba_aislar.png")
    app._clear_highlights()

    # 02_3. Detección de nodos desconectados (P29 al 100 % en t = 40 min)
    app._on_pipe_selected("P29")
    app.var_obstruction_pct.set(100.0)
    app._action_apply_intervention()
    _goto_step(app, 40.0)
    shots["02_3_nodos_desconectados"] = _grab_window(app, "02_3_nodos_desconectados.png")
    app._action_restore_all_interventions()

    # 02_4. Composición por fuente aportante (Nodo 30 en Inspector)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app._on_node_selected("30")
    app.notebook.select(0)
    _goto_step(app, 40.0)
    shots["02_4_composicion_fuentes"] = _grab_widget_crop(app, app.right_panel, "02_4_composicion_fuentes.png")

    # 02_5. Persistencia de sobrecarga (Tuberías Críticas en Esc. 5)
    _set_scenario_and_run(app, 4, target_min=45.0)
    app._set_map_mode("overload")
    app.notebook.select(1)
    shots["02_5_persistencia_sobrecarga"] = _grab_widget_crop(app, app.right_panel, "02_5_persistencia_sobrecarga.png")
    app.notebook.select(0)

    # 03_1a, b, c. 3 Modos cartográficos en Esc. 5
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    shots["03_1a_modo_instantaneo"] = _grab_window(app, "03_1a_modo_instantaneo.png")

    app._set_map_mode("peak")
    shots["03_1b_modo_pico"] = _grab_window(app, "03_1b_modo_pico.png")

    app._set_map_mode("overload")
    shots["03_1c_modo_sobrecarga"] = _grab_window(app, "03_1c_modo_sobrecarga.png")

    # 03_2. NetworkCanvas avanzado (zoom en confluencia 30-D-G-31 con rebose en t = 45 min)
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    cw = app.network_canvas.winfo_width()
    ch = app.network_canvas.winfo_height()
    app.network_canvas._zoom_at(cw * 0.38, ch * 0.65, 1.85)
    shots["03_2_canvas_zoom_rebose"] = _grab_widget_crop(app, app.network_canvas, "03_2_canvas_zoom_rebose.png")
    app.network_canvas.reset_view()

    # 03_3a & 03_3b. Gráficas avanzadas (Hidrograma twinx + Perfil longitudinal)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app.notebook.select(2)
    app.temporal_charts.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["03_3a_hidrograma_twinx"] = _grab_widget_crop(app, app.temporal_charts, "03_3a_hidrograma_twinx.png", wait=0.40)
    app.temporal_charts.set_subtab("profile")
    _goto_step(app, 40.0)
    shots["03_3b_perfil_longitudinal"] = _grab_widget_crop(app, app.temporal_charts, "03_3b_perfil_longitudinal.png", wait=0.40)
    app.notebook.select(0)

    # 03_4. Recorrido Guiado (Esc. 5, parada 2)
    _set_scenario_and_run(app, 4, target_min=45.0)
    app.toggle_guided_tour()
    app._go_tour_stop(1, animate_cam=False)
    shots["03_4_recorrido_guiado"] = _grab_window(app, "03_4_recorrido_guiado.png", wait=0.45)
    app._close_guided_tour(reset_view=True)

    # 03_5a. Comparación 5 escenarios
    app.notebook.select(3)
    app._action_compare_scenarios()
    shots["03_5a_comparacion_escenarios"] = _grab_window(app, "03_5a_comparacion_escenarios.png", wait=0.45)

    # 03_5b. UI responsiva modo compacto
    app.geometry("900x700+30+20")
    app.notebook.select(0)
    shots["03_5b_ui_compacta"] = _grab_window(app, "03_5b_ui_compacta.png", wait=0.40)

    app.destroy()

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
        proc_cli = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), "--report", md_p, "--report-docx", docx_p, "--technical-docx", tech_p],
            cwd=ROOT, capture_output=True, text=True, timeout=90,
        )
        cli_lines = [
            "$ python main.py --report REPORTE.md --report-docx REPORTE.docx --technical-docx DOC.docx",
            f"Exit code: {proc_cli.returncode} (Generacion pura Python sin Pandoc)",
        ] + [l for l in (proc_cli.stdout or "").splitlines()[:6]] + [
            "Artefactos generados:"
        ] + [
            f"  - {fn:<35} ({os.path.getsize(os.path.join(td, fn)):>7,} bytes)"
            for fn in sorted(os.listdir(td)) if os.path.isfile(os.path.join(td, fn))
        ]
    shots["04_2_cli_reportes"] = _render_terminal_card(
        "4.2 Generacion Automatica CLI (main.py)", cli_lines, "04_2_cli_reportes.png"
    )

    # 04_3. Suite de 43 pruebas unitarias
    proc_test = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, capture_output=True, text=True, timeout=150,
    )
    test_lines = (proc_test.stdout + "\n" + proc_test.stderr).strip().splitlines()
    if len(test_lines) > 22:
        shown = test_lines[:12] + ["  ... (pruebas intermedias omitidas) ..."] + test_lines[-8:]
    else:
        shown = test_lines
    shots["04_3_tests_41"] = _render_terminal_card(
        "4.3 Suite de 43 Pruebas Unitarias (unittest)",
        ["$ python -m unittest discover -s tests -v"] + shown,
        "04_3_tests_41.png",
    )

    return shots


if __name__ == "__main__":
    capture_all_screenshots()
