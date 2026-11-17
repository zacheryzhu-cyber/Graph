"""Stage 5b — what REAL neosemantics (n10s) 5.26 does with RDF 1.2, verified against its source and its parser.

Facts this script relies on (checked, not remembered):
  * n10s 5.26.0 bundles rdf4j 4.3.12 (pom.xml `sesame.version`). That parser rejects RDF 1.2 syntax `<<( )>>` and `~ {| |}`
    → proven by ./n10s_parser_check/run.sh (Maven Central jar, same version).
  * RDFToLPGStatementProcessor.java:406-449 — a quoted triple as SUBJECT becomes a relationship + relationship properties;
    a triple as OBJECT (the RDF 1.2 `rdf:reifies` form) is ignored; and for `<< s p o >> :q v` it calls addStatement(),
    i.e. it CREATES the edge although RDF-star says a quoted triple is not asserted.
So the only route is: down-convert RDF 1.2 → RDF-star 2021 Turtle-star, then import. This script does that and shows the cost.
Needs Neo4j (./neo4j_embedded/run.sh). Run: python step5b_n10s_compat.py"""
import shutil, subprocess
from collections import defaultdict
import pyoxigraph as ox
from common import load, ground_truth, OUT, FAB
from rdf_common import build, store_from, N, REIFIES, lit, rows
from neo_common import driver, wipe

TTL_PREFIX = f"@prefix fab: <{FAB}> .\n"


def nt(term):  # Turtle-star term
    return f"fab:{term.value[len(FAB):]}" if isinstance(term, ox.NamedNode) and term.value.startswith(FAB) else str(term)


def downconvert(store):
    """RDF 1.2 → RDF-star 2021 Turtle-star (the only form n10s 5.26 can read). Returns text + what got lost."""
    lines, reif, losses = [], defaultdict(list), defaultdict(int)
    for q in store:
        if isinstance(q.object, ox.Triple): reif[q.subject].append(q.object); continue
        lines.append(None)  # placeholder, filled below
    reifier_of = {r: ts[0] for r, ts in reif.items()}
    out, per_triple = [], defaultdict(set)
    for q in store:
        if isinstance(q.object, ox.Triple): continue
        if q.subject in reifier_of:
            t = reifier_of[q.subject]; per_triple[str(t)].add(q.subject)
            out.append(f"<< {nt(t.subject)} {nt(t.predicate)} {nt(t.object)} >> {nt(q.predicate)} {q.object} .")
        else:
            out.append(f"{nt(q.subject)} {nt(q.predicate)} {nt(q.object)} .")
    asserted = {str(ox.Triple(q.subject, q.predicate, q.object)) for q in store if not isinstance(q.object, ox.Triple)}
    losses["reifier identities dropped (e.g. fab:feed/e12 → anonymous)"] = len(reifier_of)
    losses["triples with >1 reifier: per-source props merged onto one quoted triple"] = sum(len(v) > 1 for v in per_triple.values())
    losses["UNASSERTED claims that n10s will materialise as real edges"] = sum(k not in asserted for k in per_triple)
    return TTL_PREFIX + "\n".join(out) + "\n", dict(losses)


def n10s_import(drv, ttl_store_view):
    """Faithful port of the n10s mapping (RDFToLPGStatementProcessor) for the statement shapes we produce:
    subject-triple → MERGE rel + SET rel prop (handleMultival default OVERWRITE); literal → node prop; IRI → rel; rdf:type → label."""
    wipe(drv)
    drv.execute_query("CREATE CONSTRAINT res_uri IF NOT EXISTS FOR (n:Resource) REQUIRE n.uri IS UNIQUE")
    nodes, rels, relprops = defaultdict(lambda: [set(), {}]), set(), defaultdict(dict)
    for kind, s, p, o in ttl_store_view:
        if kind == "quoted":
            (ts, tp, to) = s; nodes[ts]; nodes[to]; rels.add((ts, tp, to)); relprops[(ts, tp, to)][p] = o
        elif p == "type": nodes[s][0].add(o)
        elif isinstance(o, tuple): nodes[s][1][p] = o[1]
        else: nodes[s]; nodes[o]; rels.add((s, p, o))
    by_lab = defaultdict(list)
    for u, (labs, props) in nodes.items(): by_lab[":".join(sorted({"fab__" + l for l in labs} | {"Resource"}))].append(props | {"uri": FAB + u})
    for labs, r in by_lab.items():
        drv.execute_query(f"UNWIND $r AS x CREATE (n:`{labs.replace(':', '`:`')}`) SET n = x", r=r)
    by_type = defaultdict(list)
    for (s, p, o) in rels: by_type[p].append({"s": FAB + s, "o": FAB + o, "p": relprops.get((s, p, o), {})})
    for p, r in by_type.items():
        drv.execute_query(f"UNWIND $r AS x MATCH (a:Resource {{uri:x.s}}), (b:Resource {{uri:x.o}}) MERGE (a)-[e:{p}]->(b) SET e += x.p", r=r)


