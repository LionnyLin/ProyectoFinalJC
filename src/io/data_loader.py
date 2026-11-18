"""Cargador y validador de la red desde DataSetBicentenario.xlsx o archivos CSV."""

import csv
from dataclasses import dataclass
import math
import os
from typing import Dict, List, Optional, Tuple
import openpyxl

from src.algorithms.traversals import topological_sort
from src.data_structures import DirectedGraph, ManholeNode, PipeEdge


class DataLoadError(ValueError):
    """Error de formato o validación al cargar los archivos de entrada."""


@dataclass(frozen=True)
class DrainageBasin:
    """Parámetros de la cuenca de drenaje (Método Racional)."""

    runoff_coefficient_c: float
    area_ha: float


@dataclass(frozen=True)
class PrecipitationScenario:
    """Escenario de precipitación suministrado."""

    scenario_id: int
    intensity_mm_h: float
    condition: str

    @property
    def display_name(self) -> str:
        return f"Escenario {self.scenario_id}: {self.condition} ({self.intensity_mm_h:.0f} mm/h)"


@dataclass
class NetworkDataset:
    """Conjunto completo validado de grafo, cuenca y escenarios de lluvia."""

    graph: DirectedGraph
    basin: DrainageBasin
    scenarios: List[PrecipitationScenario]
    source_path: str


# Coordenadas esquemáticas basadas en Anexo 2 (Grafo Dirigido) de la guía.
DEFAULT_NODE_COORDS: Dict[str, Tuple[float, float, str]] = {
    "6": (0.46, 0.06, "6 (S)"),
    "Q": (0.36, 0.09, "Q"),
    "R": (0.56, 0.09, "R"),
    "O": (0.36, 0.15, "O"),
    "P": (0.56, 0.15, "P"),
    "5": (0.36, 0.22, "5"),
    "N": (0.46, 0.22, "N"),
    "7": (0.56, 0.22, "7"),
    "8": (0.74, 0.22, "8"),
    "9": (0.90, 0.22, "9 (S)"),
    "26": (0.36, 0.30, "26"),
    "25": (0.46, 0.30, "25"),
    "M": (0.56, 0.30, "M"),
    "24": (0.36, 0.38, "24"),
    "J": (0.46, 0.38, "J"),
    "23": (0.56, 0.38, "23"),
    "K": (0.74, 0.38, "K"),
    "L": (0.90, 0.38, "L"),
    "G": (0.29, 0.44, "G"),
    "H": (0.46, 0.44, "H"),
    "I": (0.56, 0.44, "I"),
    "3": (0.38, 0.50, "3"),
    "F": (0.46, 0.50, "F"),
    "12": (0.56, 0.50, "12"),
    "11": (0.74, 0.50, "11"),
    "10": (0.90, 0.50, "10"),
    "31": (0.08, 0.57, "31 (PTAR)"),
    "29": (0.19, 0.57, "29"),
    "30": (0.29, 0.57, "30"),
    "D": (0.38, 0.57, "D"),
    "E": (0.56, 0.57, "E"),
    "15": (0.90, 0.63, "15"),
    "C": (0.19, 0.67, "C"),
    "22": (0.56, 0.64, "22"),
    "13": (0.47, 0.73, "13"),
    "21": (0.56, 0.73, "21"),
    "14": (0.74, 0.73, "14"),
    "16": (0.90, 0.77, "16"),
    "1": (0.19, 0.79, "1 (S)"),
    "27": (0.29, 0.79, "27 (S)"),
    "A": (0.47, 0.82, "A"),
    "B": (0.56, 0.82, "B"),
    "19": (0.47, 0.92, "19 (S)"),
    "20": (0.56, 0.92, "20 (S)"),
    "18": (0.74, 0.92, "18 (S)"),
    "17": (0.90, 0.92, "17 (S)"),
}


def _parse_float(raw: object, field_name: str, row_ctx: str) -> float:
    if raw is None:
        raise DataLoadError(f"Valor nulo en '{field_name}' ({row_ctx}).")
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        text = str(raw).strip().lstrip("=")
        # Limpiar unidades si vienen adjuntas (ej. '10 mm/h')
        text = text.replace("mm/h", "").strip()
        try:
            val = float(text)
        except ValueError as exc:
            raise DataLoadError(
                f"Valor numérico inválido '{raw}' en '{field_name}' ({row_ctx})."
            ) from exc
    if math.isnan(val) or math.isinf(val):
        raise DataLoadError(f"Valor no finito en '{field_name}' ({row_ctx}).")
    return val


