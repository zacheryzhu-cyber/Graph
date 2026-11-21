# Hands-on: feel the difference between RDF and LPG yourself

There are two parts:
- **Part A: build it by hand** (about 30 minutes). No scripts. You type a 4-item plant **yourself**, as an RDF file and as Neo4j commands. You load it, look at it, ask it questions and change it. This is where you learn what RDF actually *is*.
- **Part B: the full plant** (about 45 minutes). A script loads the 60-item chiller plant, because typing 532 facts by hand teaches nothing new. Then 10 exercises show the differences on something realistic.

Everything below was run and checked before this sheet was written.

---

## Set up the tools (once)

You need:
- Python;
- Oxigraph;
- Neo4j **with its browser page**, meaning Docker or Neo4j Desktop.

```powershell
cd D:\work\RDF\Graph
git pull
py -m pip install -r requirements.txt
py -m pip install oxigraph
```

**Neo4j:** start it with Docker in its own window, and leave that window open:
```powershell
docker run --name neo4j-lab -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=none neo4j:5.26-community
```
If you created this container before, run `docker start -a neo4j-lab` instead. Then open **http://localhost:7474**, choose **No authentication** and connect. You type commands in the box at the top and run them with Ctrl+Enter.

**Oxigraph:** pip puts it in a folder that isn't on your PATH. Save its location in a variable. You need this line again in every new PowerShell window:
```powershell
$ox = "$env:LOCALAPPDATA\Programs\Python\Python314\Scripts\oxigraph.exe"
```

---

# Part A: build a tiny plant by hand

The plant: **chiller CH-1 → valve V-1 → pump P-1 → etch tool ETCH-1.** That's 4 items and 3 pipes.

## A1. Write it as RDF: a text file
RDF data is just text. In this format, Turtle, every statement is **subject, predicate, object** followed by a full stop, like a short sentence.

Open Notepad, paste the following, and save it as **`D:\work\RDF\Graph\mini.ttl`**. Use "All files" and UTF-8, so Notepad doesn't add `.txt`.
```turtle
@prefix fab:  <http://example.org/fab#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

# 1. The vocabulary: what kinds of things exist, and how they relate
fab:Chiller   rdfs:subClassOf fab:Equipment .
fab:Valve     rdfs:subClassOf fab:Equipment .
fab:Pump      rdfs:subClassOf fab:Equipment .
fab:EtchTool  rdfs:subClassOf fab:Consumer .

# 2. The things in the plant
fab:CH-1    a fab:Chiller ;   rdfs:label "Chiller 1" ;  fab:capacityKW 1800 .
fab:V-1     a fab:Valve ;     rdfs:label "Valve 1" ;    fab:position "open" .
fab:P-1     a fab:Pump ;      rdfs:label "Pump 1" .
fab:ETCH-1  a fab:EtchTool ;  rdfs:label "Etch 1" .

# 3. How the cooling flows
fab:CH-1  fab:flowsTo  fab:V-1 .
fab:V-1   fab:flowsTo  fab:P-1 .
fab:P-1   fab:flowsTo  fab:ETCH-1 .
```
**How to read it:**
- **`fab:CH-1`** is a short form of the full, worldwide-unique name `<http://example.org/fab#CH-1>`. The `@prefix` line defines the short form. **Global names** are why RDF from different systems can be merged: the same name always means the same thing.
- **`a`** means "is of type". So `fab:CH-1 a fab:Chiller` reads "CH-1 is a chiller".
- **`;`** means "same subject, next fact". The CH-1 line is 3 facts: its type, its label and its capacity.
- **`rdfs:subClassOf`** builds the vocabulary: "an etch tool is a kind of consumer". **That meaning is data**, stored just like the plant itself.
- **`"Chiller 1"`** and **`1800`** are plain values ("literals"). Everything else is a name.

If you get stuck, compare with `hands_on\mini_plant.ttl`; it's the same file.

