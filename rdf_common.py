"""Build RDF from the canonical JSON. Two encodings of edge metadata:
  mode="nary"  — RDF 1.1: each `feeds` edge becomes a fab:Feed node (n-ary relation pattern). No direct triple.
  mode="rdf12" — RDF 1.2: direct triple `s fab:feeds d` + reifier `r rdf:reifies <<( s fab:feeds d )>>` carrying the properties."""
import pyoxigraph as ox
from common import FAB, TOOL_TYPES

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
N = lambda local: ox.NamedNode(FAB + local)
TYPE, SUBCLASS, LABEL, REIFIES = ox.NamedNode(RDF + "type"), ox.NamedNode(RDFS + "subClassOf"), ox.NamedNode(RDFS + "label"), ox.NamedNode(RDF + "reifies")
PREFIXES = f"PREFIX fab: <{FAB}>\nPREFIX rdf: <{RDF}>\nPREFIX rdfs: <{RDFS}>\n"
PROP = {"installed": "installed", "redundant": "redundant", "capacity_kw": "capacityKW", "load_kw": "loadKW",
        "medium": "medium", "source": "sourceSystem", "confidence": "confidence", "tag": "winccTag", "unit": "unit",
        "severity": "severity", "active": "active", "raised": "raisedAt", "cleanroomClass": "cleanroomClass"}


def lit(v):
    if isinstance(v, bool): return ox.Literal("true" if v else "false", datatype=ox.NamedNode(XSD + "boolean"))
    if isinstance(v, int): return ox.Literal(str(v), datatype=ox.NamedNode(XSD + "integer"))
    if isinstance(v, float): return ox.Literal(repr(v), datatype=ox.NamedNode(XSD + "decimal"))
    return ox.Literal(v)


def ontology():
    """Tiny ontology: the class hierarchy is *data* you can query (an RDF strength)."""
    t = []
    for c in TOOL_TYPES: t.append((c, "ProductionTool"))
    for c in ["ProductionTool", "Switchgear", "UPS", "PDU", "Chiller", "CoolingLoop"]: t.append((c, "Asset"))
    for c in ["Switchgear", "UPS", "PDU"]: t.append((c, "ElectricalAsset"))
    for c in ["Chiller", "CoolingLoop"]: t.append((c, "CoolingAsset"))
    return [ox.Triple(N(a), SUBCLASS, N(b)) for a, b in t]


def build(d: dict, mode: str) -> list:
    ts = ontology()
    for n in d["nodes"]:
        s = N(n["id"])
        ts += [ox.Triple(s, TYPE, N(n["type"])), ox.Triple(s, LABEL, ox.Literal(n["name"]))]
        ts += [ox.Triple(s, N(PROP[k]), lit(v)) for k, v in n.items() if k in PROP]
    for e in d["edges"]:
        s, o = N(e["src"]), N(e["dst"])
        props = [(N(PROP[k]), lit(v)) for k, v in e.items() if k in PROP]
        if e["type"] != "feeds":
            ts.append(ox.Triple(s, N(e["type"]), o)); continue
        r = N("feed/" + e["id"])
        if mode == "nary":   # RDF 1.1: edge → node
            ts += [ox.Triple(r, TYPE, N("Feed")), ox.Triple(r, N("feedFrom"), s), ox.Triple(r, N("feedTo"), o)]
        else:                # RDF 1.2: asserted triple + reifier pointing at the triple term
            base = ox.Triple(s, N("feeds"), o)
            ts += [base, ox.Triple(r, REIFIES, base)]
        ts += [ox.Triple(r, p, v) for p, v in props]
    return ts


def store_from(triples) -> ox.Store:
    st = ox.Store()
    st.bulk_extend(ox.Quad(t.subject, t.predicate, t.object) for t in triples)
    return st


def local(term) -> str:
    if term is None: return ""
    v = term.value
    return v.split("#", 1)[1] if v.startswith("http://example.org/fab#") else v


def rows(store, q):
    return [[local(r[i]) for i in range(len(r))] for r in store.query(PREFIXES + q)]


def hops_union(hop: str, src: str, dst: str, max_depth: int = 5) -> str:
    """SPARQL cannot return a path. Common workaround: unroll depths 1..k as UNION branches, keep the shortest.
    It works, but only up to a depth you fix in advance."""
    branches = []
    for k in range(1, max_depth + 1):
        vs = ["?n0"] + [f"?n{i}" for i in range(1, k)] + ["?nk"]
        pats = " . ".join(f"{vs[i]} {hop} {vs[i+1]}" for i in range(k))
        sel = " ".join(f"BIND(STR({vs[i]}) AS ?p{i})" for i in range(1, k))
        branches.append(f"{{ {pats} . BIND({k} AS ?depth) {sel} }}")
    return (f"SELECT ?depth ?p1 ?p2 ?p3 ?p4 WHERE {{ VALUES (?n0 ?nk) {{ (fab:{src} fab:{dst}) }} "
            + " UNION ".join(branches) + " } ORDER BY ?depth LIMIT 1")
