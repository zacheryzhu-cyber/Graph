# UPW Graph Lab: the process-plant scenario

A small, hand-built slice of a fab's **ultrapure-water (UPW) plant and the cooling that serves it**, stored three ways:
- RDF 1.1;
- RDF 1.2;
- a Neo4j property graph.

You work through it as six everyday operator questions. No electrical switchgear: this scenario is about water and cooling.

## Start it
```bash
pip install -r requirements.txt        # once (Windows: py -m pip install -r requirements.txt)
python upw_demo/server.py              # Windows: py upw_demo\server.py
```
Open **http://127.0.0.1:8766**.

**Neo4j is optional.** Without it, the Neo4j column says "offline".
- To add it, start Neo4j with Docker, Neo4j Desktop or the lab launcher (see `SETUP.md`), then reload the page.
- For a Neo4j with a password, set `NEO4J_PASSWORD`, and `NEO4J_USER` if it isn't `neo4j`, before starting the server.
- The demo **wipes and reloads** the Neo4j database it connects to, so point it at a lab database.

**Published copy:** `upw_demo/dist/upw_graph_lab.html` (built by `python upw_demo/build_published.py`) holds every preset, recorded from the real engines. It needs no install, but its queries can't be edited.

## The plant
```
cooling   cooling towers ─condenser water─► chillers ─chilled water─► PCW heat exchanger ─► PCW loop ─► CMP / litho / etch
                                                    └──────────────► UPW trim cooler
UPW       city water → raw tank → multimedia filter → carbon filter → RO-1 / RO-2 → degasifier → mixed bed → UPW tank
          → trim cooler → 185 nm UV → polishing train A (MBP-A → UF-A → loop A) / train B (MBP-B → UF-B → loop B) → tools
reclaim   wet bench + CMP rinse water → reclaim tank → raw tank   (a recycle loop)
```
- **Tools:** 11 in total. They draw UPW from loop A, loop B, or both; etch tools use process cooling only.
- **SCADA:** 22 datapoints carry tag names and last values. 4 alarms are active, 2 cleared.
- **Pipe metadata:** each pipe has a medium, capacity and flow in m³/h, its install year, the system that documents it (DCS, P&ID or BIM) and a confidence.

## The six steps and what each one teaches
| # | Operator question | Result | Lesson |
|---|---|---|---|
| 1 | Polishing train B goes offline: what is downstream? | 8 units/tools, 6 tools | All engines fine. The reclaim loop means "downstream" must follow **supply pipes only**: Cypher filters inline, RDF needs a materialised `fab:supplies` predicate. |
| 2 | If I isolate a unit, which tools lose UPW completely? | MBP-B → 3 tools · RO-2 → none · UV-1 → all 9 | **Biggest difference.** "A path that avoids this unit" is one Cypher pattern; SPARQL can't express it. The RDF columns run the best single-query approximation, which is wrong for 6 units: the chillers, the cooling towers and the RO trains. UV-1 is a hidden single point of failure. |
| 3 | WET-03 reports bad water: which upstream units are alarming? | MBP-B, loop B, RO-2, CH-2 (WET-02 on loop A: only RO-2, CH-2) | Graph topology + SCADA alarms joined by tag; all models good. |
| 4 | Trace the water from the UPW tank to WET-03 | 6 pipes; from CITY 13 | Paths are native in Cypher; SPARQL spells out depths (6 here), so the 13-pipe route returns "no path". |
| 5 | Which tools hang on one polishing train? | 6 tools; "include reclaim pipes" → 0 (wrong) | Recycle loops make naive traversal wrong in **every** model. |
| 6 | BIM shows an unconfirmed pipe loop B → WET-02 | Neo4j via n10s: 5 (WET-02 hidden); RDF: 6 | RDF 1.2 holds a claim without asserting it; n10s 5.26 imports it as a real pipe. Keep claims as nodes. |

`python upw_demo/check.py` runs every preset on every engine against a plain-Python reference. It lists exactly the "differs" cases above, and nothing else.

## Files
| File | What |
|---|---|
| `scenario.py` | The plant data, RDF 1.1 / 1.2 builders, Neo4j loader, the six questions in SPARQL + Cypher, story text, Python reference |
| `server.py` | Local server (stdlib only), port 8766 |
| `web/app.html` | The UI (live and recorded modes) |
| `check.py` | Engine-vs-reference check over every parameter combination and claim state |
| `build_published.py` | Builds the recorded single-file edition |
| `tests/ui_smoke.js` | Playwright walkthrough of the story (`node upw_demo/tests/ui_smoke.js`) |
