"""Stage 6 — bottlenecks: redundancy path explosion, SCADA write rate, consolidated scale table.
Needs Neo4j (./neo4j_embedded/run.sh). Run: python step6_bottlenecks.py"""
import json, time
import pyoxigraph as ox
from neo4j.exceptions import ClientError
from common import OUT
from rdf_common import N, lit, rows
from neo_common import driver, wipe


def mesh(k):
    """2N redundant distribution: k layers, 2 nodes each, every node feeds both nodes of the next layer → 2^k paths."""
    edges = [("SRC", f"L1_{j}") for j in "ab"]
    for i in range(1, k):
        edges += [(f"L{i}_{a}", f"L{i+1}_{b}") for a in "ab" for b in "ab"]
    edges += [(f"L{k}_{a}", "SINK") for a in "ab"]
    return edges


def path_explosion(drv):
    print("[1] Redundancy path explosion — 2N mesh with k layers (2^k distinct paths SRC → SINK)")
    print(f"   {'k':>3} {'paths':>9} | {'SPARQL feeds+ (reach)':>22} | {'Cypher DISTINCT reach':>22} | {'Cypher count(paths)':>22} | {'Cypher shortestPath':>20}")
    res = []
    for k in [8, 12, 16, 18, 20, 22]:
        E = mesh(k)
        st = ox.Store(); st.bulk_extend(ox.Quad(N(a), N("feeds"), N(b)) for a, b in E)
        t = time.perf_counter(); r = rows(st, "SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { fab:SRC fab:feeds+ ?x }"); sp = (time.perf_counter() - t) * 1000
        wipe(drv)
        drv.execute_query("UNWIND $e AS e MERGE (a:M {id:e[0]}) MERGE (b:M {id:e[1]}) CREATE (a)-[:FEEDS]->(b)", e=[list(x) for x in E])

        def cy(q, timeout=20):
            t = time.perf_counter()
            try:
                with drv.session() as s:
                    v = s.run(q, timeout=timeout).single()[0]
                return v, (time.perf_counter() - t) * 1000
            except ClientError as ex:
                return "TIMEOUT" if "timeout" in str(ex).lower() or "terminated" in str(ex).lower() else type(ex).__name__, None
        reach = cy("MATCH (:M {id:'SRC'})-[:FEEDS*]->(x) RETURN count(DISTINCT x)")
        paths = cy("MATCH p = (:M {id:'SRC'})-[:FEEDS*]->(:M {id:'SINK'}) RETURN count(p)") if k <= 20 else ("skipped", None)
        short = cy("MATCH p = shortestPath((:M {id:'SRC'})-[:FEEDS*]->(:M {id:'SINK'})) RETURN length(p)")
        f = lambda r: f"{r[0]} in {r[1]:.0f} ms" if r[1] is not None else str(r[0])
        print(f"   {k:>3} {2**k:>9} | {r[0][0] + ' in ' + format(sp, '.1f') + ' ms':>22} | {f(reach):>22} | {f(paths):>22} | {f(short):>20}")
        res.append({"k": k, "paths": 2**k, "sparql_reach_ms": sp, "cypher_reach_ms": reach[1], "cypher_paths_ms": paths[1], "cypher_paths": paths[0], "cypher_short_ms": short[1]})
    return res


def scada_writes(drv, n=5000, rounds=3):
    print(f"\n[2] SCADA live-value writes: update {n} datapoint values per 'tick'")
    tags = [f"DP{i}" for i in range(n)]
    st = ox.Store()   # NB: in-memory, no durability — Neo4j below writes a durable transaction log
    st.bulk_extend(ox.Quad(N(t), N("value"), lit(0.0)) for t in tags)
    t = time.perf_counter()
    for r in range(rounds):
        st.update("PREFIX fab: <http://example.org/fab#> DELETE { ?d fab:value ?v } INSERT { ?d fab:value ?nv } "
                  f"WHERE {{ ?d fab:value ?v BIND(?v + 1.0 AS ?nv) }}")
    ox_rate = n * rounds / (time.perf_counter() - t)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:          # durable, on-disk RocksDB store — fair vs Neo4j's transaction log
        dst = ox.Store(tmp); dst.bulk_extend(ox.Quad(N(x), N("value"), lit(0.0)) for x in tags); dst.flush()
        t = time.perf_counter()
        for r in range(rounds):
            dst.update("PREFIX fab: <http://example.org/fab#> DELETE { ?d fab:value ?v } INSERT { ?d fab:value ?nv } "
                       "WHERE { ?d fab:value ?v BIND(?v + 1.0 AS ?nv) }")
        ox_disk = n * rounds / (time.perf_counter() - t)
        t = time.perf_counter()
        for x in tags[:500]:
            dst.update(f"PREFIX fab: <http://example.org/fab#> DELETE {{ fab:{x} fab:value ?v }} INSERT {{ fab:{x} fab:value 1.0 }} WHERE {{ fab:{x} fab:value ?v }}")
        ox_single = 500 / (time.perf_counter() - t)
        del dst
    wipe(drv); drv.execute_query("UNWIND $t AS t CREATE (:DP {id:t, value:0.0})", t=tags)
    drv.execute_query("CREATE INDEX dp_id IF NOT EXISTS FOR (d:DP) ON (d.id)")
    drv.execute_query("CALL db.awaitIndexes(60)")   # index builds async — without this, SETs label-scan (measured: 1.6k/s)
    t = time.perf_counter()
    for r in range(rounds):
        drv.execute_query("UNWIND $rows AS r MATCH (d:DP {id:r.id}) SET d.value = r.v", rows=[{"id": x, "v": float(r)} for x in tags])
    neo_batch = n * rounds / (time.perf_counter() - t)
    t = time.perf_counter()
    for x in tags[:500]:
        drv.execute_query("MATCH (d:DP {id:$id}) SET d.value = $v", id=x, v=1.0)
    neo_single = 500 / (time.perf_counter() - t)
    print(f"   Oxigraph SPARQL UPDATE (batched, in-memory) : {ox_rate:>10,.0f} values/s")
    print(f"   Oxigraph SPARQL UPDATE (batched, on-disk)   : {ox_disk:>10,.0f} values/s")
    print(f"   Oxigraph one UPDATE per value (on-disk)     : {ox_single:>10,.0f} values/s")
    print(f"   Neo4j UNWIND batch SET                      : {neo_batch:>10,.0f} values/s")
    print(f"   Neo4j one transaction per value change      : {neo_single:>10,.0f} values/s")
    print("   (a mid-size fab WinCC OA system: ~100k–1M tags; at 1 Hz on 10 % of them = 10k–100k changes/s)")
    return {"oxigraph_disk_batch": ox_disk, "oxigraph_disk_single": ox_single, "oxigraph_batch": ox_rate, "neo4j_batch": neo_batch, "neo4j_single_tx": neo_single}


