# SETUP — step by step: the three use cases, and getting values out of SCADA

This guide gets you from an empty machine to each of the three set-ups this lab compares, then connects live SCADA values.
Every command marked **✓ tested** was run for this guide (Linux, Python 3.13, Java 21, Nov 2026).
Commands marked **⚠ not run here** are documented vendor paths that this sandbox could not reach (no Docker daemon; GitHub releases blocked).

| Use case | Model | What it's for in a fab / data centre | Lab scripts |
|---|---|---|---|
| **A. Asset information model** | RDF 1.1 + SHACL | One governed model of assets shared by BIM, CMMS, MES and SCADA; validation gate | `step2`, `step5`, `export_rdf.py` |
| **B. Provenance and conflicting sources** | RDF 1.2 (triple terms, reifiers) | Who asserted each link, with what confidence; as-designed vs as-operated | `step3`, `step5b` |
| **C. Operational topology** | LPG (Neo4j 5.26) | Impact analysis, single points of failure, paths, dashboards | `step4`, `step6` |
| **D. Live SCADA values** | Historian + graph context | Alarm → affected tools → live power draw | `step7_scada_bridge.py` |

Why these roles, with the measured numbers behind them: `SUMMARY.md`.

---

## 0. Prerequisites (once)

| You need | For | Check |
|---|---|---|
| Python 3.11+ | everything | `python --version` |
| Java 17 or 21 + Maven | only the embedded Neo4j launcher and the n10s parser check | `java -version`, `mvn -v` |
| *or* Docker | Neo4j / Oxigraph as containers instead | `docker info` |
| Node.js + Playwright | only `make demo-test` | — |

```bash
git clone <this repo> && cd Graph
python -m venv .venv && source .venv/bin/activate      # optional but recommended
pip install -r requirements.txt                         # ✓ tested (pyoxigraph, rdflib, pyshacl, neo4j, asyncua)
python step0_env_check.py                               # ✓ prints versions, and proves RDF 1.2 parsing works
python step1_generate_data.py                           # ✓ data/facility_s1.json (SCALE=10 for 10 buildings)
```

The dataset is one fab building:
- switchgear → UPS → PDU → tools, and chillers → cooling loops → tools;
- every `feeds` link carries medium, capacity, load, source system and confidence;
- WinCC OA-style datapoints (`System1:CH_B01_01.SupplyTemp`) and alarms.

---

## A. RDF 1.1: the asset information model

**Goal:** one model with global IDs that every system can read, with a validation gate in front of it.

### A1. Run it embedded (no server): ✓ tested
```bash
python step2_rdf_plain.py          # loads into in-memory Oxigraph, runs Q1–Q6, checks answers
python step5_interop.py            # includes the SHACL gate: 2 injected defects → 2 violations
```

### A2. Run it as a real SPARQL server: ✓ tested
```bash
python export_rdf.py               # writes out/fab_rdf11.ttl, out/fab_rdf12.ttl, out/fab_shapes.ttl
pip install oxigraph               # the Oxigraph CLI/server (same engine as pyoxigraph)
oxigraph serve --location ./oxi_db --bind 127.0.0.1:7878 &
# load into the DEFAULT graph: plain POST /store would create a new named graph instead
curl -X POST -H 'Content-Type: text/turtle' --data-binary @out/fab_rdf11.ttl 'http://127.0.0.1:7878/store?default'
# query (SPARQL 1.1 protocol)
curl -X POST -H 'Content-Type: application/sparql-query' -H 'Accept: text/csv' \
  --data-binary 'PREFIX fab: <http://example.org/fab#>
                 SELECT ?tool WHERE { ?f fab:feedFrom fab:PDU-B01-01 ; fab:feedTo ?tool }' \
  http://127.0.0.1:7878/query
```
Open http://127.0.0.1:7878 for the built-in query UI. Updates go to `/update` (Content-Type `application/sparql-update`).
⚠ not run here, Docker variant from the Oxigraph docs:
`docker run --rm -v $PWD/oxi_db:/data -p 7878:7878 ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878`.
If the endpoint is reachable by others, put a reverse proxy with authentication in front of `/update` and `/store`.

### A3. Validate before loading (the gate): ✓ tested
```bash
pyshacl -s out/fab_shapes.ttl -i rdfs out/fab_rdf11.ttl     # → Conforms: True
```
Put this in the pipeline that ingests BIM / CMMS exports. Reject or quarantine anything that doesn't conform.

### A4. Make it real
1. **Replace `fab:` with a shared vocabulary.** Brick or RealEstateCore for building/utility equipment; ISA-95 for the production hierarchy.
   Keep `fab:` only for site-specific terms. Lab classes map roughly as Chiller→`brick:Chiller` and PDU→`brick:PDU`.
