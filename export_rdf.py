"""Export the lab dataset as files you can load into any RDF store (Oxigraph server, Jena, GraphDB, ...).
Run: python export_rdf.py            (SCALE=10 python export_rdf.py for bigger)
Writes out/fab_rdf11.ttl  (RDF 1.1, n-ary Feed nodes — loads everywhere)
       out/fab_rdf12.ttl  (RDF 1.2 Turtle with triple terms — needs an RDF 1.2 parser, e.g. Oxigraph 0.5)"""
import pyoxigraph as ox
from common import FAB, OUT, load, scale
from rdf_common import build, store_from, RDF, RDFS

d = load(scale())
for mode, name in [("nary", "fab_rdf11.ttl"), ("rdf12", "fab_rdf12.ttl")]:
    st = store_from(build(d, mode))
    p = OUT / name
    st.dump(str(p), ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph(), prefixes={"fab": FAB, "rdf": RDF, "rdfs": RDFS})
    print(f"wrote {p.relative_to(OUT.parent)}: {len(st)} triples")
from step5_interop import SHAPES
(OUT / "fab_shapes.ttl").write_text(SHAPES + "\n")
print("wrote out/fab_shapes.ttl (SHACL shapes from step5)")