## A2. Load it and look at it (RDF)
```powershell
& $ox load --location mini_db --file mini.ttl
& $ox serve --location mini_db --bind 127.0.0.1:7878
```
Leave that window open and go to **http://127.0.0.1:7878**. Check the endpoint box ends in **`/sparql`**. Paste and run:
```sparql
SELECT ?subject ?predicate ?object WHERE { ?subject ?predicate ?object }
```
→ **17 rows.** These are exactly the 17 facts you wrote, each as one row. **That's all an RDF database is: a big set of these 3-part facts.** There are no tables and no boxes, only facts linking names to names or to values.

## A3. Ask it questions (RDF)
**What gets cooling from CH-1?** `+` means "follow flowsTo one or more times":
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?x WHERE { fab:CH-1 fab:flowsTo+ ?x }
```
→ V-1, P-1, ETCH-1.

**Which consumers are there?** Try it two ways:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?c WHERE { ?c a fab:Consumer }
```
→ **nothing.** You never wrote "ETCH-1 is a consumer".
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?c WHERE { ?c a/rdfs:subClassOf* fab:Consumer }
```
→ **ETCH-1.** The query followed your vocabulary: ETCH-1 is an etch tool, and an etch tool is a kind of consumer. **This is the main thing RDF gives you: meaning you can query.**

## A4. Add details to a pipe (RDF 1.2)
The pipe P-1 → ETCH-1 is documented in the DCS with confidence 0.98. Add that fact *about the pipe*:
```sparql
PREFIX fab: <http://example.org/fab#>
INSERT DATA { fab:P-1 fab:flowsTo fab:ETCH-1 {| fab:sourceSystem "DCS" ; fab:confidence 0.98 |} . }
```
Now see what RDF really stored:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?subject ?predicate ?object WHERE {
  ?subject ?predicate ?object FILTER(isTRIPLE(?object) || ?predicate IN (fab:sourceSystem, fab:confidence)) }
```
→ 3 new facts about an **unnamed note** (shown as `_:…`):
- the note **reifies**, meaning "is about", the statement `P-1 flowsTo ETCH-1`;
- the note has **sourceSystem** DCS;
- the note has **confidence** 0.98.

So RDF 1.2 doesn't put properties "on the arrow". It creates **a note that points at the arrow**, and that is what lets several sources each keep their own note (Part B, exercise 8). Read the details back the short way:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?source ?confidence WHERE { fab:P-1 fab:flowsTo fab:ETCH-1 {| fab:sourceSystem ?source ; fab:confidence ?confidence |} }
```

## A5. Close the valve (RDF)
```sparql
PREFIX fab: <http://example.org/fab#>
DELETE { fab:V-1 fab:position ?p } INSERT { fab:V-1 fab:position "closed" } WHERE { fab:V-1 fab:position ?p }
```
Ask A3's first question again: **V-1, P-1 and ETCH-1 are still listed.** `flowsTo+` doesn't know what a valve is. Now try filtering:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?x WHERE { fab:CH-1 fab:flowsTo+ ?x FILTER NOT EXISTS { ?x fab:position "closed" } }
```
→ the valve disappears, but **P-1 and ETCH-1 are still there.** The filter runs *after* the walk, so it can remove the valve but not what lies behind it. **This is the RDF limitation from the demo, in 4 facts.**

