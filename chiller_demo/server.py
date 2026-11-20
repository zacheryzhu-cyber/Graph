r"""Chiller plant demo server: one chilled-water plant, three engines, one browser UI.

  python chiller_demo/server.py    → http://127.0.0.1:8766   (Windows: py chiller_demo\server.py)
  (Neo4j optional: Docker / Neo4j Desktop / ./neo4j_embedded/run.sh — without it the Neo4j column shows "offline")
  Note: loading wipes the Neo4j database it connects to (it's a lab database).

Standard library only, plus the lab's own modules. Runs locally; the console endpoint executes whatever
SPARQL/Cypher you type, so don't expose it beyond localhost."""
import importlib.metadata as md
import json, math, re, statistics, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent)); sys.path.insert(0, str(ROOT))
import pyoxigraph as ox
from scenario import dataset, build_rdf, load_lpg, catalogue, positions, PREFIXES, UPDATES, STEP_SEP, fill

FAB = "http://example.org/fab#"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


def local(term):
    if term is None: return None
    if isinstance(term, ox.Literal):
        dt = term.datatype.value.rsplit("#", 1)[-1]
        if dt in ("integer", "int", "long"): return int(term.value)
        if dt in ("decimal", "double", "float"): return float(term.value)
        if dt == "boolean": return term.value == "true"
        v = term.value
    elif isinstance(term, ox.Triple):
        return f"<<( {local(term.subject)} {local(term.predicate)} {local(term.object)} )>>"
    else:
        v = term.value
    return v[len(FAB):] if v.startswith(FAB) else v


def neo_val(v):
    if hasattr(v, "element_id") and hasattr(v, "items"): return dict(v.items())   # Node / Relationship
    if isinstance(v, list): return [neo_val(x) for x in v]
    if hasattr(v, "nodes"): return [n.get("id") for n in v.nodes]                     # Path
    return v


