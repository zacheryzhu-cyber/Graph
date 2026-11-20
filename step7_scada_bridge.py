"""Stage 7 — getting values out of SCADA and giving them graph context.

Pattern from SUMMARY.md §4: live values go to a historian; the graph holds tag identity and topology; the two
are joined by tag name; only slow state (alarm active) is written into the graph.

  OPC UA server ──subscribe──► bridge ──batch insert──► historian (SQLite here; a TSDB/WinCC OA archive in real life)
  (simulated WinCC OA tags)       │
                                  └─ rule fires (chiller supply temp too high) ──► graph:
                                       1. tag → datapoint → asset → impacted tools   (RDF 1.2 / SPARQL and Neo4j / Cypher)
                                       2. write the alarm as slow state into both graphs
                                       3. join impacted tools back to the historian by tag (latest PowerDraw)

Run:   python step7_scada_bridge.py                     (built-in OPC UA simulator, ~8 s)
       DURATION=20 python step7_scada_bridge.py
Real server (e.g. the WinCC OA OPC UA server, or any OPC UA server):
       OPCUA_URL=opc.tcp://host:4840 OPCUA_NS=urn:your:namespace OPCUA_ID_FMT='{tag}' python step7_scada_bridge.py
       The node id of each tag is OPCUA_ID_FMT.format(tag=<fab:winccTag>) in namespace OPCUA_NS.
       Find the real pattern by browsing the server once (e.g. UaExpert) and adjust OPCUA_ID_FMT.
Neo4j is optional: when bolt://127.0.0.1:7687 is reachable it is (re)loaded with SCALE=1 and used too.
Needs: pip install asyncua"""
import asyncio, logging, math, os, random, sqlite3, time
from collections import defaultdict

from asyncua import Client, Server, ua

from common import OUT, TOOL_TYPES, check, load, save_metrics
from rdf_common import N, build, rows, store_from

logging.getLogger("asyncua").setLevel(logging.ERROR)
DURATION = float(os.environ.get("DURATION", 8))
EXTERNAL = os.environ.get("OPCUA_URL")
URL = EXTERNAL or "opc.tcp://127.0.0.1:4841/fab/"
NS_URI = os.environ.get("OPCUA_NS", "urn:fab-graph-lab")
ID_FMT = os.environ.get("OPCUA_ID_FMT", "{tag}")
HOT_ASSET, HOT_SIGNAL, LIMIT = "CH-B01-01", "SupplyTemp", 10.0   # rule: chiller supply water above 10 degC
HISTORIAN = OUT / "historian.sqlite"


def baseline(sig: str) -> float:
    return {"SupplyTemp": 7.0, "ReturnTemp": 13.0, "Power": 450.0, "State": 1.0, "ChuckTemp": 22.0,
            "Vacuum": 1e-3, "PowerDraw": 80.0}.get(sig, 0.0)


# ---------------------------------------------------------------- simulated SCADA (stands in for WinCC OA)
async def simulator(tags: dict, ready: asyncio.Event, stop: asyncio.Event):
    """OPC UA server exposing one variable per datapoint, node id = ns=<idx>;s=<WinCC OA style tag>.
    All values update every 100 ms; after 40 % of the run the hot chiller's supply temperature ramps past the limit."""
    srv = Server()
    await srv.init()
    srv.set_endpoint(URL)
    srv.set_security_policy([ua.SecurityPolicyType.NoSecurity])   # lab only; real plants: Basic256Sha256 + certificates
    idx = await srv.register_namespace(NS_URI)
    fab = await srv.nodes.objects.add_object(idx, "Fab")
    nodes = {}
    for tag, sig in tags.items():
        nodes[tag] = await fab.add_variable(ua.NodeId(ID_FMT.format(tag=tag), idx), ua.QualifiedName(tag, idx), baseline(sig))
    rnd, t0 = random.Random(7), time.monotonic()
    async with srv:
        ready.set()
        while not stop.is_set():
            el = (time.monotonic() - t0) / DURATION
            for tag, sig in tags.items():
                v = baseline(sig) * (1 + rnd.uniform(-0.01, 0.01))
                if tag.endswith(f"{HOT_ASSET.replace('-', '_')}.{HOT_SIGNAL}") and el > 0.4:
                    v = baseline(sig) + 8 * min(1.0, (el - 0.4) / 0.3)          # 7 → 15 degC excursion
                await nodes[tag].write_value(ua.Variant(round(v, 4), ua.VariantType.Double))
            await asyncio.sleep(0.1)


