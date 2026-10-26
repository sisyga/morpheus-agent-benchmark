"""3D visualization of the Atwell et al. (2015) C. elegans gonad reimplementation (Morpheus, 3D CPM).

Reads the lattice states that Morpheus wrote for one benchmark attempt and, for each time point:
  * builds the labelled 3D lattice (one label per cell),
  * writes it as VTK image data (<out>/vtk/atwell_<t>hph.vti; cell data "cell_id" and "colour"),
    which opens directly in ParaView,
  * extracts one smoothed surface per cell (vtkSurfaceNets3D) and renders it offscreen in the orientation
    of Atwell et al. Fig. 3 (orthographic view onto the plane of the U: distal arm on top, loop on the
    left, proximal arm with the sperm at the bottom right), with the colour code of the model's own
    Gnuplotter (= Atwell Fig. 3):
      gold = proliferative, green = meiotic, light blue = spermatocyte, blue = sperm, red = oocyte.
    The distal tip cell (DTC) is not a CPM cell in this model but an explicit global leader coordinate
    (dtc_x_um, dtc_y_um, dtc_z_um, logged in cell_counts.csv) that sits at the centre of the gonad's
    hemispherical end cap, so the germ cells fill the cap around it and would hide it. It is drawn as a
    small teal sphere (radius DTC_RADIUS, a drawing choice: the model gives the DTC no body) that starts
    at the logged coordinate and is moved along the DTC's direction of migration (taken from the logged
    trajectory) until it lies ahead of all germ cells in the tube, i.e. just ahead of the distal tip as in
    Atwell Fig. 3.
    Cells smaller than MARK_VOXELS voxels (in this run every sperm cell is a single voxel) would be
    invisible as surfaces, so they are additionally drawn as small spheres at their centroid.

Time points:
  * the initial lattice (18.5 hph) is rebuilt exactly from model.xml: <InitCellObjects mode="distance">
    with <Sphere> objects assigns each node inside any sphere to the nearest sphere centre, and the
    initial colours are taken from the first row block of cell_states.csv;
  * all later states come from the Morpheus checkpoints (<title><time>.xml.gz), whose <Nodes> list every
    voxel of every cell; colours are matched by cell id from cell_states.csv at the nearest logged time.

Usage:
  python atwell_3d.py <attempt_dir> <out_dir>
  (attempt_dir holds model.xml, cell_states.csv, cell_counts.csv and the *.xml.gz checkpoints)

Requires numpy, pandas, matplotlib, pyvista (>= 0.45, for contour_labels); offscreen rendering needs
OSMesa or EGL (e.g. apt install libosmesa6) when no display is available.
"""
import glob
import gzip
import os
import re
import sys
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import pyvista as pv

COLOURS = {1: ("#e6b400", "proliferative"), 2: ("#228b22", "meiotic"), 3: ("#87cefa", "spermatocyte"),
           4: ("#1f3fd6", "sperm"), 5: ("#d62020", "oocyte")}
DTC_COLOUR = ("#0f9b9b", "distal tip cell (DTC)")
DTC_RADIUS = 3.0
MARK_VOXELS = 8


def lattice_size(model):
    size = model.find(".//Lattice/Size").get("value")
    return tuple(int(float(v)) for v in size.split(","))


def initial_lattice(model, shape):
    """Reproduce <InitCellObjects mode="distance">: nodes inside a sphere go to the nearest centre."""
    lab = np.zeros(shape, np.int32)
    best = np.full(shape, np.inf)
    gx, gy, gz = np.meshgrid(*[np.arange(n) for n in shape], indexing="ij")
    cid = 0
    for obj in model.iter("InitCellObjects"):
        for sph in obj.iter("Sphere"):
            cid += 1
            c = [float(v) for v in sph.get("center").split(",")]
            r = float(sph.get("radius"))
            d2 = (gx - c[0]) ** 2 + (gy - c[1]) ** 2 + (gz - c[2]) ** 2
            m = (d2 <= r * r) & (d2 < best)
            lab[m] = cid
            best[m] = d2[m]
    return lab


def checkpoint_lattice(path, shape, cell_type="germ"):
    txt = gzip.open(path, "rt").read()
    pop = txt[txt.index(f'<Population type="{cell_type}"'):]
    pop = pop[:pop.index("</Population>")]
    lab = np.zeros(shape, np.int32)
    for cell in re.finditer(r'<Cell id="(\d+)"[^>]*>(.*?)</Cell>', pop, re.S):
        nodes = re.search(r"<Nodes>(.*?)</Nodes>", cell.group(2), re.S)
        if not nodes or not nodes.group(1).strip():
            continue
        a = np.array([list(map(int, s.split(","))) for s in nodes.group(1).strip().strip(";").split(";")])
        lab[a[:, 0], a[:, 1], a[:, 2]] = int(cell.group(1))
    return lab