class Engines:
    def __init__(self):
        self.lock = threading.RLock()
        self.scale = None; self.stores = {}; self.drv = None; self.neo_version = None; self.counts = {}
        self.claim = None; self.dataset = None; self.load_ms = {}; self.valves = "normal"; self.valve_ms = None
        self._connect()

    def _connect(self, quiet=False):
        try:
            from neo_common import driver
            self.drv = driver()
            rec = self.drv.execute_query("CALL dbms.components() YIELD name, versions, edition RETURN versions[0] AS v, edition AS e")[0][0]
            self.neo_version = f"Neo4j {rec['v']} {rec['e']}"
        except BaseException as e:   # driver() raises SystemExit when Neo4j is down
            self.drv = None
            if not quiet: print("Neo4j offline (the demo runs without it; start Neo4j and reload the page):", str(e).split(" (")[0])

    def load(self, scale: int = 1):
        with self.lock:
            d = dataset(); self.dataset = d; t = {}
            for eng, mode in (("rdf11", "nary"), ("rdf12", "rdf12")):
                t0 = time.perf_counter()
                st = build_rdf(d, mode)
                t[eng] = round((time.perf_counter() - t0) * 1000); self.stores[eng] = st
                self.counts[eng] = f"{len(st):,} triples"
            if self.drv:
                from neo_common import wipe
                t0 = time.perf_counter(); wipe(self.drv); load_lpg(self.drv, d); t["neo4j"] = round((time.perf_counter() - t0) * 1000)
                n = self.drv.execute_query("MATCH (n) RETURN count(n) AS c")[0][0]["c"]
                r = self.drv.execute_query("MATCH ()-[r]->() RETURN count(r) AS c")[0][0]["c"]
                self.counts["neo4j"] = f"{n:,} nodes · {r:,} rels"
            self.scale, self.claim, self.load_ms, self.valves, self.valve_ms = scale, None, t, "normal", None

    def reconnect(self):
        """Neo4j started after the demo? Pick it up on the next page load."""
        with self.lock:
            if self.drv: return
            self._connect(quiet=True)
            if self.drv: self.load()

    def meta(self):
        return {"mode": "live", "scenario": "chiller", "valves": self.valves, "valve_ms": self.valve_ms,
                "engines": {"rdf11": {"name": f"Oxigraph {md.version('pyoxigraph')} · RDF 1.1", "online": True},
                            "rdf12": {"name": f"Oxigraph {md.version('pyoxigraph')} · RDF 1.2", "online": True},
                            "neo4j": {"name": self.neo_version or "Neo4j", "online": self.drv is not None}},
                "counts": self.counts, "load_ms": self.load_ms, "claim": self.claim, "catalogue": catalogue()}

    def _once(self, engine, text):
        if engine in self.stores and STEP_SEP in text:   # multi-step script: updates + one query, run in order
            out = None
            for step in text.split(STEP_SEP):
                body = "\n".join(l for l in step.splitlines() if not l.lstrip().startswith("#")).lstrip().upper()
                if body.startswith(("SELECT", "ASK", "CONSTRUCT", "DESCRIBE")): out = self._once(engine, step)
                else: self.stores[engine].update(PREFIXES + step)
            return out
        if engine in self.stores:
            res = self.stores[engine].query(PREFIXES + text)
            if isinstance(res, ox.QueryBoolean): return ["ask"], [[bool(res)]], None
            if isinstance(res, ox.QuerySolutions):
                cols = [v.value for v in res.variables]
                return cols, [[local(s[c]) for c in cols] for s in res], None
            return ["subject", "predicate", "object"], [[local(t.subject), local(t.predicate), local(t.object)] for t in res], None
        if engine == "neo4j":
            if not self.drv: raise RuntimeError("Neo4j is offline. Start it (Docker, Neo4j Desktop or ./neo4j_embedded/run.sh), then reload the page.")
            recs, summ, keys = self.drv.execute_query(text)
            return keys, [[neo_val(v) for v in r.values()] for r in recs], summ.result_available_after + summ.result_consumed_after
        raise ValueError("unknown engine")

    def query(self, engine, text, repeat=5):
        with self.lock:
            cols, rows, srv = self._once(engine, text)          # warm-up (and the result we return)
            ts, srvs = [], [srv] if srv is not None else []
            for _ in range(repeat):
                t0 = time.perf_counter(); _, _, s = self._once(engine, text); ts.append((time.perf_counter() - t0) * 1000)
                if s is not None: srvs.append(s)
            out = {"cols": cols, "rows": rows[:2000], "total": len(rows), "ms": statistics.median(ts) if ts else None, "runs": len(ts)}
            if srvs: out["server_ms"] = statistics.median(srvs)
            return out

    def update(self, engine, text):
        with self.lock:
            if engine in self.stores: self.stores[engine].update(PREFIXES + text)
            elif engine == "neo4j" and self.drv: self.drv.execute_query(text)

    def explore(self, engine, ident):
        """What the database itself holds around one thing: raw triples (RDF) or nodes + relationships (Neo4j).
        For RDF this includes the helper resources that belong to it: pipe nodes (1.1), reifiers (1.2), claims, datapoints."""
        if not re.fullmatch(r"[A-Za-z0-9._-]+", ident): raise ValueError("bad id")
        with self.lock:
            if engine in self.stores:
                st, X = self.stores[engine], ox.NamedNode(FAB + ident)
                RDF_REIFIES = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")
                quads, extra = [], []
                for q in st.quads_for_pattern(X, None, None, ox.DefaultGraph()):
                    quads.append(q)
                    if q.predicate.value == FAB + "hasDatapoint": extra.append(q.object)
                for q in st.quads_for_pattern(None, None, X, ox.DefaultGraph()):
                    quads.append(q)
                    if q.predicate.value in (FAB + "from", FAB + "to", FAB + "claimFrom", FAB + "claimTo"): extra.append(q.subject)
                for q in st.quads_for_pattern(None, RDF_REIFIES, None, ox.DefaultGraph()):
                    t = q.object
                    if isinstance(t, ox.Triple) and X in (t.subject, t.object): extra.append(q.subject)
                for r in dict.fromkeys(extra):
                    quads += list(st.quads_for_pattern(r, None, None, ox.DefaultGraph()))
                seen, out = set(), []
                for q in quads:
                    k = (str(q.subject), str(q.predicate), str(q.object))
                    if k in seen or (q.subject != X and q.object == X and q.predicate.value == RDFS_LABEL): continue
                    seen.add(k)
                    o = q.object
                    kind = "triple" if isinstance(o, ox.Triple) else "literal" if isinstance(o, ox.Literal) else "iri"
                    out.append([local(q.subject), local(q.predicate), local(o), kind])
                return {"engine": engine, "focus": ident, "triples": out}
            if engine == "neo4j":
                if not self.drv: raise RuntimeError("Neo4j is offline.")
                rec = self.drv.execute_query(
                    "MATCH (x:Entity {id: $id}) OPTIONAL MATCH (x)-[r]-(n) "
                    "RETURN labels(x) AS xl, properties(x) AS xp, collect(CASE WHEN r IS NULL THEN NULL ELSE "
                    "{s: coalesce(startNode(r).id, 'claim:' + elementId(startNode(r))), t: type(r), d: coalesce(endNode(r).id, 'claim:' + elementId(endNode(r))), rp: properties(r), "
                    "n: coalesce(n.id, 'claim:' + elementId(n)), nl: labels(n), np: properties(n)} END) AS rels", id=ident)[0]
                if not rec: return {"engine": engine, "focus": ident, "node": None, "rels": []}
                r0 = rec[0]
                return {"engine": engine, "focus": ident, "node": {"labels": r0["xl"], "props": r0["xp"]}, "rels": r0["rels"]}
            raise ValueError("unknown engine")

    def set_valves(self, preset):
        """SCADA reports valve positions. Each engine does what it must for its queries to stay right; timed."""
        with self.lock:
            want, have = positions(preset), positions(self.valves)
            changed = {v: p for v, p in want.items() if have.get(v) != p}
            ms = {}
            for e in ("rdf11", "rdf12"):
                t0 = time.perf_counter()
                for v, p in changed.items(): self.update(e, fill(UPDATES["valve_set_rdf"], {"valve": v, "position": p}))
                self.update(e, UPDATES["recompute_open_" + e])
                ms[e] = round((time.perf_counter() - t0) * 1000, 2)
            if self.drv:
                t0 = time.perf_counter()
                for v, p in changed.items(): self.update("neo4j", fill(UPDATES["valve_set_neo4j"], {"valve": v, "position": p}))
                ms["neo4j"] = round((time.perf_counter() - t0) * 1000, 2)
            self.valves, self.valve_ms = preset, {"changed": changed, "ms": ms}
            return {"valves": preset, "valve_ms": self.valve_ms}

    def set_claim(self, action, src=None, dst=None, neo_mode="n10s"):
        with self.lock:
            for e in ("rdf11", "rdf12"): self.update(e, UPDATES["claim_remove_rdf"])
            self.update("neo4j", UPDATES["claim_remove_neo4j"]); self.claim = None
            if action == "add":
                p = {"src": src, "dst": dst}
                self.update("rdf11", fill(UPDATES["claim_add_rdf11"], p))
                self.update("rdf12", fill(UPDATES["claim_add_rdf12"], p))
                self.update("neo4j", fill(UPDATES["claim_add_neo4j_" + ("n10s" if neo_mode == "n10s" else "node")], p))
                self.claim = {"src": src, "dst": dst, "neo_mode": neo_mode}
            return self.claim