2. **Mint stable IRIs from the system of record** (e.g. the CMMS asset number), never from display names.
3. **Write mappers per source.** BIM (IFC) → RDF, CMMS → RDF, WinCC OA datapoint list → RDF.
   Each mapper is a script like `rdf_common.build()`, emitting Turtle that passes A3.
4. **Edge attributes in RDF 1.1:** use the n-ary pattern (`fab:Feed` node). Check query plans: Q1 went from 169 ms to 2.7 ms after a rewrite (SUMMARY §5.3).
5. **Put attributes that steer traversal into the predicate** (`fab:feedsPower rdfs:subPropertyOf fab:feeds`). SPARQL property paths cannot filter on edge metadata (Q6, SUMMARY §5.8).

---

## B. RDF 1.2: provenance and conflicting claims

**Goal:** keep a direct `s fab:feeds o` edge, and attach who said so, when, and how sure they were. Several sources can do that independently, and a claim can be recorded without being asserted.

### B1. Run it: ✓ tested
```bash
python step3_rdf_star.py           # RDF 1.2 triple terms + reifiers, SPARQL 1.2, provenance demo
```

### B2. The data shape (Turtle 1.2)
```turtle
fab:PDU-B01-01 fab:feeds fab:T-B01-105 ~ fab:feed-e17 {| fab:sourceSystem "WinCCOA" ; fab:confidence 0.93 |} .
fab:feed-e18 rdf:reifies <<( fab:PDU-B01-01 fab:feeds fab:T-B01-105 )>> ; fab:sourceSystem "BIM" ; fab:confidence 0.70 .
# a claim that is NOT asserted: no plain triple, only a reifier
fab:claim-1 rdf:reifies <<( fab:PDU-B01-01 fab:feeds fab:T-B01-107 )>> ; fab:sourceSystem "BIM" .
```
Query with SPARQL 1.2 annotation syntax: ✓ tested on the Oxigraph server from A2, after loading `out/fab_rdf12.ttl`.
```sparql
SELECT ?s ?d ?src ?conf WHERE { ?s fab:feeds ?d {| fab:sourceSystem ?src ; fab:confidence ?conf |} FILTER(?conf < 0.6) }
```

### B3. Before you adopt it, check every tool in the chain
| Tool | RDF 1.2 status (checked in this lab, Nov 2026) |
|---|---|
| W3C RDF 1.2 specs | **Working Draft**, not yet a Recommendation |
| Oxigraph / pyoxigraph 0.5.13 | ✓ parses and queries RDF 1.2 and SPARQL 1.2 |
| rdflib 7.6 → pyshacl | ✗ cannot parse `<<( )>>`, so you can't SHACL-validate RDF 1.2 files directly. Validate an RDF 1.1 projection (A3). |
| n10s 5.26 (rdf4j 4.3.12) | ✗ parse error on RDF 1.2. Accepts only 2021 Turtle-star `<< s p o >>` (see C4). |
| Jena, GraphDB, Stardog, … | not tested here: check their current release notes |

Legacy RDF-star `<< s p o >>` changes meaning in RDF 1.2 (it becomes a reifier). Don't mix the two syntaxes in one pipeline.

---

## C. LPG: Neo4j for operations

**Goal:** fast traversals and paths for impact analysis, single-point-of-failure audits, and apps.

### C1. Start Neo4j 5.26: pick one
| Option | Command | Status |
|---|---|---|
| Embedded launcher (no Docker) | `./neo4j_embedded/run.sh` (or `make neo4j`). First run downloads jars from Maven Central. Bolt on 127.0.0.1:7687, no auth, data in `neo4j_data/`. | ✓ tested |
| Docker | `docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=none neo4j:5.26-community` | ⚠ not run here (no Docker daemon) |
| Neo4j Desktop / server tarball | install 5.26 LTS, then `export NEO4J_URI=bolt://host:7687` | ⚠ not run here |

The lab code connects without auth. For a server with a password, change `auth=None` in `neo_common.py:driver()`.

### C2. Load and query: ✓ tested
```bash
python step4_lpg_neo4j.py          # wipes, loads 261 nodes / 398 rels, runs Q1–Q6
```
The loader (`neo_common.load_lpg`) shows the patterns that matter:
- unique constraint on `id`;
- `UNWIND` batches of 5,000;
- `CALL db.awaitIndexes()` before bulk writes. Writes ran at 1.6k/s before the index was online and 76k/s after.
- extra labels (`:ProductionTool`, `:ElectricalAsset`) set at load time, because Neo4j has no subclass reasoning.

