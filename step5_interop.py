"""Stage 5 — interop: RDF 1.2 → LPG (n10s-style mapping) → RDF 1.2 round trip, and SHACL validation.
n10s itself isn't installable here (DECISIONS D5); this reproduces its default conventions:
  rdf:type → node label, literal → node property, IRI object → relationship, `uri` property keeps the IRI,
  and (like n10s' RDF-star import) statement-level annotations → relationship properties.
Needs Neo4j (./neo4j_embedded/run.sh). Run: python step5_interop.py"""
import time
from collections import defaultdict
import pyoxigraph as ox
from common import load, OUT, FAB
from rdf_common import build, store_from, N, REIFIES, TYPE, lit
from neo_common import driver, wipe

RDF_TYPE = TYPE.value


NS = {"fab": FAB, "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#"}


def short(iri):  # n10s handleVocabUris: "SHORTEN" → prefix__local
    for pre, ns in NS.items():
        if iri.startswith(ns): return f"{pre}__" + iri[len(ns):].replace("/", "_")
    return iri


def unshort(x):
    pre, _, loc = x.partition("__")
    if pre not in NS: return x
    return NS[pre] + (loc.replace("feed_", "feed/", 1) if pre == "fab" else loc)


def pyval(l: ox.Literal):
    dt = l.datatype.value.rsplit("#", 1)[-1]
    return {"integer": int, "decimal": float, "double": float, "boolean": lambda v: v == "true"}.get(dt, str)(l.value)


def rdf_to_lpg(store, drv):
    """Returns a report of what could NOT be mapped 1:1."""
    nodes = defaultdict(lambda: {"labels": {"Resource"}, "props": {}})
    rels, reifiers, loss = [], defaultdict(dict), defaultdict(int)
    for q in store:
        s, p, o = q.subject, q.predicate.value, q.object
        if isinstance(o, ox.Triple):                       # r rdf:reifies <<( s p o )>>
            reifiers[s.value]["__triple"] = o; continue
        if isinstance(s, ox.BlankNode) or (isinstance(s, ox.NamedNode) and "#feed/" in s.value):
            reifiers[s.value][short(p)] = pyval(o) if isinstance(o, ox.Literal) else o.value; continue
        n = nodes[s.value]
        if p == RDF_TYPE: n["labels"].add(short(o.value))
        elif isinstance(o, ox.Literal): n["props"][short(p)] = pyval(o)
        else: nodes[o.value]; rels.append([s.value, short(p), o.value, {}])
    # attach reifier properties to the matching relationship
    by_key = {(r[0], r[1], r[2]): r for r in rels}
    seen = set()
    for rid, props in reifiers.items():
        t = props.pop("__triple", None)
        key = (t.subject.value, short(t.predicate.value), t.object.value)
        if key not in by_key:
            loss["unasserted claims dropped (no edge to hang them on)"] += 1; continue
        if key in seen:
            loss["2nd+ statements about same edge overwritten"] += 1
        seen.add(key)
        by_key[key][3].update(props | {"reifier": rid})
    wipe(drv)
    drv.execute_query("CREATE CONSTRAINT res_uri IF NOT EXISTS FOR (n:Resource) REQUIRE n.uri IS UNIQUE")
    by_lab = defaultdict(list)
    for uri, n in nodes.items(): by_lab[":".join(sorted(n["labels"]))].append(n["props"] | {"uri": uri})
    for labs, rows in by_lab.items():
        drv.execute_query(f"UNWIND $rows AS r CREATE (n:`{labs.replace(':', '`:`')}`) SET n = r", rows=rows)
    by_type = defaultdict(list)
    for s, p, o, props in rels: by_type[p].append({"s": s, "o": o, "p": props})
    for p, rows in by_type.items():
        drv.execute_query(f"UNWIND $rows AS r MATCH (a:Resource {{uri:r.s}}), (b:Resource {{uri:r.o}}) CREATE (a)-[x:{p}]->(b) SET x = r.p", rows=rows)
    return loss


def lpg_to_rdf(drv) -> ox.Store:
    """Export the LPG back to RDF 1.2: labels → rdf:type, rel props → reifier (n10s export style)."""
    st = ox.Store()
    for rec in drv.execute_query("MATCH (n:Resource) RETURN n.uri AS u, labels(n) AS l, properties(n) AS p")[0]:
        s = ox.NamedNode(rec["u"])
        for l in rec["l"]:
            if l != "Resource": st.add(ox.Quad(s, TYPE, ox.NamedNode(unshort(l))))
        for k, v in rec["p"].items():
            if k != "uri": st.add(ox.Quad(s, ox.NamedNode(unshort(k)), lit(v)))
    for rec in drv.execute_query("MATCH (a)-[r]->(b) RETURN a.uri AS a, type(r) AS t, b.uri AS b, properties(r) AS p")[0]:
        t = ox.Triple(ox.NamedNode(rec["a"]), ox.NamedNode(unshort(rec["t"])), ox.NamedNode(rec["b"]))
        st.add(ox.Quad(t.subject, t.predicate, t.object))
        p = dict(rec["p"])
        if "reifier" in p:
            r = ox.NamedNode(p.pop("reifier")); st.add(ox.Quad(r, REIFIES, t))
            for k, v in p.items(): st.add(ox.Quad(r, ox.NamedNode(unshort(k)), lit(v)))
    return st