# ---------------------------------------------------------------- graph side
class Graphs:
    def __init__(self, d):
        self.rdf = store_from(build(d, "rdf12"))
        self.neo = None
        try:
            from neo_common import driver, load_lpg, wipe
            drv = driver()
            wipe(drv); load_lpg(drv, d); self.neo = drv
        except SystemExit as e:
            print(f"  (Neo4j skipped: {str(e).split('.')[0]})")

    def context(self, tag):
        """tag → asset → every production tool downstream (any medium), with each tool's PowerDraw tag."""
        q = f"""SELECT DISTINCT ?asset ?tool ?ptag WHERE {{
          ?dp fab:winccTag "{tag}" . ?asset fab:hasDatapoint ?dp .
          ?asset fab:feeds+ ?tool . ?tool a/rdfs:subClassOf* fab:ProductionTool .
          ?tool fab:hasDatapoint ?pdp . ?pdp fab:winccTag ?ptag . FILTER(STRENDS(?ptag, ".PowerDraw"))
        }} ORDER BY ?tool"""
        out = {"rdf12": rows(self.rdf, q)}
        if self.neo:
            rec, _, _ = self.neo.execute_query(
                """MATCH (dp:Datapoint {tag: $tag})<-[:HAS_DATAPOINT]-(asset)-[:FEEDS*]->(tool:ProductionTool)
                   MATCH (tool)-[:HAS_DATAPOINT]->(p:Datapoint) WHERE p.tag ENDS WITH '.PowerDraw'
                   RETURN DISTINCT asset.id AS asset, tool.id AS tool, p.tag AS ptag ORDER BY tool""", tag=tag)
            out["neo4j"] = [[r["asset"], r["tool"], r["ptag"]] for r in rec]
        return out

    def raise_alarm(self, tag, value, ts):
        """Slow state only: one alarm node per excursion, never the sample stream."""
        aid = "ALM-LIVE-" + tag.split(":")[1].replace(".", "-")
        self.rdf.update(f"""PREFIX fab: <http://example.org/fab#>
          INSERT {{ fab:{aid} a fab:Alarm ; fab:severity "major" ; fab:active true ; fab:raisedAt "{ts}" ;
                     fab:value {value} ; fab:raisedOn ?dp }}
          WHERE {{ ?dp fab:winccTag "{tag}" }}""")
        if self.neo:
            self.neo.execute_query("""MATCH (dp:Datapoint {tag: $tag})
                MERGE (a:Entity:Alarm {id: $aid}) SET a.severity='major', a.active=true, a.raised=$ts, a.value=$v, a.type='Alarm'
                MERGE (a)-[:RAISED_ON]->(dp)""", tag=tag, aid=aid, ts=ts, v=value)
        return aid


def truth_impacted(d, asset):
    adj = defaultdict(set)
    for e in d["edges"]:
        if e["type"] == "feeds": adj[e["src"]].add(e["dst"])
    seen, todo = set(), [asset]
    while todo:
        for y in adj[todo.pop()] - seen: seen.add(y); todo.append(y)
    types = {n["id"]: n["type"] for n in d["nodes"]}
    return sorted(x for x in seen if types[x] in TOOL_TYPES)


