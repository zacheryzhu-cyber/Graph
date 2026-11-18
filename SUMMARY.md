# SUMMARY — RDF vs RDF 1.2 vs LPG for fab / data-centre facility graphs

Everything below is measured in this lab: one dataset, six questions, and all three models gave identical, ground-truth-checked answers at four scales (up to ~0.5M triples / 78k relationships).
A refinement pass added p50/p95 timing, a single-point-of-failure audit (Q6), and **verification of real neosemantics behaviour** against its source code and its bundled parser.
Times are medians, on a laptop-class container.

## 1. The one-paragraph answer
- **RDF** is a *contract*: global IDs, a shared ontology, SHACL rules, and standard query/exchange formats.
- **LPG** is an *engine*: fast traversals, native paths, and properties on edges with no ceremony.
- **RDF 1.2** closes most of RDF's "edges can't have properties" gap, and adds one thing LPG cannot do: **several independent, sourced statements about the same edge, and claims that aren't asserted**.

In a fab, that means: **model and govern in RDF (1.2), operate and analyse in LPG, and keep live values in the SCADA historian**.
**But the bridge is not RDF 1.2-ready yet:** n10s 5.26 cannot parse RDF 1.2 at all, and when given 2021 RDF-star it turns *unasserted* claims into real edges (see §5, item 7).

