"""Cargador y validador unificado de la red desde Excel (.xlsx) o archivos CSV."""

import csv
from dataclasses import dataclass
import math
import os
from typing import Dict, List, Optional, Tuple
import openpyxl

from src.data_structures import DirectedGraph, HashTable, ManholeNode, PipeEdge, Queue


class DataLoadError(ValueError):
    """Error de formato o validación al cargar los archivos de entrada."""


@dataclass(frozen=True)
class DrainageBasin:
    runoff_coefficient_c: float
    area_ha: float


@dataclass(frozen=True)
class PrecipitationScenario:
    scenario_id: int
    intensity_mm_h: float
    condition: str

    @property
    def display_name(self) -> str:
        return f"Escenario {self.scenario_id}: {self.condition} ({self.intensity_mm_h:.0f} mm/h)"


@dataclass
class NetworkDataset:
    graph: DirectedGraph
    basin: DrainageBasin
    scenarios: List[PrecipitationScenario]
    source_path: str


# Coordenadas esquemáticas basadas en Anexo 2 (Grafo Dirigido) de Ciudad Bicentenario.
DEFAULT_NODE_COORDS: Dict[str, Tuple[float, float, str]] = {
    "6": (0.48, 0.045, "6 (S)"), "Q": (0.37, 0.085, "Q"), "R": (0.60, 0.085, "R"), "O": (0.37, 0.165, "O"), "P": (0.60, 0.165, "P"),
    "5": (0.37, 0.245, "5"), "N": (0.48, 0.245, "N"), "7": (0.60, 0.245, "7"), "8": (0.76, 0.245, "8"), "9": (0.92, 0.245, "9 (S)"),
    "26": (0.37, 0.325, "26"), "25": (0.48, 0.325, "25"), "M": (0.60, 0.325, "M"), "24": (0.37, 0.405, "24"), "J": (0.48, 0.405, "J"),
    "23": (0.60, 0.405, "23"), "K": (0.76, 0.405, "K"), "L": (0.92, 0.405, "L"), "G": (0.28, 0.485, "G"), "H": (0.48, 0.485, "H"),
    "I": (0.60, 0.485, "I"), "3": (0.38, 0.565, "3"), "F": (0.48, 0.565, "F"), "12": (0.60, 0.565, "12"), "11": (0.76, 0.565, "11"),
    "10": (0.92, 0.565, "10"), "31": (0.06, 0.645, "31 (PTAR)"), "29": (0.17, 0.645, "29"), "30": (0.28, 0.645, "30"), "D": (0.38, 0.645, "D"),
    "E": (0.60, 0.645, "E"), "15": (0.92, 0.690, "15"), "22": (0.60, 0.720, "22"), "C": (0.17, 0.740, "C"), "13": (0.48, 0.795, "13"),
    "21": (0.60, 0.795, "21"), "14": (0.76, 0.795, "14"), "16": (0.92, 0.815, "16"), "1": (0.17, 0.855, "1 (S)"), "27": (0.28, 0.855, "27 (S)"),
    "A": (0.48, 0.870, "A"), "B": (0.60, 0.870, "B"), "19": (0.48, 0.945, "19 (S)"), "20": (0.60, 0.945, "20 (S)"), "18": (0.76, 0.945, "18 (S)"),
    "17": (0.92, 0.945, "17 (S)"),
}
_PIPE_NUM_COLS = ("diameter_in", "diameter_m", "manning_n", "slope", "q_max_m3s", "length_m")
_EXCEL_PIPE_DEFAULTS = {"from_node": 1, "to_node": 2, "diameter_in": 3, "diameter_m": 4, "manning_n": 5, "slope": 6, "q_max_m3s": 7, "pipe_id": 9, "length_m": 10, "note": 11}
_EXCEL_PIPE_ALIASES = {
    "from(i)": "from_node", "from": "from_node", "from_node": "from_node", "to(i)": "to_node", "to": "to_node", "to_node": "to_node",
    "⌀ (in)": "diameter_in", "diameter (in)": "diameter_in", "diameter_in": "diameter_in", "⌀ (m)": "diameter_m", "diameter (m)": "diameter_m", "diameter_m": "diameter_m",
    "n": "manning_n", "manning_n": "manning_n", "s": "slope", "slope": "slope", "q": "q_max_m3s", "q_max": "q_max_m3s", "q_max_m3s": "q_max_m3s",
    "pipe": "pipe_id", "pipe_id": "pipe_id", "lenght (m)": "length_m", "length (m)": "length_m", "length_m": "length_m", "note": "note", "nota": "note",
}
_RawPipeRow = Tuple[str, str, str, object, object, object, object, object, object, str, str]