# ---------------------------------------------------------------- simulated shop floor: SCADA → historian (→ graphs)
DEADBAND = {"°C": 0.2, "%": 2.0, "mm/s": 0.3, "K": 0.2, "Pa": 5.0}


class ShopFloor:
    """Every second, SCADA produces a new value for every numeric tag. Every sample goes to the historian.
    If 'write to graphs' is on, a value is also written into the three databases, but only when it has moved
    more than its deadband since the last graph write (what real projects do)."""

    def __init__(self, eng):
        self.eng, self.lock, self.sync = eng, threading.Lock(), False
        self.tags = {}   # tag -> {dp, unit, base}
        for n in eng.dataset["nodes"]:
            if n["type"] == "Datapoint" and isinstance(n.get("value"), (int, float)):
                self.tags[n["tag"]] = {"dp": n["id"], "unit": n["unit"], "base": float(n["value"])}
        self.hist = {t: [] for t in self.tags}           # the historian: tag -> [(time, value)]
        self.in_graph = {t: v["base"] for t, v in self.tags.items()}   # last value written into the graphs
        self.stats = {"samples": 0, "graph_writes": 0, "skipped": 0, "ms": {}, "last": None}
        self.tick = 0
        threading.Thread(target=self.run, daemon=True).start()

    def value(self, tag, t):
        b, i = self.tags[tag]["base"], hash(tag) % 7
        if tag.endswith("PCW_B.SupplyTemp"): return round(19.6 + 0.5 * math.sin(t / 12), 2)
        if tag.endswith("P_B1.Vibration"): return round(7.8 + 0.7 * math.sin(t / 7 + 1), 2)
        if tag.endswith(".Load"): return round(max(0, b + (3 * math.sin(t / 9 + i) if b else 0)), 1)
        return round(b + 0.02 * b * math.sin(t / (5 + i) + i), 2)

    def run(self):
        while True:
            time.sleep(1.0)
            now = time.time(); self.tick += 1
            with self.lock:
                changed = {}
                for tag in self.tags:
                    v = self.value(tag, self.tick)
                    h = self.hist[tag]; h.append((now, v)); del h[:-300]
                    self.stats["samples"] += 1
                    if self.sync:
                        if abs(v - self.in_graph[tag]) >= DEADBAND.get(self.tags[tag]["unit"], 0.5): changed[tag] = v
                        else: self.stats["skipped"] += 1
            if changed: self.write_graphs(changed)

    def write_graphs(self, changed):
        e, ms = self.eng, {}
        rows = [(self.tags[t]["dp"], v) for t, v in changed.items()]
        sparql = " ;\n".join(f'DELETE {{ fab:{dp} fab:value ?v }} INSERT {{ fab:{dp} fab:value {v} }} WHERE {{ fab:{dp} fab:value ?v }}' for dp, v in rows)
        with e.lock:
            for eng in ("rdf11", "rdf12"):
                t0 = time.perf_counter(); e.stores[eng].update(PREFIXES + sparql); ms[eng] = round((time.perf_counter() - t0) * 1000, 2)
            if e.drv:
                t0 = time.perf_counter()
                e.drv.execute_query("UNWIND $rows AS r MATCH (d:Datapoint {id: r[0]}) SET d.value = r[1]", rows=[list(r) for r in rows])
                ms["neo4j"] = round((time.perf_counter() - t0) * 1000, 2)
        with self.lock:
            self.in_graph.update(changed); self.stats["graph_writes"] += len(changed)
            self.stats["ms"] = ms; self.stats["last"] = {"tags": list(changed)[:6], "n": len(changed)}

    def set_sync(self, on):
        with self.lock:
            self.sync = bool(on)
            if not on: return
        # switching on: bring the graphs up to the current values once
        with self.lock: cur = {t: h[-1][1] for t, h in self.hist.items() if h}
        if cur: self.write_graphs(cur)

    def snapshot(self):
        with self.lock:
            return {"tick": self.tick, "sync": self.sync, "stats": self.stats,
                    "values": {t: h[-1][1] for t, h in self.hist.items() if h},
                    "in_graph": dict(self.in_graph) if self.sync else None,
                    "trend": {t: [v for _, v in h[-60:]] for t, h in self.hist.items()}}

    def latest(self, tags):
        with self.lock:
            return {t: (self.hist[t][-1][1] if self.hist.get(t) else None) for t in tags}


