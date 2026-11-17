"""Query catalogue shared by the live server, the browser UI and the artifact builder.

Templates use `$name` placeholders (string.Template syntax) so SPARQL/Cypher braces need no escaping.
The UI fills them client-side from validated values; the filled text is exactly what each engine runs,
and (in the published artifact) the key under which Neo4j results were recorded.
"""
import json
import re

ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

PREFIXES = ("PREFIX fab: <http://example.org/fab#>\n"
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n")

NARY_HOP = "^fab:feedFrom/fab:feedTo"
TOOL_LABEL_FILTER = "['Entity','Asset','ProductionTool','ElectricalAsset','CoolingAsset']"


def _unrolled(hop: str, max_depth: int = 5) -> str:
    """SPARQL can't return a path: unroll depths 1..k and keep the shortest."""
    branches = []
    for k in range(1, max_depth + 1):
        vs = ["?n0"] + [f"?n{i}" for i in range(1, k)] + ["?nk"]
        pats = " . ".join(f"{vs[i]} {hop} {vs[i + 1]}" for i in range(k))
        binds = " ".join(f"BIND(STR({vs[i]}) AS ?p{i})" for i in range(1, k))
        branches.append(f"  {{ {pats} . BIND({k} AS ?depth) {binds} }}")
    return ("SELECT ?depth ?p1 ?p2 ?p3 ?p4 WHERE {\n  VALUES (?n0 ?nk) { (fab:$src fab:$dst) }\n"
            + "\n  UNION\n".join(branches) + "\n} ORDER BY ?depth LIMIT 1")


QUESTIONS = [
    {
        "id": "Q1", "title": "Impact analysis",
        "ask": "Asset $asset trips. What loses power or cooling downstream?",
        "stresses": "Transitive traversal across power and cooling",
        "params": {"asset": {"kind": "infra", "default": "SWG-B01-A", "label": "Tripped asset"}},
        "rdf11": "SELECT ?x ?type WHERE {\n  { SELECT DISTINCT ?x WHERE { fab:$asset (" + NARY_HOP + ")+ ?x } }\n  ?x a ?type .\n} ORDER BY ?x",
        "rdf12": "SELECT DISTINCT ?x ?type WHERE {\n  fab:$asset fab:feeds+ ?x .\n  ?x a ?type .\n} ORDER BY ?x",
        "neo4j": "MATCH (:Entity {id: '$asset'})-[:FEEDS*]->(x)\nRETURN DISTINCT x.id AS x, x.type AS type ORDER BY x",
        "notes": {
            "rdf11": "The edge is a fab:Feed node, so one hop is an inverse step plus a forward step. The sub-select forces traversal first; without it, Oxigraph picked a 100× slower join order (see lab Stage 6).",
            "rdf12": "The direct triple survives, so the path reads as plain fab:feeds+.",
            "neo4j": "The planner turns [:FEEDS*] + DISTINCT into a pruning BFS.",
        },
    },
    {
        "id": "Q2", "title": "Risky feeds",
        "ask": "Non-redundant feeds installed before $year running above $ratio of capacity",
        "stresses": "Filtering on properties of the relationship",
        "params": {"year": {"kind": "choice", "options": [2012, 2015, 2018, 2021], "default": 2018, "label": "Installed before"},
                   "ratio": {"kind": "choice", "options": [0.5, 0.6, 0.7, 0.8, 0.9], "default": 0.7, "label": "Load above"}},
        "rdf11": "SELECT ?s ?d ?y ?ratio WHERE {\n  ?f a fab:Feed ; fab:feedFrom ?s ; fab:feedTo ?d ;\n     fab:redundant false ; fab:installed ?y ;\n     fab:loadKW ?l ; fab:capacityKW ?c .\n  BIND(?l / ?c AS ?ratio)\n  FILTER(?y < $year && ?ratio > $ratio)\n} ORDER BY ?s ?d",
        "rdf12": "SELECT ?s ?d ?y ?ratio WHERE {\n  ?s fab:feeds ?d {| fab:redundant false ; fab:installed ?y ;\n                     fab:loadKW ?l ; fab:capacityKW ?c |} .\n  BIND(?l / ?c AS ?ratio)\n  FILTER(?y < $year && ?ratio > $ratio)\n} ORDER BY ?s ?d",
        "neo4j": "MATCH (s)-[f:FEEDS]->(d)\nWHERE f.redundant = false AND f.installed < $year\n  AND f.load_kw / f.capacity_kw > $ratio\nRETURN s.id AS s, d.id AS d, f.installed AS y,\n       round(f.load_kw / f.capacity_kw, 2) AS ratio\nORDER BY s, d",
        "notes": {
            "rdf11": "Seven properties hang off an intermediate node.",
            "rdf12": "Annotation syntax {| |} matches the asserted triple and its reifier together.",
            "neo4j": "Properties sit directly on the relationship.",
        },
    },
    {
        "id": "Q3", "title": "Provenance",
        "ask": "Links asserted by $source with confidence below $conf",
        "stresses": "Metadata about a statement",
        "params": {"source": {"kind": "choice", "options": ["BIM", "CMMS", "WinCCOA"], "default": "BIM", "label": "Source system"},
                   "conf": {"kind": "choice", "options": [0.7, 0.8, 0.9, 1.0], "default": 0.8, "label": "Confidence below"}},
        "rdf11": "SELECT ?s ?d ?conf WHERE {\n  ?f a fab:Feed ; fab:feedFrom ?s ; fab:feedTo ?d ;\n     fab:sourceSystem \"$source\" ; fab:confidence ?conf .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "rdf12": "SELECT ?s ?d ?conf WHERE {\n  ?s fab:feeds ?d {| fab:sourceSystem \"$source\" ;\n                     fab:confidence ?conf |} .\n  FILTER(?conf < $conf)\n} ORDER BY ?s ?d",
        "neo4j": "MATCH (s)-[f:FEEDS]->(d)\nWHERE f.source = '$source' AND f.confidence < $conf\nRETURN s.id AS s, d.id AS d, f.confidence AS conf\nORDER BY s, d",
        "notes": {
            "rdf11": "Provenance is just more properties on the Feed node.",
            "rdf12": "Statement-level metadata is what reifiers are for. Several sources can each have their own.",
            "neo4j": "One property map per relationship, so a second source would overwrite the first.",
        },
    },
    {
        "id": "Q4", "title": "Return the path",
        "ask": "The shortest supply chain from $src to $dst",
        "stresses": "Returning a path, not just reachability",
        "params": {"src": {"kind": "infra", "default": "SWG-B01-A", "label": "From"},
                   "dst": {"kind": "tool", "default": "T-B01-101", "label": "To tool"}},
        "rdf11": _unrolled(NARY_HOP),
        "rdf12": _unrolled("fab:feeds"),
        "neo4j": "MATCH p = shortestPath(\n  (:Entity {id: '$src'})-[:FEEDS*]->(:Entity {id: '$dst'}))\nRETURN [n IN nodes(p) | n.id] AS path",
        "notes": {
            "rdf11": "Property paths only answer whether a path exists, so depths 1 to 5 are spelled out.",
            "rdf12": "Same workaround. RDF 1.2 doesn't change SPARQL's lack of path results.",
            "neo4j": "shortestPath is native. Ties are real in redundant topologies.",
        },
    },
    {
        "id": "Q5", "title": "Datapoints and alarms",
        "ask": "WinCC OA datapoints and active alarms per cleanroom area",
        "stresses": "Aggregation",
        "params": {},
        "rdf11": "SELECT ?area (COUNT(DISTINCT ?dp) AS ?datapoints) (COUNT(DISTINCT ?al) AS ?alarms) WHERE {\n  ?area a fab:Area . ?tool fab:locatedIn ?area ; fab:hasDatapoint ?dp .\n  OPTIONAL { ?al fab:raisedOn ?dp ; fab:active true }\n} GROUP BY ?area ORDER BY ?area",
        "rdf12": "SELECT ?area (COUNT(DISTINCT ?dp) AS ?datapoints) (COUNT(DISTINCT ?al) AS ?alarms) WHERE {\n  ?area a fab:Area . ?tool fab:locatedIn ?area ; fab:hasDatapoint ?dp .\n  OPTIONAL { ?al fab:raisedOn ?dp ; fab:active true }\n} GROUP BY ?area ORDER BY ?area",
        "neo4j": "MATCH (a:Area)<-[:LOCATED_IN]-(:Asset)-[:HAS_DATAPOINT]->(dp)\nOPTIONAL MATCH (al:Alarm {active: true})-[:RAISED_ON]->(dp)\nRETURN a.id AS area, count(DISTINCT dp) AS datapoints,\n       count(DISTINCT al) AS alarms ORDER BY area",
        "notes": {
            "rdf11": "Edges without metadata look the same in every model.",
            "rdf12": "Identical to RDF 1.1 here.",
            "neo4j": "Equivalent pattern.",
        },
    },
    {
        "id": "Q6", "title": "Single point of failure",
        "ask": "Production tools whose power comes from exactly one switchgear",
        "stresses": "A path where every edge must satisfy medium = power",
        "params": {"filter": {"kind": "choice", "options": ["power only", "ignore medium"], "default": "power only", "label": "Edge filter"}},
        "variants": {
            "power only": {
                "rdf11": "# SPARQL property paths can't filter on edge metadata.\n# fab:feedsPower is materialised at load time (a model change).\nSELECT ?t WHERE {\n  ?sw a fab:Switchgear . ?sw fab:feedsPower+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?sw) = 1) ORDER BY ?t",
                "rdf12": "# Same limitation in RDF 1.2: fab:feedsPower is materialised\n# from asserted triples whose reifier says medium = \"power\".\nSELECT ?t WHERE {\n  ?sw a fab:Switchgear . ?sw fab:feedsPower+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?sw) = 1) ORDER BY ?t",
                "neo4j": "MATCH (sw:Switchgear)\n      (()-[f:FEEDS WHERE f.medium = 'power']->())+\n      (t:ProductionTool)\nWITH t, count(DISTINCT sw) AS n WHERE n = 1\nRETURN t.id AS t ORDER BY t",
            },
            "ignore medium": {
                "rdf11": "SELECT ?t WHERE {\n  ?sw a fab:Switchgear . ?sw (" + NARY_HOP + ")+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?sw) = 1) ORDER BY ?t",
                "rdf12": "SELECT ?t WHERE {\n  ?sw a fab:Switchgear . ?sw fab:feeds+ ?t .\n  ?t a/rdfs:subClassOf* fab:ProductionTool .\n} GROUP BY ?t HAVING (COUNT(DISTINCT ?sw) = 1) ORDER BY ?t",
                "neo4j": "MATCH (sw:Switchgear)-[:FEEDS*]->(t:ProductionTool)\nWITH t, count(DISTINCT sw) AS n WHERE n = 1\nRETURN t.id AS t ORDER BY t",
            },
        },
        "notes": {
            "rdf11": "Needs a materialised fab:feedsPower predicate.",
            "rdf12": "Needs it too, built only from asserted triples, so unasserted claims stay out.",
            "neo4j": "A quantified path pattern filters every hop in place.",
        },
    },
]

# Model-level updates (also SPARQL/Cypher, so the browser build can run the RDF ones itself)
UPDATES = {
    "materialise_power_rdf11": "INSERT { ?s fab:feedsPower ?d } WHERE { ?f fab:feedFrom ?s ; fab:feedTo ?d ; fab:medium \"power\" }",
    "materialise_power_rdf12": "INSERT { ?s fab:feedsPower ?d } WHERE { ?s fab:feeds ?d {| fab:medium \"power\" |} }",
    # an UNASSERTED BIM claim: "$src feeds $dst"
    "claim_add_rdf11": "INSERT DATA { fab:claim-1 a fab:Claim ; fab:claimFrom fab:$src ; fab:claimTo fab:$dst ;\n  fab:medium \"power\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_add_rdf12": "INSERT DATA { fab:claim-1 rdf:reifies <<( fab:$src fab:feeds fab:$dst )>> ;\n  fab:medium \"power\" ; fab:sourceSystem \"BIM\" ; fab:confidence 0.55 }",
    "claim_remove_rdf": "DELETE WHERE { fab:claim-1 ?p ?o }",
    # what neosemantics 5.26 does with `<< s p o >> :q v`: it creates the edge (RDFToLPGStatementProcessor.java:421)
    "claim_add_neo4j_n10s": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (s)-[:FEEDS {medium: 'power', source: 'BIM', confidence: 0.55, claim: true}]->(d)",
    # the recommended alternative: keep the claim as a node, off the traversal graph
    "claim_add_neo4j_node": "MATCH (s:Entity {id: '$src'}), (d:Entity {id: '$dst'})\nCREATE (c:Claim {source: 'BIM', confidence: 0.55, medium: 'power'}),\n       (c)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)",
    "claim_remove_neo4j": "MATCH ()-[f:FEEDS {claim: true}]->() DELETE f WITH count(*) AS x MATCH (c:Claim) DETACH DELETE c",
}


CONSOLE = [
    {"title": "RDF 1.2 · every statement about one edge", "engine": "rdf12",
     "text": "SELECT ?reifier ?property ?value WHERE {\n  ?reifier rdf:reifies <<( fab:UPS-B01-1 fab:feeds fab:PDU-B01-01 )>> ;\n           ?property ?value .\n}"},
    {"title": "RDF 1.2 · claimed but not asserted", "engine": "rdf12",
     "text": "SELECT ?s ?d ?source ?conf WHERE {\n  ?r rdf:reifies ?t ; fab:sourceSystem ?source ; fab:confidence ?conf .\n  BIND(SUBJECT(?t) AS ?s) BIND(OBJECT(?t) AS ?d)\n  FILTER NOT EXISTS { ?s fab:feeds ?d }\n}"},
    {"title": "RDF 1.1 · the class hierarchy is data", "engine": "rdf11",
     "text": "SELECT ?class ?parent WHERE { ?class rdfs:subClassOf ?parent } ORDER BY ?parent ?class"},
    {"title": "RDF 1.1 · WinCC OA tags of one EUV scanner", "engine": "rdf11",
     "text": "SELECT ?dp ?tag ?unit WHERE {\n  fab:T-B01-101 fab:hasDatapoint ?dp .\n  ?dp fab:winccTag ?tag ; fab:unit ?unit .\n}"},
    {"title": "Neo4j · every power path into T-B01-107", "engine": "neo4j",
     "text": "MATCH p = (:Switchgear)-[:FEEDS*]->(:Entity {id: 'T-B01-107'})\nWHERE all(f IN relationships(p) WHERE f.medium = 'power')\nRETURN [n IN nodes(p) | n.id] AS path, [f IN relationships(p) | f.source] AS sources"},
    {"title": "Neo4j · most connected assets", "engine": "neo4j",
     "text": "MATCH (a:Asset)-[f:FEEDS]->()\nRETURN a.id AS asset, a.type AS type, count(f) AS feeds\nORDER BY feeds DESC, asset LIMIT 10"},
    {"title": "Neo4j · claims stored as nodes", "engine": "neo4j",
     "text": "MATCH (c:Claim)-[:CLAIMS_FROM]->(s), (c)-[:CLAIMS_TO]->(d)\nRETURN s.id AS s, d.id AS d, c.source AS source, c.confidence AS conf"},
    {"title": "Neo4j · labels used", "engine": "neo4j",
     "text": "CALL db.labels() YIELD label RETURN label ORDER BY label"},
]


def fill(template: str, params: dict) -> str:
    """Same substitution the browser does. Only ids, numbers and fixed choices are accepted."""
    out = template
    for k, v in sorted(params.items(), key=lambda kv: -len(kv[0])):
        sv = str(v)
        if not (ID_RE.match(sv) or re.fullmatch(r"-?\d+(\.\d+)?", sv)):
            raise ValueError(f"bad parameter {k}={v!r}")
        out = out.replace("$" + k, sv)
    return out


def catalogue() -> dict:
    return {"prefixes": PREFIXES, "questions": QUESTIONS, "updates": UPDATES, "console": CONSOLE}


if __name__ == "__main__":
    print(json.dumps(catalogue(), indent=1)[:600])
