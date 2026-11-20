"""Chiller plant scenario: a fab's chilled-water plant, from cooling towers to the tools and cleanroom air.

Everything the demo needs about the plant lives here: the dataset, how it becomes RDF 1.1 / RDF 1.2 / LPG,
the six operator questions with each engine's best exact method, the valve presets (live SCADA state),
the story text, and a plain-Python reference answer for each question (used by check.py; the browser has its
own independent JavaScript copy).

Rules of the comparison
  * same data, same question for every engine;
  * each engine uses its best exact method: no approximations, no strawmen;
  * extra work is counted, not hidden: precomputed predicates, multi-step scripts, upkeep when SCADA state changes.

One relationship type only: "cooling flows from A to B" (fab:flowsTo / FLOWS_TO), with the medium as a property.

The plant
  cooling towers CT-1..3 ─condenser water─► chillers CH-1..3 ─chilled water─► CHW header
  CHW header ─► valve V-HX1 ─► heat exchanger HX-1 ─► pumps P-A1, P-A2 ─► PCW loop A ─┐
  CHW header ─► valve V-HX2 ─► heat exchanger HX-2 ─► pump  P-B1      ─► PCW loop B ─┤─► tools (loop A, loop B or both)
                                      cross-tie valve V-TIE between loop A and loop B ┘ (normally closed)
  CHW header ─► valves V-MAU1/2 ─► make-up air units MAU-1/2 ─supply air─► cleanroom bays BAY-1/2
"""
import json
import re

FAB = "http://example.org/fab#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
PREFIXES = f"PREFIX fab: <{FAB}>\nPREFIX rdf: <{RDF}>\nPREFIX rdfs: <{RDFS}>\n"
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
STEP_SEP = "\n;;\n"   # separates the steps of a multi-step script (each step is one SPARQL update or query)

TYPES = {   # type: (category, plain-language explanation)
    "CoolingTower": ("plant", "Throws the plant's heat out to the air by evaporating water. Each one serves one chiller here."),
    "Chiller":      ("plant", "A refrigeration machine. Makes ~6 °C chilled water and dumps the heat into the condenser water."),
    "Header":       ("plant", "A large common pipe. All chillers feed it and every user draws from it, so it's shared by everything."),
    "Valve":        ("plant", "Open or closed; its position comes live from SCADA. A closed valve stops the flow."),
    "HeatExchanger": ("plant", "Passes cold from the chilled water to the process cooling water (PCW) without mixing them."),
    "Pump":         ("plant", "Circulates the process cooling water. Loop A has two pumps (one spare); loop B has one."),
    "CoolingLoop":  ("plant", "A PCW loop: closed piping that carries cooling past the tools."),
    "AirHandler":   ("plant", "Make-up air unit (MAU): cools and filters fresh air for the cleanroom with a chilled-water coil."),
    "EtchTool":     ("consumer", "Plasma etch tool. Needs process cooling for its chamber and RF generator."),
    "CVDTool":      ("consumer", "Chemical vapour deposition tool. Needs process cooling."),
    "CMPTool":      ("consumer", "Chemical-mechanical polishing tool. Needs process cooling."),
    "ImplantTool":  ("consumer", "Ion implanter. Needs process cooling."),
    "LithoTool":    ("consumer", "Lithography scanner. Very temperature sensitive; fed from both loops."),
    "CleanroomBay": ("consumer", "A cleanroom zone. Its air is cooled by a make-up air unit."),
}
TOOL_TYPES = ["EtchTool", "CVDTool", "CMPTool", "ImplantTool", "LithoTool"]
MEDIA = {"cw": "condenser water", "chw": "chilled water", "pcw": "process cooling water", "air": "supply air"}