CHECK = {
    "rdf": "SELECT ?item ?tag WHERE {{\n  {{ BIND(fab:{u} AS ?item) }} UNION {{ fab:{u} fab:openFlow+ ?item }}\n  ?item fab:hasDatapoint ?dp . ?dp fab:tag ?tag .\n}} ORDER BY ?item",
    "neo4j": "MATCH (x:Entity {{id: '{u}'}})\nOPTIONAL MATCH (x)((a)-[:FLOWS_TO]->(b) WHERE coalesce(a.position,'open') = 'open' AND coalesce(b.position,'open') = 'open')+(y)\nWITH x, collect(DISTINCT y) AS ys\nUNWIND [x] + ys AS i\nMATCH (i)-[:HAS_DATAPOINT]->(dp)\nRETURN DISTINCT i.id AS item, dp.tag AS tag ORDER BY item",
}


def check_unit(eng, floor, unit):
    """What a screen does: (1) ask the graph which tags matter, (2) ask the historian for their latest values, (3) combine."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", unit): raise ValueError("bad id")
    out = {}
    for e in ("rdf11", "rdf12", "neo4j"):
        if e == "neo4j" and not eng.drv: out[e] = {"offline": True}; continue
        text = CHECK["neo4j" if e == "neo4j" else "rdf"].format(u=unit)
        t0 = time.perf_counter(); cols, rows, _ = eng._once(e, text); g_ms = (time.perf_counter() - t0) * 1000
        tags = [r[1] for r in rows if r[1] in floor.tags]
        t1 = time.perf_counter(); vals = floor.latest(tags); h_ms = (time.perf_counter() - t1) * 1000
        in_graph = None
        if floor.sync:   # the value stored inside this graph, for comparison
            dps = {floor.tags[t]["dp"]: t for t in tags}
            if e == "neo4j":
                res = eng.drv.execute_query("UNWIND $ids AS i MATCH (d:Datapoint {id: i}) RETURN d.id AS id, d.value AS v", ids=list(dps))[0]
                in_graph = {dps[r["id"]]: r["v"] for r in res}
            else:
                in_graph = {}
                for dp, t in dps.items():
                    q = list(eng.stores[e].query(PREFIXES + f"SELECT ?v WHERE {{ fab:{dp} fab:value ?v }}"))
                    in_graph[t] = float(q[0][0].value) if q else None
        out[e] = {"graph_query": text, "graph_rows": [[r[0], r[1]] for r in rows], "graph_ms": round(g_ms, 2),
                  "historian_ms": round(h_ms, 3), "values": vals, "in_graph": in_graph}
    return out


ENG = None
FLOOR = None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = (ROOT / "web" / "app.html").read_text(encoding="utf-8")   # a body fragment (same file feeds the published build)
            html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + page + "</body></html>")
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if self.path == "/api/meta":
            ENG.reconnect(); return self._send(200, ENG.meta())
        if self.path == "/api/dataset": return self._send(200, ENG.dataset)
        if self.path == "/api/live": return self._send(200, FLOOR.snapshot())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/query":
                return self._send(200, ENG.query(body["engine"], body["text"], int(body.get("repeat", 5))))
            if self.path == "/api/live":
                FLOOR.set_sync(body.get("sync")); return self._send(200, FLOOR.snapshot())
            if self.path == "/api/check":
                return self._send(200, check_unit(ENG, FLOOR, body["unit"]))
            if self.path == "/api/explore":
                return self._send(200, ENG.explore(body["engine"], body["id"]))
            if self.path == "/api/valves":
                return self._send(200, ENG.set_valves(body["preset"]))
            if self.path == "/api/reconnect":
                ENG.reconnect(); return self._send(200, ENG.meta())
            if self.path == "/api/claim":
                return self._send(200, {"claim": ENG.set_claim(body["action"], body.get("src"), body.get("dst"), body.get("neo_mode", "n10s"))})
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(400, {"error": f"{type(e).__name__}: {str(e).splitlines()[0][:400]}"})


def main():
    global ENG, FLOOR
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    ENG = Engines(); ENG.load(); FLOOR = ShopFloor(ENG)
    print(f"Chiller plant demo on http://127.0.0.1:{port}  ({ENG.counts})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
