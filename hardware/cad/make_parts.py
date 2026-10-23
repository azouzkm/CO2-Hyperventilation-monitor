"""Team 6 - printed parts for the CO2 gas path, version 1 (22 Oct 2026).

Makes three STL files for PLA printing:
  flowcell_tray_v1.stl    open tray the MH-Z19C sits in; cable leaves through a notch
  flowcell_lid_v1.stl     flat lid with an inlet barb over the sensor's gas window and
                          an outlet barb at the far end; drops into a ledge in the tray
  barb_fit_coupon_v1.stl  five test barbs (4.8 to 6.4 mm), 1 to 5 dots, to choose the
                          barb that grips our oxygen tubing best

Version 1 uses the datasheet size (32.9 x 19.7 x 8.6 mm) and the bench photos, with
generous clearances, so it fits before anyone has measured. Nothing touches the gold
chamber: the datasheet says not to press on it. When the caliper numbers are in, change
the SENSOR block below and run again:

    python3 hardware/cad/make_parts.py          (needs numpy and scikit-image)

Method: each part is a signed-distance function (negative inside) sampled on a 0.25 mm
grid and meshed with marching cubes, which always gives a closed, printable surface.
"""
import os
import struct
import numpy as np
from skimage.measure import marching_cubes

HERE = os.path.dirname(os.path.abspath(__file__))
VOXEL = 0.25  # mm (flat faces come out exact; 0.25 keeps the files small)

# ---- SENSOR (estimates; replace with caliper measurements) --------------------------
BOARD_LEN = 37.5      # green board, end to end, including the connector tab
HOUSING_W = 19.7      # gold housing width (datasheet 19.7)
SENSOR_H = 8.6        # board + gold housing height (datasheet 8.6)
BOARD_TO_HOUSING = 9.7   # connector end of the board to the start of the gold housing
WINDOW_LEN = 8.3      # white filter (gas window) along the length, from the housing edge
PLUG_OUT = 6.0        # cable plug sticking out past the board end, plus wire bend

# ---- TUBING ----------------------------------------------------------------------------
BARB_RIDGE = 5.6      # barb ridge diameter: pick from the coupon (4.8/5.2/5.6/6.0/6.4)
BARB_BORE = 2.4

# ---- PRINT / FIT -----------------------------------------------------------------------
CLEAR = 1.5           # air gap around the sensor on every side
TOP_GAP = 1.5         # gas space above the gold housing (nothing presses on it)
FOAM = 1.5            # foam pad under the board
WALL, FLOOR = 2.4, 2.0
LID_T = 2.0           # lid thickness = ledge depth
REBATE = 1.2          # ledge width the lid rests on
FIT = 0.2             # lid clearance in its ledge, per side
NOTCH_W, NOTCH_D = 10.0, 10.0  # cable notch in the end wall, down to about plug height

CAV_L = CLEAR + PLUG_OUT + BOARD_LEN + CLEAR
CAV_W = HOUSING_W + 2 * CLEAR
CAV_H = FOAM + SENSOR_H + TOP_GAP
INLET_X = CLEAR + PLUG_OUT + BOARD_TO_HOUSING + WINDOW_LEN / 2   # over the gas window
OUTLET_X = CAV_L - 5.0


# ---- signed distance primitives (negative inside) --------------------------------------
def box(P, lo, hi):
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    h = [(b - a) / 2 for a, b in zip(lo, hi)]
    q = [np.abs(P[i] - c[i]) - h[i] for i in range(3)]
    outside = np.sqrt(sum(np.maximum(qi, 0) ** 2 for qi in q))
    inside = np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0)
    return outside + inside


def cyl(P, cx, cy, r, z0, z1):
    dr = np.hypot(P[0] - cx, P[1] - cy) - r
    dz = np.maximum(z0 - P[2], P[2] - z1)
    return np.sqrt(np.maximum(dr, 0) ** 2 + np.maximum(dz, 0) ** 2) + np.minimum(np.maximum(dr, dz), 0)


def frustum(P, cx, cy, r0, r1, z0, z1):
    """Cone section: radius r0 at z0 to r1 at z1 (approximate distance, exact surface)."""
    t = np.clip((P[2] - z0) / (z1 - z0), 0, 1)
    r = r0 + (r1 - r0) * t
    k = 1 / np.sqrt(1 + ((r1 - r0) / (z1 - z0)) ** 2)
    dr = (np.hypot(P[0] - cx, P[1] - cy) - r) * k
    dz = np.maximum(z0 - P[2], P[2] - z1)
    return np.sqrt(np.maximum(dr, 0) ** 2 + np.maximum(dz, 0) ** 2) + np.minimum(np.maximum(dr, dz), 0)


def union(*ds):
    out = ds[0]
    for d in ds[1:]:
        out = np.minimum(out, d)
    return out


def minus(a, b):
    return np.maximum(a, -b)