NODES = [  # id, type, name, extra properties
    ("CT-1", "CoolingTower", "Cooling tower 1", {}), ("CT-2", "CoolingTower", "Cooling tower 2", {}), ("CT-3", "CoolingTower", "Cooling tower 3", {}),
    ("CH-1", "Chiller", "Chiller 1", {"capacity_kw": 1800, "mode": "running"}),
    ("CH-2", "Chiller", "Chiller 2", {"capacity_kw": 1800, "mode": "running"}),
    ("CH-3", "Chiller", "Chiller 3 (older, smaller)", {"capacity_kw": 1400, "mode": "standby"}),
    ("CHW-HDR", "Header", "Chilled-water header", {}),
    ("V-HX1", "Valve", "Valve to HX-1", {"position": "open"}), ("V-HX2", "Valve", "Valve to HX-2", {"position": "open"}),
    ("V-MAU1", "Valve", "Valve to MAU-1", {"position": "open"}), ("V-MAU2", "Valve", "Valve to MAU-2", {"position": "open"}),
    ("HX-1", "HeatExchanger", "PCW heat exchanger 1", {}), ("HX-2", "HeatExchanger", "PCW heat exchanger 2", {}),
    ("P-A1", "Pump", "Loop A pump 1", {}), ("P-A2", "Pump", "Loop A pump 2 (spare)", {}), ("P-B1", "Pump", "Loop B pump", {}),
    ("PCW-A", "CoolingLoop", "PCW loop A", {}), ("PCW-B", "CoolingLoop", "PCW loop B", {}),
    ("V-TIE", "Valve", "Cross-tie valve, loop A ↔ loop B", {"position": "closed"}),
    ("MAU-1", "AirHandler", "Make-up air unit 1", {}), ("MAU-2", "AirHandler", "Make-up air unit 2", {}),
    ("ETCH-01", "EtchTool", "Etch 1", {"design_load_kw": 250}), ("CVD-01", "CVDTool", "CVD 1", {"design_load_kw": 300}),
    ("CMP-01", "CMPTool", "CMP 1", {"design_load_kw": 200}), ("CMP-02", "CMPTool", "CMP 2", {"design_load_kw": 200}),
    ("LITH-01", "LithoTool", "Litho scanner 1", {"design_load_kw": 250}), ("ETCH-02", "EtchTool", "Etch 2", {"design_load_kw": 250}),
    ("CVD-02", "CVDTool", "CVD 2", {"design_load_kw": 300}), ("IMP-01", "ImplantTool", "Implanter 1", {"design_load_kw": 150}),
    ("BAY-1", "CleanroomBay", "Cleanroom bay 1", {"design_load_kw": 700}), ("BAY-2", "CleanroomBay", "Cleanroom bay 2", {"design_load_kw": 700}),
]
# src, dst, medium, installed, [source system, confidence]
PIPES = [
    ("CT-1", "CH-1", "cw", 2014), ("CT-2", "CH-2", "cw", 2014), ("CT-3", "CH-3", "cw", 2009),
    ("CH-1", "CHW-HDR", "chw", 2014), ("CH-2", "CHW-HDR", "chw", 2014), ("CH-3", "CHW-HDR", "chw", 2009, "P&ID", 0.88),
    ("CHW-HDR", "V-HX1", "chw", 2014), ("CHW-HDR", "V-HX2", "chw", 2014),
    ("CHW-HDR", "V-MAU1", "chw", 2014), ("CHW-HDR", "V-MAU2", "chw", 2019, "BIM", 0.72),
    ("V-HX1", "HX-1", "chw", 2014), ("V-HX2", "HX-2", "chw", 2014),
    ("V-MAU1", "MAU-1", "chw", 2014), ("V-MAU2", "MAU-2", "chw", 2019),
    ("HX-1", "P-A1", "pcw", 2014), ("HX-1", "P-A2", "pcw", 2014), ("HX-2", "P-B1", "pcw", 2014),
    ("P-A1", "PCW-A", "pcw", 2014), ("P-A2", "PCW-A", "pcw", 2014), ("P-B1", "PCW-B", "pcw", 2014),
    ("PCW-A", "V-TIE", "pcw", 2017, "P&ID", 0.9), ("V-TIE", "PCW-B", "pcw", 2017, "P&ID", 0.9),
    ("PCW-B", "V-TIE", "pcw", 2017, "P&ID", 0.9), ("V-TIE", "PCW-A", "pcw", 2017, "P&ID", 0.9),
    ("PCW-A", "ETCH-01", "pcw", 2014), ("PCW-A", "CVD-01", "pcw", 2014), ("PCW-A", "CMP-01", "pcw", 2015),
    ("PCW-A", "CMP-02", "pcw", 2015), ("PCW-B", "CMP-02", "pcw", 2015),
    ("PCW-A", "LITH-01", "pcw", 2016), ("PCW-B", "LITH-01", "pcw", 2016),
    ("PCW-B", "ETCH-02", "pcw", 2021, "BIM", 0.64), ("PCW-B", "CVD-02", "pcw", 2018), ("PCW-B", "IMP-01", "pcw", 2022, "BIM", 0.7),
    ("MAU-1", "BAY-1", "air", 2014), ("MAU-2", "BAY-2", "air", 2019, "BIM", 0.78),
]
DATAPOINTS = [  # asset, signal, unit, last value
    ("CT-1", "BasinTemp", "°C", 26.8), ("CT-2", "BasinTemp", "°C", 27.0), ("CT-3", "FanStatus", "", "fault reset"),
    ("CH-1", "LeavingTemp", "°C", 6.1), ("CH-1", "Load", "%", 82), ("CH-2", "LeavingTemp", "°C", 7.6), ("CH-2", "Load", "%", 91),
    ("CH-3", "LeavingTemp", "°C", 12.4), ("CH-3", "Load", "%", 0),
    ("CHW-HDR", "SupplyTemp", "°C", 6.6),
    ("V-HX1", "Position", "", "open"), ("V-HX2", "Position", "", "open"), ("V-MAU1", "Position", "", "open"),
    ("V-MAU2", "Position", "", "open"), ("V-TIE", "Position", "", "closed"),
    ("HX-1", "ApproachTemp", "K", 1.4), ("HX-2", "ApproachTemp", "K", 3.4),
    ("P-A1", "Vibration", "mm/s", 2.1), ("P-A2", "Vibration", "mm/s", 0.0), ("P-B1", "Vibration", "mm/s", 7.8),
    ("PCW-A", "SupplyTemp", "°C", 18.1), ("PCW-B", "SupplyTemp", "°C", 19.6),
    ("MAU-1", "FilterDP", "Pa", 180), ("MAU-2", "FilterDP", "Pa", 210),
]
ALARMS = [  # id, datapoint, text, severity, active, raised
    ("ALM-PCWB-TEMP", "PCW-B.SupplyTemp", "Loop B supply temp high: 19.6 °C (limit 19.0)", "critical", True, "2026-11-20T07:05:00Z"),
    ("ALM-PB1-VIB", "P-B1.Vibration", "Pump vibration high: 7.8 mm/s (limit 7.1)", "major", True, "2026-11-20T06:40:00Z"),
    ("ALM-HX2-APP", "HX-2.ApproachTemp", "Approach temp high: 3.4 K (limit 2.0), likely fouling", "major", True, "2026-11-19T22:10:00Z"),
    ("ALM-CH2-LWT", "CH-2.LeavingTemp", "Leaving water temp high: 7.6 °C (limit 7.0)", "warning", True, "2026-11-20T05:30:00Z"),
    ("ALM-CT3-FAN", "CT-3.FanStatus", "Fan fault (cleared)", "major", False, "2026-11-18T14:00:00Z"),
    ("ALM-MAU2-DP", "MAU-2.FilterDP", "Filter differential pressure high (cleared)", "warning", False, "2026-11-19T09:15:00Z"),
]
VALVE_PRESETS = {   # live SCADA state of the valves
    "normal": {"label": "Normal operation (cross-tie closed)", "positions": {"V-TIE": "closed"}},
    "tie-open": {"label": "Cross-tie opened", "positions": {"V-TIE": "open"}},
    "hx2-isolated": {"label": "HX-2 isolated for cleaning, cross-tie open", "positions": {"V-TIE": "open", "V-HX2": "closed"}},
}
CLAIM_DEFAULT = ("PCW-B", "ETCH-01")   # BIM shows loop B also feeding Etch 1; nobody has confirmed it


