"""Stage 0 — verify the toolchain instead of trusting memory.
Run: python step0_env_check.py"""
import importlib.metadata as md, shutil, socket, subprocess

def ver(p):
    try: return md.version(p)
    except md.PackageNotFoundError: return "MISSING"

for p in ["pyoxigraph", "rdflib", "pyshacl", "neo4j"]:
    print(f"{p:12s} {ver(p)}")

import pyoxigraph as ox
tests = {
    "RDF 1.2 triple term  <<( s p o )>>": '@prefix : <http://e/> . :r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( :a :b :c )>> .',
    "RDF 1.2 reifier+annotation ~ {| |}": '@prefix : <http://e/> . :a :b :c ~ :r {| :since 2020 |} .',
    "legacy RDF-star  << s p o >> :p o": '@prefix : <http://e/> . << :a :b :c >> :since 2020 .',
}
for name, ttl in tests.items():
    s = ox.Store()
    try:
        s.load(ttl.encode(), ox.RdfFormat.TURTLE)
        print(f"[OK]   {name}: {len(s)} quads")
        for q in s: print("         ", q)
    except Exception as e:
        print(f"[FAIL] {name}: {e}")

s = ox.Store(); s.load(b'@prefix : <http://e/> . :a :b :c {| :since 2020 |} .', ox.RdfFormat.TURTLE)
r = list(s.query('PREFIX : <http://e/> SELECT ?s ?y WHERE { ?s :b :c {| :since ?y |} }'))
print("[OK]  SPARQL 1.2 annotation pattern" if r else "[FAIL] SPARQL 1.2 annotation pattern", [str(x) for x in r[0]] if r else "")

print("java:", shutil.which("java"), "| mvn:", shutil.which("mvn"))
d = subprocess.run(["docker", "info"], capture_output=True, text=True)
print("docker daemon:", "UP" if d.returncode == 0 else "DOWN (using embedded Neo4j, see DECISIONS D4)")
with socket.socket() as so:
    so.settimeout(0.5)
    print("neo4j bolt :7687:", "LISTENING" if so.connect_ex(("127.0.0.1", 7687)) == 0 else "not running (start: ./neo4j_embedded/run.sh)")
