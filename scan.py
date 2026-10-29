# send every tile to a vision model, ask for boxes around TARGET; resume-safe, follows fetch.py as tiles appear
# usage: TARGET='swimming pool' LLM_URL=http://127.0.0.1:8080 python3 scan.py [out.jsonl] [limit]
import base64, io, json, os, re, sys, time, glob, requests, threading, concurrent.futures as cf
from PIL import Image
OUT = sys.argv[1] if len(sys.argv) > 1 else "scan.jsonl"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
PAR = int(os.environ.get("PAR", "64"))                       # match your llama-server -np
TARGET = os.environ.get("TARGET", "swimming pool")
URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/") + "/v1/chat/completions"
MODEL = os.environ.get("MODEL", "lfm3-vl-2b")
PROMPT = f'Detect every {TARGET} in this aerial photo. Output only a JSON list of bounding boxes [x1, y1, x2, y2] in 0-1000 coordinates, or [] if there are none.'
def parse(c):
    try: bx = json.loads(re.search(r'\[.*\]', c, re.S).group(0))
    except Exception: return None
    if bx and not isinstance(bx[0], (list, dict)): bx = [bx]
    res = []
    for q in bx:
        if isinstance(q, dict): q = q.get("bbox_2d") or q.get("bbox") or []
        if isinstance(q, list) and len(q) >= 4:
            try: res.append([round(float(v)) for v in q[:4]])
            except Exception: pass
    return res
def one(f):
    buf = io.BytesIO(); Image.open(f).resize((640, 640), Image.LANCZOS).save(buf, "JPEG", quality=92)
    b = base64.b64encode(buf.getvalue()).decode(); t = time.time()
    for attempt in range(3):
        try:
            r = requests.post(URL, json={"model": MODEL, "max_tokens": 4096,
                "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}},
                                                          {"type": "text", "text": PROMPT}]}]}, timeout=1800).json()
            m = r["choices"][0]["message"]; c = (m.get("content") or "").strip()
            return {"tile": os.path.basename(f)[:-4], "boxes": parse(c), "raw": c[:4000], "finish": r["choices"][0].get("finish_reason"),
                    "ctok": r["usage"]["completion_tokens"], "ptok": r["usage"]["prompt_tokens"], "sec": round(time.time() - t, 1)}
        except Exception as e:
            err = repr(e); time.sleep(5)
    return {"tile": os.path.basename(f)[:-4], "boxes": None, "error": err}
seen = set()
if os.path.exists(OUT):
    for l in open(OUT): seen.add(json.loads(l)["tile"])
lock = threading.Lock(); out = open(OUT, "a"); n = 0; t0 = time.time()
def write(rec):
    global n
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush(); n += 1
        if n % 200 == 0: print(f"{n} tiles, {n/(time.time()-t0):.2f}/s", flush=True)
with cf.ThreadPoolExecutor(PAR) as ex:
    pending = set()
    while True:
        fetch_done = "FETCH DONE" in open("fetch.log").read()
        new = [f for f in sorted(glob.glob("tiles/*.jpg")) if os.path.basename(f)[:-4] not in seen]
        if LIMIT: new = new[:max(0, LIMIT - len(seen))]
        for f in new:
            seen.add(os.path.basename(f)[:-4]); fut = ex.submit(one, f); fut.add_done_callback(lambda fu: write(fu.result())); pending.add(fut)
        pending = {p for p in pending if not p.done()}
        if (fetch_done or (LIMIT and len(seen) >= LIMIT)) and not new and not pending: break
        time.sleep(10)
print(f"SCAN DONE {n} tiles in {(time.time()-t0)/60:.1f} min", flush=True)