def positions(preset: str) -> dict:
    base = {i: p["position"] for i, t, _, p in NODES if t == "Valve"}
    base.update(VALVE_PRESETS[preset]["positions"]); return base


def dataset() -> dict:
    nodes, edges = [], []
    for i, t, name, extra in NODES:
        nodes.append({"id": i, "type": t, "name": name, "category": TYPES[t][0], **extra})
    conf_cycle = [0.97, 0.98, 0.95, 0.99, 0.96]
    for k, p in enumerate(PIPES):
        s, d, m, inst = p[:4]
        src, conf = (p[4], p[5]) if len(p) > 4 else ("DCS", conf_cycle[k % 5])
        edges.append({"id": f"e{k}", "src": s, "dst": d, "type": "flowsTo", "medium": m, "installed": inst, "source": src, "confidence": conf})
    for a, sig, unit, val in DATAPOINTS:
        dp = f"{a}.{sig}"
        nodes.append({"id": dp, "type": "Datapoint", "name": dp, "tag": f"CHW:{a.replace('-', '_')}.{sig}", "unit": unit, "value": val})
        edges.append({"id": f"h-{dp}", "src": a, "dst": dp, "type": "hasDatapoint"})
    for aid, dp, text, sev, active, raised in ALARMS:
        nodes.append({"id": aid, "type": "Alarm", "name": aid, "text": text, "severity": sev, "active": active, "raised": raised})
        edges.append({"id": f"r-{aid}", "src": aid, "dst": dp, "type": "raisedOn"})
    return {"scenario": "chiller", "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- RDF
PROP = {"medium": "medium", "installed": "installed", "source": "sourceSystem", "confidence": "confidence",
        "tag": "tag", "unit": "unit", "value": "value", "text": "text", "severity": "severity", "active": "active",
        "raised": "raisedAt", "capacity_kw": "capacityKW", "design_load_kw": "designLoadKW", "mode": "mode", "position": "position"}


def build_rdf(d: dict, mode: str):
    """mode 'nary' = RDF 1.1 (each pipe is a fab:Pipe node); 'rdf12' = direct fab:flowsTo triple + a reifier with the properties."""
    import pyoxigraph as ox
    N = lambda x: ox.NamedNode(FAB + x)
    TYPE, SUB, LABEL = ox.NamedNode(RDF + "type"), ox.NamedNode(RDFS + "subClassOf"), ox.NamedNode(RDFS + "label")

    def lit(v):
        if isinstance(v, bool): return ox.Literal("true" if v else "false", datatype=ox.NamedNode(XSD + "boolean"))
        if isinstance(v, int): return ox.Literal(str(v), datatype=ox.NamedNode(XSD + "integer"))
        if isinstance(v, float): return ox.Literal(repr(v), datatype=ox.NamedNode(XSD + "decimal"))
        return ox.Literal(v)

    ts = [ox.Triple(N(t), SUB, N("ProductionTool")) for t in TOOL_TYPES]
    ts += [ox.Triple(N("ProductionTool"), SUB, N("Consumer")), ox.Triple(N("CleanroomBay"), SUB, N("Consumer"))]
    ts += [ox.Triple(N(t), SUB, N("PlantEquipment")) for t, (c, _) in TYPES.items() if c == "plant"]
    for n in d["nodes"]:
        s = N(n["id"])
        ts += [ox.Triple(s, TYPE, N(n["type"])), ox.Triple(s, LABEL, ox.Literal(n["name"]))]
        ts += [ox.Triple(s, N(PROP[k]), lit(v)) for k, v in n.items() if k in PROP]
    for e in d["edges"]:
        s, o = N(e["src"]), N(e["dst"])
        if e["type"] != "flowsTo":
            ts.append(ox.Triple(s, N(e["type"]), o)); continue
        r = N("pipe/" + e["id"])
        if mode == "nary":
            ts += [ox.Triple(r, TYPE, N("Pipe")), ox.Triple(r, N("from"), s), ox.Triple(r, N("to"), o)]
        else:
            base = ox.Triple(s, N("flowsTo"), o)
            ts += [base, ox.Triple(r, ox.NamedNode(RDF + "reifies"), base)]
        ts += [ox.Triple(r, N(PROP[k]), lit(v)) for k, v in e.items() if k in PROP]
    st = ox.Store()
    st.bulk_extend(ox.Quad(t.subject, t.predicate, t.object) for t in ts)
    st.update(PREFIXES + UPDATES["recompute_open_" + ("rdf11" if mode == "nary" else "rdf12")])
    return st


# ---------------------------------------------------------------- LPG
def extra_labels(t):
    if t in TOOL_TYPES: return ["Asset", "Consumer", "ProductionTool"]
    if t == "CleanroomBay": return ["Asset", "Consumer"]
    if TYPES.get(t, ("",))[0] == "plant": return ["Asset", "PlantEquipment"]
    return []


def load_lpg(drv, d):
    from collections import defaultdict
    drv.execute_query("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
    drv.execute_query("CALL db.awaitIndexes()")
    by_type = defaultdict(list)
    for n in d["nodes"]: by_type[n["type"]].append(dict(n))
    for t, rows in by_type.items():
        drv.execute_query(f"UNWIND $rows AS r CREATE (n:{':'.join(['Entity', t] + extra_labels(t))}) SET n = r", rows=rows)
    rel = {"flowsTo": "FLOWS_TO", "hasDatapoint": "HAS_DATAPOINT", "raisedOn": "RAISED_ON"}
    by_rel = defaultdict(list)
    for e in d["edges"]: by_rel[e["type"]].append({"src": e["src"], "dst": e["dst"], "p": {k: v for k, v in e.items() if k not in ("type", "src", "dst")}})
    for t, rows in by_rel.items():
        drv.execute_query(f"UNWIND $rows AS r MATCH (a:Entity {{id: r.src}}), (b:Entity {{id: r.dst}}) CREATE (a)-[x:{rel[t]}]->(b) SET x = r.p", rows=rows)


# ---------------------------------------------------------------- the questions
OPEN = "coalesce(a.position, 'open') = 'open' AND coalesce(b.position, 'open') = 'open'"
OPEN_NOTE_RDF = "# fab:openFlow = pipes not blocked by a closed valve.\n# Precomputed, and recomputed whenever SCADA reports a valve change.\n"

QUESTIONS = [
    {
        "id": "Q1", "title": "What depends on it",
        "ask": "Which equipment and consumers get their cooling through $unit?",
        "stresses": "Following the flow downstream, through open valves only",
        "params": {"unit": {"kind": "unit", "default": "P-B1", "label": "Unit"}},
        "rdf11": OPEN_NOTE_RDF + "SELECT DISTINCT ?x WHERE {\n  fab:$unit fab:openFlow+ ?x .\n} ORDER BY ?x",
        "rdf12": OPEN_NOTE_RDF + "SELECT DISTINCT ?x WHERE {\n  fab:$unit fab:openFlow+ ?x .\n} ORDER BY ?x",
        "neo4j": "MATCH (:Entity {id: '$unit'})\n      ((a)-[:FLOWS_TO]->(b) WHERE " + OPEN + ")+\n      (x)\nRETURN DISTINCT x.id AS x ORDER BY x",
        "method": {"rdf11": "1 query + precomputed open-flow predicate", "rdf12": "1 query + precomputed open-flow predicate", "neo4j": "1 query, valve check inline"},
        "notes": {"rdf11": "A SPARQL property path can't skip closed valves, so the open pipes are worked out in advance.",
                  "rdf12": "Same as RDF 1.1 for this question.",
                  "neo4j": "The valve check sits inside the path pattern, so it always reflects the current valve positions."},
    },
    {
        "id": "Q2", "title": "Who loses cooling",
        "ask": "If $unit trips, which consumers lose cooling completely?",
        "stresses": "What-if: is there still a route from a cooling tower that avoids this unit?",
        "params": {"unit": {"kind": "unit", "default": "P-B1", "label": "Trip"}},
        "rdf11": "# Step 1 of 3: copy the open network without $unit\nINSERT { GRAPH fab:whatif { ?a fab:openFlow ?b } }\nWHERE { ?a fab:openFlow ?b FILTER(?a != fab:$unit && ?b != fab:$unit) }" + STEP_SEP +
                 "# Step 2 of 3: consumers no cooling tower reaches in the copy\nSELECT ?c WHERE {\n  ?c a/rdfs:subClassOf* fab:Consumer .\n  FILTER NOT EXISTS { ?ct a fab:CoolingTower .\n                      GRAPH fab:whatif { ?ct fab:openFlow+ ?c } }\n} ORDER BY ?c" + STEP_SEP +
                 "# Step 3 of 3: drop the copy\nDROP SILENT GRAPH fab:whatif",
        "neo4j": "MATCH (c:Consumer)\nWHERE NOT EXISTS {\n  (:CoolingTower)\n  ((a)-[:FLOWS_TO]->(b) WHERE a.id <> '$unit' AND b.id <> '$unit'\n                          AND " + OPEN + ")+\n  (c) }\nRETURN c.id AS c ORDER BY c",
        "method": {"rdf11": "3-step script: copy network without the unit, query, drop", "rdf12": "3-step script: copy network without the unit, query, drop", "neo4j": "1 query"},
        "notes": {"rdf11": "SPARQL can't say 'a route that avoids this unit' in one query. The exact way is to query a temporary copy of the network without it.",
                  "rdf12": "Identical script: RDF 1.2 adds statements about pipes, not new path features.",
                  "neo4j": "The 'avoid this unit' and 'open valves only' conditions are both written inside the path."},
    },
    {
        "id": "Q3", "title": "Chiller maintenance (N+1)",
        "ask": "With $chiller out of service, can the other chillers carry the design load?",
        "stresses": "A plain sum over properties: no graph traversal at all",
        "params": {"chiller": {"kind": "chiller", "default": "CH-3", "label": "Out of service"}},
        "rdf11": "SELECT ?remaining_kw ?load_kw (?remaining_kw - ?load_kw AS ?margin_kw) WHERE {\n  { SELECT (SUM(?cap) AS ?remaining_kw) WHERE {\n      ?ch a fab:Chiller ; fab:capacityKW ?cap . FILTER(?ch != fab:$chiller) } }\n  { SELECT (SUM(?l) AS ?load_kw) WHERE { ?c fab:designLoadKW ?l } }\n}",
        "rdf12": "SELECT ?remaining_kw ?load_kw (?remaining_kw - ?load_kw AS ?margin_kw) WHERE {\n  { SELECT (SUM(?cap) AS ?remaining_kw) WHERE {\n      ?ch a fab:Chiller ; fab:capacityKW ?cap . FILTER(?ch != fab:$chiller) } }\n  { SELECT (SUM(?l) AS ?load_kw) WHERE { ?c fab:designLoadKW ?l } }\n}",
        "neo4j": "MATCH (ch:Chiller) WHERE ch.id <> '$chiller'\nWITH sum(ch.capacity_kw) AS remaining_kw\nMATCH (c:Consumer)\nWITH remaining_kw, sum(c.design_load_kw) AS load_kw\nRETURN remaining_kw, load_kw, remaining_kw - load_kw AS margin_kw",
        "method": {"rdf11": "1 aggregate query", "rdf12": "1 aggregate query", "neo4j": "1 aggregate query"},
        "notes": {"rdf11": "Ordinary aggregation. Any database does this.", "rdf12": "Same.", "neo4j": "Same."},
    },
    {
        "id": "Q4", "title": "Single heat exchanger",
        "ask": "Which tools depend on a single PCW heat exchanger, with the valves as they are now?",
        "stresses": "Redundancy that changes when SCADA reports a valve move",
        "params": {},
        "rdf11": OPEN_NOTE_RDF + "# Count only heat exchangers that chilled water reaches right now.\nSELECT ?t WHERE {\n  ?hx a fab:HeatExchanger ; fab:openFlow+ ?t .\n  FILTER EXISTS { ?ct a fab:CoolingTower ; fab:openFlow+ ?hx }\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?hx) = 1) ORDER BY ?t",
        "rdf12": OPEN_NOTE_RDF + "# Count only heat exchangers that chilled water reaches right now.\nSELECT ?t WHERE {\n  ?hx a fab:HeatExchanger ; fab:openFlow+ ?t .\n  FILTER EXISTS { ?ct a fab:CoolingTower ; fab:openFlow+ ?hx }\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?hx) = 1) ORDER BY ?t",
        "neo4j": "// Count only heat exchangers that chilled water reaches right now.\nMATCH (hx:HeatExchanger)\nWHERE EXISTS { (:CoolingTower)((a)-[:FLOWS_TO]->(b) WHERE " + OPEN + ")+(hx) }\nMATCH (hx)((a)-[:FLOWS_TO]->(b) WHERE " + OPEN + ")+(t:ProductionTool)\nWITH DISTINCT hx, t\nWITH t, count(hx) AS n WHERE n = 1\nRETURN t.id AS t ORDER BY t",
        "method": {"rdf11": "1 query + precomputed open-flow predicate", "rdf12": "1 query + precomputed open-flow predicate", "neo4j": "1 query, valve check inline"},
        "notes": {"rdf11": "Correct as long as fab:openFlow was recomputed after the last valve change.", "rdf12": "Same.",
                  "neo4j": "Always reads the current valve positions."},
    },
    {
        "id": "Q5", "title": "Running hot: where to look",
        "ask": "$consumer is running hot. Which units upstream of it have an active alarm?",
        "stresses": "Upstream traversal joined with live SCADA alarms",
        "params": {"consumer": {"kind": "consumer", "default": "CVD-02", "label": "Consumer"}},
        "rdf11": OPEN_NOTE_RDF + "SELECT ?unit ?alarm ?severity WHERE {\n  ?unit fab:openFlow+ fab:$consumer ;\n        fab:hasDatapoint ?dp .\n  ?al fab:raisedOn ?dp ; fab:active true ;\n      fab:text ?alarm ; fab:severity ?severity .\n} ORDER BY ?unit",
        "rdf12": OPEN_NOTE_RDF + "SELECT ?unit ?alarm ?severity WHERE {\n  ?unit fab:openFlow+ fab:$consumer ;\n        fab:hasDatapoint ?dp .\n  ?al fab:raisedOn ?dp ; fab:active true ;\n      fab:text ?alarm ; fab:severity ?severity .\n} ORDER BY ?unit",
        "neo4j": "MATCH (unit)-[:HAS_DATAPOINT]->(dp)<-[:RAISED_ON]-(al:Alarm {active: true})\nWHERE EXISTS {\n  (unit)((a)-[:FLOWS_TO]->(b) WHERE " + OPEN + ")+(:Entity {id: '$consumer'}) }\nRETURN unit.id AS unit, al.text AS alarm, al.severity AS severity\nORDER BY unit",
        "method": {"rdf11": "1 query + precomputed open-flow predicate", "rdf12": "1 query + precomputed open-flow predicate", "neo4j": "1 query, valve check inline"},
        "notes": {"rdf11": "Topology + alarms, joined in one query.", "rdf12": "Same.", "neo4j": "Same."},
    },
    {
        "id": "Q6", "title": "Who says this pipe exists",
        "ask": "Pipes documented only by $source, with confidence below $conf",
        "stresses": "Metadata about each pipe (provenance)",
        "params": {"source": {"kind": "choice", "options": ["BIM", "P&ID", "DCS"], "default": "BIM", "label": "Source"},
                   "conf": {"kind": "choice", "options": [0.7, 0.8, 0.9, 1.0], "default": 0.8, "label": "Confidence below"}},
        "rdf11": "SELECT ?s ?d ?medium ?conf WHERE {\n  ?p a fab:Pipe ; fab:from ?s ; fab:to ?d ; fab:medium ?medium ;\n     fab:sourceSystem \"$source\" ; fab:confidence ?conf .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "rdf12": "SELECT ?s ?d ?medium ?conf WHERE {\n  ?s fab:flowsTo ?d {| fab:sourceSystem \"$source\" ;\n                      fab:confidence ?conf ; fab:medium ?medium |} .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "neo4j": "MATCH (s)-[f:FLOWS_TO]->(d)\nWHERE f.source = '$source' AND f.confidence < $conf\nRETURN s.id AS s, d.id AS d, f.medium AS medium, f.confidence AS conf\nORDER BY s, d",
        "method": {"rdf11": "1 query (the pipe is a node)", "rdf12": "1 query (statement annotations)", "neo4j": "1 query (relationship properties)"},
        "notes": {"rdf11": "Provenance is ordinary properties on the pipe node.",
                  "rdf12": "Statements about a statement are what RDF 1.2 adds; several sources could each annotate the same pipe.",
                  "neo4j": "One property map per relationship; a second source would need extra properties or a separate node."},
    },
]

QUESTIONS[1]["rdf12"] = QUESTIONS[1]["rdf11"]   # Q2: the same 3-step script works on both RDF encodings (it only uses fab:openFlow)

UPDATES = {
    "recompute_open_rdf11": "DELETE WHERE { ?a fab:openFlow ?b } ;\nINSERT { ?a fab:openFlow ?b } WHERE {\n  ?p a fab:Pipe ; fab:from ?a ; fab:to ?b .\n  FILTER NOT EXISTS { ?a fab:position \"closed\" }\n  FILTER NOT EXISTS { ?b fab:position \"closed\" } }",
    "recompute_open_rdf12": "DELETE WHERE { ?a fab:openFlow ?b } ;\nINSERT { ?a fab:openFlow ?b } WHERE {\n  ?a fab:flowsTo ?b .\n  FILTER NOT EXISTS { ?a fab:position \"closed\" }\n  FILTER NOT EXISTS { ?b fab:position \"closed\" } }",
    "valve_set_rdf": "DELETE { fab:$valve fab:position ?p } INSERT { fab:$valve fab:position \"$position\" } WHERE { fab:$valve fab:position ?p }",
    "valve_set_neo4j": "MATCH (v:Valve {id: '$valve'}) SET v.position = '$position'",
    "claim_add_rdf11": "INSERT DATA { fab:claim-1 a fab:Claim ; fab:claimFrom fab:$src ; fab:claimTo fab:$dst ;\n  fab:medium \"pcw\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_add_rdf12": "INSERT DATA { fab:claim-1 rdf:reifies <<( fab:$src fab:flowsTo fab:$dst )>> ;\n  fab:medium \"pcw\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_remove_rdf": "DELETE WHERE { fab:claim-1 ?p ?o }",
    # what neosemantics 5.26 does with `<< s p o >> :q v`: it creates the relationship (RDFToLPGStatementProcessor.java:421)
    "claim_add_neo4j_n10s": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (s)-[:FLOWS_TO {medium: 'pcw', source: 'BIM', confidence: 0.55, claim: true}]->(d)",
    "claim_add_neo4j_node": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (c:Claim {source: 'BIM', confidence: 0.55, medium: 'pcw'}),\n       (c)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)",
    "claim_remove_neo4j": "MATCH ()-[f:FLOWS_TO {claim: true}]->() DELETE f WITH count(*) AS x MATCH (c:Claim) DETACH DELETE c",
}
VALVE_METHOD = {"rdf11": "update the position, then recompute fab:openFlow", "rdf12": "update the position, then recompute fab:openFlow",
                "neo4j": "1 SET on the valve node"}
CLAIM_METHOD = {"rdf11": "kept as a separate fab:Claim node", "rdf12": "kept as a claimed, not asserted, statement",
                "neo4j": {"n10s": "n10s 5.26 import: becomes a real pipe", "node": "kept as a :Claim node"}}

CONSOLE = [
    {"title": "RDF 1.2 · claimed but not asserted", "engine": "rdf12",
     "text": "SELECT ?s ?d ?source ?conf WHERE {\n  ?r rdf:reifies ?t ; fab:sourceSystem ?source ; fab:confidence ?conf .\n  BIND(SUBJECT(?t) AS ?s) BIND(OBJECT(?t) AS ?d)\n  FILTER NOT EXISTS { ?s fab:flowsTo ?d }\n}"},
    {"title": "RDF 1.2 · everything said about one pipe", "engine": "rdf12",
     "text": "SELECT ?property ?value WHERE {\n  ?r rdf:reifies <<( fab:CHW-HDR fab:flowsTo fab:V-MAU2 )>> ; ?property ?value .\n}"},
    {"title": "RDF 1.1 · the class hierarchy is data", "engine": "rdf11",
     "text": "SELECT ?class ?parent WHERE { ?class rdfs:subClassOf ?parent } ORDER BY ?parent ?class"},
    {"title": "RDF 1.1 · SCADA tags of loop B", "engine": "rdf11",
     "text": "SELECT ?tag ?value ?unit WHERE {\n  fab:PCW-B fab:hasDatapoint ?dp .\n  ?dp fab:tag ?tag ; fab:value ?value ; fab:unit ?unit .\n}"},
    {"title": "Neo4j · the route from cooling tower 1 to Litho 1", "engine": "neo4j",
     "text": "MATCH p = shortestPath((:Entity {id: 'CT-1'})-[:FLOWS_TO*]->(:Entity {id: 'LITH-01'}))\nRETURN [n IN nodes(p) | n.id] AS route"},
    {"title": "Neo4j · valve positions", "engine": "neo4j",
     "text": "MATCH (v:Valve) RETURN v.id AS valve, v.position AS position ORDER BY valve"},
    {"title": "Neo4j · claims stored as nodes", "engine": "neo4j",
     "text": "MATCH (c:Claim)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)\nRETURN s.id AS s, d.id AS d, c.source AS source, c.confidence AS conf"},
]

STORY = [
    {"id": "plant", "title": "Meet the plant", "q": None,
     "plant": "A fab's chilled-water plant. Left to right: three cooling towers each serve a chiller. The chillers make ~6 °C chilled water into one shared header. From the header, valves feed two heat exchangers that cool the process cooling water (PCW) for the tools, and two make-up air units that cool the cleanroom air. Loop A has two pumps (one spare); loop B has one. A cross-tie valve between the loops is normally closed. Some tools hang on loop A, some on loop B, two on both.",
     "look": "Hover any box for what it is, its SCADA tags and values. A red dot is an active alarm; a dashed grey box is a closed valve. The valve positions come from SCADA: change them with 'Valve positions'.",
     "teaches": "The rules of this comparison: same data and same question for every engine; each engine uses its best exact method; extra steps and upkeep are counted, not hidden. The scorecard at the bottom fills in as you run each step."},
    {"id": "s1", "title": "A pump trips", "q": "Q1", "params": {"unit": "P-B1"},
     "plant": "Loop B's only pump, P-B1, has a vibration alarm. The operator considers what happens if it trips.",
     "ask": "What gets its cooling through P-B1?",
     "look": "Loop B and the five tools on it light up. Two of them (CMP-02, LITH-01) are also on loop A, so 'depends on' isn't the same as 'loses cooling'. That's the next step.",
     "teaches": "All three get it right in one query. The difference is hidden: SPARQL paths can't skip closed valves, so both RDF versions query a precomputed 'open pipes' predicate, which has to be kept up to date. Neo4j checks valves inside the query."},
    {"id": "s2", "title": "Who actually loses cooling?", "q": "Q2", "params": {"unit": "P-B1"},
     "plant": "Before acting, the operator needs the consumers that would have no cooling at all, taking redundancy into account.",
     "ask": "If P-B1 trips, which consumers lose cooling completely?",
     "look": "Three tools: those on loop B only. Then pick CHW-HDR: everything is lost, because the shared header is a single point of failure. Pick CH-1: nothing is lost, because the other chillers cover it. All three engines agree.",
     "teaches": "This is the clearest difference in effort, not in correctness. Neo4j: one query ('is there still a route that avoids this unit?'). RDF: a 3-step script, because SPARQL can't exclude a unit from a path. Compare the time and the method in the scorecard."},
    {"id": "s3", "title": "Can we service a chiller?", "q": "Q3", "params": {"chiller": "CH-3"},
     "plant": "Maintenance wants a chiller out for a week. The plant must still carry the design load of 3,300 kW (N+1).",
     "ask": "With CH-3 out, is there enough capacity?",
     "look": "CH-3 (the small one) out: 3,600 kW left, a 300 kW margin, so yes. Pick CH-1: 3,200 kW left, 100 kW short, so not at design load.",
     "teaches": "No graph needed: it's a sum. All three are equally good. A fair comparison includes questions where the database choice doesn't matter."},
    {"id": "s4", "title": "SCADA reports a valve move", "q": "Q4", "params": {}, "valves": "tie-open",
     "plant": "The operator opens the cross-tie between loop A and loop B, so either heat exchanger can feed every tool.",
     "ask": "Which tools now depend on a single heat exchanger?",
     "look": "Normal operation: six tools have only one heat exchanger. With the cross-tie open: none. Choose 'HX-2 isolated for cleaning': every tool now hangs on HX-1. The 'Valve positions' panel shows what each engine had to do for the change.",
     "teaches": "The real-time case. Neo4j: one property update on the valve, and every query sees it. RDF: update the position, then recompute the open-pipes predicate before any query is right again. Both are fast here; on a large plant with frequent valve changes, that upkeep is the cost to watch."},
    {"id": "s5", "title": "A tool is running hot", "q": "Q5", "params": {"consumer": "CVD-02"},
     "plant": "CVD-02 reports its chamber cooling is too warm.",
     "ask": "Which units upstream of CVD-02 have an active alarm?",
     "look": "Four suspects: loop B (supply temp high), pump P-B1 (vibration), HX-2 (fouling) and chiller 2 (leaving temp high). Pick ETCH-01 on loop A: only chiller 2 remains, so the problem points at the loop B side.",
     "teaches": "Topology from the graph plus alarms from SCADA, joined by tag. All three do this well."},
    {"id": "s6", "title": "An unconfirmed BIM pipe", "q": "Q4", "params": {}, "valves": "normal", "claim": True,
     "plant": "The BIM model shows a pipe from loop B to ETCH-01, which would make ETCH-01 redundant. It isn't in the DCS and nobody has checked it in the field.",
     "ask": "Inject the claim and re-run the single-heat-exchanger audit.",
     "look": "With the 'n10s 5.26 import', Neo4j drops ETCH-01 from the list (5 instead of 6): the claim became a real pipe and hides a real risk. Both RDF versions still say 6. Switch to 'Claim node' and all three agree.",
     "teaches": "RDF 1.2 can hold a statement that is claimed but not asserted. The standard RDF→Neo4j importer (n10s 5.26) turns it into a real relationship. That's an integration pitfall, not a Neo4j limit: modelled as a separate node, Neo4j is right too."},
]


def fill(template: str, params: dict) -> str:
    out = template
    for k, v in sorted(params.items(), key=lambda kv: -len(kv[0])):
        sv = str(v)
        if not (ID_RE.match(sv) or re.fullmatch(r"-?\d+(\.\d+)?", sv) or sv == "P&ID"):
            raise ValueError(f"bad parameter {k}={v!r}")
        out = out.replace("$" + k, sv)
    return out


def catalogue() -> dict:
    return {"prefixes": PREFIXES, "questions": QUESTIONS, "updates": UPDATES, "console": CONSOLE, "story": STORY,
            "types": {k: {"category": c, "about": a} for k, (c, a) in TYPES.items()}, "media": MEDIA,
            "valve_presets": {k: {"label": v["label"], "positions": positions(k)} for k, v in VALVE_PRESETS.items()},
            "valve_method": VALVE_METHOD, "claim_method": CLAIM_METHOD, "claim_default": CLAIM_DEFAULT, "step_sep": STEP_SEP}


# ---------------------------------------------------------------- plain-Python reference (for check.py)
def reference(d: dict, q: str, p: dict, preset: str = "normal") -> list:
    from collections import defaultdict, deque
    typ = {n["id"]: n["type"] for n in d["nodes"]}
    node = {n["id"]: n for n in d["nodes"]}
    pos = positions(preset)
    closed = {v for v, s in pos.items() if s == "closed"}
    pipes = [e for e in d["edges"] if e["type"] == "flowsTo"]
    out, rin = defaultdict(list), defaultdict(list)
    for e in pipes:
        if e["src"] in closed or e["dst"] in closed: continue
        out[e["src"]].append(e["dst"]); rin[e["dst"]].append(e["src"])
    consumers = [i for i, t in typ.items() if t in TOOL_TYPES or t == "CleanroomBay"]

    def reach(start, adj, skip=None):
        if start == skip: return set()
        seen, dq = set(), deque([start])
        while dq:
            for v in adj[dq.popleft()]:
                if v != skip and v not in seen: seen.add(v); dq.append(v)
        return seen
    if q == "Q1": return sorted(reach(p["unit"], out))
    if q == "Q2":
        ok = set()
        for ct in (i for i, t in typ.items() if t == "CoolingTower"): ok |= reach(ct, out, p["unit"])
        return sorted(c for c in consumers if c not in ok)
    if q == "Q3":
        rem = sum(n["capacity_kw"] for n in node.values() if n["type"] == "Chiller" and n["id"] != p["chiller"])
        load = sum(n.get("design_load_kw", 0) for n in node.values())
        return [f"{rem}|{load}"]
    if q == "Q4":
        hits, live = defaultdict(set), set()
        for ct in (i for i, t in typ.items() if t == "CoolingTower"): live |= reach(ct, out)
        for hx in (i for i, t in typ.items() if t == "HeatExchanger" and i in live):
            for t in reach(hx, out):
                if typ[t] in TOOL_TYPES: hits[t].add(hx)
        return sorted(t for t, s in hits.items() if len(s) == 1)
    if q == "Q5":
        up = reach(p["consumer"], rin)
        owner = {e["dst"]: e["src"] for e in d["edges"] if e["type"] == "hasDatapoint"}
        al = {n["id"]: n for n in d["nodes"] if n["type"] == "Alarm" and n["active"]}
        return sorted(f'{owner[e["dst"]]}|{al[e["src"]]["text"]}' for e in d["edges"]
                      if e["type"] == "raisedOn" and e["src"] in al and owner[e["dst"]] in up)
    if q == "Q6": return sorted(f'{e["src"]}>{e["dst"]}' for e in pipes if e["source"] == p["source"] and e["confidence"] < float(p["conf"]))
    raise ValueError(q)


if __name__ == "__main__":
    d = dataset()
    print(json.dumps({"nodes": len(d["nodes"]), "edges": len(d["edges"])}))
    for q, p, pre in [("Q1", {"unit": "P-B1"}, "normal"), ("Q2", {"unit": "P-B1"}, "normal"), ("Q2", {"unit": "CHW-HDR"}, "normal"),
                      ("Q2", {"unit": "CH-1"}, "normal"), ("Q2", {"unit": "P-B1"}, "tie-open"), ("Q3", {"chiller": "CH-3"}, "normal"),
                      ("Q3", {"chiller": "CH-1"}, "normal"), ("Q4", {}, "normal"), ("Q4", {}, "tie-open"), ("Q4", {}, "hx2-isolated"),
                      ("Q5", {"consumer": "CVD-02"}, "normal"), ("Q5", {"consumer": "ETCH-01"}, "normal"), ("Q6", {"source": "BIM", "conf": 0.8}, "normal")]:
        print(pre, q, p, reference(d, q, p, pre))