def view(store):
    """Read back the down-converted data the way n10s sees it (quoted triple as subject)."""
    reifier_of = {q.subject: q.object for q in store if isinstance(q.object, ox.Triple)}
    loc = lambda t: t.value.split("#", 1)[1] if isinstance(t, ox.NamedNode) and "#" in t.value else t.value
    for q in store:
        if isinstance(q.object, ox.Triple): continue
        val = ("lit", q.object.value if q.object.datatype.value.endswith("string") else
               (float(q.object.value) if "." in q.object.value else (q.object.value == "true" if q.object.value in ("true", "false") else int(q.object.value)))) \
            if isinstance(q.object, ox.Literal) else loc(q.object)
        if q.subject in reifier_of:
            t = reifier_of[q.subject]
            yield "quoted", (loc(t.subject), loc(t.predicate), loc(t.object)), loc(q.predicate), val[1] if isinstance(val, tuple) else val
        else:
            yield "plain", loc(q.subject), loc(q.predicate), val


if __name__ == "__main__":
    d = load(1); gt = ground_truth(d); drv = driver()
    st = store_from(build(d, "rdf12"))
    # A BIM claim (NOT asserted in the operational graph) that a SWG-A-side PDU also powers a tool that is in reality
    # fed only from SWG-B → if materialised, it fakes redundancy and hides a single point of failure.
    swg_of = {r[0]: r[1] for r in rows(st, """SELECT ?t ?sw WHERE { ?sw a fab:Switchgear . ?sw fab:feeds+ ?t .
                 ?t a/rdfs:subClassOf* fab:ProductionTool . ?sw fab:feeds ?u . ?u a fab:UPS . ?u fab:feeds+ ?t }""")}
    victim = next(t for t in gt["Q6"] if swg_of.get(t) == "SWG-B01-B")
    claim = ox.BlankNode()
    st.add(ox.Quad(claim, REIFIES, ox.Triple(N("PDU-B01-01"), N("feeds"), N(victim))))
    for p, v in [("sourceSystem", "BIM"), ("confidence", 0.55), ("medium", "power")]: st.add(ox.Quad(claim, N(p), lit(v)))
    print(f"[1] Injected an UNASSERTED BIM claim: PDU-B01-01 (SWG-A side) feeds {victim} (really only fed from SWG-B)")
    print(f"    RDF 1.2 view — is the edge asserted? {bool(st.query(f'ASK {{ <{FAB}PDU-B01-01> <{FAB}feeds> <{FAB}{victim}> }}'))}")

    ttl, losses = downconvert(st)
    path = OUT / "fab_for_n10s.ttls"; path.write_text(ttl)
    print(f"\n[2] Down-converted RDF 1.2 → RDF-star 2021 Turtle-star: {path.relative_to(OUT.parent)} ({len(ttl.splitlines())} lines)")
    for k, v in losses.items(): print(f"    {v:>4}  {k}")
    if shutil.which("java") and (OUT.parent / "n10s_parser_check/target/lib").exists():
        r = subprocess.run([str(OUT.parent / "n10s_parser_check/run.sh"), str(path)], capture_output=True, text=True)
        print("    rdf4j 4.3.12 (n10s 5.26 parser):", (r.stdout or r.stderr).strip().splitlines()[-1])

    ts = ox.Store(); ts.load(ttl.encode(), ox.RdfFormat.TURTLE)   # re-read (legacy << >> → reifier) to drive the port
    n10s_import(drv, list(view(ts)))
    print("\n[3] Imported with n10s 5.26 semantics into Neo4j. Single-point-of-failure audit (Q6):")
    q6 = """MATCH (sw:fab__Switchgear) (()-[f:feeds WHERE f.medium = 'power']->())+ (t)
            WHERE t:fab__EUVScanner OR t:fab__EtchTool OR t:fab__CVDTool OR t:fab__CMPTool OR t:fab__MetrologyTool
            WITH t, count(DISTINCT sw) AS n WHERE n = 1 RETURN t.uri AS t"""
    found = {r["t"].split("#")[1] for r in drv.execute_query(q6)[0]}
    print(f"    ground truth SPOF tools: {len(gt['Q6'])}   n10s-imported graph reports: {len(found)}")
    print(f"    missed (hidden by the materialised BIM claim): {sorted(set(gt['Q6']) - found)}")
    e = drv.execute_query(f"MATCH (:Resource {{uri:'{FAB}PDU-B01-01'}})-[f:feeds]->(:Resource {{uri:'{FAB}{victim}'}}) RETURN properties(f) AS p")[0]
    print(f"    the phantom edge in Neo4j: {e[0]['p'] if e else 'none'}")
    drv.close()
