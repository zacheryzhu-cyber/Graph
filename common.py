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
    return json.loads(p.read_text(encoding="utf-8"))


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
    # Q6: single point of failure — tools whose POWER (medium=power edges only) comes from exactly one switchgear
    radj = defaultdict(list)
    for e in feeds:
        if e["medium"] == "power": radj[e["dst"]].append(e["src"])
    q6 = []
    for t in (n for n, ty in types.items() if ty in TOOL_TYPES):
        seen, st = set(), [t]
        while st:
            for u in radj[st.pop()]:
                if u not in seen: seen.add(u); st.append(u)
        if sum(types[u] == "Switchgear" for u in seen) == 1: q6.append(t)
    q6_naive = []   # same question WITHOUT the medium filter (cooling paths via chillers count as 'power') → wrong answer
    radj_all = defaultdict(list)
    for e in feeds: radj_all[e["dst"]].append(e["src"])
    for t in (n for n, ty in types.items() if ty in TOOL_TYPES):
        seen, st = set(), [t]
        while st:
            for u in radj_all[st.pop()]:
                if u not in seen: seen.add(u); st.append(u)
        if sum(types[u] == "Switchgear" for u in seen) == 1: q6_naive.append(t)
    return {"Q6": sorted(q6), "Q6_naive_count": len(q6_naive), "Q1": q1, "Q2": q2, "Q3": q3, "Q4_target": q4_target, "Q4_len": dist[q4_target],
            "Q5": sorted((a, c[0], c[1]) for a, c in q5.items())}


REPEAT = int(os.environ.get("REPEAT", 15))
LAST_P95 = {}


def timed(fn, repeat: int | None = None, key: str | None = None):
    """1 untimed warm-up (plan cache, JIT, page cache), then `repeat` timed runs.
    Returns (result, p50_ms); p95 is stored in LAST_P95[key] for the metrics file."""
    repeat = repeat or REPEAT
    res = fn()
    ts = []
    for _ in range(repeat):
        t = time.perf_counter(); res = fn(); ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    if key: LAST_P95[key] = ts[min(len(ts) - 1, int(round(0.95 * (len(ts) - 1))))]
    return res, statistics.median(ts)


def check(name: str, got, want) -> bool:
    ok = got == want
    print(f"   {'✓' if ok else '✗ MISMATCH'} {name}" + ("" if ok else f"\n      got  {str(got)[:200]}\n      want {str(want)[:200]}"))
    return ok


def save_metrics(model: str, metrics: dict):
    p = OUT / "metrics.json"
    allm = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    allm.setdefault(model, {})[str(scale())] = metrics
    p.write_text(json.dumps(allm, indent=1), encoding="utf-8")
