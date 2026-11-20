"""Neo4j helpers: connect, wipe, bulk-load the canonical JSON as an LPG."""
import os
from collections import defaultdict
from neo4j import GraphDatabase
from common import TOOL_TYPES

URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")


def driver():
    # no auth by default (lab); set NEO4J_USER / NEO4J_PASSWORD for a server with a password (e.g. Neo4j Desktop)
    pw = os.environ.get("NEO4J_PASSWORD")
    d = GraphDatabase.driver(URI, auth=(os.environ.get("NEO4J_USER", "neo4j"), pw) if pw else None)
    try:
        d.verify_connectivity()
    except Exception as e:
        raise SystemExit(f"Neo4j not reachable at {URI} ({e}). Start it: ./neo4j_embedded/run.sh") from e
    return d


def extra_labels(t):
    """LPG has no subclass reasoning: the hierarchy is flattened into multiple labels at load time."""
    if t in TOOL_TYPES: return ["Asset", "ProductionTool"]
    if t in {"Switchgear", "UPS", "PDU"}: return ["Asset", "ElectricalAsset"]
    if t in {"Chiller", "CoolingLoop"}: return ["Asset", "CoolingAsset"]
    return []


def wipe(drv):
    with drv.session() as s:   # CALL {..} IN TRANSACTIONS needs an auto-commit (implicit) transaction
        s.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS").consume()


def load_lpg(drv, d, batch=5000):
    drv.execute_query("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
    by_type = defaultdict(list)
    for n in d["nodes"]:
        by_type[n["type"]].append(dict(n))   # keep `type` as a property too (handy for display)
    for t, rows in by_type.items():
        labels = ":".join(["Entity", t] + extra_labels(t))
        for i in range(0, len(rows), batch):
            drv.execute_query(f"UNWIND $rows AS r CREATE (n:{labels}) SET n = r", rows=rows[i:i + batch])
    by_rel = defaultdict(list)
    for e in d["edges"]:
        by_rel[e["type"]].append({"s": e["src"], "d": e["dst"],
                                  "p": {k: v for k, v in e.items() if k not in ("src", "dst", "type")}})
    rel_name = {"feeds": "FEEDS", "locatedIn": "LOCATED_IN", "hasDatapoint": "HAS_DATAPOINT", "raisedOn": "RAISED_ON"}
    for t, rows in by_rel.items():
        for i in range(0, len(rows), batch):
            drv.execute_query(f"""UNWIND $rows AS r MATCH (a:Entity {{id: r.s}}), (b:Entity {{id: r.d}})
                                   CREATE (a)-[x:{rel_name[t]}]->(b) SET x = r.p""", rows=rows[i:i + batch])
