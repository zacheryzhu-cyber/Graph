# DECISIONS.md — choices made autonomously during the lab

| # | Decision | Why |
|---|----------|-----|
| D1 | The prompt referenced "checkpoints below" / "Stages 1–6" but they were not included. I defined 7 stages (0 = env check, 1–6 = core lab, 7 = summary). | Keep moving; stage list in README.md. |
| D2 | **RDF + RDF 1.2 store: pyoxigraph 0.5.13** (embedded, pip). | Verified empirically in step0: parses RDF 1.2 triple terms `<<( )>>`, reifiers `~`, annotations `{| |}`, and SPARQL 1.2 `isTRIPLE()` / annotation patterns. Fastest pip-installable SPARQL engine. |
| D3 | **rdflib + pyshacl** for SHACL validation only. | pyshacl is the standard free validator; oxigraph has no SHACL. |
| D4 | **Neo4j 5.26.33 Community run *embedded* in a tiny Java launcher with a Bolt connector** (`neo4j_embedded/`), instead of Docker or the tarball. | Docker CLI is present but no daemon; `dist.neo4j.org` is blocked by the network proxy (403). Maven Central is reachable and Java 21 is installed. The Python `neo4j` driver connects over Bolt exactly as to a server, so the Cypher experience is identical. 5.26 is the final 5.x LTS (supported to June 2028). |
| D5 | **neosemantics (n10s) not installed** — implemented the n10s mapping conventions (`uri` property, `Resource` label, shortened prefixes, `n10s`-style "rels for object props, node props for literals") in Python (`step5_interop.py`). | n10s jar is distributed via GitHub releases (blocked: 403) and is not on Maven Central. Also, registering plugins in embedded mode is non-standard. The point of the stage — what survives RDF→LPG→RDF — is still demonstrated. In a real fab deployment: Neo4j 5.26 LTS + n10s 5.26.x jar in `plugins/`. |
| D6 | Synthetic data, deterministic (seeded), one canonical `data/facility.json` that all three models are generated from. | Fair comparison: same entities, same edges, same edge metadata. |
| D7 | Scale factor via `SCALE` env var (default 1 ≈ 1 fab). Benchmarks use 1, 10, 50. | Time-box: keeps the default run in seconds. |
| D8 | Plain-RDF edge metadata uses **n-ary relation pattern** (an intermediate `:Feed` node), not classic `rdf:Statement` reification. | That's what practitioners actually do in RDF 1.1; classic reification is worse (4 extra triples, no query support). |