def colour_map(states, t):
    """Colour per cell id at the logged time nearest to t; cells missing there (born or removed in
    between) take their colour from the closest logged time at which they exist."""
    times = states.time_hph.unique()
    tn = times[np.abs(times - t).argmin()]
    s = states.assign(dt=(states.time_hph - t).abs()).sort_values("dt").drop_duplicates("cell.id")
    cmap = dict(zip(s["cell.id"].astype(int), s.colour.astype(int)))
    cur = states[states.time_hph == tn]
    cmap.update(zip(cur["cell.id"].astype(int), cur.colour.astype(int)))
    return cmap, tn


def to_image(lab, colours):
    """Voxel image (cell data) for the .vti export, and point-sampled labels for surface extraction."""
    col = np.vectorize(lambda i: colours.get(int(i), 0) if i else 0, otypes=[np.int32])(lab)
    vox = pv.ImageData(dimensions=np.array(lab.shape) + 1, spacing=(1, 1, 1), origin=(-0.5, -0.5, -0.5))
    vox.cell_data["cell_id"] = lab.ravel(order="F")
    vox.cell_data["colour"] = col.ravel(order="F")
    pts = pv.ImageData(dimensions=lab.shape, spacing=(1, 1, 1))
    pts.point_data["cell_id"] = lab.ravel(order="F")
    return vox, pts


def cell_surfaces(pts, colours):
    surf = pts.contour_labels(boundary_style="all", scalars="cell_id", smoothing=True,
                              smoothing_iterations=20, output_mesh_type="triangles")
    bl = surf.cell_data["boundary_labels"]
    # colour each polygon by the cell on its first side (background on the other side for the hull)
    owner = np.where(bl[:, 0] > 0, bl[:, 0], bl[:, 1]).astype(int)
    surf.cell_data["colour"] = np.array([colours.get(i, 0) for i in owner])
    return surf


def small_cell_markers(lab, colours):
    ids, counts = np.unique(lab[lab > 0], return_counts=True)
    small = ids[counts < MARK_VOXELS]
    if not len(small):
        return None
    idx = np.argwhere(np.isin(lab, small))
    owner = lab[tuple(idx.T)]
    centres = np.array([idx[owner == i].mean(0) for i in small])
    pts = pv.PolyData(centres)
    pts.point_data["colour"] = np.array([colours.get(int(i), 0) for i in small])
    return pts.glyph(geom=pv.Sphere(radius=1.1), scale=False, orient=False)


def dtc_position(counts, t, lab):
    """Logged DTC coordinate at t, pushed forward along its last direction of motion until a sphere of
    DTC_RADIUS lies ahead of all germ cells in the tube."""
    xyz = counts[["dtc_x_um", "dtc_y_um", "dtc_z_um"]].to_numpy()
    i = int((counts.time_hph - t).abs().argmin())
    step = np.diff(xyz[:i + 1], axis=0)
    moving = np.flatnonzero(np.linalg.norm(step, axis=1) > 1e-6)
    d = step[moving[-1]] if len(moving) else np.array([1.0, 0, 0])
    d = d / np.linalg.norm(d)
    # germ voxels inside the gonad tube around the line through the DTC (the rachis can leave the axis
    # itself empty); put the DTC just beyond the foremost of them
    rel = np.argwhere(lab > 0) - xyz[i]
    along = rel @ d
    lateral = np.linalg.norm(rel - np.outer(along, d), axis=1)
    ahead = along[lateral <= counts.gonad_radius_um.iloc[i]]
    shift = max(0.0, ahead.max() + DTC_RADIUS + 0.5) if len(ahead) else 0.0
    c = xyz[i] + shift * d
    return c, DTC_RADIUS


