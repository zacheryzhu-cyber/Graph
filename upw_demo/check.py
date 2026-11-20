"""Run every preset of the UPW demo on every engine and compare with the plain-Python reference.
Run: python upw_demo/check.py      (Neo4j optional; claim states are tested only when Neo4j is up)
Expected 'differs' cases are the lessons of the demo and are listed, not counted as failures."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scenario import QUESTIONS, TOOL_TYPES, dataset, fill, reference
import server

E = server.Engines(); E.load()
d = E.dataset
typ = {n["id"]: n["type"] for n in d["nodes"]}
units = sorted(n for n, t in typ.items() if n and t not in TOOL_TYPES and t not in ("Datapoint", "Alarm"))
tools = sorted(n for n, t in typ.items() if t in TOOL_TYPES)


def canon(q, r, p):
    c = r["cols"]; col = lambda n: c.index(n)
    if q == "Q1": return sorted({x[col("x")] for x in r["rows"]})
    if q in ("Q2", "Q6"): return sorted(x[col("t")] for x in r["rows"])
    if q == "Q3": return sorted(f'{x[col("s")]}>{x[col("d")]}' for x in r["rows"])
    if q == "Q4":
        if not r["rows"]: return ["no path"]
        if c[0] == "path": return [f"length {len(r['rows'][0][0]) - 1}"]
        return [f"length {r['rows'][0][0]}"]
    if q == "Q5": return sorted(f'{x[col("unit")]}|{x[col("alarm")]}' for x in r["rows"])


def combos(qd):
    ps = qd["params"]
    opts = {k: (s["options"] if s["kind"] == "choice" else units if s["kind"] == "unit" else tools) for k, s in ps.items()}
    out = [{}]
    for k, vs in opts.items(): out = [{**o, k: v} for o in out for v in vs]
    return out


engines = ["rdf11", "rdf12"] + (["neo4j"] if E.drv else [])
claims = [None] + ([("n10s", "LOOP-B", "WET-02"), ("node", "LOOP-B", "WET-02")] if E.drv else [])
fails, expected = 0, {}
for claim in claims:
    if claim: E.set_claim("add", claim[1], claim[2], claim[0])
    else: E.set_claim("remove")
    for qd in QUESTIONS:
        for p in combos(qd):
            ref = reference(d, qd["id"], p)
            for e in engines:
                tpl = qd["variants"][p["filter"]][e] if "variants" in qd else qd[e]
                text = fill(tpl, {k: v for k, v in p.items() if k != "filter"})
                got = canon(qd["id"], E.query(e, text, repeat=0), p)
                if got != ref:
                    key = (claim[0] if claim else "none", qd["id"], e)
                    expected.setdefault(key, []).append(p)
print(f"engines: {engines}; claim states: {[c[0] if c else 'none' for c in claims]}")
for (cl, q, e), ps in sorted(expected.items()):
    print(f"  differs  claim={cl:5s} {q} {e:6s} for {len(ps)} parameter set(s), e.g. {ps[:3]}")
