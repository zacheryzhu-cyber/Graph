"""Build the recorded edition of the Chiller Plant Graph Lab: one self-contained HTML page.

Runs every preset (each question × each parameter choice × each valve state × each claim state, plus the console examples)
on the live engines, and embeds the exact answers and timings keyed by a hash of the exact query text.
Needs Neo4j running. Don't run it while chiller_demo/server.py is serving a user:
both share the one Neo4j database.

  python chiller_demo/build_published.py   → chiller_demo/dist/chiller_plant_graph_lab.html"""
import datetime, itertools, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent)); sys.path.insert(0, str(ROOT))
import importlib.metadata as md
from server import Engines
from scenario import QUESTIONS, CONSOLE, CLAIM_DEFAULT, VALVE_PRESETS, fill

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
    eng.load()
    cat = {n["id"]: n.get("category") for n in eng.dataset["nodes"]}
    typ = {n["id"]: n["type"] for n in eng.dataset["nodes"]}
    dom = {"unit": [k for k, c in cat.items() if c == "plant"], "consumer": [k for k, c in cat.items() if c == "consumer"],
           "chiller": [k for k, t in typ.items() if t == "Chiller"]}
    claims = [{"src": CLAIM_DEFAULT[0], "dst": CLAIM_DEFAULT[1]}]
    claim_states = [("none", None)] + [(f"{m}:{c['src']}>{c['dst']}", dict(c, neo_mode=m)) for c in claims for m in ("n10s", "node")]

    def jobs():
        for q in QUESTIONS:
            spec = q["params"]
            domains = {k: (s["options"] if s["kind"] == "choice" else dom[s["kind"]]) for k, s in spec.items()}
            keys = list(domains)
            for combo in itertools.product(*[domains[k] for k in keys]):
                p = dict(zip(keys, combo))
                for e in ("rdf11", "rdf12", "neo4j"):
                    yield (e, fill(q[e], {k: js_str(v) for k, v in p.items()}))
        for c in CONSOLE: yield (c["engine"], c["text"])

    rec, t0, n, valve_ms = {}, time.time(), 0, {}
    for preset in VALVE_PRESETS:
        eng.set_valves("normal"); valve_ms[preset] = eng.set_valves(preset)["valve_ms"]   # cost of moving from normal to this state
        for key, claim in claim_states:
            eng.set_claim("add", claim["src"], claim["dst"], claim["neo_mode"]) if claim else eng.set_claim("remove")
            seen = set()
            for e, text in jobs():
                if (e, text) in seen: continue
                seen.add((e, text))
                rec[f"{preset}|{key}|{e}|{cyrb53(text)}"] = eng.query(e, text, repeat=2); n += 1
            print(f"  valves {preset}, claim {key}: {len(seen)} queries recorded ({time.time() - t0:.0f} s)")
    eng.set_claim("remove"); eng.set_valves("normal")
    valve_ms["normal"] = None

    meta = eng.meta(); meta["mode"] = "recorded"; meta["oxigraph"] = md.version("pyoxigraph"); meta["claim"] = None
    meta["valves"] = "normal"; meta["valve_ms"] = None
    embed = {"meta": meta, "dataset": eng.dataset, "rec": rec, "claims": claims, "valve_ms": valve_ms,
             "recorded_at": datetime.date.today().isoformat()}
    page = (ROOT / "web" / "app.html").read_text(encoding="utf-8")
    blob = json.dumps(embed, separators=(",", ":"), default=str).replace("</", "<\\/")
    marker = '<script>\n(() => {\n"use strict";'
    assert marker in page
    out = page.replace(marker, f"<script>window.__EMBED={blob};</script>\n" + marker, 1)
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    path = dist / "chiller_plant_graph_lab.html"; path.write_text(out, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT.parent)}: {len(out) / 1e6:.2f} MB, {len(rec)} recordings, {n} query runs")


if __name__ == "__main__":
    main()
