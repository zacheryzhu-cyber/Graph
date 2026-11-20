# RDF vs RDF 1.2 (RDF-star) vs LPG — hands-on lab, fab facility use case

One dataset (fab utility chain → production tools → WinCC OA-style datapoints → alarms), modelled three ways,
asked the same six questions (Q6 = single-point-of-failure audit), with every answer checked against a Python ground truth.

**Start here if you're new: the Chiller Plant Graph Lab** (a fab's chilled-water plant, guided story, fair three-engine scorecard): `python chiller_demo/server.py` → http://127.0.0.1:8766 (see [`chiller_demo/README.md`](chiller_demo/README.md)).

| Stage | Script | What it shows |
|---|---|---|
| 0 | `step0_env_check.py` | Verifies tool versions and RDF 1.2 parsing instead of trusting memory |
| 1 | `step1_generate_data.py` | Canonical model-neutral dataset (`SCALE=n`) |
| 2 | `step2_rdf_plain.py` | RDF 1.1 + n-ary relations in Oxigraph, SPARQL 1.1 |
| 3 | `step3_rdf_star.py` | RDF 1.2 triple terms + reifiers, SPARQL 1.2 annotation syntax, provenance |
| 4 | `step4_lpg_neo4j.py` | Neo4j 5.26 LPG, Cypher |
| 5 | `step5_interop.py` | RDF 1.2 → LPG → RDF 1.2 round trip (n10s conventions), SHACL |
| 5b | `step5b_n10s_compat.py` + `n10s_parser_check/` | What **real** n10s 5.26 does with RDF 1.2 (parser + source verified) and the phantom-edge risk |
| 6 | `step6_bottlenecks.py` | Path explosion, SCADA write rate, optimizer pitfalls, scale table |
| 7 | `step7_scada_bridge.py` | Live SCADA values: OPC UA subscribe → historian; alarm → graph context by tag name |
| — | `export_rdf.py` | Writes Turtle (RDF 1.1, RDF 1.2) + SHACL shapes for loading into any RDF store |

**Set it up for real, step by step (all three models + SCADA): [`SETUP.md`](SETUP.md).**

**Original workbench (electrical + cooling, the lab's dataset):** `python demo/server.py` → http://127.0.0.1:8765 (see `demo/README.md`). **Visual summary:** `lab_summary.html`. **Read:** `SUMMARY.md` (decision guide) → `LEARNING_NOTES.md` (why + measured results per stage) → `DECISIONS.md`.

## Run
```bash
pip install -r requirements.txt
./neo4j_embedded/run.sh &        # Neo4j 5.26 embedded, Bolt :7687, needs Java 17/21 + Maven (or use any Neo4j 5 server: NEO4J_URI=...)
./run_all.sh                     # or: make all / python stepN_*.py individually (SCALE=10 python step3_rdf_star.py)
```
With Docker available, `docker run -p7687:7687 -e NEO4J_AUTH=none neo4j:5.26-community` works too.