Typical questions in Cypher:
```cypher
// impact: what goes down if SWG-B01-A trips
MATCH (:Entity {id:'SWG-B01-A'})-[:FEEDS*]->(x:ProductionTool) RETURN DISTINCT x.id;
// single point of failure: tools whose power comes from exactly one switchgear (power edges only)
MATCH (t:ProductionTool)
MATCH (s:Switchgear)(()-[f:FEEDS WHERE f.medium='power']->())+(t)
WITH t, count(DISTINCT s) AS n WHERE n = 1 RETURN t.id;
```

### C3. Avoid the measured traps
- Never enumerate all paths on N+1/2N topologies: 1M paths took 1.7 s, doubling per tier. Use `DISTINCT` reachability, `shortestPath`, or depth bounds.
- Aggregate on the server: Bolt transfer dominated wide results (202 ms client vs 29 ms server).
- Batch writes: per-transaction writes managed only 230–360/s.

### C4. Feeding Neo4j from the RDF model with n10s: ⚠ not run here
n10s could not be installed in this sandbox. These are the documented steps; the import rules come from what the lab verified in the n10s source.
```bash
docker run -p7474:7474 -p7687:7687 -e NEO4J_AUTH=none \
  -e NEO4J_PLUGINS='["n10s"]' \
  -e NEO4J_dbms_security_procedures_unrestricted='n10s.*' \
  neo4j:5.26-community
```
```cypher
CREATE CONSTRAINT n10s_unique_uri FOR (r:Resource) REQUIRE r.uri IS UNIQUE;
CALL n10s.graphconfig.init();
CALL n10s.rdf.import.fetch('file:///import/fab_rdf11.ttl', 'Turtle');
```
Rules (verified, see `step5b_n10s_compat.py` and LEARNING_NOTES R1):
1. n10s 5.26 **cannot parse RDF 1.2**. Export RDF 1.2 as **2021 Turtle-star** (`<< s p o >> :q v`).
2. **Export only asserted triples.** n10s turns every quoted triple into a real edge. An unasserted BIM claim became a phantom `feeds` edge and hid a single point of failure (30 → 29).
3. Reifier IRIs are lost: carry a stable `id` property if you need to round-trip.
4. Treat Neo4j as a **rebuildable projection**: RDF stays the system of record.

If you'd rather not depend on n10s, `step5_interop.py` shows a ~40-line custom mapper that does the same lossless (asserted-only) import.

---

## D. Getting values out of SCADA

### D0. The rule: values don't go into the graph
| Data | Rate | Where it lives |
|---|---|---|
| Samples (temps, kW, vacuum, states) | 1k–100k values/s | **historian / time-series DB** (WinCC OA archive, TimescaleDB, InfluxDB, …) |
| Tag identity: which datapoint belongs to which asset, unit | changes with engineering | **graph** (`fab:winccTag`, `(:Asset)-[:HAS_DATAPOINT]->(:Datapoint {tag})`) |
| Slow state: alarm active/cleared, mode, maintenance | a few per minute | **graph** (written by rules) |

**The join key is the tag name.** Measured in step 7: 8,649 samples went to the historian and the graph received **one** write (the alarm).

### D1. Run the bridge against the built-in simulator: ✓ tested
```bash
./neo4j_embedded/run.sh &          # optional: without Neo4j it runs RDF-only
python step7_scada_bridge.py       # ~8 s; DURATION=20 for longer
```
What happens:
1. An **OPC UA server** starts on `opc.tcp://127.0.0.1:4841/fab/` with 169 tags named like the graph's datapoints. It stands in for WinCC OA.
2. The bridge **subscribes** to all tags (100 ms publishing interval) and **batch-inserts** samples into `out/historian.sqlite`.
3. Midway, chiller `CH-B01-01` supply water rises past 10 °C. The rule fires and then:
   - looks up **tag → datapoint → asset → every tool downstream**, in SPARQL (RDF 1.2) and Cypher (Neo4j). Both are checked against ground truth: 25 tools.
   - writes the **alarm** into both graphs as slow state;
   - **joins back to the historian by tag name** to show each affected tool's latest PowerDraw.

Measured: about 1,080 samples/s; source→historian latency p50 50 ms, p95 100 ms (bounded by the 100 ms publishing interval); 1 graph write.
The context lookup plus alarm write took ~0.6 s right after Neo4j started (first query plans) and 16 ms on the next run. Precompute asset→downstream sets for production.

