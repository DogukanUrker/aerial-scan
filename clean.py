# lenient re-parse of raw answers, drop impossible boxes, merge pools cut by tile edges -> pools.json
import json, os, re
MAX_BOX = float(os.environ.get("MAX_BOX_M", "67")) / 192 * 1000   # drop boxes bigger than this many metres
G = json.load(open("grid.json")); C = G["cell"]
R = [json.loads(l) for l in open("scan.jsonl")]
num = r"(-?\d+(?:\.\d+)?)"
def lenient(raw):
    out = [list(map(float, m)) for m in re.findall(r"\[\s*" + r"\s*,\s*".join([num] * 4) + r"\s*\]", raw)]
    for m in re.finditer(r"\{[^{}]*\}", raw):
        d = dict(re.findall(r'"(x1|y1|x2|y2)"\s*:\s*' + num, m.group(0)))
        if len(d) == 4: out.append([float(d[k]) for k in ("x1", "y1", "x2", "y2")])
    return out
stats = {"reparsed": 0, "dropped_big": 0, "dropped_bad": 0, "unparsed": []}
pools = []
for r in R:
    bx = r["boxes"]
    if bx is None:
        bx = lenient(r.get("raw", "")); stats["reparsed"] += 1
        if not bx and "[]" not in r.get("raw", ""): stats["unparsed"].append(r["tile"])
    j, i = map(int, r["tile"].split("_"))
    for x1, y1, x2, y2 in bx:
        if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000): stats["dropped_bad"] += 1; continue
        if x2 - x1 > MAX_BOX or y2 - y1 > MAX_BOX: stats["dropped_big"] += 1; continue   # default 67 m: bigger than any backyard pool
        # to UTM metres
        ex0 = G["x0"] + i * C + x1 / 1000 * C; ex1 = G["x0"] + i * C + x2 / 1000 * C
        ny0 = G["y1"] - j * C - y1 / 1000 * C; ny1 = G["y1"] - j * C - y2 / 1000 * C
        pools.append({"tile": r["tile"], "box": [x1, y1, x2, y2], "utm": [ex0, ny1, ex1, ny0]})
# merge: boxes touching a shared tile edge from neighbouring tiles that overlap after a 2 m pad
def edge(p): return any(v <= 15 or v >= 985 for v in p["box"])
cand = [k for k, p in enumerate(pools) if edge(p)]
grid = {}
for k in cand:
    u = pools[k]["utm"]; grid.setdefault((int(u[0] // 50), int(u[1] // 50)), []).append(k)
parent = list(range(len(pools)))
def find(a):
    while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
    return a
merged = 0
for k in cand:
    a = pools[k]["utm"]
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for m in grid.get((int(a[0] // 50) + dx, int(a[1] // 50) + dy), []):
                if m <= k or pools[m]["tile"] == pools[k]["tile"]: continue
                b = pools[m]["utm"]
                if a[0] - 2 <= b[2] and b[0] - 2 <= a[2] and a[1] - 2 <= b[3] and b[1] - 2 <= a[3]:
                    if find(k) != find(m): parent[find(k)] = find(m); merged += 1
for k, p in enumerate(pools): p["id"] = find(k)
n = len({p["id"] for p in pools})
stats.update({"boxes": len(pools), "edge_merges": merged, "pools": n})
json.dump(pools, open("pools.json", "w"))
print(json.dumps(stats))
