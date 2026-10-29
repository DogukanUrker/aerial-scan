# download NAIP 2022 quarter-quads over BBOX, cut a global 192m UTM grid into 320px jpgs, build a thumbnail mosaic
import json, os, sys, subprocess, numpy as np, requests, rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from PIL import Image
BBOX = tuple(float(v) for v in os.environ.get("BBOX", "-118.67,34.15,-118.35,34.33").split(","))   # lon/lat, default: san fernando valley
YEAR = os.environ.get("YEAR", "2022")
CELL = 192.0; PX = 320; THUMB = 40
COG = "cog"; TILES = "tiles"
os.makedirs(COG, exist_ok=True); os.makedirs(TILES, exist_ok=True)
x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:26911", *BBOX)
x0 = np.floor(x0 / CELL) * CELL; y1 = np.ceil(y1 / CELL) * CELL
NX = int(np.ceil((x1 - x0) / CELL)); NY = int(np.ceil((y1 - y0) / CELL))
json.dump({"bbox": BBOX, "x0": x0, "y1": y1, "cell": CELL, "nx": NX, "ny": NY}, open("grid.json", "w"))
print("grid", NX, "x", NY, "=", NX * NY, "cells", flush=True)
mosaic = np.zeros((NY * THUMB, NX * THUMB, 3), np.uint8)
done = np.zeros((NY, NX), bool)
feats = requests.post("https://planetarycomputer.microsoft.com/api/stac/v1/search", json={
    "collections": ["naip"], "bbox": BBOX, "datetime": f"{YEAR}-01-01T00:00:00Z/{YEAR}-12-31T23:59:59Z", "limit": 100}).json()["features"]
print(len(feats), "items", flush=True)
for n, f in enumerate(feats):
    href = f["assets"]["image"]["href"]; path = f"{COG}/{f['id']}.tif"
    tok = requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/naip").json()["token"]
    subprocess.run(["curl", "-s", "--retry", "5", "-o", path, f"{href}?{tok}"], check=True)
    cut = 0
    with rasterio.open(path) as r:
        assert r.crs.to_epsg() == 26911, r.crs
        L, B, R, T = r.bounds
        for j in range(NY):
            for i in range(NX):
                if done[j, i]: continue
                cx0 = x0 + i * CELL; cy1 = y1 - j * CELL
                if cx0 < L or cx0 + CELL > R or cy1 > T or cy1 - CELL < B: continue
                w = from_bounds(cx0, cy1 - CELL, cx0 + CELL, cy1, r.transform)
                a = np.moveaxis(r.read([1, 2, 3], window=w, out_shape=(3, PX, PX)), 0, -1)
                if (a.max(axis=2) == 0).mean() > 0.05: continue   # nodata edge, let another item take it
                im = Image.fromarray(a); im.save(f"{TILES}/{j:03d}_{i:03d}.jpg", quality=92)
                mosaic[j*THUMB:(j+1)*THUMB, i*THUMB:(i+1)*THUMB] = np.asarray(im.resize((THUMB, THUMB), Image.BOX))
                done[j, i] = True; cut += 1
    os.remove(path)
    print(f"[{n+1}/{len(feats)}] {f['id']} +{cut} tiles, total {done.sum()}/{NX*NY}", flush=True)
    Image.fromarray(mosaic).save("mosaic.jpg", quality=90)
np.save("done.npy", done)
print("FETCH DONE", done.sum(), flush=True)
