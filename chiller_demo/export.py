"""Write the chiller plant as files you can open and look at.
Run: python chiller_demo/export.py   (Windows: py chiller_demo\\export.py)
  out/chiller_rdf11.ttl  - RDF 1.1 (each pipe is a fab:Pipe node)   open in any text editor
  out/chiller_rdf12.ttl  - RDF 1.2 (each pipe is one statement + a reifier with its properties)
Both load into an Oxigraph server (SETUP.md A2). The Neo4j version is the live database itself:
open Neo4j Browser at http://localhost:7474 while the demo is running."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT.parent))
import pyoxigraph as ox
from scenario import FAB, RDF, RDFS, build_rdf, dataset

out = ROOT.parent / "out"; out.mkdir(exist_ok=True)
for mode, name in (("nary", "chiller_rdf11.ttl"), ("rdf12", "chiller_rdf12.ttl")):
    st = build_rdf(dataset(), mode)
    p = out / name
    st.dump(str(p), ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph(), prefixes={"fab": FAB, "rdf": RDF, "rdfs": RDFS})
    print(f"wrote {p}: {len(st)} triples")
