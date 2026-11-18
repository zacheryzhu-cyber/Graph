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

---
## Stage 3 — RDF 1.2 (RDF-star / triple terms) in Oxigraph
**Why:** RDF 1.2 keeps the direct triple `A fab:feeds B` and hangs the metadata on a **reifier**: `r rdf:reifies <<( A fab:feeds B )>>`.
Traversal stays simple, and the metadata is still standard RDF. RDF 1.2 can also express things an LPG cannot:
**several independent statements about the same edge** (BIM says 0.7, WinCC OA says 0.95) and **claims that are not asserted**
(BIM *says* PDU-01 feeds tool X, but the link isn't in the operational graph).
**Watch for:** triple count compared with n-ary, query readability, and whether the queries get faster.
**What happened:**
| SCALE | triples | reifier triples | load | Q1 impact | Q2 | Q3 | Q4 path | Q5 |
|---|---|---|---|---|---|---|---|---|
| 1  | 2,457   | 1,104  | 17 ms  | **0.40 ms** | 0.36 | 0.27 | 0.38 | 0.24 |
| 10 | 23,751  | 10,760 | 126 ms | **0.28 ms** | 3.2  | 3.5  | 0.6  | 2.6  |
| 50 | 118,641 | 53,592 | 852 ms | **0.29 ms** | 22   | 24   | 0.5  | 14   |

- **Triple count:** about 5 % *fewer* than n-ary (9 per edge vs 10: direct triple + `rdf:reifies` + 7 props, vs type/from/to + 7). This is **not** the 50 % saving early RDF-star marketing implied. The win is shape, not size.
- **Q1 impact became constant-time with respect to graph size** (0.3 ms at 125k triples vs 169 ms for n-ary). The direct `fab:feeds+` path anchors from the tripped switchgear, so this is a **580× difference at SCALE=50** for the same answer. The traversal query reads the way an engineer thinks: `fab:SWG-B01-A fab:feeds+ ?t`.
- **Q2/Q3 (filter on edge metadata) are no faster:** the engine still joins reifier → triple term → properties. The annotation syntax `?s fab:feeds ?d {| fab:redundant false |}` is far more readable, though.
- **Load is ~50 % slower** (852 vs 538 ms at SCALE=50): triple terms are indexed as nested terms.
- **Capabilities no LPG edge has** (demo at SCALE=1):
  - a **claimed-but-not-asserted** link (`PDU-B01-01 → T-B01-402`, BIM, conf 0.55) is queryable as a claim, yet correctly **not** traversed by impact analysis;
  - one edge carries **two independent statements** (CMMS=0.83, WinCC OA=0.99), each with its own provenance.

  That is the RDF 1.2 sweet spot: reconciling conflicting facility sources (BIM vs CMMS vs SCADA).
- Turtle written to `out/fab_rdf12.ttl`. Look for `rdf:reifies <<( ... )>>`.

---
## Stage 4 — LPG (Neo4j 5.26 + Cypher)
**Why:** In an LPG, relationships are first-class records **with properties**. The 138 feeds are 138 relationships, each with 7 properties, with no extra nodes or triples.
Traversal is pointer-chasing (index-free adjacency), and Cypher returns **paths** natively. There are no global IRIs and no ontology, though:
"is a ProductionTool" becomes **an extra label you must remember to set**, not something inferred.
**Watch for:** query readability, path return (Q4), what replaces `rdfs:subClassOf*`, and Bolt round-trip overhead vs the in-process Oxigraph (a fairness caveat).
**What happened** (client = Python wall-clock incl. Bolt round trip; server = Neo4j-reported):
| SCALE | nodes / rels | load | Q1 impact | Q2 | Q3 | Q4 path | Q5 |
|---|---|---|---|---|---|---|---|
| 1  | 261 / 398       | 373 ms   | 10.0 (srv 4) | 8.7 (2)  | 8.4 (2)  | 7.2 (2) | 9.3 (3) |
| 10 | 2,544 / 3,888   | 1,229 ms | 6.6 (2)      | 15 (6)   | 14 (3)   | 4.4 (2) | 8.7 (4) |
| 50 | 12,748 / 19,446 | 2,136 ms | 4.4 (0)      | 22 (12)  | 51 (13)  | 4.6 (2) | 18 (11) |

- **Storage:** 398 relationships vs 2,457–2,595 triples, the same information. Edge metadata costs **no extra structural elements**.
- **Q1:** `(:Entity {id:$src})-[:FEEDS*]->(t:ProductionTool)`. The planner chose `VarLengthExpand(Pruning,BFS,All)` from a unique-index seek, so it stays constant with respect to graph size (like RDF 1.2, unlike n-ary RDF). **But `:ProductionTool` works only because the loader added that label.** Add a new tool type, forget the label, and impact analysis silently misses it. That is the LPG price for having no ontology.
- **Q4 is the LPG home turf:** `shortestPath(...)` returns the **actual path**, no depth unrolling. Note it returned a *different* path of equal length (via UPS/PDU instead of chiller/PCW). Ties are real in redundant facility topologies, and `allShortestPaths` returns all of them.
- **Q2/Q3:** relationship-property filters scan all FEEDS relationships. Neo4j 5 supports **relationship property indexes** (`CREATE INDEX FOR ()-[f:FEEDS]-() ON (f.source)`) if this became hot.
- **Fairness caveat:** Oxigraph runs in-process, while Neo4j adds ~4–8 ms of Bolt + driver overhead per query. At this data size the **server-side** times are the honest comparison: both engines answer everything in **< 25 ms at SCALE=50**. Load is slower in Neo4j (transactional writes plus index maintenance over Bolt).

---
## Stage 5 — making them work together (RDF ⇄ LPG, plus SHACL)
**Why:** Real fab and data-centre architectures rarely pick one model. The typical pattern is **RDF/ontology as the semantic layer**
(shared vocabulary, IRIs, SHACL governance, integration of BIM, CMMS and SCADA) and **LPG as the operational/analytics projection**
(traversals, path finding, GDS algorithms). This stage measures what survives the trip **RDF 1.2 → LPG → RDF 1.2**,
emulating neosemantics (n10s) conventions, and checks whether SHACL tooling handles RDF 1.2 yet.
**Watch for:** information loss at the boundary (multiple reifiers, unasserted claims, class hierarchy), and tool-support gaps.
**What happened:**
- **Clean round trip RDF 1.2 → LPG → RDF 1.2 is lossless:** 2,457 triples → 275 nodes / 414 rels → 2,457 triples, 0 lost, 0 gained.
  It works because every reifier has exactly one *asserted* triple, which maps 1:1 onto a relationship with properties.
  (The extra 14 nodes / 16 rels are the ontology classes and their `rdfs__subClassOf` links, which n10s also imports as nodes.)
- **With RDF 1.2-only provenance, 6 triples are lost**: 1 *unasserted* BIM claim (no edge exists to hang it on) and 1 *second statement* about an existing edge
  (an LPG relationship has a single property map, so one source silently overwrote the other). The fix in LPG is modelling, not mapping:
  separate `:Claim` nodes, or parallel relationships, which brings back the n-ary pattern you left RDF to avoid.
- **SHACL:** pyshacl, with `rdfs` inference so `sh:targetClass fab:ProductionTool` reaches EUVScanner, EtchTool, etc., found **exactly the 2 injected defects**
  (tool without power feed; load 2,500 kW > capacity) in 342 ms. **Tool gap:** rdflib 7.6 **cannot parse RDF 1.2** (`<<( )>>` fails), so SHACL had to run on the
  RDF 1.1 n-ary copy. Oxigraph handles RDF 1.2, but the Python validation ecosystem doesn't yet. Check this before committing to RDF 1.2 in a project.
- Neo4j's own answer to governance is constraints (uniqueness, existence, property type in 5.x Enterprise), which is much weaker than SHACL shapes over class hierarchies.

---
## Stage 6 — where each one hits the wall
**Why:** At fab-building scale everything is fast (< 25 ms). Real decisions hinge on the failure modes:
1. **Redundancy explosion:** fabs and data centres are built N+1 / 2N, so the number of *paths* grows exponentially with depth while the number of *nodes* grows linearly.
   Cypher matches **paths** (with relationship-uniqueness), while SPARQL property paths use **set semantics** (reachability only).
2. **SCADA write rate:** WinCC OA tags change many times a second. Can the graph hold live values?
3. **Scale trend** of everything from stages 2–4 (consolidated table).
**Watch for:** a single query going from milliseconds to timeout, and which model can't even *express* the question.
**What happened** (full output: `out/step6_output.txt`, table: `out/comparison.md`):

**1. Redundancy path explosion (2N mesh, k layers):**
| k | distinct paths | SPARQL `feeds+` reach | Cypher `count(DISTINCT x)` reach | Cypher `count(p)` paths | Cypher `shortestPath` |
|---|---|---|---|---|---|
| 8  | 256       | 0.4 ms | 38 ms (cold) | 41 ms    | 29 ms (cold) |
| 16 | 65,536    | 0.2 ms | 2 ms | 170 ms   | 6 ms |
| 20 | 1,048,576 | 0.2 ms | 2 ms | **1,662 ms** | 4 ms |
| 22 | 4,194,304 | 0.2 ms | 2 ms | skipped (projected ~7 s) | 3 ms |
- Asking "*what* is reachable" is cheap in both: SPARQL set semantics, and Neo4j's planner rewrites `[:FEEDS*]` + `DISTINCT` into a pruning BFS.
- **Enumerating paths is exponential**, and only Cypher can even express it. That's the double edge: Cypher lets you ask "list every power path to this EUV scanner", which is a legitimate redundancy audit, but in a 2N/N+1 data centre with 20 tiers it takes seconds to minutes and can exhaust memory.
  **Rule:** use `DISTINCT` reachability or `shortestPath`/`allShortestPaths`, bound the depth (`*..8`), or use GDS. Never write an unbounded `MATCH p=...-[*]->...` on a redundant topology.
- **SPARQL can't enumerate paths at all.** In a redundancy audit ("is there any tool with only ONE independent power path?") RDF has to fall back to client-side code or unrolled patterns.

**2. SCADA live-value writes (5,000 values per tick):**
- Oxigraph SPARQL UPDATE, batched: **~350k values/s** (in-memory, no durability).
- Neo4j batched `UNWIND … SET`: **~76k values/s** (durable transactions).
- Neo4j one transaction per value: **~360 values/s**, about **200× slower** than batching.
- **My own measurement mistake:** before I added `CALL db.awaitIndexes()`, batched Neo4j writes measured **1.6k/s**. The index was still building, so every `MATCH` label-scanned. Make index readiness part of the deployment checklist.
- **Verdict:** a mid-size fab's WinCC OA produces 10k–100k value changes/s. **Neither graph is a historian.** Keep values in WinCC OA archive / NGA / a TSDB.
  Put **only the tag identity and its context** (which asset, which area, which feed) in the graph, plus *slow* state (alarm active, maintenance mode), and join at query time by tag name.

**3. Optimizer bottleneck behind Stage 2's slow Q1 (SCALE=50):**
- n-ary path alone: 0.7 ms. Path + `?t a/rdfs:subClassOf* fab:ProductionTool`: **187 ms**. Same query with the traversal forced first via a subquery: **2.7 ms**.
- The SPARQL planner started from "all ProductionTools in all 50 buildings" and tested reachability for each. **Declarative isn't plan-proof**; check plans (Oxigraph `explain`, Cypher `EXPLAIN/PROFILE`).

---
## Stage 7 — wrap-up
`./run_all.sh` runs everything end-to-end in **~19 s** (all scales, 54/54 ground-truth checks ✓). A re-run varied ±20 % on individual timings,
so treat any sub-5 ms difference as noise. The big effects (580× for Q1 shape, exponential path counting, 200× batching) are robust.
Decision guide: **SUMMARY.md**. Latest numbers: **RESULTS.md**.

---
# Refinement pass (+30 min)

## R1 — real neosemantics behaviour, checked against its code and its parser
**Why:** My Stage 5 emulation mapped RDF 1.2 reifiers onto relationship properties. That was *more capable than the real tool*. I checked what n10s 5.26 actually does.

**What happened:**
- n10s 5.26.0 bundles **rdf4j 4.3.12**. Parsing with that exact jar (`./n10s_parser_check/run.sh`):
  - RDF-star 2021 `<< :UPS-1 :feeds :PDU-1 >> :installed 2012` → parsed, mapped to **relationship property** ✓
  - RDF 1.2 `:r1 rdf:reifies <<( … )>>` → **PARSE FAILED** (`Expected an RDF value here, found '('`)
  - RDF 1.2 `:a :feeds :b ~ :r1 {| … |}` → **PARSE FAILED** (`Expected '.', found '~'`)
- n10s source, `RDFToLPGStatementProcessor.java:406–449`:
  - a triple in **subject** position → relationship + properties;
  - a triple in **object** position → `// ignore RDF* statements with triples as object`. That is precisely the RDF 1.2 form.
  - For `<< s p o >> :q v` it calls `addStatement()`, i.e. it **creates the edge even though a quoted triple is not asserted**.
- **Consequence, demonstrated end-to-end** (`step5b_n10s_compat.py`):
  1. I injected one *unasserted* BIM claim ("PDU-B01-01 also powers T-B01-107"). In reality, T-B01-107 is fed only from SWG-B.
  2. Down-converting RDF 1.2 → Turtle-star 2021 and importing with n10s semantics turned it into a real `feeds` edge `{sourceSystem: BIM, confidence: 0.55, medium: power}`.
  3. The single-point-of-failure audit then reported **29 instead of 30** SPOF tools. **The phantom redundancy hid exactly the tool at risk.**
  The down-conversion also drops all 139 reifier identities and merges multi-source statements onto one quoted triple.
- **Practical rule:** with n10s today, (1) export RDF 1.2 as Turtle-star 2021, (2) **filter to asserted triples only** before import, (3) keep claims in RDF, or model them as `:Claim` nodes in Neo4j. Re-check this when an n10s release moves to rdf4j 5.x (rdf4j documents RDF 1.2 support in 5.x).

## R2 — Q6: a path filtered on an edge property (single-point-of-failure audit)
**Why:** "Which tools get power from only one switchgear?" needs a transitive path where **every edge** has `medium = power`.

**What happened:**
- **Ignoring the edge property gives a dangerously wrong answer:** 0 SPOF tools instead of 30 at SCALE=1 (cooling paths via chillers look like power redundancy).
- **Cypher (Neo4j 5.9+ quantified path pattern)** expresses it directly: `(sw:Switchgear) (()-[f:FEEDS WHERE f.medium='power']->())+ (t:ProductionTool)`.
- **SPARQL property paths cannot filter on edge metadata inside a path**, in RDF 1.1 *or* RDF 1.2. Both had to **materialise** a sub-property `fab:feedsPower` first (SPARQL UPDATE, 114 ms at SCALE=200), which then has to be maintained.
  The RDF best practice is to model typed predicates (`fab:feedsPower rdfs:subPropertyOf fab:feeds`) from day one, so put edge properties you'll traverse on *into the predicate*.
- Speed at SCALE=200: Neo4j **26 ms server** vs RDF 1.2 **140 ms** / n-ary 98 ms (after materialisation).

## R3 — tighter numbers and SCALE=200 (p50/p95, 15 runs after warm-up; full table in RESULTS.md)
| SCALE=200 (51k nodes, 78k rels; 475–502k triples) | RDF 1.1 n-ary | RDF 1.2 | Neo4j (client / server) |
|---|---|---|---|
| load | 2.6 s | 3.8 s | 6.1 s |
| Q1 impact (as written) | **802 ms** | 0.3 ms | 3.7 / 1 ms |
| Q1b traversal-first rewrite | 7.3 ms | 0.3 ms | — |
| Q2 edge-property filter | 105 ms | 100 ms | 103 / 57 ms |
| Q3 provenance filter | 88 ms | 76 ms | 202 / 29 ms |
| Q4 path | 1.4 ms (unrolled) | 0.5 ms (unrolled) | 2.9 / 2 ms (native) |
| Q5 aggregate | 65 ms | 69 ms | 46 / 24 ms |
| Q6 SPOF audit | 98 ms + 114 ms prep | 140 ms + 118 ms prep | 135 / 26 ms |
- p95 sits within ~10–20 % of p50 for almost everything, so the effects below are robust, not noise.
- **Neo4j client vs server gap** on Q3 (202 vs 29 ms): returning ~15k rows over Bolt dominates. In an app, aggregate server-side and return less.
- **Relationship-property index** on `FEEDS.source`: the plan switched from `DirectedRelationshipTypeScan` to `DirectedRelationshipIndexSeek`, and server time went 35 → 20 ms. The gain is modest because a third of all feeds match; indexes pay off on selective predicates.
- **Writes, fairer now:**

  | Engine / mode | Values/s |
  |---|---|
  | Oxigraph in-memory, batched | 215–340k |
  | Oxigraph **on-disk, batched** | ~91k |
  | Oxigraph on-disk, one update per value | ~13–20k |
  | Neo4j batched | 41–76k |
  | Neo4j one tx per value | ~230–360 |

  Neo4j's per-value cost includes the Bolt round trip and the transaction commit, so it isn't a pure engine comparison, but it's what an app that writes naively experiences.
  The historian verdict stands.

---
## Stage 8 — working demo (Fab Graph Workbench)
**Why:** Numbers in a table don't show a customer *why* the model choice matters. The workbench lets you trip assets, change thresholds and inject a
BIM claim, then watch three engines answer side by side, each checked against an independent reference.

**What happened:**
- Live mode (`demo/server.py`): all six questions agree with the reference on all three engines at scale 1. Per-query p50: Oxigraph 0.1–0.7 ms; Neo4j 5–8 ms client / 2–3.5 ms server.
- **The BIM-claim scenario reproduces live, and it is worse than Stage 5b showed.** With the n10s-style import, Neo4j differs on **Q6** (29 instead of 30 SPOF tools),
  and also on **Q1**: tripping PDU-B01-01 now "impacts" T-B01-107, which it doesn't feed. Switching Neo4j to the claim-node model makes every engine agree again.
- Another reminder of planner sensitivity: the obvious RDF 1.1 Q1 (`fab:x (^fab:feedFrom/fab:feedTo)+ ?x . ?x a ?type`) took **30 ms vs 0.26 ms** for RDF 1.2.
  The demo uses the traversal-first sub-select and says so in the query note.
- **Published copy:** running the downloaded Oxigraph JS/WASM build was blocked by the session's permission policy, so the published page is a *recorded edition*.
  Every preset × parameter × claim state (8,088 runs) is embedded, keyed by a hash of the exact query text. The topology, scenarios and correctness checks still run in the browser.

## Stage 9 — live SCADA values + step-by-step setup (SETUP.md)
**Before:** expectation that the graph should only see state changes, never samples, and that the tag name is enough to join both worlds.

**After (measured, `step7_scada_bridge.py`, SCALE=1, 8 s):**
- OPC UA simulator with 169 WinCC OA-style tags → asyncua subscription (100 ms) → SQLite historian: ~1,080 samples/s, source→historian latency p50 50 ms / p95 100 ms (bounded by the publishing interval).
- Rule (chiller supply water > 10 °C) fired once → **1 graph write** for ~8,650 samples. Tag → datapoint → asset → downstream tools: 25 tools, identical in SPARQL (RDF 1.2) and Cypher, ✓ against ground truth. Affected tools' latest PowerDraw came from the historian, joined by tag.
- Context lookup + alarm write: ≈ 0.6 s right after Neo4j start (query planning), 16 ms on a second run. Precompute asset→downstream sets when topology changes.
- Oxigraph server checked for SETUP.md: `POST /store` without `?default` silently loads into a **new named graph**, so default-graph queries return 0 rows. Use `/store?default`.
- `pyshacl -s out/fab_shapes.ttl -i rdfs out/fab_rdf11.ttl` → Conforms: True on clean data (the gate for use case A).