## A6. Build the same plant in Neo4j (LPG)
Neo4j has nothing like the text file: you **create boxes and arrows** with commands. In Neo4j Browser, first clear the database (**this deletes everything in it**; Part B reloads the big plant):
```cypher
MATCH (n) DETACH DELETE n
```
Then create the plant:
```cypher
CREATE (ch:Chiller:Equipment {id: 'CH-1', name: 'Chiller 1', capacity_kw: 1800})
CREATE (v:Valve:Equipment   {id: 'V-1',  name: 'Valve 1', position: 'open'})
CREATE (p:Pump:Equipment    {id: 'P-1',  name: 'Pump 1'})
CREATE (t:EtchTool          {id: 'ETCH-1', name: 'Etch 1'})
CREATE (ch)-[:FLOWS_TO]->(v)
CREATE (v)-[:FLOWS_TO]->(p)
CREATE (p)-[:FLOWS_TO {source: 'DCS', confidence: 0.98}]->(t)
```
**How to read it:**
- `(ch:Chiller:Equipment {…})` is **a box** with **labels** (Chiller, Equipment) and **properties** stored inside it.
- `-[:FLOWS_TO {…}]->` is **an arrow** with its own properties. The pipe's source and confidence sit **on the arrow** itself: no note, no extra facts.
- There's **no vocabulary.** Notice you had to write `Equipment` on every box by hand.
- The `id` values are only names inside this database. Nothing makes them globally unique.

Look at it:
```cypher
MATCH p = ()-[:FLOWS_TO]->() RETURN p
```
→ a **drawing**: 4 boxes and 3 arrows. Click the last arrow to see `source` and `confidence` on it.

## A7. Ask the same questions (LPG)
**What gets cooling from CH-1?**
```cypher
MATCH ({id: 'CH-1'})-[:FLOWS_TO*]->(x) RETURN x.id
```
→ V-1, P-1, ETCH-1.

**Which consumers are there?**
```cypher
MATCH (c:Consumer) RETURN c.id
```
→ **nothing**, and here there's no vocabulary to follow. Neo4j only knows the labels you typed. You have to add it yourself:
```cypher
MATCH (t {id: 'ETCH-1'}) SET t:Consumer
```
Run the consumer question again → ETCH-1.

## A8. Close the valve (LPG)
```cypher
MATCH (v {id: 'V-1'}) SET v.position = 'closed'
```
The plain question `MATCH ({id: 'CH-1'})-[:FLOWS_TO*]->(x) RETURN x.id` still lists all three. Neo4j isn't magic either. But here you **can** check the valve *during* the walk:
```cypher
MATCH ({id: 'CH-1'})((a)-[:FLOWS_TO]->(b) WHERE coalesce(b.position, 'open') = 'open')+(x)
RETURN x.id
```
→ **nothing**: the walk stops at the closed valve, so the pump and the tool behind it are cut off too. Compare with A5, where RDF could only hide the valve itself.

## What Part A taught you
| | RDF | LPG |
|---|---|---|
| What the data **is** | A file or set of **facts**: subject, predicate, object | **Boxes and arrows** with properties inside |
| Names | **Global** (`http://example.org/fab#CH-1`), so data from different systems merges | Local ids inside one database |
| Meaning ("etch tool is a consumer") | **Stored as data**, and queries follow it (A3) | Not stored; you add labels by hand (A7) |
| Details about a pipe | A **note** that points at the statement (A4); can have many | **Properties on the arrow** (A6); one set |
| Respecting a closed valve during a walk | **Can't** inside `flowsTo+`; filtering afterwards is too late (A5) | **Can**: the check sits inside the walk (A8) |
| Looking at it | A table of facts | A drawing |

Stop the Oxigraph window (Ctrl+C) before Part B; Part B uses the same port.

---

# Part B: the full plant, 10 exercises

**Load the plant into both databases.** This replaces the mini plant in Neo4j:
```powershell
py hands_on\setup.py --reset
```
- Oxigraph gets the plant in a separate folder, `hands_on_db\`. The script prints the command to start it, the same as A2 but with `hands_on_db`.
- To see what the script loaded into RDF, open **`out\chiller_rdf12.ttl`** in Notepad. It's the same kind of file you wrote in A1, just longer.

**Start Oxigraph on the big plant**, in its own window:
```powershell
& $ox serve --location hands_on_db --bind 127.0.0.1:7878
```

| | Address | Notes |
|---|---|---|
| **RDF** | http://127.0.0.1:7878 | Endpoint box ends in **`/sparql`**. Keep the `PREFIX` lines at the top of each SPARQL block. |
| **LPG** | http://localhost:7474 | No authentication. Ctrl+Enter to run. |

Don't run `chiller_demo/server.py` at the same time: it reloads the same Neo4j database.

## 1. Look at it
**RDF:**
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?subject ?predicate ?object WHERE { ?subject ?predicate ?object } LIMIT 100
```
**LPG:**
```cypher
MATCH p = ()-[:FLOWS_TO]->() RETURN p
```
**What you'll see:**
- **RDF:** a **table** of facts, 532 in total. Each row is one sentence: subject, predicate, object.
- **LPG:** a **picture** of the plant, 61 nodes and 66 arrows. Click a node and its properties appear in the side panel.

