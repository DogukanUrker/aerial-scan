# preview: valley map lights up as tiles get scanned, pools appear as dots, then zoom into one block with the model's boxes
import json, subprocess, math, sys, os
TITLE = os.environ.get("TITLE", TITLE)
NOUN = os.environ.get("NOUN", "pools")
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
G = json.load(open("grid.json")); NX, NY = G["nx"], G["ny"]
R = [json.loads(l)["tile"] for l in open("scan.jsonl")]            # scan order
P = json.load(open("pools.json"))
first = {}
for p in P: first.setdefault(p["id"], p)
pools = list(first.values())
by_tile = {}
for p in pools: by_tile.setdefault(p["tile"], []).append(p)
allbox = {}
for p in P: allbox.setdefault(p["tile"], []).append(p["box"])
TOTAL = len(pools)
W, H = 1280, 1090; MX, MY, MW = 40, 130, 1200
S = MW / NX                                                          # screen px per tile
MH = int(NY * S)
F = lambda w, s: ImageFont.truetype(f"fonts/Inter-{w}.ttf", s)
BG, INK, MUT, CY, RED = (11, 13, 18), (240, 242, 245), (130, 136, 148), (64, 220, 255), (255, 60, 60)
mos = Image.open("mosaic.jpg").convert("RGB")
lit = ImageEnhance.Brightness(mos.resize((MW, MH), Image.LANCZOS)).enhance(0.55)
dark = ImageEnhance.Brightness(ImageEnhance.Color(lit).enhance(0.0)).enhance(0.18)
dot = Image.new("RGBA", (MW, MH), (0, 0, 0, 0)); dd = ImageDraw.Draw(dot)
mask = Image.new("L", (MW, MH), 0); md = ImageDraw.Draw(mask)
def tile_xy(t):
    j, i = map(int, t.split("_")); return j, i
def header(d, sub=True):
    d.text((40, 26), TITLE, font=F("ExtraBold", 36), fill=INK)
    d.text((40, 74), f"{len(R):,} aerial tiles · {os.environ.get('SUBTITLE', 'LFM3-VL-2B on one RTX 3060')}", font=F("Regular", 24), fill=MUT)
def footer(d, n, k, hours):
    d.text((40, MY + MH + 22), f"{n:,} {NOUN} found", font=F("ExtraBold", 40), fill=CY)
    r = f"tile {k:,} / {len(R):,}   ·   {hours}"
    d.text((W - 40 - d.textlength(r, font=F("SemiBold", 24)), MY + MH + 34), r, font=F("SemiBold", 24), fill=MUT)
    note = f"{NOUN} the model found, not a census · imagery: USDA NAIP"
    d.text((40, H - 40), note, font=F("Regular", 18), fill=(90, 96, 108))
frames = []
p = subprocess.Popen(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30",
                      "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "out/preview.mp4"], stdin=subprocess.PIPE)
def emit(im): p.stdin.write(im.tobytes())
import os; os.makedirs("out", exist_ok=True)
# phase 1: scan, 17 s
N1 = 510; per = math.ceil(len(R) / N1); n = 0; MIN = int(os.environ.get("RUN_MIN", "335"))   # wall time of your scan, for the clock
for f in range(N1 + 1):
    chunk = R[f * per:(f + 1) * per]
    for t in chunk:
        j, i = tile_xy(t); x0, y0 = i * S, j * S
        md.rectangle([x0, y0, x0 + S + 1, y0 + S + 1], fill=255)
        for q in by_tile.get(t, []):
            b = q["box"]; cx = x0 + (b[0] + b[2]) / 2000 * S; cy = y0 + (b[1] + b[3]) / 2000 * S
            dd.ellipse([cx - .8, cy - .8, cx + .8, cy + .8], fill=CY + (255,)); n += 1
    k = min(len(R), (f + 1) * per)
    m = Image.composite(lit, dark, mask).convert("RGBA"); m.alpha_composite(dot)
    im = Image.new("RGB", (W, H), BG); im.paste(m.convert("RGB"), (MX, MY)); d = ImageDraw.Draw(im)
    if chunk:
        j, i = tile_xy(chunk[-1]); d.line([(MX, MY + (j + 1) * S), (MX + MW, MY + (j + 1) * S)], fill=(255, 255, 255), width=1)
    mins = int(k / len(R) * MIN); header(d); footer(d, n, k, f"{mins // 60}h {mins % 60:02d}m")
    emit(im)
final = im
for _ in range(45): emit(final)
# phase 2: zoom into the densest 3x3 block
CJ, CI = (int(v) for v in os.environ.get("ZOOM_TILE", "39,62").split(",")); Z = 7                                    # hi-res canvas: (2Z+1)^2 tiles at 320 px
HR = Image.new("RGB", ((2 * Z + 1) * 320,) * 2); hd = ImageDraw.Draw(HR)
for a in range(-Z, Z + 1):
    for b in range(-Z, Z + 1):
        t = f"{CJ + a:03d}_{CI + b:03d}"
        if os.path.exists(f"tiles/{t}.jpg"):
            ox, oy = (b + Z) * 320, (a + Z) * 320; HR.paste(Image.open(f"tiles/{t}.jpg"), (ox, oy))
            for bx in allbox.get(t, []):
                hd.rectangle([ox + bx[0] * .32, oy + bx[1] * .32, ox + bx[2] * .32, oy + bx[3] * .32], outline=RED, width=2)
FULL = Image.composite(lit, dark, mask).convert("RGBA"); FULL.alpha_composite(dot); FULL = FULL.convert("RGB")
cx0, cy0 = NX / 2, NY / 2; cx1, cy1 = CI + 0.5, CJ + 0.5
w0 = NX; w1 = 3.2                                      # view width in tiles
N2 = 240
blk = sum(len(allbox.get(f"{CJ + a:03d}_{CI + b:03d}", [])) for a in (-1, 0, 1) for b in (-1, 0, 1))
for f in range(N2 + 90):
    u = min(1, f / N2); e = u * u * (3 - 2 * u)
    w = math.exp(math.log(w0) + (math.log(w1) - math.log(w0)) * e)
    cx = cx0 + (cx1 - cx0) * e; cy = cy0 + (cy1 - cy0) * e
    hv = w * MH / MW
    if w > 2 * Z + 1:
        box = [(cx - w / 2) * S, (cy - hv / 2) * S, (cx + w / 2) * S, (cy + hv / 2) * S]
        view = FULL.crop([int(v) for v in box]).resize((MW, MH), Image.LANCZOS)
    else:
        ox, oy = (CI - Z) , (CJ - Z)
        box = [(cx - w / 2 - ox) * 320, (cy - hv / 2 - oy) * 320, (cx + w / 2 - ox) * 320, (cy + hv / 2 - oy) * 320]
        view = HR.crop([int(v) for v in box]).resize((MW, MH), Image.LANCZOS)
    im = Image.new("RGB", (W, H), BG); im.paste(view, (MX, MY)); d = ImageDraw.Draw(im); header(d)
    if e >= 1:
        d.text((40, MY + MH + 22), "zoomed in: every red box was drawn by the model", font=F("ExtraBold", 34), fill=RED)
        d.text((40, H - 40), f"{NOUN} the model found, not a census · imagery: USDA NAIP", font=F("Regular", 18), fill=(90, 96, 108))
    else:
        footer(d, TOTAL, len(R), f"{MIN // 60}h {MIN % 60:02d}m")
    emit(im)
    if f == N2 + 89: im.save("out/preview_last.png")
p.stdin.close(); p.wait()
final.save("out/preview_map.png")
print("done", TOTAL)
