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
