"""Build the recorded edition of the workbench: one self-contained HTML page.

Runs every preset (each question × each parameter choice × each claim state, plus the console examples)
on the live engines, and embeds the exact answers and timings keyed by a hash of the exact query text.
Needs Neo4j running (./neo4j_embedded/run.sh). Don't run it while demo/server.py is serving a user:
both share the one Neo4j database.

  python demo/build_published.py   → demo/dist/fab_graph_workbench.html"""
import datetime, itertools, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent)); sys.path.insert(0, str(ROOT))
import importlib.metadata as md
from server import Engines
from queries import QUESTIONS, CONSOLE, catalogue, fill

M32 = 0xFFFFFFFF


def cyrb53(s: str) -> str:
    """Port of the page's cyrb53 (UTF-16 code units, 32-bit Math.imul semantics)."""
    imul = lambda a, b: (a * b) & M32
    h1, h2 = 0xDEADBEEF, 0x41C6CE57
    b = s.encode("utf-16-le")
    for i in range(0, len(b), 2):
        ch = b[i] | (b[i + 1] << 8)
        h1 = imul(h1 ^ ch, 2654435761); h2 = imul(h2 ^ ch, 1597334677)
    h1 = imul(h1 ^ (h1 >> 16), 2246822507); h1 ^= imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = imul(h2 ^ (h2 >> 16), 2246822507); h2 ^= imul(h1 ^ (h1 >> 13), 3266489909)
    return str(4294967296 * (2097151 & h2) + (h1 & M32))


def js_str(v):
    """String(v) as JavaScript prints JSON numbers: 1.0 → "1"."""
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return str(v)


def main():
    eng = Engines()
    if not eng.drv: raise SystemExit("Neo4j must be running: ./neo4j_embedded/run.sh")
    eng.load(1)
    types = {n["id"]: n["type"] for n in eng.dataset["nodes"]}
    infra = sorted(k for k, t in types.items() if t in {"Switchgear", "UPS", "PDU", "Chiller", "CoolingLoop"} and "-B01-" in k)
    tools = sorted(k for k, t in types.items() if t.endswith(("Scanner", "Tool")) and "-B01-" in k)
    claims = [{"src": "PDU-B01-01", "dst": "T-B01-107"}]
    states = [("none", None)] + [(f"{m}:{c['src']}>{c['dst']}", dict(c, neo_mode=m)) for c in claims for m in ("n10s", "node")]

    def jobs():
        for q in QUESTIONS:
            spec = q["params"]
            domains = {k: (infra if s["kind"] == "infra" else tools if s["kind"] == "tool" else s["options"]) for k, s in spec.items()}
            keys = list(domains)
            for combo in itertools.product(*[domains[k] for k in keys]):
                p = dict(zip(keys, combo))
                for e in ("rdf11", "rdf12", "neo4j"):
                    if "variants" in q:
                        yield (e, q["variants"][p["filter"]][e]); continue
                    yield (e, fill(q[e], {k: js_str(v) for k, v in p.items()}))
        for c in CONSOLE: yield (c["engine"], c["text"])

    rec, t0, n = {}, time.time(), 0
    for key, claim in states:
        eng.set_claim("add", claim["src"], claim["dst"], claim["neo_mode"]) if claim else eng.set_claim("remove")
        seen = set()
        for job in jobs():
            e, text = job
            if (e, text) in seen: continue
            seen.add((e, text))
            r = eng.query(e, text, repeat=2); n += 1
            rec[f"{key}|{e}|{cyrb53(text)}"] = r
        print(f"  claim state {key}: {len(seen)} queries recorded ({time.time() - t0:.0f} s)")
    eng.set_claim("remove")

    meta = eng.meta(); meta["mode"] = "recorded"; meta["oxigraph"] = md.version("pyoxigraph"); meta["claim"] = None
    embed = {"meta": meta, "dataset": eng.dataset, "rec": rec, "claims": claims,
             "recorded_at": datetime.date.today().isoformat()}
    page = (ROOT / "web" / "app.html").read_text()
    blob = json.dumps(embed, separators=(",", ":"), default=str).replace("</", "<\\/")
    marker = '<script>\n(() => {\n"use strict";'
    assert marker in page
    out = page.replace(marker, f"<script>window.__EMBED={blob};</script>\n" + marker, 1)
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    path = dist / "fab_graph_workbench.html"; path.write_text(out)
    print(f"wrote {path.relative_to(ROOT.parent)}: {len(out) / 1e6:.2f} MB, {len(rec)} recordings, {n} query runs")


if __name__ == "__main__":
    main()
