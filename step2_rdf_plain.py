"""Stage 2 — plain RDF 1.1 (n-ary relations for edge metadata) in Oxigraph + SPARQL 1.1.
Run: python step2_rdf_plain.py   (SCALE=n env var for bigger data)"""
import time
import pyoxigraph as ox
from common import load, ground_truth, timed, check, save_metrics, OUT, TRIP_SOURCE, scale
from rdf_common import build, store_from, rows, hops_union, PREFIXES

HOP = "^fab:feedFrom/fab:feedTo"   # one 'feeds' hop through the intermediate Feed node

Q = {
 "Q1": f"""SELECT DISTINCT ?t WHERE {{ fab:{TRIP_SOURCE} ({HOP})+ ?t . ?t a/rdfs:subClassOf* fab:ProductionTool }} ORDER BY ?t""",
 "Q2": """SELECT ?s ?d WHERE { ?f a fab:Feed ; fab:feedFrom ?s ; fab:feedTo ?d ; fab:redundant false ;
            fab:installed ?y ; fab:loadKW ?l ; fab:capacityKW ?c . FILTER(?y < 2018 && ?l / ?c > 0.7) } ORDER BY ?s ?d""",
 "Q3": """SELECT ?s ?d ?conf WHERE { ?f fab:feedFrom ?s ; fab:feedTo ?d ; fab:sourceSystem "BIM" ; fab:confidence ?conf .
            FILTER(?conf < 0.8) } ORDER BY ?s ?d""",
 "Q5": """SELECT ?area (COUNT(DISTINCT ?dp) AS ?n) (COUNT(DISTINCT ?al) AS ?a) WHERE {
            ?area a fab:Area . ?tool fab:locatedIn ?area ; fab:hasDatapoint ?dp .
            OPTIONAL { ?al fab:raisedOn ?dp ; fab:active true } } GROUP BY ?area ORDER BY ?area""",
}


def run(store, gt, hop=HOP, queries=Q, label="rdf_plain"):
    m, ok = {}, True
    r, m["Q1_ms"] = timed(lambda: rows(store, queries["Q1"])); ok &= check(f"Q1 impact: {len(r)} tools", [x[0] for x in r], gt["Q1"])
    r, m["Q2_ms"] = timed(lambda: rows(store, queries["Q2"])); ok &= check(f"Q2 edge-property filter: {len(r)} feeds", [tuple(x) for x in r], gt["Q2"])
    r, m["Q3_ms"] = timed(lambda: rows(store, queries["Q3"])); ok &= check(f"Q3 provenance: {len(r)} BIM links", [(a, b, float(c)) for a, b, c in r], gt["Q3"])
    q4 = hops_union(hop, TRIP_SOURCE, gt["Q4_target"])
    r, m["Q4_ms"] = timed(lambda: rows(store, q4)); ok &= check(f"Q4 path (len {r[0][0]}): SWG-B01-A → {' → '.join(x for x in r[0][1:] if x)} → {gt['Q4_target']}", int(r[0][0]), gt["Q4_len"])
    r, m["Q5_ms"] = timed(lambda: rows(store, queries["Q5"])); ok &= check(f"Q5 aggregate: {len(r)} areas", [(a, int(n), int(c)) for a, n, c in r], gt["Q5"])
    m["all_correct"] = ok
    return m


if __name__ == "__main__":
    d = load(); gt = ground_truth(d)
    t = time.perf_counter(); triples = build(d, "nary"); store = store_from(triples); load_ms = (time.perf_counter() - t) * 1000
    feed_triples = sum(1 for q in store.quads_for_pattern(None, None, None) if "#feed/" in q.subject.value)
    print(f"[RDF 1.1 n-ary] SCALE={scale()}  triples={len(store)}  (of which on Feed nodes: {feed_triples})  load={load_ms:.0f} ms")
    m = run(store, gt)
    m.update(triples=len(store), load_ms=round(load_ms), feed_triples=feed_triples)
    for k, v in m.items(): print(f"   {k:14s} {v if not isinstance(v, float) else round(v, 2)}")
    save_metrics("rdf_plain", m)
    if scale() == 1:
        store.dump(str(OUT / "fab_plain.ttl"), ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph(), prefixes={"fab": "http://example.org/fab#"})
        print("   wrote out/fab_plain.ttl")
