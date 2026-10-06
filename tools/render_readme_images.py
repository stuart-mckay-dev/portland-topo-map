"""render_readme_images.py -- Regenerate the README figures in docs/img/.

Not part of the print pipeline. Reads pipeline outputs from data/ and writes:

  docs/img/hero_hillshade.png       hillshade, coloured inside the print boundary
  docs/img/boundary_smoothing.png   raw city limits vs smoothed print outline
  docs/img/pilot_tiles_render.png   offscreen 3D render of the pilot STLs

Requires: numpy rasterio shapely matplotlib pyvista pillow
  python3 tools/render_readme_images.py [--data data] [--out docs/img]
"""
import argparse, glob, json, os, re
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from shapely.geometry import shape

TILE_W, TILE_H, GAP = 78.46, 90.0, 6.0   # pilot footprint, mm


def outline(ax, path, **kw):
    g = shape(json.load(open(path))["features"][0]["geometry"])
    for p in getattr(g, "geoms", [g]):
        ax.plot(*p.exterior.xy, **kw)
        for ring in p.interiors:
            ax.plot(*ring.xy, **kw)


def hillshade_figures(data, out):
    with rasterio.open(f"{data}/derived/dem_32610.tif") as r:
        a = r.read(1).astype(float); b = r.bounds
    a[a < -1000] = np.nan
    a = np.where(np.isnan(a), np.nanmin(a), a)
    with rasterio.open(f"{data}/derived/dem_masked.tif") as r:
        inside = r.read(1) != r.nodata
    ls = LightSource(azdeg=315, altdeg=35)
    rgb = ls.shade(a, cmap=plt.get_cmap("gist_earth"), vert_exag=4, dx=10, dy=10,
                   blend_mode="soft", vmin=-40, vmax=420)
    hs = ls.hillshade(a, vert_exag=4, dx=10, dy=10)
    grey = np.dstack([hs * 0.55 + 0.35] * 3 + [np.ones_like(hs)])
    ext = [b.left, b.right, b.bottom, b.top]
    smoothed = f"{data}/vectors/boundary_smoothed.geojson"
    raw = f"{data}/vectors/portland_city_limits.geojson"

    fig, ax = plt.subplots(figsize=(11, 9.5))
    ax.imshow(np.where(inside[..., None], rgb, grey), extent=ext)
    outline(ax, smoothed, color="#1b1b1b", lw=1.1)
    ax.set_axis_off(); fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(f"{out}/hero_hillshade.png", dpi=110); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(12, 6), dpi=130)
    views = [((514000, 524000, 5034000, 5046000), "West / SW fringe"),
             ((531000, 541000, 5032000, 5040000), "South-east staircase")]
    for ax, ((x0, x1, y0, y1), title) in zip(axs, views):
        ax.imshow(np.dstack([hs * 0.5 + 0.45] * 3), extent=ext)
        outline(ax, raw, color="#c0392b", lw=0.9)
        outline(ax, smoothed, color="#1f4e9c", lw=1.6)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_title(title); ax.set_xticks([]); ax.set_yticks([])
    axs[0].plot([], [], color="#c0392b", lw=0.9, label="raw city limits")
    axs[0].plot([], [], color="#1f4e9c", lw=1.6, label="smoothed (D=50, Chaikin x2, DP 10)")
    axs[0].legend(loc="lower left", fontsize=9)
    fig.tight_layout(); fig.savefig(f"{out}/boundary_smoothing.png"); plt.close(fig)


def tile_render(data, out):
    import pyvista as pv
    from PIL import Image, ImageChops
    p = pv.Plotter(off_screen=True, window_size=(2000, 1250))
    p.set_background("white")
    for f in sorted(glob.glob(f"{data}/tiles/pdx_pilot_*.stl")):
        if os.path.getsize(f) < 200_000:      # omitted slivers
            continue
        r, c = map(int, re.search(r"r(\d+)c(\d+)", f).groups())
        m = pv.read(f).decimate(0.6)
        m.translate(((c - 1) * (TILE_W + GAP), -(r - 1) * (TILE_H + GAP), 0), inplace=True)
        p.add_mesh(m, color="#e8e2d6", specular=0.15, ambient=0.15, diffuse=0.85)
    p.add_light(pv.Light(position=(-400, 400, 250), focal_point=(120, -90, 0), intensity=0.8))
    p.view_vector((0.15, -1, 0.75), viewup=(0, 0, 1)); p.reset_camera(); p.camera.zoom(1.45)
    path = f"{out}/pilot_tiles_render.png"
    p.screenshot(path)
    im = Image.open(path).convert("RGB")
    x0, y0, x1, y1 = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
    im.crop((max(0, x0 - 40), max(0, y0 - 40), min(im.width, x1 + 40),
             min(im.height, y1 + 40))).save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="docs/img")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    hillshade_figures(a.data, a.out)
    tile_render(a.data, a.out)
    print("wrote", sorted(os.listdir(a.out)))
