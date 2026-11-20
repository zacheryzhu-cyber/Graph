"""UPW scenario: a small, hand-built slice of a fab's ultrapure-water plant and the cooling that serves it.

Everything the demo needs about the plant lives here: the dataset, how it becomes RDF 1.1 / RDF 1.2 / LPG,
the six operator questions (as SPARQL and Cypher), the story text, and a plain-Python reference answer for each
question (used by check.py; the browser has its own independent JavaScript copy).

The plant (left → right is the direction water flows):
  cooling:  cooling towers ─condenser water─► chillers ─chilled water─► heat exchangers ─► process-cooling loop ─► tools
  UPW:      city water → raw tank → multimedia filter → carbon filter → RO ×2 → degasifier → mixed bed → UPW tank
            → trim cooler (cooled by chilled water) → 185 nm UV → polishing train A / B (mixed bed + ultrafilter)
            → supply loop A / B → tools
  reclaim:  rinse water from wet benches and CMP → reclaim tank → back to the raw tank (a recycle loop)
"""
import json
import re

FAB = "http://example.org/fab#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
PREFIXES = f"PREFIX fab: <{FAB}>\nPREFIX rdf: <{RDF}>\nPREFIX rdfs: <{RDFS}>\n"
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# ---------------------------------------------------------------- vocabulary (also shown in the UI glossary)
TYPES = {   # type: (category, plain-language explanation)
    "CoolingTower":     ("cooling", "Rejects the plant's heat to the outside air by evaporating water. Sends cooled condenser water to the chillers."),
    "Chiller":          ("cooling", "A refrigeration machine. Takes heat out of the chilled-water loop and dumps it into the condenser water."),
    "HeatExchanger":    ("cooling", "Two water circuits pass each other through plates without mixing; heat moves from the warm one to the cold one."),
    "CoolingLoop":      ("cooling", "Process cooling water (PCW): a closed loop that carries chilled-water cooling to the tools."),
    "Source":           ("water", "Where the plant's water comes from (here: city water)."),
    "Tank":             ("water", "Buffer storage between treatment stages."),
    "Filter":           ("water", "Pretreatment. The multimedia filter removes particles; the activated-carbon filter removes chlorine and organics."),
    "ReverseOsmosis":   ("water", "Pushes water through a membrane that holds back ~99 % of dissolved salts. Two trains run in parallel."),
    "Degasifier":       ("water", "Membrane contactor that strips dissolved oxygen and CO₂."),
    "MixedBed":         ("water", "Ion-exchange resin that removes the last ions. Output is judged by resistivity: 18.2 MΩ·cm is pure water."),
    "UVReactor":        ("water", "185 nm ultraviolet light that breaks down organic carbon (TOC)."),
    "Ultrafilter":      ("water", "Final membrane that catches particles just before the water goes to the fab."),
    "DistributionLoop": ("water", "A loop of piping that circulates ultrapure water past the tools; each tool taps off it at its point of use."),
    "WetBench":         ("tool", "Wafer cleaning in chemical and ultrapure-water baths. Uses a lot of UPW; rinse water is reclaimed."),
    "CMPTool":          ("tool", "Chemical-mechanical polishing. Uses UPW for slurry and rinsing, and process cooling."),
    "LithoTrack":       ("tool", "Coat/develop track next to the scanner. Uses UPW for rinsing and process cooling."),
    "EtchTool":         ("tool", "Plasma etch. Needs process cooling only, no UPW."),
}
MEDIA = {   # medium on a pipe: (short label, explanation)
    "cw": ("condenser water", "cooling tower ↔ chiller"),
    "chw": ("chilled water", "chiller → heat exchangers, ~6 °C"),
    "pcw": ("process cooling", "PCW loop → tools"),
    "makeup": ("pretreatment", "city water through filters"),
    "ro": ("RO permeate", "RO → degasifier → mixed bed"),
    "upw": ("ultrapure water", "18.2 MΩ·cm water to the tools"),
    "reclaim": ("reclaimed rinse", "used rinse water back to the raw tank"),
}
TOOL_TYPES = [t for t, (c, _) in TYPES.items() if c == "tool"]

