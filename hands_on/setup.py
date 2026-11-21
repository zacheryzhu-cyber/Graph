"""Set up the hands-on comparison: the same chiller plant in Oxigraph (RDF) and in Neo4j (LPG).

  py hands_on\\setup.py            (Windows)      python hands_on/setup.py      (Mac/Linux)
  py hands_on\\setup.py --reset    start again from a clean plant (deletes hands_on_db\\ and reloads Neo4j)

What it does
  1. writes the plant as RDF files: out/chiller_rdf12.ttl (and out/chiller_rdf11.ttl)
  2. loads out/chiller_rdf12.ttl into an Oxigraph database folder: hands_on_db/
  3. loads the same plant into Neo4j (bolt://127.0.0.1:7687), if Neo4j is running. This WIPES that Neo4j database.
Then it prints the two commands to open both in your browser. See HANDS_ON.md for the exercises.
Needs: pip install -r requirements.txt  and  pip install oxigraph"""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chiller_demo")); sys.path.insert(0, str(ROOT))
import pyoxigraph as ox
from scenario import FAB, RDF, RDFS, build_rdf, dataset, load_lpg

DB = ROOT / "hands_on_db"
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)


def find_oxigraph():
    exe = shutil.which("oxigraph")
    if exe: return exe
    base = Path(sys.executable).parent
    for cand in (base / "Scripts" / "oxigraph.exe", base / "oxigraph.exe", base / "oxigraph"):
        if cand.exists(): return str(cand)
    return None


def main():
    reset = "--reset" in sys.argv
    d = dataset()
    print("1. Writing the plant as RDF files")
    for mode, name in (("rdf12", "chiller_rdf12.ttl"), ("nary", "chiller_rdf11.ttl")):
        st = build_rdf(d, mode); p = OUT / name
        st.dump(str(p), ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph(), prefixes={"fab": FAB, "rdf": RDF, "rdfs": RDFS})
        print(f"   {p.relative_to(ROOT)}  ({len(st)} triples)")

    print("2. Loading RDF 1.2 into Oxigraph")
    exe = find_oxigraph()
    if not exe:
        print("   Oxigraph not found. Install it with:  py -m pip install oxigraph   then run this script again.")
    else:
        if DB.exists() and reset:
            shutil.rmtree(DB); print(f"   removed old {DB.name}{'/'}")
        if DB.exists():
            print(f"   {DB.name}/ already exists, keeping your changes. (Use --reset to start clean.)")
        else:
            subprocess.run([exe, "load", "--location", str(DB), "--file", str(OUT / "chiller_rdf12.ttl")], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"   loaded into {DB.name}/")

    print("3. Loading the same plant into Neo4j")
    try:
        from neo_common import driver, wipe
        drv = driver()
        if reset or drv.execute_query("MATCH (n:Entity) RETURN count(n) AS c")[0][0]["c"] == 0:
            wipe(drv); load_lpg(drv, d); print("   loaded (61 nodes, 66 relationships)")
        else:
            print("   Neo4j already has data, keeping your changes. (Use --reset to start clean.)")
    except SystemExit as e:
        print("   Neo4j isn't running, so it was skipped. Start Neo4j (Docker or Neo4j Desktop), then run this again.")

    print("\nNow open both, each in its own window:")
    if exe:
        q = f'"{exe}"' if " " in exe else exe
        print(f"   RDF (Oxigraph):  {q} serve --location {DB.name} --bind 127.0.0.1:7878   → http://127.0.0.1:7878")
    print("   LPG (Neo4j):     Neo4j Browser → http://localhost:7474  (connect with no password if you used NEO4J_AUTH=none)")
    print("Then follow HANDS_ON.md.  Don't run chiller_demo/server.py at the same time: it reloads the same Neo4j database.")


if __name__ == "__main__":
    main()