# ---------------------------------------------------------------- the bridge
async def main():
    d = load(1)
    tags = {n["tag"]: n["id"].rsplit(".", 1)[1] for n in d["nodes"] if n["type"] == "Datapoint"}
    hot_tag = next(t for t in tags if t.endswith(f"{HOT_ASSET.replace('-', '_')}.{HOT_SIGNAL}"))
    print(f"{len(tags)} SCADA tags in the graph, e.g. {hot_tag}")
    g = Graphs(d)

    HISTORIAN.unlink(missing_ok=True)
    db = sqlite3.connect(HISTORIAN)
    db.execute("CREATE TABLE samples (tag TEXT, ts REAL, value REAL)")
    db.execute("CREATE INDEX samples_tag_ts ON samples (tag, ts)")
    buf, lat, fired, m = [], [], {}, {}
    stop, ready = asyncio.Event(), asyncio.Event()
    sim = None
    if not EXTERNAL:
        sim = asyncio.create_task(simulator(tags, ready, stop))
        await asyncio.wait_for(ready.wait(), 30)

    class Handler:
        def datachange_notification(self, node, val, data):
            tag = node2tag[node.nodeid.Identifier]
            src = data.monitored_item.Value.SourceTimestamp
            now = time.time()
            if src: lat.append(now - src.timestamp())
            buf.append((tag, now, float(val)))
            if tag == hot_tag and val > LIMIT and tag not in fired:
                fired[tag] = (val, now)

    t_start = time.monotonic()
    async with Client(URL) as cl:
        idx = await cl.get_namespace_index(NS_URI)
        node2tag = {ID_FMT.format(tag=t): t for t in tags}
        nodes = [cl.get_node(ua.NodeId(i, idx)) for i in node2tag]
        sub = await cl.create_subscription(100, Handler())
        await sub.subscribe_data_change(nodes, queuesize=10)
        print(f"subscribed to {len(nodes)} tags at {URL}")
        handled = False
        while time.monotonic() - t_start < DURATION:
            await asyncio.sleep(0.25)
            if buf:   # historian: batched inserts, never one transaction per sample
                db.executemany("INSERT INTO samples VALUES (?,?,?)", buf); db.commit(); buf.clear()
            if fired and not handled:
                handled = True
                val, t_detect = fired[hot_tag]
                t0 = time.perf_counter()
                ctx = g.context(hot_tag)
                aid = g.raise_alarm(hot_tag, round(val, 2), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_detect)))
                m["context_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                print(f"\nRULE  {hot_tag} = {val:.2f} degC > {LIMIT}  → alarm {aid} written to graph(s)")
                want = truth_impacted(d, HOT_ASSET)
                for eng, r in ctx.items():
                    check(f"impacted tools via {eng}", sorted({x[1] for x in r}), want)
                # join back to the historian by tag name
                print(f"  {len(want)} tools are downstream of {HOT_ASSET} (power or cooling); latest power draw from the historian:")
                for _, tool, ptag in ctx["rdf12"][:6]:
                    v = db.execute("SELECT value FROM samples WHERE tag=? ORDER BY ts DESC LIMIT 1", (ptag,)).fetchone()
                    print(f"    {tool:12s} {ptag:34s} {v[0] if v else float('nan'):7.1f} kW")
                if len(want) > 6: print(f"    … {len(want) - 6} more")
                m["impacted_tools"] = len(want)
        await sub.delete()
    if buf: db.executemany("INSERT INTO samples VALUES (?,?,?)", buf); db.commit()
    stop.set()
    if sim: await sim

    n = db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    lat.sort()
    m.update(samples=n, samples_per_s=round(n / DURATION), tags=len(tags),
             latency_p50_ms=round(lat[len(lat) // 2] * 1000, 1) if lat else None,
             latency_p95_ms=round(lat[int(len(lat) * .95)] * 1000, 1) if lat else None,
             graph_alarm_rows_rdf=len(rows(g.rdf, 'SELECT ?a WHERE { ?a a fab:Alarm ; fab:active true }')),
             rule_fired=bool(fired))
    print(f"\nhistorian {HISTORIAN.name}: {n} samples ({m['samples_per_s']}/s) from {len(tags)} tags; "
          f"source→historian latency p50 {m['latency_p50_ms']} ms, p95 {m['latency_p95_ms']} ms")
    print(f"graph got {1 if fired else 0} write for {n} samples (only the alarm); context lookup + alarm write "
          f"{m.get('context_ms')} ms")
    save_metrics("scada_bridge", m)
    if not fired: raise SystemExit("rule never fired — increase DURATION")


if __name__ == "__main__":
    asyncio.run(main())
