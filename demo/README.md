# Fab Graph Workbench (working demo)

An interactive front end to the lab. The same fab utility network lives in three engines, and the same
six questions run side by side. Every answer is checked against an independent JavaScript reference
computed from the source data in your browser.

| | Live demo | Recorded edition |
|---|---|---|
| Engines | Oxigraph (RDF 1.1 + RDF 1.2) in-process, Neo4j 5.26 over Bolt | none: answers recorded from the live engines |
| Edit queries / console | ✓ any SPARQL or Cypher | presets and console examples only |
| Scale switch (1/10/50) | ✓ | scale 1 |
| Topology, scenarios, correctness checks | ✓ | ✓ (run in the browser) |
| Start | `python demo/server.py` → http://127.0.0.1:8765 | open `demo/dist/fab_graph_workbench.html` |

## What you can do
- **Trip an asset**: click switchgear, a UPS, PDU, chiller or PCW loop. Q1 runs on all three engines and the downstream impact lights up.
- **Click a tool**: Q4 returns the supply chain. Neo4j returns the path natively; SPARQL unrolls depths 1–5.
- **Q2/Q3**: change thresholds and source system. Flagged feeds are drawn in red.
- **Q6 single point of failure**: switch between *power only* and *ignore medium* to watch 30 SPOF tools become 0.
- **BIM claim scenario**: inject an unconfirmed BIM claim (PDU-B01-01 → T-B01-107):
  - *n10s 5.26 import*: Neo4j gets a real `FEEDS` edge. Its Q6 drops T-B01-107 and its Q1 from PDU-B01-01 gains a tool. Both are marked **differs**.
    RDF 1.1 (a `fab:Claim` node) and RDF 1.2 (an unasserted reifier) stay correct.
  - *Claim node*: the claim is kept off the traversal graph, and every engine agrees again.
- **Highlight from**: colour the diagram by Reference, RDF 1.1, RDF 1.2 or Neo4j results.
- **Console**: free SPARQL (prefixes added) or Cypher, with examples such as "claimed but not asserted".

## Files
- `queries.py`: the one query catalogue (templates for all engines, scenario updates, console examples)
- `server.py`: stdlib HTTP server and engine adapters (`/api/meta`, `/api/dataset`, `/api/query`, `/api/load`, `/api/claim`)
- `web/app.html`: the whole UI (vanilla JS); the same file powers both modes
- `build_published.py`: records every preset × parameter × claim state (8,088 runs, ~40 s) into one self-contained page.
  Recordings are keyed by a hash of the exact query text, so the published page can only show what each engine really returned.
- `tests/ui_smoke.js`: headless browser walk-through of the live demo (`node demo/tests/ui_smoke.js`)

The console runs whatever you type, so keep the server on localhost.