**What it means:** RDF stores **facts**; Neo4j stores **things and connections**. For an operator or a developer, Neo4j feels natural straight away. For a data steward, RDF's "every fact is a sentence with a global name" is what makes it shareable.

---

## 2. Add equipment: a second pump for loop B
**RDF:**
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
INSERT DATA {
  fab:P-B2 a fab:Pump ; rdfs:label "Loop B pump 2 (new)" .
  fab:HX-2 fab:flowsTo fab:P-B2 ~ fab:pipe-new1 {| fab:medium "pcw" ; fab:sourceSystem "DCS" ; fab:confidence 0.99 |} .
  fab:P-B2 fab:flowsTo fab:PCW-B ~ fab:pipe-new2 {| fab:medium "pcw" ; fab:sourceSystem "DCS" ; fab:confidence 0.99 |} .
}
```
**LPG:**
```cypher
MATCH (hx {id:'HX-2'}), (loop {id:'PCW-B'})
CREATE (p:Entity:Asset:PlantEquipment:Pump {id:'P-B2', name:'Loop B pump 2 (new)'})
CREATE (hx)-[:FLOWS_TO {medium:'pcw', source:'DCS', confidence:0.99}]->(p)
CREATE (p)-[:FLOWS_TO {medium:'pcw', source:'DCS', confidence:0.99}]->(loop)
```
**What you'll see:** both work. In RDF 1.2 the `~ … {| … |}` part attaches the pipe's details to the arrow. In Neo4j they go straight onto the relationship.

**What it means:** writing data is easy in both. Neo4j reads more like a drawing; RDF reads more like a list of statements.

---

## 3. "What depends on pump P-B1?" asked naively in both
**RDF:**
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?x WHERE { fab:P-B1 fab:flowsTo+ ?x } ORDER BY ?x
```
**LPG:**
```cypher
MATCH (:Entity {id:'P-B1'})-[:FLOWS_TO*]->(x) RETURN DISTINCT x.id ORDER BY x.id
```
**What you'll see:** both return **11** items, and **both are wrong**. They walked through the **closed** cross-tie valve V-TIE into loop A.

**What it means:** a graph only knows what you tell the query. A naive query is wrong in **both** databases, so this isn't a weakness of either one.

---

## 4. Make the query respect the valve, and feel the upkeep
**LPG:** check the valve **inside** the walk:
```cypher
MATCH (:Entity {id:'P-B1'})((a)-[:FLOWS_TO]->(b) WHERE coalesce(b.position,'open') = 'open')+(x)
RETURN DISTINCT x.id ORDER BY x.id
```
→ **6** items, correct.