### D2. Point it at your real SCADA (OPC UA)
WinCC OA ships an **OPC UA server** (default TCP port 4840) and an **MQTT driver**. Most other SCADA/PLC platforms offer OPC UA as well.
1. **Enable the OPC UA server** in WinCC OA and choose which datapoints it publishes. See the WinCC OA *OPC UA Server* docs for your version (3.18–3.20 differ).
2. **Create a read-only user and use security**: `Basic256Sha256` + certificates. The lab simulator uses `NoSecurity`, which is acceptable only on a lab laptop.
3. **Find the node-id pattern once.** Browse the server with a generic client (e.g. UaExpert) and note the namespace URI and how a datapoint element appears as a node id.
4. **Run the bridge with that mapping**:
   ```bash
   OPCUA_URL=opc.tcp://scada-host:4840 \
   OPCUA_NS='urn:<your server namespace uri>' \
   OPCUA_ID_FMT='{tag}' \
   python step7_scada_bridge.py
   ```
   Each graph tag `fab:winccTag` becomes node id `OPCUA_ID_FMT.format(tag=...)` in that namespace. Adjust the format until the ids match what you browsed. The lab can't verify WinCC OA's exact node-id scheme, so take it from the server.
   For security modes, add `await cl.set_security_string("Basic256Sha256,SignAndEncrypt,cert.der,key.pem")` and `cl.set_user(...)` in `main()` (asyncua client API).
5. **Reconcile tags both ways** before trusting impact answers. A SCADA tag with no datapoint in the graph is invisible to impact analysis; a graph datapoint with no SCADA tag is stale. Run that diff as part of the SHACL gate (A3).

### D3. Alternative: MQTT
If your SCADA publishes to a broker (WinCC OA MQTT driver, Sparkplug B edge nodes, …):
- Subscribe to the topics.
- Map topic or JSON path → tag name.
- From there, follow the same path as D1: batch into the historian, and run rules → graph context → slow-state write.

The WinCC OA MQTT driver maps JSON paths to datapoint attributes. Per its docs, it **does not buffer**, so a broker outage loses values unless your historian is fed another way. Not run in this lab.

### D4. Production checklist
- **Historian:** replace SQLite with your TSDB, or read the WinCC OA archive directly. Keep `(tag, ts)` indexed. Insert in batches.
- **Rules:** start with thresholds as in step 7. Later read alarm states from SCADA rather than recomputing them.
- **Graph writes:** only state changes (raise/clear), debounced. Neo4j per-transaction writes are slow (SUMMARY §5.4).
- **Context queries:** precompute "asset → downstream tools" per asset when topology changes, so alarm-time lookups are a key read.
- **Dashboards:** the graph answers *what is affected*; the historian answers *how it is behaving*. Join them in the app by tag.

---

## E. All together (reference pipeline)
```
BIM / CMMS / MES / WinCC OA datapoint list
        │  mappers → Turtle (A4)  →  SHACL gate (A3)
        ▼
RDF 1.2 store (Oxigraph server)    ← system of record: IRIs, ontology, provenance per link (B)
        │  asserted-only export → n10s import or custom mapper (C4)
        ▼
Neo4j 5.26 (projection)            ← impact, SPOF, paths, apps (C)
        ▲
WinCC OA ──OPC UA/MQTT──► bridge ──► historian (D)
                             └── alarm state + context lookup by tag name
```
Try all of it interactively with the workbench: `make demo` → http://127.0.0.1:8765 (`demo/README.md`).

## F. Troubleshooting
| Symptom | Fix |
|---|---|
| `Neo4j not reachable at bolt://127.0.0.1:7687` | Start `./neo4j_embedded/run.sh`; wait for `NEO4J_READY` in its output; or set `NEO4J_URI` |
| `run.sh` fails downloading | Needs Maven Central access; or use Docker / Desktop (C1) |
| Oxigraph server returns 0 rows after loading | You POSTed to `/store` without `?default`, so the data went into a new named graph |
| pyshacl / rdflib parse error on `<<(` | Expected: rdflib can't read RDF 1.2. Validate `fab_rdf11.ttl` |
| n10s `RDFParseException` on `<<(` | Expected for n10s 5.26: down-convert to 2021 Turtle-star (C4) |
| Cypher returns 0 rows | `step5_interop.py` / `step5b` reload Neo4j in n10s style; rerun `python step4_lpg_neo4j.py` |
| `step7` says "rule never fired" | Run longer: `DURATION=20` |
| OPC UA `BadNodeIdUnknown` | Node-id pattern wrong: browse the server and fix `OPCUA_NS` / `OPCUA_ID_FMT` |
| Port 4841 or 7878 in use | Another simulator or Oxigraph is running. Stop it, or change the port in the command / `URL` |
