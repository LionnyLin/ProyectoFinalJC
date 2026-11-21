"""Motor de simulación temporal discreta con PriorityQueue, HashTable y LinkedList propias."""

from bisect import bisect_left
import math
import time
from typing import Dict, List, Tuple

from src.algorithms.analysis import classify_utilization
from src.algorithms.traversals import topological_sort
from src.data_structures import DirectedGraph, HashTable, LinkedList, PriorityQueue
from src.io.data_loader import DrainageBasin
from .models import NodeStepState, PipeStepState, SimulationConfig, SimulationResult, TimeStepSnapshot

_DRAIN_SCALE_S = 60.0  # Escala fija de drenaje (s) para presión de respaldo independiente de Δt


class SewerSimulationEngine:
    """Simulador discreto-temporal conservativo de masa para la red de alcantarillado."""

    def __init__(self, graph: DirectedGraph, basin: DrainageBasin) -> None:
        self.graph, self.basin = graph, basin
        self._topo_order, self._is_dag = topological_sort(graph)
        if not self._is_dag:
            raise ValueError("El grafo debe ser un DAG para ejecutar la simulación.")
        self.history: LinkedList[TimeStepSnapshot] = LinkedList()
        self._node_idx = {nid: i for i, nid in enumerate(self._topo_order)}
        all_pipes = graph.pipes()
        self._pipe_ids = [p.pipe_id for p in all_pipes]
        self._pipe_idx = {pid: i for i, pid in enumerate(self._pipe_ids)}
        self._is_sink = [nid in set(graph.sink_ids()) for nid in self._topo_order]
        min_t = min((p.transit_time_s for p in all_pipes if p.transit_time_s > 0.0), default=60.0)
        self._max_substep_s = max(1.0, min(15.0, 0.35 * min_t))
        self._rational_coeff = 0.00278 * basin.runoff_coefficient_c * basin.area_ha

    def _source_weights(self, distribution: str) -> List[Tuple[int, float]]:
        """Precalcula los pesos (node_idx, peso) del caudal racional entre alcantarillas fuente."""
        sources = self.graph.source_ids()
        if not sources:
            return []
        if distribution != "equal":
            caps = [sum(e.q_max_m3s for e in self.graph.outgoing_pipes(s)) for s in sources]
            total = sum(caps)
            if total > 0.0:
                return [(self._node_idx[s], c / total) for s, c in zip(sources, caps)]
        return [(self._node_idx[s], 1.0 / len(sources)) for s in sources]

    @staticmethod
    def _interval_intensity(config: SimulationConfig, t0_min: float, t1_min: float) -> float:
        """Intensidad media efectiva (mm/h) en [t0_min, t1_min] durante el evento de lluvia."""
        dt, storm_dur = t1_min - t0_min, float(config.storm_duration_min)
        if dt <= 1e-12 or storm_dur <= 0.0 or config.intensity_mm_h <= 0.0:
            return 0.0
        overlap = min(storm_dur, t1_min) - max(0.0, t0_min)
        return float(config.intensity_mm_h) * (overlap / dt) if overlap > 0.0 else 0.0

    def _build_out_table(self, split_rule: str, uniform_dt: float) -> List[Tuple[Tuple[int, str, int, float, float, float, int], ...]]:
        """Precalcula aristas salientes (pipe_idx, pipe_id, to_idx, q_max, transit_s, weight, delta_slot)."""
        n_idx, p_idx = self._node_idx, self._pipe_idx
        table: List[Tuple[Tuple[int, str, int, float, float, float, int], ...]] = []
        for u in self._topo_order:
            outs = self.graph.outgoing_pipes(u).to_list()
            if not outs:
                table.append(())
                continue
            tot_cap = 0.0 if split_rule == "equal" else sum(p.q_max_m3s for p in outs)
            inv_n = 1.0 / len(outs)
            table.append(tuple(
                (p_idx[p.pipe_id], p.pipe_id, n_idx[p.to_node], p.q_max_m3s, p.transit_time_s,
                 (p.q_max_m3s / tot_cap) if tot_cap > 0.0 else inv_n,
                 max(1, int(math.ceil((p.transit_time_s - 1e-9) / uniform_dt))) if (uniform_dt > 0.0 and p.transit_time_s > 1e-9) else 0)
                for p in outs
            ))
        return table

    def run(self, config: SimulationConfig) -> SimulationResult:
        """Ejecuta la simulación temporal completa y almacena cada instante en LinkedList."""
        t_start = time.perf_counter()
        self.history.clear()
        topo, pipe_ids, is_sink = self._topo_order, self._pipe_ids, self._is_sink
        n_nodes, n_pipes = len(topo), len(pipe_ids)
        cap_manhole = max(0.0, float(config.max_manhole_storage_m3))
        src_weights = self._source_weights(config.source_distribution)
        q_rain_rate = self._rational_coeff * max(0.0, float(config.intensity_mm_h))
        storm_s = max(0.0, float(config.storm_duration_min) * 60.0)
        user_dt_min = max(0.1, float(config.dt_min))
        duration_min = max(user_dt_min, float(config.duration_min))

        step_schedule: List[Tuple[float, float, float, float, int, float]] = []
        sub_end_s: List[float] = []
        t_prev = 0.0
        while t_prev + 1e-9 < duration_min:
            t_curr = min(duration_min, t_prev + user_dt_min)
            prev_s, dt_s = t_prev * 60.0, max(1e-9, (t_curr - t_prev) * 60.0)
            n_sub = max(1, int(math.ceil(dt_s / self._max_substep_s)))
            sub_dt = dt_s / n_sub
            step_schedule.append((t_prev, t_curr, prev_s, dt_s, n_sub, sub_dt))
            sub_end_s.extend(prev_s + k * sub_dt for k in range(1, n_sub + 1))
            t_prev = t_curr
        n_total_subs = len(sub_end_s)
        sub_end_s.append(sub_end_s[-1] + 1.0)  # Centinela para llegadas > duration_min
        base_dt = step_schedule[0][5]
        uniform_dt = base_dt if all(abs(x[5] - base_dt) < 1e-9 for x in step_schedule) else 0.0
        out_table = self._build_out_table(config.split_rule, uniform_dt)

        # Estructuras propias (HashTable y PriorityQueue) con pre-bind de métodos locales
        node_stored, node_flooded, pipe_transit_vol = HashTable(128), HashTable(128), HashTable(128)
        event_queue: PriorityQueue[List[Tuple[str, int, float]]] = PriorityQueue()
        pq_push, pq_pop, pq_peek = event_queue.push, event_queue.pop, event_queue.peek
        ns_get, ns_put, nf_get, nf_add = node_stored.__getitem__, node_stored.put, node_flooded.__getitem__, node_flooded.add
        pt_get, pt_add, pt_put, hist_append = pipe_transit_vol.get, pipe_transit_vol.add, pipe_transit_vol.put, self.history.append

        low_cat = classify_utilization(0.0)
        hist_append(TimeStepSnapshot(
            0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            {pid: PipeStepState(pid, 0.0, 0.0, 0.0, 0.0, low_cat, 0.0) for pid in pipe_ids},
            {nid: NodeStepState(nid, 0.0, 0.0, 0.0, 0.0, 0.0) for nid in topo},
        ))

        pending_slots: Dict[int, List[Tuple[str, int, float]]] = {}
        stored_active, flooded_active, ever_near, ever_over = set(), set(), set(), set()
        cum_in = cum_sink = tot_stored = tot_transit = tot_flooded = peak_sink_q = max_mass_err = 0.0
        peak_util, peak_flow, max_storage = [0.0] * n_pipes, [0.0] * n_pipes, [0.0] * n_nodes
        curr_slot = 0

        for step, (prev_m, curr_m, prev_s, snap_dt_s, n_sub, sub_dt_s) in enumerate(step_schedule, start=1):
            snap_arr, snap_sent, snap_spill = [0.0] * n_nodes, [0.0] * n_nodes, [0.0] * n_nodes
            snap_pipe_sent, snap_inflow, snap_sink, inv_snap_dt = [0.0] * n_pipes, 0.0, 0.0, 1.0 / snap_dt_s
            for sub in range(n_sub):
                t0_s, t1_s = prev_s + sub * sub_dt_s, prev_s + (sub + 1) * sub_dt_s
                sub_arr, has_arrivals = [0.0] * n_nodes, False
                while event_queue and pq_peek()[0] <= t1_s + 1e-9:
                    has_arrivals = True
                    for pid, tgt_idx, vol in pq_pop()[1]:
                        sub_arr[tgt_idx] += vol
                        snap_arr[tgt_idx] += vol
                        if pt_add(pid, -vol) < 0.0:
                            pt_put(pid, 0.0)
                        tot_transit -= vol
                tot_transit = max(0.0, tot_transit)

                if q_rain_rate > 0.0 and t0_s < storm_s:
                    vol_rain = q_rain_rate * (min(storm_s, t1_s) - t0_s)
                    has_arrivals = True
                    for s_idx, sw in src_weights:
                        vol_in = vol_rain * sw
                        sub_arr[s_idx] += vol_in
                        snap_arr[s_idx] += vol_in
                    cum_in += vol_rain
                    snap_inflow += vol_rain

                if not has_arrivals and not stored_active:
                    curr_slot += 1
                    continue
                for u_idx in range(n_nodes):
                    arr_u, in_st = sub_arr[u_idx], u_idx in stored_active
                    if arr_u <= 0.0 and not in_st:
                        continue
                    u = topo[u_idx]
                    st_before = ns_get(u) if in_st else 0.0
                    avail = st_before + arr_u
                    if avail <= 1e-12:
                        continue
                    if is_sink[u_idx]:
                        snap_sink += avail
                        cum_sink += avail
                        snap_sent[u_idx] += avail
                        continue
                    out_edges = out_table[u_idx]
                    rem_st, sent_u = (0.0 if out_edges else avail), 0.0
                    for p_idx, pid, to_idx, q_max, tr_s, w, d_slot in out_edges:
                        dem_v, cap_v = avail * w, q_max * sub_dt_s
                        sent_v = dem_v if dem_v <= cap_v else cap_v
                        rem_st += dem_v - sent_v
                        if sent_v <= 0.0:
                            continue
                        sent_u += sent_v
                        snap_pipe_sent[p_idx] += sent_v
                        if tr_s <= 1e-9:
                            sub_arr[to_idx] += sent_v
                            snap_arr[to_idx] += sent_v
                        else:
                            pt_add(pid, sent_v)
                            tot_transit += sent_v
                            s_idx = min(n_total_subs, (curr_slot + d_slot) if d_slot else bisect_left(sub_end_s, t1_s + tr_s - 1e-9))
                            bucket = pending_slots.get(s_idx)
                            if bucket is None:
                                pending_slots[s_idx] = bucket = []
                                pq_push(sub_end_s[s_idx], bucket)
                            bucket.append((pid, to_idx, sent_v))
                    stored_u = rem_st if rem_st <= cap_manhole else cap_manhole
                    spill_u = rem_st - stored_u
                    if stored_u != st_before:
                        ns_put(u, stored_u)
                        tot_stored += stored_u - st_before
                        (stored_active.add if stored_u > 0.0 else stored_active.discard)(u_idx)
                    if spill_u > 0.0:
                        nf_add(u, spill_u)
                        flooded_active.add(u_idx)
                        tot_flooded += spill_u
                        snap_spill[u_idx] += spill_u
                    if sent_u > 0.0:
                        snap_sent[u_idx] += sent_u
                    max_storage[u_idx] = max(max_storage[u_idx], stored_u)
                curr_slot += 1

            # Consolidar instantánea con tasa de demanda física invariante a Δt
            pipe_states: Dict[str, PipeStepState] = {}
            critical_ids, near_ids, over_ids = [], [], []
            for u_idx in range(n_nodes):
                out_edges = out_table[u_idx]
                if not out_edges:
                    continue
                st_u = ns_get(topo[u_idx]) if u_idx in stored_active else 0.0
                q_node_dem = snap_arr[u_idx] * inv_snap_dt + st_u / _DRAIN_SCALE_S
                for p_idx, pid, _, q_max, _, w, _ in out_edges:
                    q_cond = snap_pipe_sent[p_idx] * inv_snap_dt
                    q_dem = max(q_node_dem * w, q_cond)
                    util_pct = (q_dem / q_max) * 100.0 if q_max > 0.0 else 0.0
                    cat = classify_utilization(util_pct)
                    pipe_states[pid] = PipeStepState(
                        pid, q_cond, q_dem, pt_get(pid, 0.0), util_pct, cat, max(0.0, q_dem - q_max)
                    )
                    peak_util[p_idx] = max(peak_util[p_idx], util_pct)
                    peak_flow[p_idx] = max(peak_flow[p_idx], q_cond)
                    if cat.is_critical:
                        critical_ids.append(pid)
                        (over_ids if cat.is_overloaded else near_ids).append(pid)

            ever_over.update(over_ids)
            ever_near.update(near_ids)
            mass_err = abs(cum_in - (cum_sink + tot_stored + tot_transit + tot_flooded))
            max_mass_err = max(max_mass_err, mass_err)
            sink_q = snap_sink * inv_snap_dt
            peak_sink_q = max(peak_sink_q, sink_q)
            node_states = {
                topo[i]: NodeStepState(
                    topo[i], snap_arr[i] * inv_snap_dt, snap_sent[i] * inv_snap_dt,
                    ns_get(topo[i]) if i in stored_active else 0.0,
                    nf_get(topo[i]) if i in flooded_active else 0.0, snap_spill[i] * inv_snap_dt,
                ) for i in range(n_nodes)
            }
            hist_append(TimeStepSnapshot(
                step, curr_m, self._interval_intensity(config, prev_m, curr_m),
                snap_inflow * inv_snap_dt, sink_q, cum_in, cum_sink,
                tot_stored, tot_transit, tot_flooded, mass_err,
                pipe_states, node_states, critical_ids, near_ids, over_ids,
            ))

        return SimulationResult(
            config, self.history.to_list(),
            {pipe_ids[i]: peak_util[i] for i in range(n_pipes)},
            {pipe_ids[i]: peak_flow[i] for i in range(n_pipes)},
            {topo[i]: max_storage[i] for i in range(n_nodes)},
            peak_sink_q, cum_in, cum_sink, tot_stored + tot_transit, tot_flooded, max_mass_err,
            sorted(ever_near | ever_over), sorted(ever_near), sorted(ever_over),
            (time.perf_counter() - t_start) * 1000.0,
        )