def diff(a: ox.Store, b: ox.Store):
    A = {str(q) for q in a}; B = {str(q) for q in b}
    return A - B, B - A


SHAPES = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix fab: <http://example.org/fab#> .
    fab:ToolShape a sh:NodeShape ; sh:targetClass fab:ProductionTool ;   # applies to EUVScanner etc. via rdfs:subClassOf
      sh:property [ sh:path [ sh:inversePath fab:feedTo ] ; sh:qualifiedMinCount 1 ;
                    sh:qualifiedValueShape [ sh:property [ sh:path fab:medium ; sh:hasValue "power" ] ] ;
                    sh:message "Production tool has no power feed" ] ;
      sh:property [ sh:path [ sh:inversePath fab:feedTo ] ; sh:qualifiedMinCount 1 ;
                    sh:qualifiedValueShape [ sh:property [ sh:path fab:medium ; sh:hasValue "pcw" ] ] ;
                    sh:message "Production tool has no process-cooling feed" ] .
    fab:FeedShape a sh:NodeShape ; sh:targetClass fab:Feed ;
      sh:property [ sh:path fab:loadKW ; sh:lessThanOrEquals fab:capacityKW ; sh:message "Feed overloaded: load > capacity" ] ;
      sh:property [ sh:path fab:confidence ; sh:minInclusive 0 ; sh:maxInclusive 1 ] ;
      sh:property [ sh:path fab:sourceSystem ; sh:in ("WinCCOA" "CMMS" "BIM") ; sh:minCount 1 ] ."""


def shacl():
    """SHACL on the RDF side. rdflib 7.6 cannot parse RDF 1.2 (<<( )>>), so pyshacl validates the RDF 1.1 n-ary graph."""
    import rdflib, pyshacl
    shapes = SHAPES
    st = store_from(build(load(1), "nary"))
    # inject two defects: tool T-B01-101 loses its power feed(s); one feed is overloaded
    for q in list(st.quads_for_pattern(None, N("feedTo"), N("T-B01-101"))):
        if any(x.object.value == "power" for x in st.quads_for_pattern(q.subject, N("medium"), None)):
            for x in list(st.quads_for_pattern(q.subject, None, None)): st.remove(x)
    f0 = next(st.quads_for_pattern(None, N("loadKW"), None))
    st.remove(f0); st.add(ox.Quad(f0.subject, N("loadKW"), lit(2500.0)))
    g = rdflib.Graph(); g.parse(data=st.dump(format=ox.RdfFormat.N_TRIPLES, from_graph=ox.DefaultGraph()).decode(), format="nt")
    g.parse(data="""@prefix fab: <http://example.org/fab#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .""", format="turtle")
    t = time.perf_counter()
    conforms, rg, _ = pyshacl.validate(g, shacl_graph=rdflib.Graph().parse(data=shapes, format="turtle"), inference="rdfs")
    ms = (time.perf_counter() - t) * 1000
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    msgs = sorted({(str(rg.value(r, SH.focusNode)).split("#")[1], str(rg.value(r, SH.resultMessage))) for r in rg.subjects(rdflib.RDF.type, SH.ValidationResult)})
    print(f"   SHACL conforms={conforms}  violations={len(msgs)}  ({ms:.0f} ms, {len(g)} triples, rdfs inference on)")
    for m in msgs: print("     -", m)
    return len(msgs), ms


if __name__ == "__main__":
    d = load(1); drv = driver()
    print("[1] RDF 1.2 → LPG (n10s-style) → RDF 1.2 round trip on the clean dataset")
    src = store_from(build(d, "rdf12"))
    loss = rdf_to_lpg(src, drv)
    back = lpg_to_rdf(drv)
    only_src, only_back = diff(src, back)
    n = drv.execute_query("MATCH (n) RETURN count(n) AS c")[0][0]["c"]; r = drv.execute_query("MATCH ()-[r]->() RETURN count(r) AS c")[0][0]["c"]
    print(f"   RDF triples {len(src)} → LPG {n} nodes / {r} rels → RDF triples {len(back)}")
    print(f"   lost: {len(only_src)}  gained: {len(only_back)}  mapping losses: {dict(loss) or 'none'}")
    for x in sorted(only_src)[:3]: print("     lost  :", x[:150])
    for x in sorted(only_back)[:3]: print("     gained:", x[:150])

    print("\n[2] Same round trip after adding RDF 1.2-only provenance (unasserted claim + 2nd statement)")
    from step3_rdf_star import provenance_demo
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()): provenance_demo(src)
    loss = rdf_to_lpg(src, drv); back = lpg_to_rdf(drv); only_src, only_back = diff(src, back)
    print(f"   lost: {len(only_src)} triples  mapping losses: {dict(loss)}")
    for x in sorted(only_src): print("     lost  :", x[:160])

    print("\n[3] SHACL governance on the RDF side (2 defects injected)")
    shacl()
    drv.close()