def _load_coords_csv(path: str) -> Dict[str, Tuple[float, float, str]]:
    coords: Dict[str, Tuple[float, float, str]] = {}
    if not os.path.isfile(path):
        return coords
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            nid = (row.get("node_id") or "").strip()
            if not nid:
                continue
            x = _parse_float(row.get("x"), "x", f"node_coords.csv fila {idx}")
            y = _parse_float(row.get("y"), "y", f"node_coords.csv fila {idx}")
            label = (row.get("label") or nid).strip()
            coords[nid] = (x, y, label)
    return coords


def _assign_missing_coordinates(
    graph: DirectedGraph,
    coords: Dict[str, Tuple[float, float, str]],
) -> None:
    """Asigna coordenadas desde mapa conocido o por capas topológicas para grafos nuevos."""
    missing = [n for n in graph.nodes() if n.node_id not in coords]
    for node in graph.nodes():
        if node.node_id in coords:
            x, y, label = coords[node.node_id]
            node.x = x
            node.y = y
            node.label = label
        elif node.node_type == "source":
            node.label = f"{node.node_id} (S)"
        elif node.node_type == "sink":
            node.label = f"{node.node_id} (T)"

    if not missing:
        return

    order, _ = topological_sort(graph)
    if len(order) != graph.num_nodes:
        order = graph.node_ids()

    layer_of: Dict[str, int] = {nid: 0 for nid in order}
    for u in order:
        for edge in graph.outgoing_pipes(u):
            layer_of[edge.to_node] = max(layer_of[edge.to_node], layer_of[u] + 1)

    max_layer = max(layer_of.values(), default=1) or 1
    by_layer: Dict[int, List[str]] = {}
    for nid in order:
        by_layer.setdefault(layer_of[nid], []).append(nid)

    for layer, nids in by_layer.items():
        count = len(nids)
        for i, nid in enumerate(nids):
            node = graph.get_node(nid)
            if node is not None and nid not in coords:
                node.x = 0.1 + 0.8 * (layer / max_layer)
                node.y = (i + 1) / (count + 1)


def _validate_graph_and_data(
    graph: DirectedGraph,
    basin: DrainageBasin,
    scenarios: List[PrecipitationScenario],
) -> None:
    if graph.num_nodes == 0 or graph.num_pipes == 0:
        raise DataLoadError("La red cargada no contiene nodos ni tuberías válidas.")
    if not graph.source_ids():
        raise DataLoadError("Debe existir al menos un nodo fuente en Source(s).")
    if not graph.sink_ids():
        raise DataLoadError("Debe existir al menos un nodo sumidero en Sink(s).")
    overlap = set(graph.source_ids()) & set(graph.sink_ids())
    if overlap:
        raise DataLoadError(
            f"Nodos declarados simultáneamente como fuente y sumidero: {', '.join(sorted(overlap))}."
        )
    if basin.runoff_coefficient_c <= 0.0 or basin.runoff_coefficient_c > 1.0:
        raise DataLoadError(
            f"Coeficiente de escorrentía C inválido: {basin.runoff_coefficient_c}."
        )
    if basin.area_ha <= 0.0:
        raise DataLoadError(f"Área de drenaje inválida: {basin.area_ha} ha.")
    if not scenarios:
        raise DataLoadError("No se encontraron escenarios de precipitación.")

    seen_sids = set()
    for sc in scenarios:
        if sc.intensity_mm_h < 0.0:
            raise DataLoadError(
                f"El escenario {sc.scenario_id} tiene intensidad negativa ({sc.intensity_mm_h})."
            )
        if sc.scenario_id in seen_sids:
            raise DataLoadError(f"Escenario duplicado con ID {sc.scenario_id}.")
        seen_sids.add(sc.scenario_id)

    for pipe in graph.pipes():
        if (
            pipe.diameter_in <= 0
            or pipe.diameter_m <= 0
            or pipe.manning_n <= 0
            or pipe.slope <= 0
            or pipe.q_max_m3s <= 0
            or pipe.length_m <= 0
        ):
            raise DataLoadError(
                f"La tubería {pipe.pipe_id} tiene parámetros geométricos/hidráulicos <= 0."
            )

    _, is_dag = topological_sort(graph)
    if not is_dag:
        raise DataLoadError(
            "La red contiene ciclos dirigidos; se esperaba un grafo acíclico dirigido (DAG)."
        )