NODES = [  # id, type, name
    ("CT-1", "CoolingTower", "Cooling tower 1"), ("CT-2", "CoolingTower", "Cooling tower 2"),
    ("CH-1", "Chiller", "Chiller 1"), ("CH-2", "Chiller", "Chiller 2"),
    ("HX-PCW", "HeatExchanger", "PCW heat exchanger"), ("PCW-LOOP", "CoolingLoop", "Process cooling water loop"),
    ("CITY", "Source", "City water"), ("RAW-TK", "Tank", "Raw water tank"),
    ("MMF-1", "Filter", "Multimedia filter"), ("ACF-1", "Filter", "Activated carbon filter"),
    ("RO-1", "ReverseOsmosis", "RO train 1"), ("RO-2", "ReverseOsmosis", "RO train 2"),
    ("DEG-1", "Degasifier", "Membrane degasifier"), ("MB-1", "MixedBed", "Primary mixed bed"),
    ("UPW-TK", "Tank", "UPW storage tank"), ("HX-UPW", "HeatExchanger", "UPW trim cooler"),
    ("UV-1", "UVReactor", "185 nm UV (TOC)"),
    ("MBP-A", "MixedBed", "Polishing mixed bed A"), ("MBP-B", "MixedBed", "Polishing mixed bed B"),
    ("UF-A", "Ultrafilter", "Ultrafilter A"), ("UF-B", "Ultrafilter", "Ultrafilter B"),
    ("LOOP-A", "DistributionLoop", "UPW supply loop A"), ("LOOP-B", "DistributionLoop", "UPW supply loop B"),
    ("RCL-TK", "Tank", "Rinse reclaim tank"),
    ("WET-01", "WetBench", "Wet bench 1"), ("WET-02", "WetBench", "Wet bench 2"),
    ("WET-03", "WetBench", "Wet bench 3"), ("WET-04", "WetBench", "Wet bench 4"),
    ("CMP-01", "CMPTool", "CMP 1"), ("CMP-02", "CMPTool", "CMP 2"), ("CMP-03", "CMPTool", "CMP 3"),
    ("LITH-01", "LithoTrack", "Litho track 1"), ("LITH-02", "LithoTrack", "Litho track 2"),
    ("ETCH-01", "EtchTool", "Etch 1"), ("ETCH-02", "EtchTool", "Etch 2"),
]
# src, dst, medium, capacity m³/h, flow m³/h, installed, source system, confidence
PIPES = [
    ("CT-1", "CH-1", "cw", 400, 310, 2016), ("CT-2", "CH-2", "cw", 400, 290, 2016),
    ("CT-1", "CH-2", "cw", 400, 60, 2019, "BIM", 0.74),                      # cross-tie on the condenser header
    ("CH-1", "HX-UPW", "chw", 60, 38, 2016), ("CH-2", "HX-UPW", "chw", 60, 22, 2016),
    ("CH-1", "HX-PCW", "chw", 250, 190, 2016), ("CH-2", "HX-PCW", "chw", 250, 205, 2016),
    ("HX-PCW", "PCW-LOOP", "pcw", 300, 240, 2016, "P&ID", 0.9),
    ("CITY", "RAW-TK", "makeup", 120, 70, 2015), ("RAW-TK", "MMF-1", "makeup", 140, 104, 2015),
    ("MMF-1", "ACF-1", "makeup", 140, 104, 2015),
    ("ACF-1", "RO-1", "makeup", 80, 52, 2015), ("ACF-1", "RO-2", "makeup", 80, 52, 2018, "P&ID", 0.88),
    ("RO-1", "DEG-1", "ro", 60, 39, 2015), ("RO-2", "DEG-1", "ro", 60, 39, 2018),
    ("DEG-1", "MB-1", "ro", 100, 78, 2015), ("MB-1", "UPW-TK", "upw", 100, 78, 2015),
    ("UPW-TK", "HX-UPW", "upw", 120, 92, 2015), ("HX-UPW", "UV-1", "upw", 120, 92, 2015),
    ("UV-1", "MBP-A", "upw", 70, 48, 2015), ("UV-1", "MBP-B", "upw", 70, 44, 2018),
    ("MBP-A", "UF-A", "upw", 70, 48, 2015), ("MBP-B", "UF-B", "upw", 70, 44, 2018),
    ("UF-A", "LOOP-A", "upw", 70, 48, 2015), ("UF-B", "LOOP-B", "upw", 70, 44, 2018),
    # tools: loop A, loop B, or both (redundant)
    ("LOOP-A", "WET-01", "upw", 12, 9, 2015), ("LOOP-B", "WET-01", "upw", 12, 2, 2018),
    ("LOOP-A", "WET-02", "upw", 12, 10, 2015),
    ("LOOP-B", "WET-03", "upw", 12, 10, 2018),
    ("LOOP-A", "WET-04", "upw", 12, 11, 2021, "BIM", 0.62),
    ("LOOP-A", "CMP-01", "upw", 8, 5, 2015), ("LOOP-B", "CMP-01", "upw", 8, 1, 2018),
    ("LOOP-A", "CMP-02", "upw", 8, 6, 2015),
    ("LOOP-B", "CMP-03", "upw", 8, 6, 2018),
    ("LOOP-A", "LITH-01", "upw", 4, 2, 2015), ("LOOP-B", "LITH-01", "upw", 4, 1, 2018),
    ("LOOP-B", "LITH-02", "upw", 4, 3, 2020, "BIM", 0.7),
    # process cooling to tools
    ("PCW-LOOP", "CMP-01", "pcw", 20, 14, 2015), ("PCW-LOOP", "CMP-02", "pcw", 20, 15, 2015),
    ("PCW-LOOP", "CMP-03", "pcw", 20, 13, 2018), ("PCW-LOOP", "LITH-01", "pcw", 10, 6, 2015),
    ("PCW-LOOP", "LITH-02", "pcw", 10, 7, 2020), ("PCW-LOOP", "ETCH-01", "pcw", 30, 22, 2016),
    ("PCW-LOOP", "ETCH-02", "pcw", 30, 24, 2022, "BIM", 0.66),
    # reclaim: rinse water back to the start (a recycle loop)
    ("WET-01", "RCL-TK", "reclaim", 10, 6, 2015, "P&ID", 0.86), ("WET-02", "RCL-TK", "reclaim", 10, 7, 2015),
    ("WET-03", "RCL-TK", "reclaim", 10, 7, 2018), ("WET-04", "RCL-TK", "reclaim", 10, 8, 2021),
    ("CMP-01", "RCL-TK", "reclaim", 6, 3, 2015), ("CMP-02", "RCL-TK", "reclaim", 6, 4, 2015),
    ("CMP-03", "RCL-TK", "reclaim", 6, 4, 2018),
    ("RCL-TK", "RAW-TK", "reclaim", 40, 34, 2015, "P&ID", 0.85),
]
# SCADA datapoints (tag, unit, last value) and alarms on them
DATAPOINTS = [
    ("CT-1", "BasinTemp", "°C", 27.1), ("CT-2", "BasinTemp", "°C", 27.4), ("CT-2", "FanVibration", "mm/s", 3.1),
    ("CH-1", "CHWSupplyTemp", "°C", 6.1), ("CH-2", "CHWSupplyTemp", "°C", 9.4),
    ("HX-UPW", "UPWOutletTemp", "°C", 22.6), ("PCW-LOOP", "SupplyTemp", "°C", 18.2),
    ("RAW-TK", "Level", "%", 64), ("RO-1", "PermeateConductivity", "µS/cm", 1.9), ("RO-2", "PermeateConductivity", "µS/cm", 4.8),
    ("DEG-1", "DissolvedO2", "ppb", 4.1), ("MB-1", "Resistivity", "MΩ·cm", 18.1), ("UPW-TK", "Level", "%", 71),
    ("UV-1", "LampIntensity", "%", 93), ("MBP-A", "Resistivity", "MΩ·cm", 18.2), ("MBP-B", "Resistivity", "MΩ·cm", 17.6),
    ("UF-A", "DiffPressure", "kPa", 58), ("UF-B", "DiffPressure", "kPa", 61),
    ("LOOP-A", "Resistivity", "MΩ·cm", 18.2), ("LOOP-A", "TOC", "ppb", 0.8),
    ("LOOP-B", "Resistivity", "MΩ·cm", 17.9), ("LOOP-B", "TOC", "ppb", 0.9),
]
ALARMS = [  # id, on datapoint, text, severity, active, raised
    ("ALM-MBP-B-RES", "MBP-B.Resistivity", "Resistivity low: 17.6 MΩ·cm (limit 18.0)", "critical", True, "2026-11-20T06:42:00Z"),
    ("ALM-LOOP-B-RES", "LOOP-B.Resistivity", "Loop resistivity low: 17.9 MΩ·cm (limit 18.0)", "major", True, "2026-11-20T06:51:00Z"),
    ("ALM-RO-2-COND", "RO-2.PermeateConductivity", "Permeate conductivity high: 4.8 µS/cm (limit 3.0)", "major", True, "2026-11-20T05:10:00Z"),
    ("ALM-CH-2-TEMP", "CH-2.CHWSupplyTemp", "Chilled-water supply temp high: 9.4 °C (limit 8.0)", "warning", True, "2026-11-20T04:30:00Z"),
    ("ALM-UF-A-DP", "UF-A.DiffPressure", "Differential pressure high (cleared)", "major", False, "2026-11-18T22:05:00Z"),
    ("ALM-CT-2-VIB", "CT-2.FanVibration", "Fan vibration high (cleared)", "warning", False, "2026-11-19T13:20:00Z"),
]
CLAIM_DEFAULT = ("LOOP-B", "WET-02")   # BIM says loop B also feeds wet bench 2; nobody has confirmed it


