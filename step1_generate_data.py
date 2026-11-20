"""Stage 1 — generate the canonical fab-facility dataset (model-neutral JSON).
Run: python step1_generate_data.py            (SCALE=1 → one fab building)
     SCALE=10 python step1_generate_data.py   (10 buildings)
Output: data/facility_s{SCALE}.json"""
import json, os, random
from pathlib import Path

SCALE = int(os.environ.get("SCALE", 1))
OUT = Path(__file__).parent / "data" / f"facility_s{SCALE}.json"
TOOL_TYPES = ["EUVScanner", "EtchTool", "CVDTool", "CMPTool", "MetrologyTool"]
SOURCES = [("WinCCOA", 0.95), ("CMMS", 0.9), ("BIM", 0.7)]  # (system that asserted the link, typical confidence)


def generate(scale: int, seed: int = 42) -> dict:
    rnd = random.Random(seed)
    nodes, edges = [], []

    def node(i, t, **p):
        nodes.append({"id": i, "type": t, "name": i, **p}); return i

    def edge(s, d, t, **p):
        edges.append({"id": f"e{len(edges)}", "src": s, "dst": d, "type": t, **p})

    def feed(s, d, medium, cap):
        src, conf = rnd.choice(SOURCES)
        edge(s, d, "feeds", medium=medium, installed=rnd.randint(2008, 2025),
             redundant=rnd.random() < 0.4, capacity_kw=cap,
             load_kw=round(cap * rnd.uniform(0.3, 0.95), 1),
             source=src, confidence=round(min(1.0, conf + rnd.uniform(-0.15, 0.05)), 2))

    def datapoints(asset, signals):
        for sig, unit in signals:
            dp = node(f"{asset}.{sig}", "Datapoint", tag=f"System1:{asset.replace('-', '_')}.{sig}", unit=unit)
            edge(asset, dp, "hasDatapoint")
            if rnd.random() < 0.12:
                al = node(f"ALM-{dp}", "Alarm", severity=rnd.choice(["warning", "major", "critical"]),
                          active=rnd.random() < 0.6, raised="2026-11-%02dT%02d:00:00Z" % (rnd.randint(1, 16), rnd.randint(0, 23)))
                edge(al, dp, "raisedOn")

    site = node("SITE-FAB", "Site")
    for b in range(1, scale + 1):
        B = f"B{b:02d}"
        bld = node(f"BLD-{B}", "Building"); edge(bld, site, "locatedIn")
        swg = [node(f"SWG-{B}-{x}", "Switchgear") for x in "AB"]
        ups = [node(f"UPS-{B}-{i}", "UPS") for i in range(1, 5)]
        pdu = [node(f"PDU-{B}-{i:02d}", "PDU") for i in range(1, 9)]
        ch = [node(f"CH-{B}-{i:02d}", "Chiller") for i in range(1, 4)]
        loops = [node(f"PCW-{B}-{i}", "CoolingLoop") for i in range(1, 5)]
        for x in swg + ups + pdu + ch + loops: edge(x, bld, "locatedIn")
        for i, u in enumerate(ups): feed(swg[i // 2], u, "power", 2000)
        for i, p in enumerate(pdu): feed(ups[i // 2], p, "power", 400)
        for i, c in enumerate(ch):
            feed(swg[i % 2], c, "power", 800)
            datapoints(c, [("SupplyTemp", "degC"), ("ReturnTemp", "degC"), ("Power", "kW")])
        for i, l in enumerate(loops):
            feed(ch[i % 3], l, "pcw", 1500)
            if rnd.random() < 0.5: feed(ch[(i + 1) % 3], l, "pcw", 1500)  # redundant 2nd chiller
        for a in range(1, 5):
            area = node(f"AREA-{B}-{a}", "Area", cleanroomClass="ISO5"); edge(area, bld, "locatedIn")
            for t in range(1, 11):
                tool = node(f"T-{B}-{a}{t:02d}", rnd.choice(TOOL_TYPES)); edge(tool, area, "locatedIn")
                for p in rnd.sample(pdu, rnd.choice([1, 1, 2])): feed(p, tool, "power", 150)
                for l in rnd.sample(loops, rnd.choice([1, 2])): feed(l, tool, "pcw", 200)
                datapoints(tool, [("State", ""), ("ChuckTemp", "degC"), ("Vacuum", "mbar"), ("PowerDraw", "kW")])
    return {"scale": scale, "nodes": nodes, "edges": edges}


if __name__ == "__main__":
    d = generate(SCALE)
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(d, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"wrote {OUT.name}: {len(d['nodes'])} nodes, {len(d['edges'])} edges")
    print(" node types:", dict(Counter(n["type"] for n in d["nodes"])))
    print(" edge types:", dict(Counter(e["type"] for e in d["edges"])))
    print(" edges WITH metadata (feeds):", sum(e["type"] == "feeds" for e in d["edges"]))
