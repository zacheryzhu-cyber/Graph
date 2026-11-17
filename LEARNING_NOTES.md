# LEARNING_NOTES.md

One use case throughout: **a semiconductor fab's facility systems** — utility chain
(switchgear → UPS → PDU, chillers → cooling loops → CRAH/process-cooling) feeding production tools
(EUV scanners, etch, CVD) and SCADA datapoints (WinCC OA-style tags like `Fab1.CH01.SupplyTemp`)
with alarms. Everything is generated from `data/facility.json`.

The questions every model must answer (Q1–Q5):
- **Q1 impact**: chiller CH-01 trips — which production tools lose cooling (multi-hop, transitive)?
- **Q2 edge facts**: non-redundant feeds installed before 2018 with load > 70 % of capacity (properties *of the relationship*).
- **Q3 provenance**: which links come from the BIM model with confidence < 0.8 (statement-level metadata — "who said this edge exists?").
- **Q4 path**: the actual chain from switchgear SWG-A to a given tool (return the path, not just reachability).
- **Q5 aggregate**: datapoints and active alarms per area.

---
## Stage 0 — toolchain reality check
**Why:** "RDF-star" has changed meaning while the spec matured. Tools that claim support may implement
the 2021 Community Group draft (quoted triples) or the RDF 1.2 draft (triple terms + reifiers). Check, don't assume.

**What happened (measured, 2026-11-17):**
- **W3C status:** RDF 1.2 is still at **Working Draft** stage (latest drafts dated 2026). RDF 1.1 is still the current Recommendation. "RDF-star" as a name is effectively replaced by RDF 1.2 *triple terms*.
- **pyoxigraph 0.5.13** fully parses RDF 1.2: triple terms `<<( s p o )>>`, reifiers `~ :r`, annotations `{| |}`, and SPARQL 1.2 annotation patterns.
- **Key semantic surprise:** the *old* RDF-star syntax `<< :a :b :c >> :since 2020` is **no longer a quoted triple used as a subject**. Under RDF 1.2 it becomes **2 triples**: a blank-node *reifier* `_:r rdf:reifies <<( :a :b :c )>>` plus `_:r :since 2020`. Triple terms may only appear in the **object** position. Data written for RDF-star 2021 can silently change shape when an RDF 1.2 parser loads it. **Watch for this in migrations.**
- An *annotation* `:a :b :c {| :since 2020 |}` **asserts** the base triple (3 triples). A bare `<< >>` only **mentions** it (2 triples, base triple not asserted). Asserted vs mentioned matters for fab provenance ("is this link real, or just claimed by the BIM model?").
- **Neo4j:** Docker has no daemon here and dist.neo4j.org returns 403, so I run Neo4j **5.26.33** (the final 5.x LTS) embedded via Maven with a Bolt port. **n10s:** not reachable (GitHub releases blocked, not on Maven Central). Its conventions are emulated in step 5.

---
## Stage 1 — one canonical dataset
**Why:** Comparisons between graph models are usually unfair, because each demo uses data shaped for its own strengths.
Here one model-neutral JSON (`nodes` + `edges` with properties) is generated once. Every model is *derived* from it.
**Watch for:** how many edges carry **metadata** (install year, capacity, load, redundancy, source system, confidence).
That metadata is exactly where RDF, RDF 1.2 and LPG diverge.
**What happened:** SCALE=1 → **261 nodes, 398 edges**, of which **138 `feeds` edges carry 7 properties each**
(medium, installed, redundant, capacity_kW, load_kW, source, confidence). SCALE=10 → 2,544 / 3,888; SCALE=50 → 12,748 / 19,446.
About **35 % of edges carry metadata**. That share is typical of facility graphs, where utility links have engineering attributes and structural links (`locatedIn`) don't.

---
## Stage 2 — plain RDF (RDF 1.1) in Oxigraph
**Why:** RDF gives global identifiers (IRIs), a schema/ontology (`rdfs:subClassOf`), and standards (SPARQL, SHACL)
that are the same across vendors. A triple, though, **has no place for properties**. To say "this feed was installed in 2012,
is non-redundant, and comes from BIM with 0.7 confidence", RDF 1.1 has to turn the edge into a node (an n-ary relation / "Feed" object).
**Watch for:** how many triples that costs, and how much more awkward the multi-hop query (Q1) and path query (Q4) become.
**What happened:**
| SCALE | triples | of which Feed-node triples | load | Q1 impact | Q2 | Q3 | Q4 path | Q5 |
|---|---|---|---|---|---|---|---|---|
| 1  | 2,595   | 1,380 (53 %)  | 13 ms  | 1.8 ms | 0.5 | 0.3 | 0.8 | 0.3 |
| 10 | 25,096  | 13,450        | 124 ms | 33 ms  | 5.0 | 2.7 | 0.9 | 2.0 |
| 50 | 125,340 | 66,990        | 538 ms | 169 ms | 22  | 15  | 1.0 | 13  |

All five answers match the Python ground truth (40 impacted tools, 23 risky feeds, 48 low-confidence BIM links, path length 3).
- **Cost of edge metadata in RDF 1.1:** 138 feeds × (type + from + to + 7 props) = 10 triples per edge, which is **53 % of the whole graph**. The direct `A feeds B` triple **no longer exists**, so every traversal must step through the Feed node: `(^fab:feedFrom/fab:feedTo)+`. That is readable for experts and unfamiliar to everyone else.
- **Q1 is the strength of RDF:** "is a ProductionTool" is answered by `a/rdfs:subClassOf*`. The class hierarchy is queryable data, so adding `LaserAnnealTool rdfs:subClassOf fab:ProductionTool` needs no change to the query.
- **Q4 is the weakness:** SPARQL property paths answer *whether* a path exists, but **cannot return the path**. I had to unroll depths 1..5 as UNION branches (`hops_union()`), which only works because I know the maximum depth.
- **First bottleneck seen:** Q1's answer is constant (40 tools in building B01), yet its time grows **linearly with total graph size** (1.8 → 169 ms). The engine doesn't anchor the transitive path well when it's combined with the `subClassOf*` type check. Revisited in Stage 6.