**RDF:** there's **no place inside `flowsTo+` to check the valve**. RDF uses a precomputed shortcut `fab:openFlow`, meaning "pipes not blocked by a closed valve", which was built when the plant was loaded. First look at what's downstream of HX-2:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?x WHERE { fab:HX-2 fab:openFlow+ ?x } ORDER BY ?x
```
→ **P-B2 is missing.** The shortcut was built **before** you added the pump in step 2. It is **stale**. Rebuild it:
```sparql
PREFIX fab: <http://example.org/fab#>
DELETE WHERE { ?a fab:openFlow ?b } ;
INSERT { ?a fab:openFlow ?b } WHERE {
  ?a fab:flowsTo ?b .
  FILTER NOT EXISTS { ?a fab:position "closed" }
  FILTER NOT EXISTS { ?b fab:position "closed" }
}
```
Run the HX-2 query again: P-B2 is there now.

**What you'll see:** Neo4j reads the valve each time. RDF needs a shortcut, and **you have to remember to rebuild it** after every change to pipes or valves.

**What it means:** this is the core operational difference. **Whenever the network or its valves change often, LPG is simpler and safer.**

---

## 5. Show the route the cooling takes
**LPG:**
```cypher
MATCH p = shortestPath((:Entity {id:'CT-2'})-[:FLOWS_TO*]->(:Entity {id:'CVD-02'})) RETURN p
```
→ the route is **drawn**: CT-2 → CH-2 → CHW-HDR → V-HX2 → HX-2 → P-B1 (or your new P-B2) → PCW-B → CVD-02. `shortestPath` returns one route; there are two equally short ones now.

**RDF:** there's no route result type, so use a counting trick to put the units in order:
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?unit (COUNT(DISTINCT ?before) AS ?position) WHERE {
  fab:CT-2 fab:openFlow* ?before . ?before fab:openFlow* ?unit . ?unit fab:openFlow* fab:CVD-02 .
} GROUP BY ?unit ORDER BY ?position
```
→ the same units **as a table**, in order. P-B1 and P-B2 share position 6 because they run in parallel. The trick breaks if the network has loops, for example with the cross-tie open.

**What it means:** routes are native in LPG. RDF can do it with a trick or with application code.

---

## 6. What-if: "If P-B1 trips, which consumers lose cooling?"
**LPG**, one query:
```cypher
MATCH (c:Consumer)
WHERE NOT EXISTS {
  (:CoolingTower)((a)-[:FLOWS_TO]->(b) WHERE a.id <> 'P-B1' AND b.id <> 'P-B1'
     AND coalesce(a.position,'open') = 'open' AND coalesce(b.position,'open') = 'open')+(c) }
RETURN c.id
```
→ **no rows.** Your new pump P-B2 now covers loop B.

**RDF**, three steps, one after the other:
```sparql
PREFIX fab: <http://example.org/fab#>
INSERT { GRAPH fab:whatif { ?a fab:openFlow ?b } }
WHERE { ?a fab:openFlow ?b FILTER(?a != fab:P-B1 && ?b != fab:P-B1) }
```
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?consumer WHERE {
  ?consumer a/rdfs:subClassOf* fab:Consumer .
  FILTER NOT EXISTS { ?tower a fab:CoolingTower . GRAPH fab:whatif { ?tower fab:openFlow+ ?consumer } }
} ORDER BY ?consumer
```
```sparql
PREFIX fab: <http://example.org/fab#>
DROP SILENT GRAPH fab:whatif
```
→ **no rows**, if you rebuilt the shortcut in step 4. **Try it without the rebuild** (`py hands_on\setup.py --reset`, do step 2, skip step 4): RDF then says **3 tools lose cooling**, which is wrong, because the shortcut doesn't know about P-B2.

**What it means:**
- LPG: one read-only query.
- RDF: copy the network, query it, delete the copy. That needs write access, and it's only correct if the shortcut is up to date.
- **For operator what-if tools, propose LPG.**

---

## 7. Add a new kind of tool (RDF wins)
Add a wet bench, a **new type** of production tool, on loop A.

**RDF:** one extra line saying "a wet bench is a production tool":
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
INSERT DATA {
  fab:WetBench rdfs:subClassOf fab:ProductionTool .
  fab:WET-01 a fab:WetBench ; rdfs:label "Wet bench 1" .
  fab:PCW-A fab:flowsTo fab:WET-01 .
}
```
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?c WHERE { ?c a/rdfs:subClassOf* fab:Consumer } ORDER BY ?c
```
→ **WET-01 is listed.** RDF worked out that wet bench → production tool → consumer.

**LPG:**
```cypher
MATCH (l {id:'PCW-A'})
CREATE (w:Entity:WetBench {id:'WET-01', name:'Wet bench 1'})
CREATE (l)-[:FLOWS_TO {medium:'pcw'}]->(w)
```
```cypher
MATCH (c:Consumer) RETURN c.id ORDER BY c.id
```
→ **WET-01 is missing.** Neo4j doesn't know a wet bench is a consumer: someone has to add the labels by hand. Nothing warns you, and every "who loses cooling" answer now silently skips this tool. Fix it with:
```cypher
MATCH (w {id:'WET-01'}) SET w:Consumer:ProductionTool:Asset
```

**What it means:** in RDF, **meaning lives in the data** (the class hierarchy); in LPG it lives in whoever loads the data. **For a long-lived, shared asset model, propose RDF.**

---

## 8. Two systems disagree about one pipe (RDF 1.2 wins)
BIM already documents the pipe CHW-HDR → V-MAU2 (installed 2019, confidence 0.72). Now the DCS documents it too, with different details.

**RDF 1.2:** add a second note about the **same** pipe:
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
INSERT DATA {
  fab:dcs-note rdf:reifies <<( fab:CHW-HDR fab:flowsTo fab:V-MAU2 )>> ;
               fab:sourceSystem "DCS" ; fab:confidence 0.99 ; fab:installed 2020 .
}
```
```sparql
PREFIX fab: <http://example.org/fab#>
SELECT ?source ?confidence ?installed WHERE {
  fab:CHW-HDR fab:flowsTo fab:V-MAU2 {| fab:sourceSystem ?source ; fab:confidence ?confidence ; fab:installed ?installed |}
}
```
→ **two rows**: BIM says 2019 at 0.72, DCS says 2020 at 0.99. **Both kept.**

