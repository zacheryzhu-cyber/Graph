"""Stage 3 — RDF 1.2 triple terms + reifiers (the standardised successor of RDF-star) in Oxigraph + SPARQL 1.2.
Run: python step3_rdf_star.py   (SCALE=n env var for bigger data)"""
import time
import pyoxigraph as ox
from common import load, ground_truth, save_metrics, OUT, TRIP_SOURCE, scale
from rdf_common import build, store_from, rows, N, REIFIES, lit
from step2_rdf_plain import run

Q = {
 "Q1": f"""SELECT DISTINCT ?t WHERE {{ fab:{TRIP_SOURCE} fab:feeds+ ?t . ?t a/rdfs:subClassOf* fab:ProductionTool }} ORDER BY ?t""",
 # annotation syntax {| ... |}: match the asserted triple AND properties of its reifier
 "Q2": """SELECT ?s ?d WHERE { ?s fab:feeds ?d {| fab:redundant false ; fab:installed ?y ; fab:loadKW ?l ; fab:capacityKW ?c |}
            FILTER(?y < 2018 && ?l / ?c > 0.7) } ORDER BY ?s ?d""",
 # explicit form: the reifier points at a triple term
 "Q3": """SELECT ?s ?d ?conf WHERE { ?r rdf:reifies <<( ?s fab:feeds ?d )>> ; fab:sourceSystem "BIM" ; fab:confidence ?conf .
            FILTER(?conf < 0.8) } ORDER BY ?s ?d""",
 "Q1b": f"""SELECT ?t WHERE {{ {{ SELECT DISTINCT ?t WHERE {{ fab:{TRIP_SOURCE} fab:feeds+ ?t }} }}
            ?t a ?c . ?c rdfs:subClassOf* fab:ProductionTool }} ORDER BY ?t""",
 "Q6_prep": """INSERT { ?s fab:feedsPower ?d } WHERE { ?s fab:feeds ?d {| fab:medium "power" |} }""",
 "Q6": """SELECT ?t WHERE { ?sw a fab:Switchgear . ?sw fab:feedsPower+ ?t . ?t a/rdfs:subClassOf* fab:ProductionTool }
            GROUP BY ?t HAVING (COUNT(DISTINCT ?sw) = 1) ORDER BY ?t""",
 "Q5": """SELECT ?area (COUNT(DISTINCT ?dp) AS ?n) (COUNT(DISTINCT ?al) AS ?a) WHERE {
            ?area a fab:Area . ?tool fab:locatedIn ?area ; fab:hasDatapoint ?dp .
            OPTIONAL { ?al fab:raisedOn ?dp ; fab:active true } } GROUP BY ?area ORDER BY ?area""",
}


def provenance_demo(store):
    """Things an LPG edge property cannot express cleanly."""
    print("\n -- RDF 1.2-only capabilities --")
    a, b = N("PDU-B01-01"), N("T-B01-402")
    claim = ox.BlankNode()                    # 1) a claim that is NOT asserted
    store.add(ox.Quad(claim, REIFIES, ox.Triple(a, N("feeds"), b)))
    store.add(ox.Quad(claim, N("sourceSystem"), lit("BIM")))
    store.add(ox.Quad(claim, N("confidence"), lit(0.55)))
    first = next(store.quads_for_pattern(None, N("feeds"), None))   # 2) second, independent statement about an existing edge
    second = N("feed/second-opinion")
    store.add(ox.Quad(second, REIFIES, ox.Triple(first.subject, first.predicate, first.object)))
    store.add(ox.Quad(second, N("sourceSystem"), lit("WinCCOA"))); store.add(ox.Quad(second, N("confidence"), lit(0.99)))

    print("   claimed-but-not-asserted links (BIM says so, operational graph doesn't):")
    for r in rows(store, """SELECT ?s ?d ?src WHERE { ?r rdf:reifies ?t ; fab:sourceSystem ?src .
                 BIND(SUBJECT(?t) AS ?s) BIND(OBJECT(?t) AS ?d) FILTER NOT EXISTS { ?s fab:feeds ?d } }"""):
        print("     ", r)
    asserted = bool(store.query("PREFIX fab: <http://example.org/fab#> ASK { fab:PDU-B01-01 fab:feeds fab:T-B01-402 }"))
    print(f"   is that claimed link traversed by Q1-style impact analysis? {asserted}  (unasserted → not part of the graph)")
    print("   edges with >1 independent source statement:")
    for r in rows(store, """SELECT ?s ?d (GROUP_CONCAT(CONCAT(?src, "=", STR(?c)); separator=", ") AS ?who) WHERE {
                 ?r rdf:reifies <<( ?s fab:feeds ?d )>> ; fab:sourceSystem ?src ; fab:confidence ?c . ?s fab:feeds ?d }
                 GROUP BY ?s ?d HAVING (COUNT(?r) > 1)"""):
        print("     ", r)


if __name__ == "__main__":
    d = load(); gt = ground_truth(d)
    t = time.perf_counter(); store = store_from(build(d, "rdf12")); load_ms = (time.perf_counter() - t) * 1000
    reif = sum(1 for q in store.quads_for_pattern(None, None, None) if "#feed/" in q.subject.value)
    print(f"[RDF 1.2 reifiers] SCALE={scale()}  triples={len(store)}  (of which reifier triples: {reif})  load={load_ms:.0f} ms")
    m = run(store, gt, hop="fab:feeds", queries=Q)
    m.update(triples=len(store), load_ms=round(load_ms), feed_triples=reif)
    for k, v in m.items(): print(f"   {k:14s} {v if not isinstance(v, float) else round(v, 2)}")
    save_metrics("rdf_star", m)
    if scale() == 1:
        provenance_demo(store)
        store.dump(str(OUT / "fab_rdf12.ttl"), ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph(), prefixes={"fab": "http://example.org/fab#"})
        print("   wrote out/fab_rdf12.ttl")
