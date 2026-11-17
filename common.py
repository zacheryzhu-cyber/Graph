"""Shared helpers: load the canonical dataset, compute ground-truth answers for Q1–Q5 in plain Python,
and time queries. Every model's answers are checked against this ground truth (fairness check)."""
import json, os, statistics, subprocess, sys, time
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
TOOL_TYPES = {"EUVScanner", "EtchTool", "CVDTool", "CMPTool", "MetrologyTool"}
FAB = "http://example.org/fab#"
TRIP_SOURCE = "SWG-B01-A"   # Q1/Q4: switchgear that trips


def scale() -> int:
    return int(os.environ.get("SCALE", 1))


def load(sc: int | None = None) -> dict:
    sc = sc or scale()
    p = ROOT / "data" / f"facility_s{sc}.json"
    if not p.exists():
        subprocess.run([sys.executable, str(ROOT / "step1_generate_data.py")], env={**os.environ, "SCALE": str(sc)},
                       check=True, capture_output=True)
    return json.loads(p.read_text())


def ground_truth(d: dict) -> dict:
    types = {n["id"]: n["type"] for n in d["nodes"]}
    feeds = [e for e in d["edges"] if e["type"] == "feeds"]
    adj = defaultdict(list)
    for e in feeds: adj[e["src"]].append(e["dst"])
    # Q1 / Q4: BFS downstream from the tripped switchgear
    dist, q = {TRIP_SOURCE: 0}, deque([TRIP_SOURCE])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist: dist[v] = dist[u] + 1; q.append(v)
    q1 = sorted(n for n in dist if types[n] in TOOL_TYPES)
    q4_target = q1[0]
    q2 = sorted((e["src"], e["dst"]) for e in feeds
                if not e["redundant"] and e["installed"] < 2018 and e["load_kw"] / e["capacity_kw"] > 0.7)
    q3 = sorted((e["src"], e["dst"], e["confidence"]) for e in feeds if e["source"] == "BIM" and e["confidence"] < 0.8)
    # Q5: per area: datapoints of tools in the area, and active alarms on them
    area_of = {e["src"]: e["dst"] for e in d["edges"] if e["type"] == "locatedIn" and types[e["dst"]] == "Area"}
    dp_owner = {e["dst"]: e["src"] for e in d["edges"] if e["type"] == "hasDatapoint"}
    active = {n["id"] for n in d["nodes"] if n["type"] == "Alarm" and n["active"]}
    q5 = defaultdict(lambda: [0, 0])
    for dp, owner in dp_owner.items():
        if owner in area_of: q5[area_of[owner]][0] += 1
    for e in d["edges"]:
        if e["type"] == "raisedOn" and e["src"] in active and dp_owner.get(e["dst"]) in area_of:
            q5[area_of[dp_owner[e["dst"]]]][1] += 1
    return {"Q1": q1, "Q2": q2, "Q3": q3, "Q4_target": q4_target, "Q4_len": dist[q4_target],
            "Q5": sorted((a, c[0], c[1]) for a, c in q5.items())}


def timed(fn, repeat: int = 5):
    """Run fn `repeat` times, return (result, median_ms)."""
    ts, res = [], None
    for _ in range(repeat):
        t = time.perf_counter(); res = fn(); ts.append((time.perf_counter() - t) * 1000)
    return res, statistics.median(ts)


def check(name: str, got, want) -> bool:
    ok = got == want
    print(f"   {'✓' if ok else '✗ MISMATCH'} {name}" + ("" if ok else f"\n      got  {str(got)[:200]}\n      want {str(want)[:200]}"))
    return ok


def save_metrics(model: str, metrics: dict):
    p = OUT / "metrics.json"
    allm = json.loads(p.read_text()) if p.exists() else {}
    allm.setdefault(model, {})[str(scale())] = metrics
    p.write_text(json.dumps(allm, indent=1))