def render(surf, path, bounds, markers=None, dtc=None, window=(2000, 560)):
    p = pv.Plotter(off_screen=True, window_size=window)
    p.set_background("white")
    rgb = np.array([matplotlib.colors.to_rgb(COLOURS.get(c, ("#cccccc", ""))[0]) for c in surf.cell_data["colour"]])
    surf.cell_data["rgb"] = (rgb * 255).astype(np.uint8)
    p.add_mesh(surf, scalars="rgb", rgb=True, smooth_shading=False, specular=0.25, ambient=0.25,
               show_edges=False)
    if markers is not None:
        mrgb = np.array([matplotlib.colors.to_rgb(COLOURS.get(c, ("#cccccc", ""))[0]) for c in markers.point_data["colour"]])
        markers.point_data["rgb"] = (mrgb * 255).astype(np.uint8)
        p.add_mesh(markers, scalars="rgb", rgb=True, specular=0.25, ambient=0.25)
    if dtc is not None:
        p.add_mesh(pv.Sphere(radius=dtc[1], center=dtc[0], theta_resolution=40, phi_resolution=40),
                   color=DTC_COLOUR[0], specular=0.25, ambient=0.25)
    # Atwell Fig. 3 orientation: look onto the x-y plane of the U from -z (orthographic), y up, so that
    # the loop (high x) is on the left and the distal tip and the proximal end (low x) are on the right
    x0, x1, y0, y1, z0, z1 = bounds
    fp = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    p.camera.focal_point = fp
    p.camera.position = (fp[0], fp[1], fp[2] - 400)
    p.camera.up = (0, 1, 0)
    p.enable_parallel_projection()
    p.camera.parallel_scale = max((y1 - y0) / 2, (x1 - x0) / 2 * window[1] / window[0]) * 1.03
    p.remove_all_lights()
    p.add_light(pv.Light(position=(fp[0] + 60, fp[1] + 120, fp[2] - 300), focal_point=fp, intensity=0.9))
    p.add_light(pv.Light(light_type="headlight", intensity=0.45))
    p.add_mesh(pv.Box(bounds=bounds).outline(), color="white", opacity=0)  # fixes the framing
    img = p.screenshot(None, return_img=True)
    p.close()
    plt.imsave(path, img)


def main(attempt, out):
    os.makedirs(f"{out}/vtk", exist_ok=True)
    os.makedirs(f"{out}/png", exist_ok=True)
    model = ET.parse(f"{attempt}/model.xml").getroot()
    shape = lattice_size(model)
    states = pd.read_csv(f"{attempt}/cell_states.csv", sep="\t")
    counts = pd.read_csv(f"{attempt}/cell_counts.csv")
    t0 = float(states.time_hph.min())
    frames = [(t0, initial_lattice(model, shape))]
    for f in sorted(glob.glob(f"{attempt}/*.xml.gz")):
        t = float(re.search(r"([0-9.]+)\.xml\.gz$", f).group(1))
        frames.append((t, checkpoint_lattice(f, shape)))
    # common bounds over all frames so every view uses the same camera
    occ = np.any([lab > 0 for _, lab in frames], axis=0)
    idx = np.argwhere(occ)
    dtcs = [dtc_position(counts, t, lab) for t, lab in frames]
    lo = np.minimum(idx.min(0), np.min([c - r for c, r in dtcs], 0)) - 2
    hi = np.maximum(idx.max(0), np.max([c + r for c, r in dtcs], 0)) + 2
    bounds = (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    rows = []
    for (t, lab), dtc in zip(frames, dtcs):
        colours, tn = colour_map(states, t)
        vox, pts = to_image(lab, colours)
        tag = f"{t:06.2f}"
        vox.save(f"{out}/vtk/atwell_{tag}hph.vti")
        n = len(np.unique(lab)) - 1
        png = f"{out}/png/atwell_3d_{tag}hph.png"
        render(cell_surfaces(pts, colours), png, bounds, small_cell_markers(lab, colours), dtc)
        rows.append((f"{t:.1f} hph", n, png))
        print(f"{t:.2f} hph: {n} cells, colours from cell_states.csv at {tn} hph, DTC drawn at "
              f"{np.round(dtc[0], 1)} -> {png}")
    # panel figure like Atwell Fig. 3: one row per time point, same scale throughout
    ims = [plt.imread(p) for _, _, p in rows]
    h, w = ims[0].shape[:2]
    fig, axes = plt.subplots(len(rows), 1, figsize=(10, 10 * h / w * len(rows) * 1.12 + 0.6), dpi=150)
    for (title, n, _), im, ax in zip(rows, ims, np.atleast_1d(axes)):
        ax.imshow(im); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_ylabel(f"{title}\n{n} cells", rotation=0, ha="right", va="center", fontsize=11)
    fig.legend(handles=[Patch(color=c, label=l) for c, l in [*COLOURS.values(), DTC_COLOUR]],
               loc="lower center", ncol=6, frameon=False, fontsize=11)
    fig.subplots_adjust(left=0.13, right=0.99, top=0.99, bottom=0.07, hspace=0.08)
    fig.savefig(f"{out}/atwell_3d_panel.png", facecolor="white")
    print("panel ->", f"{out}/atwell_3d_panel.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
