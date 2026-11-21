"""Pruebas unitarias para carga, paridad Excel/CSV, round-trip y validación."""

import os, tempfile, unittest
from src.io.data_loader import (
    DEFAULT_NODE_COORDS, DataLoadError, export_to_csv_dir, load_dataset, load_from_csv_dir,
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_XLSX = os.path.join(BASE_DIR, "data", "DataSetBicentenario.xlsx")
DATA_CSV = os.path.join(BASE_DIR, "data", "csv")


def _write(directory: str, name: str, text: str, mode: str = "w") -> None:
    with open(os.path.join(directory, name), mode, encoding="utf-8", newline="") as fh:
        fh.write(text)


class TestLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ds_xlsx = load_dataset(DATA_XLSX)
        cls.ds_csv = load_dataset(DATA_CSV)

    def test_excel_and_csv_exact_parity(self) -> None:
        gx, gc = self.ds_xlsx.graph, self.ds_csv.graph
        self.assertEqual((gx.summary()[:4], gc.summary()[:4]), ((46, 59, 8, 1), (46, 59, 8, 1)))
        self.assertEqual((gx.sink_ids(), gc.sink_ids()), (["31"], ["31"]))
        self.assertAlmostEqual(gx.total_network_length_m(), 19163.57, places=2)
        self.assertAlmostEqual(gc.total_network_length_m(), 19163.57, places=2)
        self.assertEqual((self.ds_xlsx.basin.runoff_coefficient_c, self.ds_xlsx.basin.area_ha), (0.75, 388.0))
        self.assertEqual((self.ds_xlsx.basin, len(self.ds_xlsx.scenarios)), (self.ds_csv.basin, 5))
        self.assertEqual((self.ds_xlsx.scenarios, gx.pipe_ids()), (self.ds_csv.scenarios, gc.pipe_ids()))
        for pid in gx.pipe_ids():
            px, pc = gx.get_pipe(pid), gc.get_pipe(pid)
            assert px is not None and pc is not None
            self.assertEqual((px.from_node, px.to_node), (pc.from_node, pc.to_node))
            self.assertAlmostEqual(px.q_max_m3s, pc.q_max_m3s, places=8)
            self.assertAlmostEqual(px.length_m, pc.length_m, places=4)

    def test_round_trip_and_blank_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_to_csv_dir(self.ds_xlsx, tmpdir)
            reloaded = load_from_csv_dir(tmpdir)
            self.assertEqual(reloaded.graph.summary()[:4], (46, 59, 8, 1))
            self.assertAlmostEqual(reloaded.graph.total_network_length_m(), 19163.57, places=2)
            self.assertEqual((reloaded.basin, reloaded.scenarios), (self.ds_xlsx.basin, self.ds_xlsx.scenarios))
            for fname in ("sources.csv", "pipes.csv", "precipitation_scenarios.csv"):
                _write(tmpdir, fname, "\n,,,,,\n   \n", mode="a")
            clean = load_dataset(tmpdir)
            self.assertEqual((clean.graph.summary()[:4], len(clean.scenarios)), ((46, 59, 8, 1), 5))

    def test_rejects_invalid_paths_and_corrupted_networks(self) -> None:
        for bad in ("no_existe.xlsx", "archivo.txt"):
            with self.assertRaises(DataLoadError):
                load_dataset(bad)
        with tempfile.TemporaryDirectory() as empty_dir:
            with self.assertRaises(DataLoadError):
                load_dataset(empty_dir)

        def _mutated_load(mutator) -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                export_to_csv_dir(self.ds_csv, tmpdir)
                mutator(tmpdir)
                with self.assertRaises(DataLoadError):
                    load_dataset(tmpdir)

        # Ciclos dirigidos, IDs duplicados (tubería y fuente) y dead-end no sumidero
        _mutated_load(lambda d: _write(d, "pipes.csv", "PCYC,31,1,8,0.2032,0.015,0.01,0.03,50.0,\n", "a"))
        _mutated_load(lambda d: _write(d, "pipes.csv", "P1,1,C,10,0.254,0.015,0.01,0.0537,100.0,\n", "a"))
        _mutated_load(lambda d: _write(d, "sources.csv", "1\n", "a"))
        def _dead_end(d: str) -> None:
            p = os.path.join(d, "pipes.csv")
            with open(p, "r", encoding="utf-8") as fh:
                txt = fh.read()
            _write(d, "pipes.csv", txt.replace(",C,31,", ",C,3l,"))
        _mutated_load(_dead_end)

        # Diámetros inconsistentes (>2%), valores negativos y NaN
        for col, val in ((4, "0.9999"), (8, "-50.0"), (8, "nan")):
            def _corrupt(d: str, c: int = col, v: str = val) -> None:
                p = os.path.join(d, "pipes.csv")
                with open(p, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
                parts = lines[1].split(",")
                parts[c] = v
                lines[1] = ",".join(parts)
                _write(d, "pipes.csv", "".join(lines))
            _mutated_load(_corrupt)

    def test_external_synthetic_network_uses_topological_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(tmpdir, "sources.csv", "node_id\n1\n")
            _write(tmpdir, "sinks.csv", "node_id\n99\n")
            _write(tmpdir, "drainage_basin.csv", "runoff_coefficient_c,area_ha\n0.75,10.0\n")
            _write(tmpdir, "precipitation_scenarios.csv", "scenario_id,condition,intensity_mm_h\n1,Light rain,10.0\n")
            _write(tmpdir, "pipes.csv", (
                "pipe_id,from_node,to_node,diameter_in,diameter_m,manning_n,slope,q_max_m3s,length_m,note\n"
                "P1,1,2,8,0.2032,0.015,0.01,,100.0,\nP2,2,99,8,0.2032,0.015,0.01,,100.0,\n"
            ))
            ds_ext = load_dataset(tmpdir)
            self.assertEqual(ds_ext.graph.summary()[:4], (3, 2, 1, 1))
            self.assertAlmostEqual(ds_ext.graph.get_pipe("P1").q_max_m3s, 0.02965436, places=6)
            n1, n2, n99 = (ds_ext.graph.get_node(k) for k in ("1", "2", "99"))
            assert n1 is not None and n2 is not None and n99 is not None
            self.assertNotEqual((round(n1.x, 3), round(n1.y, 3)), DEFAULT_NODE_COORDS["1"][:2])
            self.assertTrue(n1.x < n2.x < n99.x and 0.0 < n1.y < 1.0 and 0.0 < n99.y < 1.0)


if __name__ == "__main__":
    unittest.main()
