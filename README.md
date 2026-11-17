# RDF vs RDF 1.2 (RDF-star) vs LPG — hands-on lab, fab facility use case

One dataset (fab utility chain → production tools → WinCC OA-style datapoints → alarms), modelled three ways,
asked the same five questions, with every answer checked against a Python ground truth.

| Stage | Script | What it shows |
|---|---|---|
| 0 | `step0_env_check.py` | Verifies tool versions and RDF 1.2 parsing instead of trusting memory |
| 1 | `step1_generate_data.py` | Canonical model-neutral dataset (`SCALE=n`) |
| 2 | `step2_rdf_plain.py` | RDF 1.1 + n-ary relations in Oxigraph, SPARQL 1.1 |
| 3 | `step3_rdf_star.py` | RDF 1.2 triple terms + reifiers, SPARQL 1.2 annotation syntax, provenance |
| 4 | `step4_lpg_neo4j.py` | Neo4j 5.26 LPG, Cypher |
| 5 | `step5_interop.py` | RDF 1.2 → LPG → RDF 1.2 round trip (n10s conventions), SHACL |
| 6 | `step6_bottlenecks.py` | Path explosion, SCADA write rate, optimizer pitfalls, scale table |

**Read:** `SUMMARY.md` (decision guide) → `LEARNING_NOTES.md` (why + measured results per stage) → `DECISIONS.md`.

## Run
```bash
pip install pyoxigraph rdflib pyshacl neo4j
./neo4j_embedded/run.sh &        # Neo4j 5.26 embedded, Bolt :7687, needs Java 17/21 + Maven (or use any Neo4j 5 server: NEO4J_URI=...)
./run_all.sh                     # or: make all / python stepN_*.py individually (SCALE=10 python step3_rdf_star.py)
```
With Docker available, `docker run -p7687:7687 -e NEO4J_AUTH=none neo4j:5.26-community` works too.