## 2. What the numbers said
| | RDF 1.1 (n-ary) | RDF 1.2 (reifiers) | LPG (Neo4j 5.26) |
|---|---|---|---|
| Size of the same SCALE=1 fab | 2,595 triples | 2,457 triples | 261 nodes / 398 rels |
| Edge metadata overhead | 10 triples/edge, 53 % of graph | 9 triples/edge | 0 extra elements |
| Q1 impact (transitive), SCALE=50 | 169 ms (2.7 ms after rewrite) | **0.3 ms** | 4 ms client / ~0 ms server |
| Q2/Q3 filter on edge metadata, SCALE=50 | 15–22 ms | 22–24 ms | 22–51 ms client / 12–13 ms server |
| Q4 return the path | ✗ only by unrolling depths | ✗ same | ✓ `shortestPath` |
| Q6 path filtered on an **edge property** (SPOF audit), SCALE=200 | ✗ needs a materialised sub-property (114 ms prep), then 98 ms | ✗ same (118 ms prep), then 140 ms | ✓ one quantified path pattern, 26 ms server |
| Q1 impact, SCALE=200 (500k triples) | 802 ms as written / 7 ms rewritten | 0.3 ms | 3.7 ms client / 1 ms server |
| "Is an EUV scanner a ProductionTool?" | ✓ `rdfs:subClassOf*` | ✓ | ⚠ only if the loader set the label |
| Conflicting sources on one edge | awkward (multiple Feed nodes) | ✓ native (multiple reifiers) | ✗ one property map → overwrite |
| Claim not asserted (BIM says so) | awkward | ✓ native | ✗ dropped, or pollutes traversal |
| Schema validation | ✓ SHACL (pyshacl: 2/2 defects, 342 ms) | ⚠ **rdflib/pyshacl can't parse RDF 1.2 yet** | constraints only |
| Load 125k-triple / 19k-rel graph | 0.5 s | 0.9 s | 2.1 s (Bolt, transactional) |
| Count all 1M redundant paths (k=20) | can't express | can't express | 1.7 s, exponential |
| Live value writes | 215–340k/s in-mem · ~91k/s on-disk batched · 13–20k/s per update | — | 41–76k/s batched · **230–360/s per-tx** |
| See the graph out of the box | ⚠ Oxigraph UI shows result **tables**; graph views need GraphDB Workbench / Stardog Explorer | same | ✓ Neo4j Browser draws query results (:7474, not in the lab's embedded launcher) |
| Import into Neo4j via n10s 5.26 | via 2021 Turtle-star | ✗ **parse error**; must down-convert | — |

## 3. When to use which (fab / DC framing)
**Plain RDF 1.1:** use it when the job is **integration and exchange**: an asset information model shared across BIM, CMMS, MES and SCADA,
a vendor-neutral ontology (Brick, RealEstateCore, ISA-95/88, IEC 61360/ECLASS, AAS), and validation gates in a data pipeline.
It's the most mature tooling (SHACL, reasoners, every triple store). Its pain point is edge attributes: use the n-ary pattern and check query plans.

**RDF 1.2 (RDF-star):** use it when **provenance and confidence per fact** matter. Examples: reconciling the "as-designed" BIM against the "as-operated"
WinCC OA topology; recording who asserted each link and when; storing contradictory claims side by side. The cost is ecosystem maturity.
The W3C specs are still **Working Drafts** (Nov 2026), the 2021 RDF-star `<< >>` syntax now **changes meaning** (it becomes a reifier),
and parts of the stack don't parse it yet: rdflib → pyshacl, and **n10s 5.26 (rdf4j 4.3.12)**. Oxigraph does.

**LPG (Neo4j):** use it when the job is **operational questions on topology**: impact analysis ("what goes down if SWG-A trips"),
root cause, path and redundancy audits, graph algorithms (centrality of single points of failure, community detection over the utility network), and
apps or dashboards that devs and SCADA engineers build quickly in Cypher. The trade-off: there's no ontology, so classification lives in loader code, and there are no global IDs or provenance per edge.

**Neither:** don't use either one as a historian. 10k–100k tag changes/s belongs in WinCC OA archiving / a TSDB. The graph holds tag identity and
context, and the join happens by tag name.

## 4. How they work together (the reference pattern)
```
 BIM / CMMS / MES / WinCC OA config ──► RDF 1.2 "semantic layer"  (ontology, IRIs, SHACL gate, provenance per link)
                                              │  n10s import (or custom mapper like step5): one reifier per asserted
                                              ▼  edge → rel properties; lossless (2,457 → 2,457 triples in this lab)
                                     LPG "operational projection" (Neo4j): impact, paths, GDS, apps
                                              ▲
 WinCC OA live values ──► historian/TSDB ─────┘ joined by tag name at query time; only slow state (alarm active) in the graph
```
**Known loss at the boundary** (measured): unasserted claims and 2nd+ statements about the same edge don't survive RDF 1.2 → LPG.
Keep RDF as the system of record for provenance, and treat the LPG as a rebuildable projection.

**With n10s 5.26 specifically** (verified):
1. Serialise RDF 1.2 as **Turtle-star 2021**: `<< s p o >> :q v`, not `<<( )>>` or `~ {| |}`.
2. **Export only asserted triples and their annotations.** n10s creates an edge for every quoted triple, asserted or not.
3. Reifier IRIs are lost: store a stable `id` property if you need to round-trip.

Re-check when n10s moves to rdf4j 5.x.

## 5. Bottlenecks to remember (each one hit for real in this lab)
1. **Unbounded Cypher path matching on redundant (N+1/2N) topologies explodes exponentially.** 1M paths took 1.7 s, and each extra tier doubles it. Use DISTINCT reachability, `shortestPath`, depth bounds, or GDS.
2. **SPARQL cannot return paths**: you unroll depths or post-process in code.
3. **Optimizers pick bad join orders**: SPARQL Q1 took 187 ms instead of 2.7 ms because it started from every tool rather than the tripped switchgear. Check plans.
4. **Neo4j writes need batching and ready indexes**: per-transaction writes were 200× slower than batched ones. Batched writes before the index was online: 1.6k/s; after: 76k/s.
5. **RDF 1.2 tooling lag**: check every tool in your chain (parser, validator, store, serializer) before adopting it.
6. **LPG classification drift**: a label you forget to add is a silent wrong answer in impact analysis.
7. **n10s phantom edges**: an unasserted BIM claim imported via n10s became a real `feeds` edge and **hid one of 30 single points of failure**. The audit reported 29.
8. **SPARQL property paths can't filter on edge metadata** (RDF 1.1 *or* 1.2). Ignoring `medium` turned 30 SPOF tools into **0**. Put traversal-relevant edge attributes into the predicate (`fab:feedsPower rdfs:subPropertyOf fab:feeds`).
9. **Bolt result transfer** dominates Neo4j client time for wide results (Q3: 202 ms client vs 29 ms server). Aggregate server-side.

## 6. Status checks done for this lab (Nov 2026)
- RDF 1.2 Concepts is still a W3C **Working Draft**; RDF 1.1 is the current Recommendation. [W3C RDF 1.2 Concepts (WD 2026-03-28)](https://www.w3.org/TR/2026/WD-rdf12-concepts-20260328/)
- Neo4j 5.26 is the final 5.x LTS (support to June 2028); newer servers use calendar versions (2026.x). [Neo4j v5 LTS blog](https://neo4j.com/blog/developer/neo4j-v5-lts-evolution/), [supported versions](https://neo4j.com/developer/kb/neo4j-supported-versions/)
- n10s: releases are tracked per Neo4j 5.x minor version on [GitHub](https://www.github.com/neo4j-labs/neosemantics/releases); a `5.26.0` tag exists. The jar couldn't be downloaded or built here, so I verified its behaviour from source (`RDFToLPGStatementProcessor.java:406–449`) and by running its bundled parser version (rdf4j 4.3.12) in `n10s_parser_check/`. The main branch now targets Neo4j 2025.06.
- Oxigraph: RDF 1.2 / SPARQL 1.2 behind the `rdf-12` feature in the Rust crate ([docs.rs](https://docs.rs/crate/oxigraph/0.5.12)). **pyoxigraph 0.5.13 has it enabled, verified empirically in step 0.**