def rel_index(drv, sc=50):
    """Q3 filters on a RELATIONSHIP property. Neo4j 5 can index relationship properties — does it help?"""
    from common import load, timed
    from neo_common import load_lpg
    print(f"\n[4] Relationship-property index (Neo4j 5) on FEEDS.source — Q3 at SCALE={sc}")
    wipe(drv); load_lpg(drv, load(sc))
    q = "MATCH (s)-[f:FEEDS]->(d) WHERE f.source = 'BIM' AND f.confidence < 0.8 RETURN s.id, d.id, f.confidence"
    def srv():
        _, summ, _ = drv.execute_query(q); return summ.result_available_after + summ.result_consumed_after
    def ops(p): return [p["operatorType"].split("@")[0]] + [o for c in p.get("children", []) for o in ops(c)]
    out = {}
    for label in ["no index", "with index"]:
        if label == "with index":
            drv.execute_query("CREATE INDEX feeds_source IF NOT EXISTS FOR ()-[f:FEEDS]-() ON (f.source)")
            drv.execute_query("CALL db.awaitIndexes(60)")
        _, ms = timed(lambda: drv.execute_query(q), repeat=15)
        server = sorted(srv() for _ in range(15))[7]
        plan = ops(drv.execute_query("EXPLAIN " + q)[1].plan)
        print(f"   {label:10s}: client p50 {ms:6.1f} ms | server p50 {server:3d} ms | plan leaf: {plan[-1]}")
        out[label] = {"client_ms": ms, "server_ms": server, "leaf": plan[-1]}
    drv.execute_query("DROP INDEX feeds_source IF EXISTS")
    return out


def table():
    m = json.loads((OUT / "metrics.json").read_text())
    qs = ["Q1", "Q1b", "Q2", "Q3", "Q4", "Q5", "Q6"]
    lines = ["| model | SCALE | size | load ms | " + " | ".join(qs) + " | Q6 prep | correct |",
             "|---|---|---|---|" + "---|" * len(qs) + "---|---|"]
    for model in ["rdf_plain", "rdf_star", "lpg_neo4j"]:
        for sc, v in sorted(m.get(model, {}).items(), key=lambda x: int(x[0])):
            size = f"{v['triples']:,} triples" if "triples" in v else f"{v['nodes']:,} n / {v['relationships']:,} r"
            def q(k):
                if k + "_ms" not in v: return "—"
                cell = f"{v[k+'_ms']:.1f}/{v.get(k+'_p95', float('nan')):.1f}"
                return cell + (f" (srv {v[k+'_server_ms']})" if k + "_server_ms" in v else "")
            prep = f"{v['Q6_prep_ms']:.0f}" if "Q6_prep_ms" in v else "not needed"
            lines.append(f"| {model} | {sc} | {size} | {v['load_ms']} | " + " | ".join(q(k) for k in qs) + f" | {prep} | {'✓' if v['all_correct'] else '✗'} |")
    md = ("Cells: p50/p95 ms over 15 runs after 1 warm-up. Neo4j cells are client-side incl. Bolt; srv = server-reported.\n"
          "Q1b = traversal-first rewrite of Q1 (RDF only). Q6 prep = one-off materialisation of fab:feedsPower that RDF needs for Q6.\n\n"
          + "\n".join(lines))
    (OUT / "comparison.md").write_text(md + "\n")
    print("\n[3] Consolidated scale table\n" + md)


if __name__ == "__main__":
    drv = driver()
    r = {"explosion": path_explosion(drv), "writes": scada_writes(drv), "rel_index": rel_index(drv, 200)}
    (OUT / "bottlenecks.json").write_text(json.dumps(r, indent=1))
    table()
    drv.close()
