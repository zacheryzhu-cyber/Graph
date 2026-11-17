"""Stage 4 — the same use case as a labelled property graph in Neo4j 5.26, queried with Cypher.
Needs Neo4j on bolt://127.0.0.1:7687 → ./neo4j_embedded/run.sh
Run: python step4_lpg_neo4j.py   (SCALE=n env var for bigger data)"""
import time
from common import load, ground_truth, timed, check, save_metrics, TRIP_SOURCE, scale
from neo_common import driver, wipe, load_lpg

Q = {
 "Q1": """MATCH (:Entity {id: $src})-[:FEEDS*]->(t:ProductionTool) RETURN DISTINCT t.id AS t ORDER BY t""",
 "Q2": """MATCH (s)-[f:FEEDS]->(d) WHERE f.redundant = false AND f.installed < 2018 AND f.load_kw / f.capacity_kw > 0.7
          RETURN s.id AS s, d.id AS d ORDER BY s, d""",
 "Q3": """MATCH (s)-[f:FEEDS]->(d) WHERE f.source = 'BIM' AND f.confidence < 0.8
          RETURN s.id AS s, d.id AS d, f.confidence AS c ORDER BY s, d""",
 "Q4": """MATCH p = shortestPath((:Entity {id: $src})-[:FEEDS*]->(:Entity {id: $dst}))
          RETURN [n IN nodes(p) | n.id] AS path""",
 "Q5": """MATCH (a:Area)<-[:LOCATED_IN]-(:Asset)-[:HAS_DATAPOINT]->(dp)
          OPTIONAL MATCH (al:Alarm {active: true})-[:RAISED_ON]->(dp)
          RETURN a.id AS a, count(DISTINCT dp) AS n, count(DISTINCT al) AS c ORDER BY a""",
}


def run_queries(drv, gt):
    params = {"src": TRIP_SOURCE, "dst": gt["Q4_target"]}
    m, ok = {}, True

    def q(name):
        def f():
            recs, summary, _ = drv.execute_query(Q[name], params)
            f.server_ms = summary.result_available_after + summary.result_consumed_after
            return [r.values() for r in recs]
        res, ms = timed(f)
        m[f"{name}_ms"] = ms; m[f"{name}_server_ms"] = f.server_ms
        return res

    r = q("Q1"); ok &= check(f"Q1 impact: {len(r)} tools", [x[0] for x in r], gt["Q1"])
    r = q("Q2"); ok &= check(f"Q2 edge-property filter: {len(r)} feeds", [tuple(x) for x in r], gt["Q2"])
    r = q("Q3"); ok &= check(f"Q3 provenance: {len(r)} BIM links", [tuple(x) for x in r], gt["Q3"])
    r = q("Q4"); ok &= check(f"Q4 path (len {len(r[0][0]) - 1}): {' → '.join(r[0][0])}", len(r[0][0]) - 1, gt["Q4_len"])
    r = q("Q5"); ok &= check(f"Q5 aggregate: {len(r)} areas", [tuple(x) for x in r], gt["Q5"])
    m["all_correct"] = ok
    return m


if __name__ == "__main__":
    d = load(); gt = ground_truth(d); drv = driver()
    wipe(drv)
    t = time.perf_counter(); load_lpg(drv, d); load_ms = (time.perf_counter() - t) * 1000
    nodes = drv.execute_query("MATCH (n) RETURN count(n) AS c")[0][0]["c"]
    rels = drv.execute_query("MATCH ()-[r]->() RETURN count(r) AS c")[0][0]["c"]
    props = drv.execute_query("MATCH ()-[f:FEEDS]->() RETURN count(f) AS c")[0][0]["c"]
    print(f"[LPG Neo4j] SCALE={scale()}  nodes={nodes} relationships={rels} (FEEDS with props: {props})  load={load_ms:.0f} ms")
    m = run_queries(drv, gt)
    m.update(nodes=nodes, relationships=rels, load_ms=round(load_ms))
    for k, v in m.items(): print(f"   {k:16s} {v if not isinstance(v, float) else round(v, 2)}")
    plan = drv.execute_query("EXPLAIN " + Q["Q1"], {"src": TRIP_SOURCE})[1].plan
    def ops(p): return [p["operatorType"]] + [o for c in p.get("children", []) for o in ops(c)]
    print("   Q1 plan operators:", " ← ".join(ops(plan)))
    save_metrics("lpg_neo4j", m)
    drv.close()