def dataset() -> dict:
    nodes, edges = [], []
    for i, t, name in NODES:
        nodes.append({"id": i, "type": t, "name": name, "category": TYPES[t][0]})
    conf_cycle = [0.97, 0.98, 0.95, 0.99, 0.96]
    for k, p in enumerate(PIPES):
        s, d, m, cap, flow, inst = p[:6]
        src, conf = (p[6], p[7]) if len(p) > 6 else ("DCS", conf_cycle[k % 5])
        edges.append({"id": f"e{k}", "src": s, "dst": d, "type": "feeds", "medium": m, "capacity_m3h": cap,
                      "flow_m3h": flow, "installed": inst, "source": src, "confidence": conf})
    for a, sig, unit, val in DATAPOINTS:
        dp = f"{a}.{sig}"
        nodes.append({"id": dp, "type": "Datapoint", "name": dp, "tag": f"UPW:{a.replace('-', '_')}.{sig}", "unit": unit, "value": val})
        edges.append({"id": f"h-{dp}", "src": a, "dst": dp, "type": "hasDatapoint"})
    for aid, dp, text, sev, active, raised in ALARMS:
        nodes.append({"id": aid, "type": "Alarm", "name": aid, "text": text, "severity": sev, "active": active, "raised": raised})
        edges.append({"id": f"r-{aid}", "src": aid, "dst": dp, "type": "raisedOn"})
    return {"scenario": "upw", "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- RDF builders
def _ox():
    import pyoxigraph as ox
    return ox


PROP = {"medium": "medium", "capacity_m3h": "capacityM3h", "flow_m3h": "flowM3h", "installed": "installed",
        "source": "sourceSystem", "confidence": "confidence", "tag": "tag", "unit": "unit", "value": "value",
        "text": "text", "severity": "severity", "active": "active", "raised": "raisedAt", "category": "category"}


def build_rdf(d: dict, mode: str):
    """mode 'nary' = RDF 1.1 (each pipe is a fab:Feed node); 'rdf12' = direct triple + reifier carrying the properties."""
    ox = _ox()
    N = lambda x: ox.NamedNode(FAB + x)
    TYPE, SUB, LABEL = ox.NamedNode(RDF + "type"), ox.NamedNode(RDFS + "subClassOf"), ox.NamedNode(RDFS + "label")

    def lit(v):
        if isinstance(v, bool): return ox.Literal("true" if v else "false", datatype=ox.NamedNode(XSD + "boolean"))
        if isinstance(v, int): return ox.Literal(str(v), datatype=ox.NamedNode(XSD + "integer"))
        if isinstance(v, float): return ox.Literal(repr(v), datatype=ox.NamedNode(XSD + "decimal"))
        return ox.Literal(v)

    ts = []
    for t, (cat, _) in TYPES.items():   # the class hierarchy is data
        parent = {"tool": "ProductionTool", "cooling": "CoolingEquipment", "water": "WaterTreatment"}[cat]
        ts.append(ox.Triple(N(t), SUB, N(parent)))
    ts += [ox.Triple(N("ProductionTool"), SUB, N("Asset")), ox.Triple(N("CoolingEquipment"), SUB, N("Equipment")),
           ox.Triple(N("WaterTreatment"), SUB, N("Equipment")), ox.Triple(N("Equipment"), SUB, N("Asset"))]
    for n in d["nodes"]:
        s = N(n["id"])
        ts += [ox.Triple(s, TYPE, N(n["type"])), ox.Triple(s, LABEL, ox.Literal(n["name"]))]
        ts += [ox.Triple(s, N(PROP[k]), lit(v)) for k, v in n.items() if k in PROP]
    for e in d["edges"]:
        s, o = N(e["src"]), N(e["dst"])
        if e["type"] != "feeds":
            ts.append(ox.Triple(s, N(e["type"]), o)); continue
        r = N("pipe/" + e["id"])
        if mode == "nary":
            ts += [ox.Triple(r, TYPE, N("Feed")), ox.Triple(r, N("feedFrom"), s), ox.Triple(r, N("feedTo"), o)]
        else:
            base = ox.Triple(s, N("feeds"), o)
            ts += [base, ox.Triple(r, ox.NamedNode(RDF + "reifies"), base)]
        ts += [ox.Triple(r, N(PROP[k]), lit(v)) for k, v in e.items() if k in PROP]
    st = ox.Store()
    st.bulk_extend(ox.Quad(t.subject, t.predicate, t.object) for t in ts)
    st.update(PREFIXES + UPDATES["materialise_supplies_" + ("rdf11" if mode == "nary" else "rdf12")])
    return st


# ---------------------------------------------------------------- LPG loader
def extra_labels(t):
    cat = TYPES.get(t, ("",))[0]
    return {"tool": ["Asset", "ProductionTool"], "cooling": ["Asset", "Equipment"], "water": ["Asset", "Equipment"]}.get(cat, [])


def load_lpg(drv, d):
    from collections import defaultdict
    drv.execute_query("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
    drv.execute_query("CALL db.awaitIndexes()")
    by_type = defaultdict(list)
    for n in d["nodes"]: by_type[n["type"]].append(dict(n))
    for t, rows in by_type.items():
        drv.execute_query(f"UNWIND $rows AS r CREATE (n:{':'.join(['Entity', t] + extra_labels(t))}) SET n = r", rows=rows)
    rel = {"feeds": "FEEDS", "hasDatapoint": "HAS_DATAPOINT", "raisedOn": "RAISED_ON"}
    by_rel = defaultdict(list)
    for e in d["edges"]:
        by_rel[e["type"]].append({k: v for k, v in e.items() if k not in ("type",)})
    for t, rows in by_rel.items():
        drv.execute_query(f"UNWIND $rows AS r MATCH (a:Entity {{id: r.src}}), (b:Entity {{id: r.dst}}) "
                          f"CREATE (a)-[x:{rel[t]}]->(b) SET x = r", rows=rows)


# ---------------------------------------------------------------- questions
SUPPLY = "f.medium <> 'reclaim'"


def _unrolled(max_depth=6):
    """SPARQL can't return a path: spell out depths 1..k and keep the shortest."""
    branches = []
    for k in range(1, max_depth + 1):
        vs = ["?n0"] + [f"?n{i}" for i in range(1, k)] + ["?nk"]
        pats = " . ".join(f"{vs[i]} fab:supplies {vs[i + 1]}" for i in range(k))
        binds = " ".join(f"BIND(STR({vs[i]}) AS ?p{i})" for i in range(1, k))
        branches.append(f"  {{ {pats} . BIND({k} AS ?depth) {binds} }}")
    sel = " ".join(f"?p{i}" for i in range(1, max_depth))
    return (f"# Paths aren't a SPARQL result type: depths 1–{max_depth} are spelled out.\n"
            f"SELECT ?depth {sel} WHERE {{\n  VALUES (?n0 ?nk) {{ (fab:$src fab:$dst) }}\n"
            + "\n  UNION\n".join(branches) + "\n} ORDER BY ?depth LIMIT 1")


Q2_RDF_NOTE = ("# SPARQL can't say \"a path that avoids $asset\".\n"
               "# Best single query: a tool loses UPW if EVERY loop feeding it\n"
               "# is downstream of $asset. Wrong when redundancy sits further up.\n")

QUESTIONS = [
    {
        "id": "Q1", "title": "What depends on it",
        "ask": "Which equipment and tools are downstream of $asset?",
        "stresses": "Following supply pipes transitively (and not the reclaim pipes)",
        "params": {"asset": {"kind": "unit", "default": "MBP-B", "label": "Unit"}},
        "rdf11": "# fab:supplies = every pipe except reclaim, materialised at load\n# (built from the fab:Feed nodes).\nSELECT DISTINCT ?x ?type WHERE {\n  fab:$asset fab:supplies+ ?x .\n  ?x a ?type .\n} ORDER BY ?x",
        "rdf12": "# fab:supplies = asserted fab:feeds triples whose reifier\n# says medium != \"reclaim\", materialised at load.\nSELECT DISTINCT ?x ?type WHERE {\n  fab:$asset fab:supplies+ ?x .\n  ?x a ?type .\n} ORDER BY ?x",
        "neo4j": "MATCH (:Entity {id: '$asset'})\n      (()-[f:FEEDS WHERE " + SUPPLY + "]->())+ (x)\nRETURN DISTINCT x.id AS x, x.type AS type ORDER BY x",
        "notes": {
            "rdf11": "A property path can't look at a pipe's medium, so a 'supply pipes only' predicate has to be built first.",
            "rdf12": "Same: the filter goes into a materialised predicate.",
            "neo4j": "The pipe filter sits inside the path pattern.",
        },
    },
    {
        "id": "Q2", "title": "Take it out of service",
        "ask": "If $asset is isolated, which tools lose ultrapure water completely?",
        "stresses": "A what-if: paths that must avoid one unit, with redundancy",
        "params": {"asset": {"kind": "unit", "default": "MBP-B", "label": "Isolate"}},
        "rdf11": Q2_RDF_NOTE + "SELECT DISTINCT ?t WHERE {\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n  ?f a fab:Feed ; fab:feedFrom ?l ; fab:feedTo ?t ; fab:medium \"upw\" .\n  FILTER NOT EXISTS {\n    ?f2 a fab:Feed ; fab:feedFrom ?l2 ; fab:feedTo ?t ; fab:medium \"upw\" .\n    FILTER NOT EXISTS { fab:$asset fab:supplies* ?l2 }\n  }\n} ORDER BY ?t",
        "rdf12": Q2_RDF_NOTE + "SELECT DISTINCT ?t WHERE {\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n  ?l fab:feeds ?t {| fab:medium \"upw\" |} .\n  FILTER NOT EXISTS {\n    ?l2 fab:feeds ?t {| fab:medium \"upw\" |} .\n    FILTER NOT EXISTS { fab:$asset fab:supplies* ?l2 }\n  }\n} ORDER BY ?t",
        "neo4j": "MATCH (t:ProductionTool)\nWHERE EXISTS { (t)<-[:FEEDS {medium: 'upw'}]-() }\n  AND NOT EXISTS {\n    (:Source)\n    ((a)-[f:FEEDS]->(b) WHERE " + SUPPLY + "\n                          AND a.id <> '$asset' AND b.id <> '$asset')+\n    (t) }\nRETURN t.id AS t ORDER BY t",
        "notes": {
            "rdf11": "Approximation. Exact needs application code or a temporary copy of the graph without the unit. Try RO-2 or CH-2.",
            "rdf12": "Same approximation. RDF 1.2 adds statement metadata, not path power.",
            "neo4j": "Exact: 'is there still a supply path from the city water that avoids this unit?'",
        },
    },
    {
        "id": "Q3", "title": "Who says this pipe exists",
        "ask": "Pipes that only $source documents, with confidence below $conf",
        "stresses": "Metadata about each pipe (provenance)",
        "params": {"source": {"kind": "choice", "options": ["BIM", "P&ID", "DCS"], "default": "BIM", "label": "Source"},
                   "conf": {"kind": "choice", "options": [0.7, 0.8, 0.9, 1.0], "default": 0.8, "label": "Confidence below"}},
        "rdf11": "SELECT ?s ?d ?medium ?conf WHERE {\n  ?f a fab:Feed ; fab:feedFrom ?s ; fab:feedTo ?d ; fab:medium ?medium ;\n     fab:sourceSystem \"$source\" ; fab:confidence ?conf .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "rdf12": "SELECT ?s ?d ?medium ?conf WHERE {\n  ?s fab:feeds ?d {| fab:sourceSystem \"$source\" ;\n                     fab:confidence ?conf ; fab:medium ?medium |} .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "neo4j": "MATCH (s)-[f:FEEDS]->(d)\nWHERE f.source = '$source' AND f.confidence < $conf\nRETURN s.id AS s, d.id AS d, f.medium AS medium, f.confidence AS conf\nORDER BY s, d",
        "notes": {
            "rdf11": "Provenance is more properties on the pipe node.",
            "rdf12": "Statements about a statement are what reifiers are for; several sources can each have their own.",
            "neo4j": "One property map per relationship: a second source would overwrite the first.",
        },
    },
    {
        "id": "Q4", "title": "Trace the water",
        "ask": "The route water takes from $src to $dst",
        "stresses": "Returning the path itself",
        "params": {"src": {"kind": "unit", "default": "UPW-TK", "label": "From"},
                   "dst": {"kind": "tool", "default": "WET-03", "label": "To tool"}},
        "rdf11": _unrolled(), "rdf12": _unrolled(),
        "neo4j": "MATCH p = shortestPath(\n  (:Entity {id: '$src'})-[:FEEDS*]->(:Entity {id: '$dst'}))\nWHERE all(f IN relationships(p) WHERE " + SUPPLY + ")\nRETURN [n IN nodes(p) | n.id] AS path",
        "notes": {
            "rdf11": "Only answers up to the depth you spelled out. From CITY the route is 13 pipes long.",
            "rdf12": "Same workaround; RDF 1.2 doesn't add path results.",
            "neo4j": "Paths are a native result.",
        },
    },
    {
        "id": "Q5", "title": "Bad water: where to look",
        "ask": "$tool reports bad water. Which units upstream of it have an active alarm?",
        "stresses": "Upstream traversal joined with live SCADA alarms",
        "params": {"tool": {"kind": "tool", "default": "WET-03", "label": "Tool"}},
        "rdf11": "SELECT ?unit ?alarm ?severity WHERE {\n  ?unit fab:supplies+ fab:$tool ;\n        fab:hasDatapoint ?dp .\n  ?al fab:raisedOn ?dp ; fab:active true ;\n      fab:text ?alarm ; fab:severity ?severity .\n} ORDER BY ?unit",
        "rdf12": "SELECT ?unit ?alarm ?severity WHERE {\n  ?unit fab:supplies+ fab:$tool ;\n        fab:hasDatapoint ?dp .\n  ?al fab:raisedOn ?dp ; fab:active true ;\n      fab:text ?alarm ; fab:severity ?severity .\n} ORDER BY ?unit",
        "neo4j": "MATCH (unit)-[:HAS_DATAPOINT]->(dp)<-[:RAISED_ON]-(al:Alarm {active: true})\nWHERE EXISTS {\n  (unit)(()-[f:FEEDS WHERE " + SUPPLY + "]->())+(:Entity {id: '$tool'}) }\nRETURN unit.id AS unit, al.text AS alarm, al.severity AS severity\nORDER BY unit",
        "notes": {
            "rdf11": "Works well once fab:supplies exists.",
            "rdf12": "Identical to RDF 1.1 here.",
            "neo4j": "Same answer; filter inline.",
        },
    },
    {
        "id": "Q6", "title": "Single point of failure",
        "ask": "Which tools get their UPW through only one polishing train?",
        "stresses": "Redundancy audit; the reclaim loop is a trap",
        "params": {"filter": {"kind": "choice", "options": ["supply pipes only", "include reclaim pipes"], "default": "supply pipes only", "label": "Follow"}},
        "variants": {
            "supply pipes only": {
                "rdf11": "SELECT ?t WHERE {\n  ?uf a fab:Ultrafilter ; fab:supplies+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?uf) = 1) ORDER BY ?t",
                "rdf12": "SELECT ?t WHERE {\n  ?uf a fab:Ultrafilter ; fab:supplies+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?uf) = 1) ORDER BY ?t",
                "neo4j": "MATCH (uf:Ultrafilter)\n      (()-[f:FEEDS WHERE " + SUPPLY + "]->())+\n      (t:ProductionTool)\nWITH DISTINCT uf, t\nWITH t, count(uf) AS n WHERE n = 1\nRETURN t.id AS t ORDER BY t",
            },
            "include reclaim pipes": {
                "rdf11": "SELECT ?t WHERE {\n  ?uf a fab:Ultrafilter ; (^fab:feedFrom/fab:feedTo)+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?uf) = 1) ORDER BY ?t",
                "rdf12": "SELECT ?t WHERE {\n  ?uf a fab:Ultrafilter ; fab:feeds+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?uf) = 1) ORDER BY ?t",
                "neo4j": "MATCH (uf:Ultrafilter)-[:FEEDS*]->(t:ProductionTool)\nWITH DISTINCT uf, t\nWITH t, count(uf) AS n WHERE n = 1\nRETURN t.id AS t ORDER BY t",
            },
        },
        "notes": {
            "rdf11": "Needs fab:supplies; without the medium filter the recycle loop connects everything.",
            "rdf12": "Same; built from asserted triples only, so an unconfirmed claim stays out.",
            "neo4j": "Filter inline. Any pipe that is really a claim will count, though (see the BIM claim).",
        },
    },
]

UPDATES = {
    "materialise_supplies_rdf11": "INSERT { ?s fab:supplies ?d } WHERE { ?f a fab:Feed ; fab:feedFrom ?s ; fab:feedTo ?d ; fab:medium ?m FILTER(?m != \"reclaim\") }",
    "materialise_supplies_rdf12": "INSERT { ?s fab:supplies ?d } WHERE { ?s fab:feeds ?d {| fab:medium ?m |} FILTER(?m != \"reclaim\") }",
    "claim_add_rdf11": "INSERT DATA { fab:claim-1 a fab:Claim ; fab:claimFrom fab:$src ; fab:claimTo fab:$dst ;\n  fab:medium \"upw\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_add_rdf12": "INSERT DATA { fab:claim-1 rdf:reifies <<( fab:$src fab:feeds fab:$dst )>> ;\n  fab:medium \"upw\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_remove_rdf": "DELETE WHERE { fab:claim-1 ?p ?o }",
    # what neosemantics 5.26 does with `<< s p o >> :q v`: it creates the edge (RDFToLPGStatementProcessor.java:421)
    "claim_add_neo4j_n10s": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (s)-[:FEEDS {medium: 'upw', source: 'BIM', confidence: 0.55, claim: true}]->(d)",
    "claim_add_neo4j_node": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (c:Claim {source: 'BIM', confidence: 0.55, medium: 'upw'}),\n       (c)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)",
    "claim_remove_neo4j": "MATCH ()-[f:FEEDS {claim: true}]->() DELETE f WITH count(*) AS x MATCH (c:Claim) DETACH DELETE c",
}

CONSOLE = [
    {"title": "RDF 1.2 · claimed but not asserted", "engine": "rdf12",
     "text": "SELECT ?s ?d ?source ?conf WHERE {\n  ?r rdf:reifies ?t ; fab:sourceSystem ?source ; fab:confidence ?conf .\n  BIND(SUBJECT(?t) AS ?s) BIND(OBJECT(?t) AS ?d)\n  FILTER NOT EXISTS { ?s fab:feeds ?d }\n}"},
    {"title": "RDF 1.2 · everything said about one pipe", "engine": "rdf12",
     "text": "SELECT ?property ?value WHERE {\n  ?r rdf:reifies <<( fab:MBP-B fab:feeds fab:UF-B )>> ; ?property ?value .\n}"},
    {"title": "RDF 1.1 · the class hierarchy is data", "engine": "rdf11",
     "text": "SELECT ?class ?parent WHERE { ?class rdfs:subClassOf ?parent } ORDER BY ?parent ?class"},
    {"title": "RDF 1.1 · SCADA tags of loop B", "engine": "rdf11",
     "text": "SELECT ?tag ?value ?unit WHERE {\n  fab:LOOP-B fab:hasDatapoint ?dp .\n  ?dp fab:tag ?tag ; fab:value ?value ; fab:unit ?unit .\n}"},
    {"title": "Neo4j · pipes running above 80 % of capacity", "engine": "neo4j",
     "text": "MATCH (s)-[f:FEEDS]->(d)\nWHERE f.flow_m3h > 0.8 * f.capacity_m3h\nRETURN s.id AS s, d.id AS d, f.medium AS medium,\n       f.flow_m3h AS flow, f.capacity_m3h AS capacity ORDER BY s"},
    {"title": "Neo4j · every route from the UPW tank to WET-01", "engine": "neo4j",
     "text": "MATCH p = (:Entity {id: 'UPW-TK'})(()-[f:FEEDS WHERE f.medium <> 'reclaim']->())+(:Entity {id: 'WET-01'})\nRETURN [n IN nodes(p) | n.id] AS route"},
    {"title": "Neo4j · claims stored as nodes", "engine": "neo4j",
     "text": "MATCH (c:Claim)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)\nRETURN s.id AS s, d.id AS d, c.source AS source, c.confidence AS conf"},
]

STORY = [
    {"id": "plant", "title": "Meet the plant", "q": None,
     "plant": "Top row: cooling. Cooling towers cool the condenser water, chillers make ~6 °C chilled water, and heat exchangers pass that cold to the process-cooling loop and to the UPW trim cooler. Middle row: city water is filtered, desalted by two parallel reverse-osmosis trains, degassed and ion-exchanged into the UPW tank. Bottom row: the water is cooled, UV-treated and split into two polishing trains (A and B), each ending in a supply loop. Tools tap off loop A, loop B, or both. Used rinse water goes to the reclaim tank and back to the start.",
     "look": "Hover any box for what it is and its live SCADA values. A red dot means an active alarm. Pipe colours are the medium (legend under the diagram).",
     "teaches": "The same plant is stored three ways: RDF 1.1 (every pipe becomes a node with properties), RDF 1.2 (the pipe stays one statement and gets statements about it), and a property graph in Neo4j (the pipe is a relationship with properties)."},
    {"id": "s1", "title": "Polishing train B goes offline", "q": "Q1", "params": {"asset": "MBP-B"},
     "plant": "Maintenance wants to change the resin in polishing mixed bed B.",
     "ask": "What sits downstream of it?",
     "look": "Six tools light up: everything fed from loop B. Three of them also have loop A, so 'downstream' isn't the same as 'loses water'. That's the next step.",
     "teaches": "All three engines answer this. The catch: the reclaim pipes form a loop back to the start, so 'downstream' must follow supply pipes only. Neo4j filters the pipe medium inside the path; both RDF versions need a ready-made fab:supplies predicate because SPARQL property paths can't look at pipe properties."},
    {"id": "s2", "title": "Is it safe to isolate?", "q": "Q2", "params": {"asset": "MBP-B"},
     "plant": "Before isolating a unit, the operator needs the tools that will be left with no UPW at all, taking redundancy into account.",
     "ask": "If MBP-B is isolated, which tools lose UPW completely?",
     "look": "Three tools (those on loop B only). Then pick RO-2 or CH-2 in the selector: the plant has a second RO train and a second chiller, so nothing is lost, but both RDF columns say every UPW tool is lost. Pick UV-1: there is only one UV, so every UPW tool really is lost. That's a hidden single point of failure.",
     "teaches": "This is the clearest operational difference. 'Is there still a path that avoids this unit?' is one Cypher pattern. SPARQL can't exclude a node from a path, so the RDF columns run the best single-query approximation, which breaks whenever the redundancy is further upstream."},
    {"id": "s3", "title": "Bad water at a wet bench", "q": "Q5", "params": {"tool": "WET-03"},
     "plant": "Wet bench 3 reports its rinse water resistivity is dropping (pure water is 18.2 MΩ·cm; lower means ions are getting through).",
     "ask": "Which units upstream of WET-03 have an active alarm?",
     "look": "Four suspects: loop B and mixed bed B (resistivity low: the likely cause), RO-2 and chiller 2. Switch to WET-02, which is on loop A: only RO-2 and chiller 2 remain, and that tool isn't complaining. So the problem points at train B.",
     "teaches": "This is the graph + SCADA join: the graph knows what feeds what, SCADA knows what is alarming, and the tag names connect them. All three models do this well once the 'supply pipes' rule exists."},
    {"id": "s4", "title": "Trace the water", "q": "Q4", "params": {"src": "UPW-TK", "dst": "WET-03"},
     "plant": "To walk the line, the operator wants the actual route the water takes.",
     "ask": "What route does water take from the UPW tank to WET-03?",
     "look": "Six pipes: tank → trim cooler → UV → MBP-B → UF-B → loop B → WET-03. Change 'From' to CITY: Neo4j finds the 13-pipe route; both RDF columns report no path, because their query only spells out 6 depths.",
     "teaches": "Paths are a native result in Cypher. SPARQL only says whether a route exists, so returning the route means writing out every possible length in advance."},
    {"id": "s5", "title": "Which tools hang on one train?", "q": "Q6", "params": {"filter": "supply pipes only"},
     "plant": "An engineering audit: which tools have no redundant UPW supply?",
     "ask": "Which tools get their UPW through only one polishing train?",
     "look": "Six tools. Switch the filter to 'include reclaim pipes': all three engines drop to 0 and are marked 'differs'. Through the reclaim tank every tool is technically 'connected' to both trains, which is false for supply. The engines aren't broken; the question is.",
     "teaches": "Recycle loops are normal in process plants, and they make naive graph traversal wrong. The fix is the same as in step 1: follow supply pipes only. Neo4j does it inline; RDF bakes it into a predicate."},
    {"id": "s6", "title": "An unconfirmed BIM cross-connect", "q": "Q6", "params": {"filter": "supply pipes only"}, "claim": True,
     "plant": "The BIM model shows a pipe from loop B to wet bench 2, which would make WET-02 redundant. Nobody has confirmed it in the field and it isn't in the DCS.",
     "ask": "Inject the claim, then re-run the audit.",
     "look": "With 'n10s 5.26 import', Neo4j now says 5 tools instead of 6: WET-02 looks redundant because the claim became a real pipe. The RDF columns still say 6. Switch the import to 'Claim node' and every engine agrees again. Check step 2 with MBP-A too: Neo4j wrongly says WET-02 keeps water.",
     "teaches": "RDF 1.2 can hold a statement that is claimed but not asserted. The standard RDF→Neo4j importer (n10s 5.26) turns it into a real relationship, which hides a real risk. Keep claims as separate nodes, and treat RDF as the source of truth."},
]


def fill(template: str, params: dict) -> str:
    out = template
    for k, v in sorted(params.items(), key=lambda kv: -len(kv[0])):
        sv = str(v)
        if not (ID_RE.match(sv) or re.fullmatch(r"-?\d+(\.\d+)?", sv) or sv in ("P&ID",)):
            raise ValueError(f"bad parameter {k}={v!r}")
        out = out.replace("$" + k, sv)
    return out


def catalogue() -> dict:
    return {"prefixes": PREFIXES, "questions": QUESTIONS, "updates": UPDATES, "console": CONSOLE, "story": STORY,
            "types": {k: {"category": c, "about": a} for k, (c, a) in TYPES.items()},
            "media": {k: {"label": l, "about": a} for k, (l, a) in MEDIA.items()}, "claim_default": CLAIM_DEFAULT}


# ---------------------------------------------------------------- plain-Python reference answers (for check.py)
def reference(d: dict, q: str, p: dict) -> list:
    from collections import defaultdict, deque
    typ = {n["id"]: n["type"] for n in d["nodes"]}
    feeds = [e for e in d["edges"] if e["type"] == "feeds"]
    sup = [e for e in feeds if e["medium"] != "reclaim"]
    out = defaultdict(list)
    for e in sup: out[e["src"]].append(e["dst"])
    tools = [n for n, t in typ.items() if t in TOOL_TYPES]

    def reach(start, adj, skip=None):
        seen, dq = set(), deque([start])
        if start == skip: return set()
        while dq:
            for v in adj[dq.popleft()]:
                if v != skip and v not in seen: seen.add(v); dq.append(v)
        return seen
    if q == "Q1": return sorted(reach(p["asset"], out))
    if q == "Q2":
        upw_tools = {e["dst"] for e in feeds if e["medium"] == "upw" and e["dst"] in tools}
        ok = set()
        for s in (n for n, t in typ.items() if t == "Source"): ok |= reach(s, out, p["asset"])
        return sorted(upw_tools - ok)
    if q == "Q3": return sorted(f'{e["src"]}>{e["dst"]}' for e in feeds if e["source"] == p["source"] and e["confidence"] < float(p["conf"]))
    if q == "Q4":
        dist, dq = {p["src"]: 0}, deque([p["src"]])
        while dq:
            u = dq.popleft()
            for v in out[u]:
                if v not in dist: dist[v] = dist[u] + 1; dq.append(v)
        return [f"length {dist[p['dst']]}"] if p["dst"] in dist else ["no path"]
    if q == "Q5":
        rin = defaultdict(list)
        for e in sup: rin[e["dst"]].append(e["src"])
        up = reach(p["tool"], rin)
        owner = {e["dst"]: e["src"] for e in d["edges"] if e["type"] == "hasDatapoint"}
        al = {n["id"]: n for n in d["nodes"] if n["type"] == "Alarm" and n["active"]}
        return sorted(f'{owner[e["dst"]]}|{al[e["src"]]["text"]}' for e in d["edges"]
                      if e["type"] == "raisedOn" and e["src"] in al and owner[e["dst"]] in up)
    if q == "Q6":
        adj = out   # physical truth: water only flows along supply pipes, whatever the query follows
        hits = defaultdict(set)
        for uf in (n for n, t in typ.items() if t == "Ultrafilter"):
            for t in reach(uf, adj):
                if t in tools: hits[t].add(uf)
        return sorted(t for t, s in hits.items() if len(s) == 1)
    raise ValueError(q)


if __name__ == "__main__":
    d = dataset()
    print(json.dumps({"nodes": len(d["nodes"]), "edges": len(d["edges"])}))
    for q, p in [("Q1", {"asset": "MBP-B"}), ("Q2", {"asset": "MBP-B"}), ("Q2", {"asset": "RO-2"}), ("Q2", {"asset": "UV-1"}),
                 ("Q4", {"src": "CITY", "dst": "WET-03"}), ("Q5", {"tool": "WET-03"}), ("Q5", {"tool": "WET-02"}),
                 ("Q6", {"filter": "supply pipes only"}), ("Q6", {"filter": "include reclaim pipes"})]:
        print(q, p, reference(d, q, p))