def barb(P, cx, cy, z0, ridge, bore):
    """Two-ridge hose barb standing on z0, hollow. Each ridge has a 45-degree chamfer
    underneath, so it prints upright without supports."""
    R = ridge / 2
    parts = [cyl(P, cx, cy, R - 0.8, z0 - 0.01, z0 + 6.6)]          # core
    for zr in (z0 + 2.0, z0 + 4.6):
        parts.append(frustum(P, cx, cy, R - 0.8, R, zr - 0.8, zr))   # chamfer
        parts.append(frustum(P, cx, cy, R, R - 0.8, zr, zr + 2.0))   # taper to the tip
    return union(*parts), cyl(P, cx, cy, bore / 2, -50, z0 + 50)


# ---- parts --------------------------------------------------------------------------------
def tray(P):
    Lo, Wo, Ho = CAV_L + 2 * WALL, CAV_W + 2 * WALL, FLOOR + CAV_H + LID_T   # lid sits on top of the cavity
    d = box(P, (0, 0, 0), (Lo, Wo, Ho))
    d = minus(d, box(P, (WALL, WALL, FLOOR), (WALL + CAV_L, WALL + CAV_W, Ho + 5)))
    d = minus(d, box(P, (WALL - REBATE, WALL - REBATE, Ho - LID_T),
                     (WALL + CAV_L + REBATE, WALL + CAV_W + REBATE, Ho + 5)))
    yc = Wo / 2
    d = minus(d, box(P, (-5, yc - NOTCH_W / 2, Ho - NOTCH_D), (WALL + 0.5, yc + NOTCH_W / 2, Ho + 5)))
    return d, (Lo, Wo, Ho)


def lid(P):
    Lp = CAV_L + 2 * REBATE - 2 * FIT
    Wp = CAV_W + 2 * REBATE - 2 * FIT
    off = REBATE - FIT                      # cavity coordinates -> lid coordinates
    yc = Wp / 2
    d = box(P, (0, 0, 0), (Lp, Wp, LID_T))
    bores = []
    for x in (INLET_X + off, OUTLET_X + off):
        d = union(d, cyl(P, x, yc, 4.5, LID_T - 0.01, LID_T + 1.5))
        b, hole = barb(P, x, yc, LID_T + 1.5, BARB_RIDGE, BARB_BORE)
        d = union(d, b)
        bores.append(hole)
    # one raised dot beside the inlet = "IN"
    d = union(d, cyl(P, INLET_X + off - 7.5, yc, 1.0, LID_T - 0.01, LID_T + 0.8))
    for hole in bores:
        d = minus(d, hole)
    return d, (Lp, Wp, LID_T + 1.5 + 6.6)


COUPON_SIZES = (4.8, 5.2, 5.6, 6.0, 6.4)


def coupon(P):
    pitch, T = 12.0, 2.4
    L, W = pitch * len(COUPON_SIZES), 14.0
    d = box(P, (0, 0, 0), (L, W, T))
    holes = []
    for i, D in enumerate(COUPON_SIZES):
        x = pitch * (i + 0.5)
        b, hole = barb(P, x, 5.0, T, D, 1.6)
        d = union(d, b)
        holes.append(hole)
        for k in range(i + 1):                       # 1..5 dots identify the size
            d = union(d, cyl(P, x - 0.9 * i + 1.8 * k, 11.6, 0.6, T - 0.01, T + 0.6))
    for hole in holes:
        d = minus(d, hole)
    return d, (L, W, T + 6.6)


# ---- meshing and STL -------------------------------------------------------------------------
def mesh(fn, voxel=VOXEL):
    _, (sx, sy, sz) = fn(np.zeros((3, 1, 1, 1)))
    lo = np.array([-1.0, -1.0, -1.0]) + voxel / 2      # half-voxel offset avoids planes on samples
    hi = np.array([sx + 1, sy + 1, sz + 1])
    axes = [np.arange(lo[i], hi[i], voxel) for i in range(3)]
    P = np.stack(np.meshgrid(*axes, indexing="ij")).astype(np.float32)
    d, _ = fn(P)
    verts, faces, _, _ = marching_cubes(-d, level=0.0, spacing=(voxel,) * 3)
    verts += lo
    tri = verts[faces]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
    if vol < 0:                                      # make normals point outwards
        faces = faces[:, ::-1]
        vol = -vol
    return verts, faces, vol


def check_closed(faces):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool(np.all(counts == 2))


def write_stl(path, verts, faces, name):
    tri = verts[faces].astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as f:
        f.write(name.encode()[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(faces)))
        f.write(rec.tobytes())


PARTS = {
    "flowcell_tray_v1": tray,
    "flowcell_lid_v1": lid,
    "barb_fit_coupon_v1": coupon,
}

if __name__ == "__main__":
    print("cavity %.1f x %.1f x %.1f mm (L x W x H); inlet barb %.1f mm from the cable end"
          % (CAV_L, CAV_W, CAV_H, INLET_X))
    for name, fn in PARTS.items():
        verts, faces, vol = mesh(fn)
        _, size = fn(np.zeros((3, 1, 1, 1)))
        path = os.path.join(HERE, name + ".stl")
        write_stl(path, verts, faces, "Team6 " + name)
        print("%-20s %5.1f x %5.1f x %5.1f mm  %6.2f cm3 PLA  %7d triangles  closed=%s"
              % (name, size[0], size[1], size[2], vol / 1000, len(faces), check_closed(faces)))