def load_from_excel(
    xlsx_path: str,
    coords_csv_path: Optional[str] = None,
) -> NetworkDataset:
    """Carga y valida el conjunto de datos desde `DataSetBicentenario.xlsx`."""
    if not os.path.isfile(xlsx_path):
        raise DataLoadError(f"No se encontró el archivo Excel: {xlsx_path}")

    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    except Exception as exc:
        raise DataLoadError(f"No se pudo abrir el archivo Excel '{xlsx_path}': {exc}") from exc

    try:
        required_sheets = [
            "Source(s)",
            "Sink(s)",
            "Pipe(s)",
            "Drainage Basin",
            "Precipitation Scenarios",
        ]
        for sheet in required_sheets:
            if sheet not in wb.sheetnames:
                raise DataLoadError(f"Falta la hoja obligatoria '{sheet}' en {xlsx_path}.")

        sources: List[str] = []
        ws_src = wb["Source(s)"]
        for r in range(2, ws_src.max_row + 1):
            val = ws_src.cell(r, 1).value
            if val is not None and str(val).strip():
                sources.append(str(val).strip())

        sinks: List[str] = []
        ws_snk = wb["Sink(s)"]
        for r in range(2, ws_snk.max_row + 1):
            val = ws_snk.cell(r, 1).value
            if val is not None and str(val).strip():
                sinks.append(str(val).strip())

        overlap_src_snk = set(sources) & set(sinks)
        if overlap_src_snk:
            raise DataLoadError(
                f"Nodos declarados simultáneamente como fuente y sumidero: {', '.join(sorted(overlap_src_snk))}."
            )

        graph = DirectedGraph()
        for s in sources:
            graph.add_node(ManholeNode(node_id=s, node_type="source"))
        for k in sinks:
            graph.add_node(ManholeNode(node_id=k, node_type="sink"))

        ws_pipes = wb["Pipe(s)"]
        for r in range(2, ws_pipes.max_row + 1):
            from_val = ws_pipes.cell(r, 1).value
            to_val = ws_pipes.cell(r, 2).value
            pid_val = ws_pipes.cell(r, 9).value
            # Saltar filas resumen finales del Excel (ej. conteos o URLs)
            if pid_val is None or str(pid_val).strip() == "":
                continue
            if from_val is None or to_val is None:
                raise DataLoadError(f"Conexión incompleta en Pipe(s) fila {r}.")

            ctx = f"Pipe(s) fila {r}"
            d_m = _parse_float(ws_pipes.cell(r, 4).value, "⌀ (m)", ctx)
            raw_d_in = ws_pipes.cell(r, 3).value
            d_in = round(
                _parse_float(raw_d_in, "⌀ (in)", ctx)
                if raw_d_in is not None and not str(raw_d_in).startswith("=")
                else (d_m / 0.0254),
                4,
            )
            manning_n = _parse_float(ws_pipes.cell(r, 5).value, "n", ctx)
            slope = _parse_float(ws_pipes.cell(r, 6).value, "S", ctx)
            raw_q = ws_pipes.cell(r, 7).value
            if raw_q is not None and not str(raw_q).startswith("="):
                q_max = _parse_float(raw_q, "Q", ctx)
            else:
                # Fallback solo si el archivo Excel no tiene valores cacheados de fórmula
                if d_m <= 0.0 or manning_n <= 0.0 or slope <= 0.0:
                    raise DataLoadError(
                        f"Parámetros geométricos/hidráulicos <= 0 en {ctx}."
                    )
                area = math.pi * (d_m ** 2) / 4.0
                q_max = (1.0 / manning_n) * area * ((d_m / 4.0) ** (2.0 / 3.0)) * (slope ** 0.5)
            length_m = _parse_float(ws_pipes.cell(r, 10).value, "Lenght (m)", ctx)
            note = str(ws_pipes.cell(r, 11).value or "").strip()

            pipe = PipeEdge(
                pipe_id=str(pid_val).strip(),
                from_node=str(from_val).strip(),
                to_node=str(to_val).strip(),
                diameter_in=d_in,
                diameter_m=d_m,
                manning_n=manning_n,
                slope=slope,
                q_max_m3s=q_max,
                length_m=length_m,
                note=note,
            )
            try:
                graph.add_pipe(pipe)
            except ValueError as exc:
                raise DataLoadError(str(exc)) from exc

        ws_basin = wb["Drainage Basin"]
        c_val = _parse_float(ws_basin.cell(2, 1).value, "C", "Drainage Basin fila 2")
        a_val = _parse_float(ws_basin.cell(2, 2).value, "A", "Drainage Basin fila 2")
        basin = DrainageBasin(runoff_coefficient_c=c_val, area_ha=a_val)

        ws_scen = wb["Precipitation Scenarios"]
        scenarios: List[PrecipitationScenario] = []
        for r in range(2, ws_scen.max_row + 1):
            sid_raw = ws_scen.cell(r, 1).value
            if sid_raw is None:
                continue
            ctx = f"Precipitation Scenarios fila {r}"
            sid = int(_parse_float(sid_raw, "Scenario", ctx))
            intensity = _parse_float(ws_scen.cell(r, 2).value, "Intensity", ctx)
            condition = str(ws_scen.cell(r, 3).value or f"Escenario {sid}").strip()
            scenarios.append(PrecipitationScenario(sid, intensity, condition))
    finally:
        wb.close()

    coords = dict(DEFAULT_NODE_COORDS)
    if coords_csv_path:
        coords.update(_load_coords_csv(coords_csv_path))
    _assign_missing_coordinates(graph, coords)
    _validate_graph_and_data(graph, basin, scenarios)

    return NetworkDataset(
        graph=graph,
        basin=basin,
        scenarios=scenarios,
        source_path=os.path.abspath(xlsx_path),
    )


