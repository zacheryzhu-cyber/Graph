# Chiller Plant Graph Lab

A fab's chilled-water plant, from cooling towers to the tools and cleanroom air. It is stored three ways:
- RDF 1.1;
- RDF 1.2;
- a Neo4j property graph.

It is compared on six everyday operator questions. Valve positions come from SCADA and can be changed live.

## Start it
```bash
pip install -r requirements.txt          # once (Windows: py -m pip install -r requirements.txt)
python chiller_demo/server.py            # Windows: py chiller_demo\server.py
```
Open **http://127.0.0.1:8766**.

**Neo4j is optional.** Without it, the Neo4j column says "offline".
- Start Neo4j (Docker, Neo4j Desktop or the lab launcher, see `SETUP.md`), then reload the page.
- For a Neo4j with a password, set `NEO4J_PASSWORD`, and `NEO4J_USER` if it isn't `neo4j`.
- The demo **wipes and reloads** the database it connects to, so point it at a lab database.

**Published copy:** `python chiller_demo/build_published.py` writes `chiller_demo/dist/chiller_plant_graph_lab.html`. It contains every preset in every valve and claim state, recorded from the real engines.

## The plant
```
CT-1..3 ─condenser water─► CH-1, CH-2 (1,800 kW, running), CH-3 (1,400 kW, standby) ─chilled water─► CHW header
CHW header ─► V-HX1 ─► HX-1 ─► P-A1 / P-A2 (spare) ─► PCW loop A ─┐
CHW header ─► V-HX2 ─► HX-2 ─► P-B1 (only pump)    ─► PCW loop B ─┼─► 8 tools on loop A, loop B or both
                             V-TIE cross-tie, normally closed ────┘
CHW header ─► V-MAU1/2 ─► make-up air units MAU-1/2 ─supply air─► cleanroom bays BAY-1/2
```
- **Design load:** 3,300 kW.
- **SCADA:** 25 datapoints, including the 5 valve positions. 4 alarms are active, 2 cleared.
- **Pipe metadata:** each pipe has a medium, an install year, its documenting system (DCS, P&ID or BIM) and a confidence.
- **One relationship type:** "cooling flows from A to B".

## Rules of the comparison
1. **Same data, same question.** One plant is loaded into all three engines.
2. **Best exact method per engine.** No approximations or strawmen. Where SPARQL can't express something in one query, the RDF column runs the exact multi-step method an RDF developer would use.
3. **Checked answers.** Every answer is compared with an independent reference: JavaScript in the page, Python in `check.py`.
4. **Effort is counted.** The scorecard shows the method each engine needed, extra steps, and upkeep when SCADA changes a valve.

## The six steps
| # | Operator question | Result | What it shows |
|---|---|---|---|
| 1 | P-B1 (loop B's only pump) trips: what depends on it? | loop B + 5 tools | All correct in one query. RDF needs a precomputed "open pipes" predicate (SPARQL paths can't skip closed valves); Neo4j checks valves inline. |
| 2 | Who actually loses cooling? | P-B1 → 3 tools · CHW header → all 10 · CH-1 → none | All correct. **Effort differs most here:** Neo4j needs 1 query; RDF needs a 3-step script (copy the network without the unit, query, drop the copy), because SPARQL can't exclude a unit from a path. |
| 3 | Can we take a chiller out (N+1)? | CH-3 out: 300 kW margin · CH-1 out: 100 kW short | A plain sum. All three are equally good, and the database choice doesn't matter. |
| 4 | SCADA: the cross-tie valve opens. Which tools hang on one heat exchanger? | normal 6 · tie open 0 · HX-2 isolated 8 | The real-time case. Neo4j: one SET on the valve. RDF: update the position, then recompute the predicate. Both are under 10 ms on this plant; the upkeep grows with plant size and valve-change rate. |
| 5 | CVD-02 runs hot: which upstream units are alarming? | loop B, P-B1, HX-2, CH-2 (ETCH-01 on loop A: CH-2 only) | Topology + SCADA alarms joined by tag. All three good. |
| 6 | BIM shows an unconfirmed pipe PCW-B → ETCH-01 | n10s import: Neo4j says 5 (ETCH-01 hidden); RDF says 6 | RDF 1.2 holds a claim without asserting it; n10s 5.26 imports it as a real pipe. That's an integration pitfall, not a Neo4j limit: imported as a claim node, Neo4j is right too. |

**Summary of what this demo measures:**
- **Correctness:** all three engines answer every question correctly when each uses its best method.
- **Effort:** they differ in what it takes. RDF needs precomputed predicates, multi-step what-ifs, and upkeep on every valve move. Neo4j does these in single queries.
- **Provenance:** RDF 1.2 is the only one that can hold an unconfirmed claim natively.
- **RDF 1.1 vs 1.2:** for these operational questions they behave the same. They differ in how pipe metadata is written and in claims.

`python chiller_demo/check.py` checks 1,836 answers across all three engines, 3 valve states and 3 claim states. The only differences are Neo4j while the claim is imported the n10s way.

## Files
| File | What |
|---|---|
| `scenario.py` | Plant data, RDF 1.1 / 1.2 builders, Neo4j loader, questions with each engine's method, valve presets, story text, Python reference |
| `server.py` | Local server (stdlib only), port 8766; runs multi-step SPARQL scripts and valve changes |
| `web/app.html` | The UI (live and recorded modes) |
| `check.py` | Engine-vs-reference check over every parameter, valve state and claim state |
| `build_published.py` | Builds the recorded single-file edition |
| `tests/ui_smoke.js` | Playwright walkthrough (`node chiller_demo/tests/ui_smoke.js`) |
