r"""UPW demo server: one ultrapure-water plant, three engines, one browser UI.

  python upw_demo/server.py        → http://127.0.0.1:8766   (Windows: py upw_demo\server.py)
  (Neo4j optional: Docker / Neo4j Desktop / ./neo4j_embedded/run.sh — without it the Neo4j column shows "offline")
  Note: loading wipes the Neo4j database it connects to (it's a lab database).

Standard library only, plus the lab's own modules. Runs locally; the console endpoint executes whatever
SPARQL/Cypher you type, so don't expose it beyond localhost."""
import importlib.metadata as md
import json, statistics, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent)); sys.path.insert(0, str(ROOT))
import pyoxigraph as ox
from scenario import dataset, build_rdf, load_lpg, catalogue, PREFIXES, UPDATES, fill

FAB = "http://example.org/fab#"


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
        self.claim = None; self.dataset = None; self.load_ms = {}
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
            self.scale, self.claim, self.load_ms = scale, None, t

    def reconnect(self):
        """Neo4j started after the demo? Pick it up on the next page load."""
        with self.lock:
            if self.drv: return
            self._connect(quiet=True)
            if self.drv: self.load()

    def meta(self):
        return {"mode": "live", "scenario": "upw",
                "engines": {"rdf11": {"name": f"Oxigraph {md.version('pyoxigraph')} · RDF 1.1", "online": True},
                            "rdf12": {"name": f"Oxigraph {md.version('pyoxigraph')} · RDF 1.2", "online": True},
                            "neo4j": {"name": self.neo_version or "Neo4j", "online": self.drv is not None}},
                "counts": self.counts, "load_ms": self.load_ms, "claim": self.claim, "catalogue": catalogue()}

    def _once(self, engine, text):
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


ENG = None


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
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/query":
                return self._send(200, ENG.query(body["engine"], body["text"], int(body.get("repeat", 5))))
            if self.path == "/api/reconnect":
                ENG.reconnect(); return self._send(200, ENG.meta())
            if self.path == "/api/claim":
                return self._send(200, {"claim": ENG.set_claim(body["action"], body.get("src"), body.get("dst"), body.get("neo_mode", "n10s"))})
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(400, {"error": f"{type(e).__name__}: {str(e).splitlines()[0][:400]}"})


def main():
    global ENG
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    ENG = Engines(); ENG.load()
    print(f"UPW graph demo on http://127.0.0.1:{port}  ({ENG.counts})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