def load_from_csv_dir(csv_dir: str) -> NetworkDataset:
    """Carga y valida el conjunto de datos desde una carpeta con archivos CSV."""
    if not os.path.isdir(csv_dir):
        raise DataLoadError(f"No se encontró la carpeta CSV: {csv_dir}")

    required_files = [
        "sources.csv",
        "sinks.csv",
        "pipes.csv",
        "drainage_basin.csv",
        "precipitation_scenarios.csv",
    ]
    for fname in required_files:
        fpath = os.path.join(csv_dir, fname)
        if not os.path.isfile(fpath):
            raise DataLoadError(f"Falta el archivo CSV obligatorio '{fname}' en {csv_dir}.")

    graph = DirectedGraph()

    source_ids_seen = set()
    with open(os.path.join(csv_dir, "sources.csv"), "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            nid = (row.get("node_id") or "").strip()
            if nid:
                source_ids_seen.add(nid)
                graph.add_node(ManholeNode(node_id=nid, node_type="source"))

    with open(os.path.join(csv_dir, "sinks.csv"), "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            nid = (row.get("node_id") or "").strip()
            if nid:
                if nid in source_ids_seen:
                    raise DataLoadError(
                        f"El nodo '{nid}' aparece simultáneamente en sources.csv y sinks.csv."
                    )
                graph.add_node(ManholeNode(node_id=nid, node_type="sink"))

    with open(os.path.join(csv_dir, "pipes.csv"), "r", encoding="utf-8-sig", newline="") as f:
        for idx, row in enumerate(csv.DictReader(f), start=2):
            ctx = f"pipes.csv fila {idx}"
            pid = (row.get("pipe_id") or "").strip()
            u = (row.get("from_node") or "").strip()
            v = (row.get("to_node") or "").strip()
            if not pid or not u or not v:
                raise DataLoadError(f"Identificador o conexión faltante en {ctx}.")

            pipe = PipeEdge(
                pipe_id=pid,
                from_node=u,
                to_node=v,
                diameter_in=_parse_float(row.get("diameter_in"), "diameter_in", ctx),
                diameter_m=_parse_float(row.get("diameter_m"), "diameter_m", ctx),
                manning_n=_parse_float(row.get("manning_n"), "manning_n", ctx),
                slope=_parse_float(row.get("slope"), "slope", ctx),
                q_max_m3s=_parse_float(row.get("q_max_m3s"), "q_max_m3s", ctx),
                length_m=_parse_float(row.get("length_m"), "length_m", ctx),
                note=(row.get("note") or "").strip(),
            )
            try:
                graph.add_pipe(pipe)
            except ValueError as exc:
                raise DataLoadError(str(exc)) from exc

    with open(os.path.join(csv_dir, "drainage_basin.csv"), "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        if not rows:
            raise DataLoadError("drainage_basin.csv está vacío.")
        basin = DrainageBasin(
            runoff_coefficient_c=_parse_float(
                rows[0].get("runoff_coefficient_c"), "runoff_coefficient_c", "drainage_basin.csv"
            ),
            area_ha=_parse_float(rows[0].get("area_ha"), "area_ha", "drainage_basin.csv"),
        )

    scenarios: List[PrecipitationScenario] = []
    with open(
        os.path.join(csv_dir, "precipitation_scenarios.csv"), "r", encoding="utf-8-sig", newline=""
    ) as f:
        for idx, row in enumerate(csv.DictReader(f), start=2):
            ctx = f"precipitation_scenarios.csv fila {idx}"
            scenarios.append(
                PrecipitationScenario(
                    scenario_id=int(_parse_float(row.get("scenario_id"), "scenario_id", ctx)),
                    intensity_mm_h=_parse_float(row.get("intensity_mm_h"), "intensity_mm_h", ctx),
                    condition=(row.get("condition") or f"Escenario {idx - 1}").strip(),
                )
            )

    coords = dict(DEFAULT_NODE_COORDS)
    coords.update(_load_coords_csv(os.path.join(csv_dir, "node_coords.csv")))
    _assign_missing_coordinates(graph, coords)
    _validate_graph_and_data(graph, basin, scenarios)

    return NetworkDataset(
        graph=graph,
        basin=basin,
        scenarios=scenarios,
        source_path=os.path.abspath(csv_dir),
    )


def load_dataset(path: str) -> NetworkDataset:
    """Detecta automáticamente si `path` es un archivo .xlsx o una carpeta CSV."""
    if os.path.isdir(path):
        return load_from_csv_dir(path)
    if path.lower().endswith(".xlsx"):
        default_coords = os.path.join(os.path.dirname(path), "csv", "node_coords.csv")
        return load_from_excel(path, default_coords if os.path.isfile(default_coords) else None)
    raise DataLoadError(
        f"Formato no soportado '{path}'. Seleccione un archivo .xlsx o una carpeta CSV."
    )


def export_to_csv_dir(dataset: NetworkDataset, out_dir: str) -> None:
    """Exporta un `NetworkDataset` a archivos CSV normalizados."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "sources.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id"])
        for nid in dataset.graph.source_ids():
            w.writerow([nid])

    with open(os.path.join(out_dir, "sinks.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id"])
        for nid in dataset.graph.sink_ids():
            w.writerow([nid])

    with open(os.path.join(out_dir, "pipes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pipe_id", "from_node", "to_node", "diameter_in", "diameter_m",
            "manning_n", "slope", "q_max_m3s", "length_m", "note",
        ])
        for p in dataset.graph.pipes():
            w.writerow([
                p.pipe_id, p.from_node, p.to_node, round(p.diameter_in, 4), p.diameter_m,
                p.manning_n, p.slope, round(p.q_max_m3s, 8), p.length_m, p.note,
            ])

    with open(os.path.join(out_dir, "drainage_basin.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["runoff_coefficient_c", "area_ha"])
        w.writerow([dataset.basin.runoff_coefficient_c, dataset.basin.area_ha])

    with open(os.path.join(out_dir, "precipitation_scenarios.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario_id", "intensity_mm_h", "condition"])
        for sc in dataset.scenarios:
            w.writerow([sc.scenario_id, sc.intensity_mm_h, sc.condition])

    with open(os.path.join(out_dir, "node_coords.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "x", "y", "label"])
        for n in dataset.graph.nodes():
            w.writerow([n.node_id, round(n.x, 4), round(n.y, 4), n.label])