**LPG:**
```cypher
MATCH ({id:'CHW-HDR'})-[f:FLOWS_TO]->({id:'V-MAU2'})
SET f.source = 'DCS', f.confidence = 0.99, f.installed = 2020
RETURN f
```
→ **one** set of values. **BIM's version is gone.** To keep both, you'd need to redesign: extra properties, or a separate node per source.

**What it means:** this is where **RDF 1.2 is really different from RDF 1.1 and from LPG**. It's the natural tool for reconciling BIM, DCS and CMMS, and for audit trails ("who said this, when, how sure").

---

## 9. An unconfirmed claim (RDF 1.2)
BIM shows a pipe PCW-B → ETCH-01 that nobody has confirmed.

**RDF 1.2:** record the claim **without** making it true:
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
INSERT DATA {
  fab:claim-1 rdf:reifies <<( fab:PCW-B fab:flowsTo fab:ETCH-01 )>> ;
              fab:sourceSystem "BIM" ; fab:confidence 0.55 .
}
```
Is the pipe real now?
```sparql
PREFIX fab: <http://example.org/fab#>
ASK { fab:PCW-B fab:flowsTo fab:ETCH-01 }
```
→ **false.** The claim is stored, but it isn't treated as a pipe. List everything that's claimed but not confirmed:
```sparql
PREFIX fab: <http://example.org/fab#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?from ?to ?source ?confidence WHERE {
  ?note rdf:reifies ?statement ; fab:sourceSystem ?source ; fab:confidence ?confidence .
  BIND(SUBJECT(?statement) AS ?from) BIND(OBJECT(?statement) AS ?to)
  FILTER NOT EXISTS { ?from fab:flowsTo ?to }
}
```
**LPG:** there's no "claimed but not true" arrow. If you CREATE it, it's a real pipe. You'd have to store it as a separate `:Claim` node.

---

## 10. A taste of GraphRAG: vector search plus the graph (in Neo4j)
Maintenance notes are text. **Vector search** finds the note closest in meaning to a question. **The graph** then says what that equipment affects.

The 3-number "embeddings" below are toys so you can see the mechanics. A real system gets them from an embedding model.
```cypher
CREATE VECTOR INDEX note_embedding IF NOT EXISTS FOR (n:Note) ON n.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 3, `vector.similarity_function`: 'cosine'}};
```
```cypher
MATCH (p {id:'P-B1'}), (h {id:'HX-2'}), (c {id:'CH-2'})
CREATE (:Note {text:'P-B1 bearing noise, vibration rising, check alignment', embedding:[0.9, 0.1, 0.1]})-[:ABOUT]->(p)
CREATE (:Note {text:'HX-2 plates fouled, approach temperature high, schedule cleaning', embedding:[0.1, 0.9, 0.2]})-[:ABOUT]->(h)
CREATE (:Note {text:'CH-2 refrigerant charge low, leaving water warm', embedding:[0.1, 0.3, 0.9]})-[:ABOUT]->(c)
```
Ask "something about pump vibration", represented here as the vector `[0.85, 0.15, 0.1]`:
```cypher
CALL db.index.vector.queryNodes('note_embedding', 1, [0.85, 0.15, 0.1]) YIELD node AS note, score
MATCH (note)-[:ABOUT]->(asset)
OPTIONAL MATCH (asset)((a)-[:FLOWS_TO]->(b) WHERE coalesce(b.position,'open') = 'open')+(affected:Consumer)
RETURN note.text, round(score, 3) AS score, asset.id, collect(DISTINCT affected.id) AS affects
```
→ it finds the P-B1 note (score 0.999), then the graph adds **which tools that pump affects**. An LLM given this result can answer "what's the risk from this vibration?" with real plant context, not just the note text.

**RDF:** Oxigraph has no vector index. Vector search in RDF depends on the product: some RDF databases include one, or you use a separate vector database that returns the asset's IRI, then ask SPARQL for its context. The pattern is the same: **vector finds the entry point, the graph supplies the facts.**

---

## What you should have felt
| # | Task | RDF | LPG |
|---|---|---|---|
| 1 | Look at it | Table of facts | Picture |
| 2 | Add equipment | Easy | Easy |
| 3 | Naive query | Wrong | Wrong |
| 4 | Respect valves | Shortcut that **goes stale** until rebuilt | Checked inline, always current |
| 5 | Show the route | Trick or app code | Native, drawn |
| 6 | What-if trip | 3 steps, writes to the DB, needs a fresh shortcut | 1 read query |
| 7 | New equipment type | **Inferred** from one line | **Silently missed** until labels are added |
| 8 | Two sources disagree | **Both kept** (RDF 1.2) | One overwrites the other |
| 9 | Unconfirmed claim | **Stored, not treated as real** | Becomes real, or needs a workaround |
| 10 | Vector + graph | Depends on the product, or a separate vector DB | Built in (Neo4j 5.26 Community) |

## When to propose what
| The customer mainly needs… | Propose | Because (the exercise that showed it) |
|---|---|---|
| Operator tools: trip impact, isolation and lock-out checks, redundancy, live valve and pump states | **LPG** | 4, 5, 6 |
| One shared asset model across BIM, CMMS, MES and SCADA, handover from the contractor, cross-site standards | **RDF** | 7 (+ standard IDs and formats) |
| Reconciling sources, audit trails, "who said this", unconfirmed design data | **RDF 1.2** | 8, 9 |
| Both of the above (most fabs) | **RDF as the system of record → LPG as the operational copy, built from confirmed facts only** | all |
| "Ask questions about our manuals, SOPs and maintenance logs" | **Vector RAG** (no graph needed) | — |
| "Ask questions that need plant relationships": what does this affect, what's upstream, what failed on the same loop | **GraphRAG**: vector search plus a graph. LPG is quickest to build (10); RDF when the answers must use governed, shared definitions (7, 8) | 10 |
| Values over time, trends, KPIs | **Historian** | — |

**Not measured here, so check before promising:**
- how well an LLM writes Cypher vs SPARQL for your schema;
- vector search in your specific RDF product;
- performance at full-fab scale.