def _parse_float(raw: object, field: str, ctx: str) -> float:
    if raw is None or isinstance(raw, bool):
        raise DataLoadError(f"Valor nulo o inválido en '{field}' ({ctx}).")
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        text = str(raw).strip()
        if text.startswith("="):
            raise DataLoadError(f"Fórmula sin valor cacheado ('{text}') en '{field}' ({ctx}).")
        try:
            val = float(text.replace("mm/h", "").strip())
        except ValueError as exc:
            raise DataLoadError(f"Valor numérico inválido '{raw}' en '{field}' ({ctx}).") from exc
    if not math.isfinite(val):
        raise DataLoadError(f"Valor no finito en '{field}' ({ctx}).")
    return val


def _is_missing_or_formula(raw: object) -> bool:
    return raw is None or (not isinstance(raw, (int, float)) and ((t := str(raw).strip()) == "" or t.startswith("=")))


def _read_csv_rows(path: str) -> List[Tuple[int, dict]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [
            (idx, row) for idx, row in enumerate(csv.DictReader(f), start=2)
            if any(any(str(x or "").strip() for x in (v or [])) if k is None else str(v or "").strip() for k, v in row.items())
        ]


def _load_coords_csv(path: str) -> Dict[str, Tuple[float, float, str]]:
    if not os.path.isfile(path):
        return {}
    coords: Dict[str, Tuple[float, float, str]] = {}
    for idx, row in _read_csv_rows(path):
        if nid := (row.get("node_id") or "").strip():
            ctx = f"node_coords.csv fila {idx}"
            coords[nid] = (_parse_float(row.get("x"), "x", ctx), _parse_float(row.get("y"), "y", ctx), (row.get("label") or nid).strip())
    return coords


def _kahn_topological_sort(graph: DirectedGraph) -> Tuple[List[str], bool]:
    """Ordenamiento topológico de Kahn con HashTable y Queue propias."""
    in_deg: HashTable[str, int] = HashTable(64)
    queue: Queue[str] = Queue()
    for nid in graph.node_ids():
        deg = graph.in_degree(nid)
        in_deg.put(nid, deg)
        if deg == 0:
            queue.enqueue(nid)
    order: List[str] = []
    while not queue.is_empty():
        u = queue.dequeue()
        order.append(u)
        for edge in graph.outgoing_pipes(u):
            new_deg = in_deg[edge.to_node] - 1
            in_deg.put(edge.to_node, new_deg)
            if new_deg == 0:
                queue.enqueue(edge.to_node)
    return order, len(order) == graph.num_nodes


def _assign_coordinates(graph: DirectedGraph, extra_coords: Dict[str, Tuple[float, float, str]], topo_order: List[str]) -> None:
    is_bicentenario = "31" in set(graph.sink_ids()) and graph.num_nodes > 0 and (
        sum(1 for nid in graph.node_ids() if nid in DEFAULT_NODE_COORDS) / graph.num_nodes >= 0.8
    )
    coords = dict(DEFAULT_NODE_COORDS) if is_bicentenario else {}
    coords.update(extra_coords)
    missing = False
    for node in graph.nodes():
        if node.node_id in coords:
            node.x, node.y, node.label = coords[node.node_id]
        else:
            missing = True
            if node.node_type in ("source", "sink"):
                node.label = f"{node.node_id} ({'S' if node.node_type == 'source' else 'T'})"
    if not missing:
        return
    layer_of = {nid: 0 for nid in topo_order}
    for u in topo_order:
        for edge in graph.outgoing_pipes(u):
            layer_of[edge.to_node] = max(layer_of[edge.to_node], layer_of[u] + 1)
    max_layer = max(layer_of.values(), default=1) or 1
    by_layer: Dict[int, List[str]] = {}
    for nid in topo_order:
        by_layer.setdefault(layer_of[nid], []).append(nid)
    for layer, nids in by_layer.items():
        for i, nid in enumerate(nids):
            if (node := graph.get_node(nid)) is not None and nid not in coords:
                node.x, node.y = 0.1 + 0.8 * (layer / max_layer), (i + 1) / (len(nids) + 1)


def _build_validated_dataset(
    sources: List[str], sinks: List[str], pipe_rows: List[_RawPipeRow], basin: DrainageBasin,
    scenarios: List[PrecipitationScenario], extra_coords: Dict[str, Tuple[float, float, str]], source_path: str,
) -> NetworkDataset:
    """Constructor y validador único compartido entre carga Excel y CSV."""
    src_set, snk_set = set(sources), set(sinks)
    if not sources or not sinks or not pipe_rows:
        raise DataLoadError("La red debe incluir al menos una fuente, un sumidero y una tubería.")
    if len(src_set) != len(sources) or len(snk_set) != len(sinks):
        raise DataLoadError("Existen identificadores duplicados en Source(s) o Sink(s).")
    if overlap := src_set & snk_set:
        raise DataLoadError(f"Nodos simultáneamente fuente y sumidero: {', '.join(sorted(overlap))}.")

    graph = DirectedGraph()
    for s in sources:
        graph.add_node(ManholeNode(node_id=s, node_type="source"))
    for k in sinks:
        graph.add_node(ManholeNode(node_id=k, node_type="sink"))
    for pid, u, v, raw_d_in, raw_d_m, raw_n, raw_s, raw_q, raw_len, note, ctx in pipe_rows:
        d_m = _parse_float(raw_d_m, "diameter_m", ctx)
        d_in = round(d_m / 0.0254, 4) if _is_missing_or_formula(raw_d_in) else round(_parse_float(raw_d_in, "diameter_in", ctx), 4)
        if d_m > 0.0 and d_in > 0.0 and abs(d_m - d_in * 0.0254) / d_m > 0.02:
            raise DataLoadError(f"Inconsistencia de unidades diámetro {d_in} in vs {d_m} m en {ctx}.")
        manning_n, slope = _parse_float(raw_n, "manning_n", ctx), _parse_float(raw_s, "slope", ctx)
        if _is_missing_or_formula(raw_q):
            if min(d_m, manning_n, slope) <= 0.0:
                raise DataLoadError(f"Parámetros geométricos/hidráulicos <= 0 en {ctx}.")
            q_max = (1.0 / manning_n) * (math.pi * d_m * d_m / 4.0) * ((d_m / 4.0) ** (2.0 / 3.0)) * (slope ** 0.5)
        else:
            q_max = _parse_float(raw_q, "q_max_m3s", ctx)
        length_m = _parse_float(raw_len, "length_m", ctx)
        if min(d_in, d_m, manning_n, slope, q_max, length_m) <= 0.0:
            raise DataLoadError(f"La tubería {pid} tiene parámetros geométricos/hidráulicos <= 0 ({ctx}).")
        try:
            graph.add_pipe(PipeEdge(pid, u, v, d_in, d_m, manning_n, slope, q_max, length_m, note))
        except ValueError as exc:
            raise DataLoadError(str(exc)) from exc

    if not (0.0 < basin.runoff_coefficient_c <= 1.0) or basin.area_ha <= 0.0:
        raise DataLoadError(f"Cuenca inválida (C={basin.runoff_coefficient_c}, A={basin.area_ha} ha).")
    if not scenarios:
        raise DataLoadError("No se encontraron escenarios de precipitación.")
    seen_sids = set()
    for sc in scenarios:
        if sc.intensity_mm_h < 0.0 or sc.scenario_id in seen_sids:
            raise DataLoadError(f"Escenario inválido o duplicado: ID={sc.scenario_id}, I={sc.intensity_mm_h}.")
        seen_sids.add(sc.scenario_id)

    topo_order, is_dag = _kahn_topological_sort(graph)
    if not is_dag:
        raise DataLoadError("La red contiene ciclos dirigidos; se esperaba un grafo acíclico dirigido (DAG).")
    dead_ends = [nid for nid in graph.node_ids() if (n := graph.get_node(nid)) is not None and n.node_type != "sink" and graph.out_degree(nid) == 0]
    if dead_ends:
        raise DataLoadError(f"Nodos no sumidero sin salida (dead-end): {', '.join(dead_ends)}.")
    reachable: HashTable[str, bool] = HashTable(64)
    q_rev: Queue[str] = Queue()
    for sid in graph.sink_ids():
        reachable.put(sid, True)
        q_rev.enqueue(sid)
    while not q_rev.is_empty():
        for edge in graph.incoming_pipes(q_rev.dequeue()):
            if not reachable.contains(edge.from_node):
                reachable.put(edge.from_node, True)
                q_rev.enqueue(edge.from_node)
    if isolated := [nid for nid in graph.node_ids() if not reachable.contains(nid)]:
        raise DataLoadError(f"Nodos aislados sin ruta hacia sumidero: {', '.join(sorted(isolated))}.")

    _assign_coordinates(graph, extra_coords, topo_order)
    return NetworkDataset(graph=graph, basin=basin, scenarios=scenarios, source_path=os.path.abspath(source_path))


def load_from_excel(xlsx_path: str, coords_csv_path: Optional[str] = None) -> NetworkDataset:
    """Carga y valida el conjunto de datos desde un archivo .xlsx."""
    if not os.path.isfile(xlsx_path):
        raise DataLoadError(f"No se encontró el archivo Excel: {xlsx_path}")
    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    except Exception as exc:
        raise DataLoadError(f"No se pudo abrir el archivo Excel '{xlsx_path}': {exc}") from exc
    try:
        for sheet in ("Source(s)", "Sink(s)", "Pipe(s)", "Drainage Basin", "Precipitation Scenarios"):
            if sheet not in wb.sheetnames:
                raise DataLoadError(f"Falta la hoja obligatoria '{sheet}' en {xlsx_path}.")
        col1 = lambda ws: [str(v).strip() for r in range(2, ws.max_row + 1) if (v := ws.cell(r, 1).value) is not None and str(v).strip()]
        sources, sinks = col1(wb["Source(s)"]), col1(wb["Sink(s)"])
        ws_p = wb["Pipe(s)"]
        pc = dict(_EXCEL_PIPE_DEFAULTS)
        for c in range(1, max(ws_p.max_column or 11, 11) + 1):
            if (hdr := ws_p.cell(1, c).value) is not None and (k := " ".join(str(hdr).strip().lower().split())) in _EXCEL_PIPE_ALIASES:
                pc[_EXCEL_PIPE_ALIASES[k]] = c
        pipe_rows: List[_RawPipeRow] = []
        for r in range(2, ws_p.max_row + 1):
            pid = ws_p.cell(r, pc["pipe_id"]).value
            if pid is None or not str(pid).strip():
                continue
            u, v = ws_p.cell(r, pc["from_node"]).value, ws_p.cell(r, pc["to_node"]).value
            if u is None or v is None:
                raise DataLoadError(f"Conexión incompleta en Pipe(s) fila {r}.")
            pipe_rows.append((str(pid).strip(), str(u).strip(), str(v).strip(), *(ws_p.cell(r, pc[k]).value for k in _PIPE_NUM_COLS), str(ws_p.cell(r, pc["note"]).value or "").strip(), f"Pipe(s) fila {r}"))
        ws_b, ws_s = wb["Drainage Basin"], wb["Precipitation Scenarios"]
        basin = DrainageBasin(_parse_float(ws_b.cell(2, 1).value, "C", "Drainage Basin fila 2"), _parse_float(ws_b.cell(2, 2).value, "A", "Drainage Basin fila 2"))
        scenarios = [
            PrecipitationScenario(sid := int(_parse_float(sr, "Scenario", f"Precipitation Scenarios fila {r}")), _parse_float(ws_s.cell(r, 2).value, "Intensity", f"Precipitation Scenarios fila {r}"), str(ws_s.cell(r, 3).value or f"Escenario {sid}").strip())
            for r in range(2, ws_s.max_row + 1) if (sr := ws_s.cell(r, 1).value) is not None and str(sr).strip()
        ]
    finally:
        wb.close()
    return _build_validated_dataset(sources, sinks, pipe_rows, basin, scenarios, _load_coords_csv(coords_csv_path) if coords_csv_path else {}, xlsx_path)


def load_from_csv_dir(csv_dir: str) -> NetworkDataset:
    """Carga y valida el conjunto de datos desde una carpeta con archivos CSV."""
    if not os.path.isdir(csv_dir):
        raise DataLoadError(f"No se encontró la carpeta CSV: {csv_dir}")
    for fname in ("sources.csv", "sinks.csv", "pipes.csv", "drainage_basin.csv", "precipitation_scenarios.csv"):
        if not os.path.isfile(os.path.join(csv_dir, fname)):
            raise DataLoadError(f"Falta el archivo CSV obligatorio '{fname}' en {csv_dir}.")
    sources = [nid for _, r in _read_csv_rows(os.path.join(csv_dir, "sources.csv")) if (nid := (r.get("node_id") or "").strip())]
    sinks = [nid for _, r in _read_csv_rows(os.path.join(csv_dir, "sinks.csv")) if (nid := (r.get("node_id") or "").strip())]
    pipe_rows: List[_RawPipeRow] = []
    for idx, row in _read_csv_rows(os.path.join(csv_dir, "pipes.csv")):
        ctx = f"pipes.csv fila {idx}"
        pid, u, v = (row.get("pipe_id") or "").strip(), (row.get("from_node") or "").strip(), (row.get("to_node") or "").strip()
        if not pid or not u or not v:
            raise DataLoadError(f"Identificador o conexión faltante en {ctx}.")
        pipe_rows.append((pid, u, v, *(row.get(k) for k in _PIPE_NUM_COLS), (row.get("note") or "").strip(), ctx))
    b_rows = _read_csv_rows(os.path.join(csv_dir, "drainage_basin.csv"))
    if not b_rows:
        raise DataLoadError("drainage_basin.csv está vacío.")
    basin = DrainageBasin(_parse_float(b_rows[0][1].get("runoff_coefficient_c"), "runoff_coefficient_c", "drainage_basin.csv"), _parse_float(b_rows[0][1].get("area_ha"), "area_ha", "drainage_basin.csv"))
    scenarios = [
        PrecipitationScenario(int(_parse_float(r.get("scenario_id"), "scenario_id", f"precipitation_scenarios.csv fila {i}")), _parse_float(r.get("intensity_mm_h"), "intensity_mm_h", f"precipitation_scenarios.csv fila {i}"), (r.get("condition") or f"Escenario {i - 1}").strip())
        for i, r in _read_csv_rows(os.path.join(csv_dir, "precipitation_scenarios.csv"))
    ]
    return _build_validated_dataset(sources, sinks, pipe_rows, basin, scenarios, _load_coords_csv(os.path.join(csv_dir, "node_coords.csv")), csv_dir)


def load_dataset(path: str) -> NetworkDataset:
    """Detecta automáticamente si path es un archivo .xlsx o una carpeta CSV."""
    if os.path.isdir(path):
        return load_from_csv_dir(path)
    if path.lower().endswith(".xlsx"):
        default_coords = os.path.join(os.path.dirname(path), "csv", "node_coords.csv")
        return load_from_excel(path, default_coords if os.path.isfile(default_coords) else None)
    raise DataLoadError(f"Formato no soportado '{path}'. Seleccione un archivo .xlsx o una carpeta CSV.")


def export_to_csv_dir(dataset: NetworkDataset, out_dir: str) -> None:
    """Exporta un NetworkDataset a archivos CSV normalizados."""
    os.makedirs(out_dir, exist_ok=True)
    tables = {
        "sources.csv": [["node_id"], *([nid] for nid in dataset.graph.source_ids())],
        "sinks.csv": [["node_id"], *([nid] for nid in dataset.graph.sink_ids())],
        "pipes.csv": [["pipe_id", "from_node", "to_node", "diameter_in", "diameter_m", "manning_n", "slope", "q_max_m3s", "length_m", "note"], *([p.pipe_id, p.from_node, p.to_node, round(p.diameter_in, 4), p.diameter_m, p.manning_n, p.slope, f"{p.q_max_m3s:.12g}", p.length_m, p.note] for p in dataset.graph.pipes())],
        "drainage_basin.csv": [["runoff_coefficient_c", "area_ha"], [dataset.basin.runoff_coefficient_c, dataset.basin.area_ha]],
        "precipitation_scenarios.csv": [["scenario_id", "intensity_mm_h", "condition"], *([sc.scenario_id, sc.intensity_mm_h, sc.condition] for sc in dataset.scenarios)],
        "node_coords.csv": [["node_id", "x", "y", "label"], *([n.node_id, round(n.x, 4), round(n.y, 4), n.label] for n in dataset.graph.nodes())],
    }
    for fname, rows in tables.items():
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
