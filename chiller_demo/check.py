"""Run every preset of the chiller demo on every engine, in every valve state and claim state,
and compare with the plain-Python reference.
Run: python chiller_demo/check.py   (Neo4j optional; claim states are tested only when Neo4j is up)
Expected result: everything matches, except Neo4j while the claim is imported the n10s way."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scenario import QUESTIONS, VALVE_PRESETS, fill, reference
import server

E = server.Engines(); E.load()
d = E.dataset
cat = {n["id"]: n.get("category") for n in d["nodes"]}
typ = {n["id"]: n["type"] for n in d["nodes"]}
DOM = {"unit": [k for k, c in cat.items() if c == "plant"], "consumer": [k for k, c in cat.items() if c == "consumer"],
       "chiller": [k for k, t in typ.items() if t == "Chiller"]}


def canon(q, r):
    c = r["cols"]; col = lambda n: c.index(n)
    if q == "Q1": return sorted({x[col("x")] for x in r["rows"]})
    if q == "Q2": return sorted(x[col("c")] for x in r["rows"])
    if q == "Q3": return [f'{r["rows"][0][col("remaining_kw")]}|{r["rows"][0][col("load_kw")]}'] if r["rows"] else []
    if q == "Q4": return sorted(x[col("t")] for x in r["rows"])
    if q == "Q5": return sorted(f'{x[col("unit")]}|{x[col("alarm")]}' for x in r["rows"])
    if q == "Q6": return sorted(f'{x[col("s")]}>{x[col("d")]}' for x in r["rows"])


def combos(qd):
    out = [{}]
    for k, s in qd["params"].items():
        vs = s["options"] if s["kind"] == "choice" else DOM[s["kind"]]
        out = [{**o, k: v} for o in out for v in vs]
    return out


engines = ["rdf11", "rdf12"] + (["neo4j"] if E.drv else [])
claims = [None] + ([("n10s",) + tuple(server.catalogue()["claim_default"]), ("node",) + tuple(server.catalogue()["claim_default"])] if E.drv else [])
diffs, total = {}, 0
for preset in VALVE_PRESETS:
    E.set_valves(preset)
    for claim in claims:
        E.set_claim("add", claim[1], claim[2], claim[0]) if claim else E.set_claim("remove")
        for qd in QUESTIONS:
            for p in combos(qd):
                ref = reference(d, qd["id"], p, preset)
                for e in engines:
                    got = canon(qd["id"], E.query(e, fill(qd[e], p), repeat=0)); total += 1
                    if got != ref: diffs.setdefault((preset, claim[0] if claim else "none", qd["id"], e), []).append(p)
E.set_valves("normal"); E.set_claim("remove")
print(f"{total} answers checked · engines {engines} · valve states {list(VALVE_PRESETS)} · claim states {['none'] + [c[0] for c in claims[1:]]}")
for (pre, cl, q, e), ps in sorted(diffs.items()):
    print(f"  differs  valves={pre:12s} claim={cl:5s} {q} {e:6s} for {len(ps)} parameter set(s), e.g. {ps[:3]}")
unexpected = [k for k in diffs if not (k[1] == "n10s" and k[3] == "neo4j")]
print("unexpected differences:", unexpected or "none")
sys.exit(1 if unexpected else 0)
