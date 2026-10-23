"""Team 6 - printed parts as STEP files (exact solid CAD), version 1 (22 Oct 2026).

Writes the three v1 parts from make_parts.py as STEP files (AP214, millimetres), for print
services and CAD programs that ask for STEP instead of STL:
  flowcell_tray_v1.step  flowcell_lid_v1.step  barb_fit_coupon_v1.step

Same design as the STL files: the sizes are read from make_parts.py, and before writing
anything this script checks its solids against make_parts.py's shapes at thousands of points.
After changing the numbers in make_parts.py, run both:
    python3 hardware/cad/make_parts.py      (STL, needs numpy and scikit-image)
    python3 hardware/cad/make_step.py       (STEP, needs numpy only)

The STEP solids are exact (flat faces, cylinders and cones, not triangles). No CAD library is
needed because the parts are simple: the tray is all flat faces, and the lid and coupon are
flat plates carrying barbs, bosses and dots that are shapes of revolution about vertical axes.
Each round face is stored as two half faces, which every CAD importer accepts.
"""
import math
import os
import time

import sys
import types

import numpy as np

try:                                   # make_parts.py imports scikit-image for its STL meshing,
    import skimage.measure             # which this script does not use: stand in for it if absent
except ImportError:
    sys.modules.setdefault("skimage", types.ModuleType("skimage"))
    sys.modules["skimage.measure"] = types.SimpleNamespace(marching_cubes=None)

import make_parts as mp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 1e-6

# Sizes inside make_parts.lid(), barb() and coupon() that are written there as plain numbers.
# The check against make_parts.py at the end fails if the two scripts ever disagree.
BOSS_R, BOSS_H = 4.5, 1.5          # lid: boss under each barb
DOT_R, DOT_H, DOT_FROM_INLET = 1.0, 0.8, 7.5   # lid: raised dot beside the inlet ("IN")
BARB_H, BARB_STEP = 6.6, 0.8       # barb: height above its base; ridge minus core radius
RIDGES = (2.0, 4.6)                # barb: ridge heights above its base
TAPER = 2.0                        # barb: length of the taper above each ridge
COUPON_PITCH, COUPON_T, COUPON_W = 12.0, 2.4, 14.0
COUPON_BARB_Y, COUPON_BORE = 5.0, 1.6
COUPON_DOT_Y, COUPON_DOT_R, COUPON_DOT_H, COUPON_DOT_PITCH = 11.6, 0.6, 0.6, 1.8


# ---- boundary representation -----------------------------------------------------------
def key(p):
    return tuple(round(float(c), 6) + 0.0 for c in p)


class Brep:
    """Faces, edges and vertices of one solid. Every face is listed with its outward normal;
    each loop runs counterclockwise around that normal (holes clockwise)."""

    def __init__(self, name):
        self.name = name
        self.points = {}      # vertex key -> point
        self.edges = {}       # edge key -> (start vertex key, end vertex key, curve)
        self.faces = []       # (surface, same_sense, outer loop, [inner loops])
        self.solids = []      # simple description used for the check against make_parts.py
        self.holes = []

    def _v(self, p):
        k = key(p)
        self.points.setdefault(k, tuple(float(c) for c in p))
        return k

    def line(self, p, q):
        a, b = self._v(p), self._v(q)
        lo, hi = (a, b) if a < b else (b, a)
        k = ("L", lo, hi)
        self.edges.setdefault(k, (lo, hi, ("LINE",)))
        return (k, a == lo)

    def arc(self, c, r, half, forward=True):
        """Half circle about +z: 'U' from angle 0 to 180 deg, 'D' from 180 to 360 deg."""
        cx, cy, z = c
        p0, p180 = (cx + r, cy, z), (cx - r, cy, z)
        s, e = (p0, p180) if half == "U" else (p180, p0)
        k = ("C", key(c), round(r, 6), half)
        self.edges.setdefault(k, (self._v(s), self._v(e), ("CIRCLE", tuple(c), r)))
        return (k, forward)

    def circle_ccw(self, c, r):
        return [self.arc(c, r, "U", True), self.arc(c, r, "D", True)]

    def circle_cw(self, c, r):
        return [self.arc(c, r, "D", False), self.arc(c, r, "U", False)]

    def polygon(self, pts):
        return [self.line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]

    def face(self, surface, outer, inner=(), same_sense=True):
        self.faces.append((surface, same_sense, outer, list(inner)))

    def ends(self, oriented):
        k, forward = oriented
        s, e, _ = self.edges[k]
        return (s, e) if forward else (e, s)

    def check(self):
        """Closed loops, and every edge used exactly twice, once each way: a closed solid."""
        use = {}
        loops = 0
        for _, _, outer, inner in self.faces:
            for loop in [outer] + inner:
                loops += 1
                for i, oe in enumerate(loop):
                    if self.ends(oe)[1] != self.ends(loop[(i + 1) % len(loop)])[0]:
                        raise AssertionError("%s: open loop at %s" % (self.name, self.ends(oe)))
                    use.setdefault(oe[0], []).append(oe[1])
        for k, dirs in use.items():
            if sorted(dirs) != [False, True]:
                raise AssertionError("%s: edge %s used %s" % (self.name, k, dirs))
        if len(use) != len(self.edges):
            raise AssertionError("%s: unused edges" % self.name)
        v, e, f = len(self.points), len(self.edges), len(self.faces)
        genus = (2 - (v - e + f - (loops - f))) // 2     # Euler-Poincare, one shell
        return v, e, f, genus


def plane(origin, normal, ref):
    return ("PLANE", tuple(origin), tuple(normal), tuple(ref))


# ---- building blocks -----------------------------------------------------------------------
def plate(B, L, W, T, top_holes, bottom_holes):
    """Box (0,0,0)-(L,W,T). top_holes: circles (cx, cy, r) where features stand on the top
    face; bottom_holes: circles where bores leave through the bottom face."""
    B.solids.append(("box", (0, 0, 0), (L, W, T)))
    B.face(plane((0, 0, 0), (0, 0, -1), (1, 0, 0)),
           B.polygon([(0, 0, 0), (0, W, 0), (L, W, 0), (L, 0, 0)]),
           [B.circle_ccw((cx, cy, 0), r) for cx, cy, r in bottom_holes])
    B.face(plane((0, 0, T), (0, 0, 1), (1, 0, 0)),
           B.polygon([(0, 0, T), (L, 0, T), (L, W, T), (0, W, T)]),
           [B.circle_cw((cx, cy, T), r) for cx, cy, r in top_holes])
    B.face(plane((0, 0, 0), (0, -1, 0), (1, 0, 0)), B.polygon([(0, 0, 0), (L, 0, 0), (L, 0, T), (0, 0, T)]))
    B.face(plane((L, 0, 0), (1, 0, 0), (0, 1, 0)), B.polygon([(L, 0, 0), (L, W, 0), (L, W, T), (L, 0, T)]))
    B.face(plane((0, W, 0), (0, 1, 0), (-1, 0, 0)), B.polygon([(L, W, 0), (0, W, 0), (0, W, T), (L, W, T)]))
    B.face(plane((0, 0, 0), (-1, 0, 0), (0, -1, 0)), B.polygon([(0, W, 0), (0, 0, 0), (0, 0, T), (0, W, T)]))


def side_loop(B, cx, cy, ra, za, rb, zb, half):
    """Half of a cylinder or cone between (ra, za) and (rb, zb), seen from outside."""
    if half == "U":
        return [B.arc((cx, cy, za), ra, "U", True), B.line((cx - ra, cy, za), (cx - rb, cy, zb)),
                B.arc((cx, cy, zb), rb, "U", False), B.line((cx + rb, cy, zb), (cx + ra, cy, za))]
    return [B.arc((cx, cy, za), ra, "D", True), B.line((cx + ra, cy, za), (cx + rb, cy, zb)),
            B.arc((cx, cy, zb), rb, "D", False), B.line((cx - rb, cy, zb), (cx - ra, cy, za))]


def bore_loop(B, cx, cy, r, z0, z1, half):
    """Half of a through hole, seen from inside the hole."""
    if half == "U":
        return [B.arc((cx, cy, z0), r, "U", False), B.line((cx + r, cy, z0), (cx + r, cy, z1)),
                B.arc((cx, cy, z1), r, "U", True), B.line((cx - r, cy, z1), (cx - r, cy, z0))]
    return [B.arc((cx, cy, z0), r, "D", False), B.line((cx - r, cy, z0), (cx - r, cy, z1)),
            B.arc((cx, cy, z1), r, "D", True), B.line((cx + r, cy, z1), (cx + r, cy, z0))]


def revolve(B, cx, cy, profile, bore=None):
    """Shape of revolution about the vertical axis through (cx, cy). profile: [(r, z), ...]
    from the base circle (left open as a hole in the face it stands on) up the outside to the
    top. Vertical steps become cylinders, slanted steps cones, horizontal steps flat rings
    facing up; a profile ending at r = 0 has a flat top. With bore = radius, the profile ends
    at (bore, top) and a hole of that radius runs down to z = 0."""
    B.solids.append(("rev", cx, cy, [p for p in profile if p[0] > (bore or 0) + TOL]))
    for (ra, za), (rb, zb) in zip(profile, profile[1:]):
        if abs(za - zb) < TOL:
            assert rb < ra, "only upward-facing steps are supported"
            B.face(plane((cx, cy, za), (0, 0, 1), (1, 0, 0)), B.circle_ccw((cx, cy, za), ra),
                   [B.circle_cw((cx, cy, za), rb)] if rb > TOL else [])
            continue
        assert zb > za
        if abs(ra - rb) < TOL:
            surf = ("CYL", (cx, cy, za), ra)
        elif rb > ra:
            surf = ("CONE", (cx, cy, za), 1, ra, math.atan((rb - ra) / (zb - za)))
        else:
            surf = ("CONE", (cx, cy, zb), -1, rb, math.atan((ra - rb) / (zb - za)))
        for half in ("U", "D"):
            B.face(surf, side_loop(B, cx, cy, ra, za, rb, zb, half))
    if bore:
        z1 = profile[-1][1]
        B.holes.append((cx, cy, bore))
        for half in ("U", "D"):
            B.face(("CYL", (cx, cy, 0.0), bore), bore_loop(B, cx, cy, bore, 0.0, z1, half), same_sense=False)


def barb_profile(ridge, z0):
    """Outside of make_parts.barb() standing on z0: core, then two ridges, each with a
    45-degree chamfer below and a taper above; the second chamfer cuts into the first taper."""
    R = ridge / 2
    rc = R - BARB_STEP
    zr1, zr2 = z0 + RIDGES[0], z0 + RIDGES[1]
    k = BARB_STEP / TAPER                      # taper slope (radius per mm of height)
    zg = (zr2 + k * zr1) / (1 + k)             # first taper meets second chamfer
    rg = R - k * (zg - zr1)
    return [(rc, z0), (rc, zr1 - BARB_STEP), (R, zr1), (rg, zg), (R, zr2), (rc, z0 + BARB_H)]


# ---- the three parts -------------------------------------------------------------------------
def lid():
    Lp = mp.CAV_L + 2 * mp.REBATE - 2 * mp.FIT
    Wp = mp.CAV_W + 2 * mp.REBATE - 2 * mp.FIT
    off = mp.REBATE - mp.FIT
    yc, T, rb = Wp / 2, mp.LID_T, mp.BARB_BORE / 2
    xs = [mp.INLET_X + off, mp.OUTLET_X + off]
    xd = mp.INLET_X + off - DOT_FROM_INLET
    B = Brep("flowcell_lid_v1")
    plate(B, Lp, Wp, T, [(x, yc, BOSS_R) for x in xs] + [(xd, yc, DOT_R)], [(x, yc, rb) for x in xs])
    for x in xs:
        z0 = T + BOSS_H
        revolve(B, x, yc, [(BOSS_R, T)] + [(BOSS_R, z0)] + barb_profile(mp.BARB_RIDGE, z0)
                + [(rb, z0 + BARB_H)], bore=rb)
    revolve(B, xd, yc, [(DOT_R, T), (DOT_R, T + DOT_H), (0.0, T + DOT_H)])
    return B, mp.lid


def coupon():
    T, rb = COUPON_T, COUPON_BORE / 2
    L = COUPON_PITCH * len(mp.COUPON_SIZES)
    barbs = [(COUPON_PITCH * (i + 0.5), COUPON_BARB_Y, D) for i, D in enumerate(mp.COUPON_SIZES)]
    dots = [(x - COUPON_DOT_PITCH / 2 * i + COUPON_DOT_PITCH * k, COUPON_DOT_Y)
            for i, (x, _, _) in enumerate(barbs) for k in range(i + 1)]
    B = Brep("barb_fit_coupon_v1")
    plate(B, L, COUPON_W, T,
          [(x, y, D / 2 - BARB_STEP) for x, y, D in barbs] + [(x, y, COUPON_DOT_R) for x, y in dots],
          [(x, y, rb) for x, y, _ in barbs])
    for x, y, D in barbs:
        revolve(B, x, y, barb_profile(D, T) + [(rb, T + BARB_H)], bore=rb)
    for x, y in dots:
        revolve(B, x, y, [(COUPON_DOT_R, T), (COUPON_DOT_R, T + COUPON_DOT_H), (0.0, T + COUPON_DOT_H)])
    return B, mp.coupon


UV = {(0, 1): (1, 2), (0, -1): (2, 1), (1, 1): (2, 0), (1, -1): (0, 2), (2, 1): (0, 1), (2, -1): (1, 0)}


def tray():
    """The tray is all flat faces at right angles: split space on every plane its boxes use,
    ask make_parts.tray() which cells are solid, and keep the faces between solid and empty."""
    Lo, Wo = mp.CAV_L + 2 * mp.WALL, mp.CAV_W + 2 * mp.WALL
    Ho = mp.FLOOR + mp.CAV_H + mp.LID_T
    W, R, yc = mp.WALL, mp.REBATE, Wo / 2
    cand = ([0, W - R, W, W + mp.CAV_L, W + mp.CAV_L + R, Lo],
            [0, W - R, W, yc - mp.NOTCH_W / 2, yc + mp.NOTCH_W / 2, W + mp.CAV_W, W + mp.CAV_W + R, Wo],
            [0, mp.FLOOR, Ho - mp.NOTCH_D, Ho - mp.LID_T, Ho])
    g = [sorted({round(v, 9) for v in c if 0 <= v <= hi}) for c, hi in zip(cand, (Lo, Wo, Ho))]
    mid = [np.array([(a + b) / 2 for a, b in zip(ax, ax[1:])]) for ax in g]
    P = np.stack(np.meshgrid(*mid, indexing="ij"))
    solid = mp.tray(P)[0] < 0
    for dx in (-0.3, 0.3):                      # every cell must be all solid or all empty
        for dy in (-0.3, 0.3):
            for dz in (-0.3, 0.3):
                Q = np.stack(np.meshgrid(*[m + d * np.diff(ax) for m, ax, d in zip(mid, g, (dx, dy, dz))],
                                         indexing="ij"))
                assert np.array_equal(mp.tray(Q)[0] < 0, solid), "tray: a box plane is missing"
    n = solid.shape
    groups = {}
    for a in range(3):
        for i in range(n[a] + 1):
            for j in range(n[(a + 1) % 3]):
                for k in range(n[(a + 2) % 3]):
                    idx = [0, 0, 0]
                    idx[(a + 1) % 3], idx[(a + 2) % 3] = j, k
                    idx[a] = i - 1
                    before = i > 0 and solid[tuple(idx)]
                    idx[a] = i
                    after = i < n[a] and solid[tuple(idx)]
                    if before != after:
                        cell = {(a + 1) % 3: j, (a + 2) % 3: k}
                        groups.setdefault((a, i, 1 if before else -1), []).append(cell)
    B = Brep("flowcell_tray_v1")
    B.solids.append(("faces",))
    cell = [np.diff(ax) for ax in g]
    B.exact_volume = float(np.sum(solid * np.einsum("i,j,k->ijk", *cell)))
    loops3d = []
    for (a, i, s), cells in groups.items():
        u, v = UV[(a, s)]
        edges = {}
        for c in cells:
            u0, v0 = c[u], c[v]
            sq = [(u0, v0), (u0 + 1, v0), (u0 + 1, v0 + 1), (u0, v0 + 1)]
            for p, q in zip(sq, sq[1:] + sq[:1]):
                if (q, p) in edges:
                    del edges[(q, p)]
                else:
                    edges[(p, q)] = True
        nxt = {}
        for p, q in edges:
            assert p not in nxt, "tray: two faces touch at a point"
            nxt[p] = q
        while nxt:
            start = next(iter(nxt))
            loop, p = [start], nxt.pop(start)
            while p != start:
                loop.append(p)
                p = nxt.pop(p)
            m = len(loop)                         # drop corners on a straight run
            loop = [p for j, p in enumerate(loop)
                    if not (loop[j - 1][0] == p[0] == loop[(j + 1) % m][0]
                            or loop[j - 1][1] == p[1] == loop[(j + 1) % m][1])]
            area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(loop, loop[1:] + loop[:1]))
            assert area > 0, "tray: a face with a hole (not expected)"
            pts = []
            for pu, pv in loop:
                xyz = [0.0, 0.0, 0.0]
                xyz[a], xyz[u], xyz[v] = g[a][i], g[u][pu], g[v][pv]
                pts.append(tuple(xyz))
            normal = [0, 0, 0]
            normal[a] = s
            ref = [0, 0, 0]
            ref[u] = 1
            loops3d.append((pts, tuple(normal), tuple(ref)))
    corners = {key(p) for pts, _, _ in loops3d for p in pts}
    for pts, normal, ref in loops3d:            # split edges where another face has a corner
        full = []
        for p, q in zip(pts, pts[1:] + pts[:1]):
            full.append(p)
            ax = [d for d in range(3) if abs(p[d] - q[d]) > TOL][0]
            between = [c for c in corners
                       if all(abs(c[d] - p[d]) < TOL for d in range(3) if d != ax)
                       and min(p[ax], q[ax]) + TOL < c[ax] < max(p[ax], q[ax]) - TOL]
            full += sorted(between, key=lambda c: abs(c[ax] - p[ax]))
        B.face(plane(pts[0], normal, ref), B.polygon(full))
    return B, mp.tray


# ---- check against make_parts.py ------------------------------------------------------------
def in_polygon(x, y, pts):
    res = np.zeros(x.shape, bool)
    for (x1, y1, _), (x2, y2, _) in zip(pts, pts[1:] + pts[:1]):
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        res ^= ((y1 > y) != (y2 > y)) & (x < xi)
    return res


def inside(B, P):
    """Point-in-solid: for the lid and coupon from the simple description kept while building;
    for the tray by counting how many of its flat faces a vertical ray from the point crosses."""
    x, y, z = P
    res = np.zeros(x.shape, bool)
    for s in B.solids:
        if s[0] == "faces":
            crossings = np.zeros(x.shape, int)
            for surf, _, outer, inner in B.faces:
                if surf[0] == "PLANE" and abs(surf[2][2]) > 0.5:
                    hit = np.zeros(x.shape, bool)
                    for lp in [outer] + inner:
                        hit ^= in_polygon(x, y, [B.points[B.ends(oe)[0]] for oe in lp])
                    crossings += hit & (surf[1][2] > z)
            res |= crossings % 2 == 1
        elif s[0] == "box":
            lo, hi = s[1], s[2]
            res |= (x > lo[0]) & (x < hi[0]) & (y > lo[1]) & (y < hi[1]) & (z > lo[2]) & (z < hi[2])
        elif s[0] == "rev":
            _, cx, cy, prof = s
            r = np.hypot(x - cx, y - cy)
            for (ra, za), (rb, zb) in zip(prof, prof[1:]):
                if zb - za > TOL:
                    t = (z - za) / (zb - za)
                    res |= (t > 0) & (t < 1) & (r < ra + (rb - ra) * t)
    for cx, cy, rr in B.holes:
        res &= np.hypot(x - cx, y - cy) > rr
    return res


def compare(B, sdf, n=40000, seed=6):
    _, size = sdf(np.zeros((3, 1, 1, 1)))
    rng = np.random.default_rng(seed)
    P = (rng.random((3, n)) * (np.array(size)[:, None] + 2) - 1).reshape(3, n, 1, 1)
    d = sdf(P)[0].ravel()
    ok = np.abs(d) > 0.01                       # skip points right on the surface
    mine = inside(B, P.reshape(3, n))
    return int(ok.sum()), int(np.sum(mine[ok] != (d[ok] < 0)))


def volume(B):
    """Exact volume from the simple description (cross-checks the STEP reader)."""
    if hasattr(B, "exact_volume"):
        return B.exact_volume
    v = 0.0
    for s in B.solids:
        if s[0] == "box":
            v += np.prod(np.subtract(s[2], s[1]))
        elif s[0] == "rev":
            for (ra, za), (rb, zb) in zip(s[3], s[3][1:]):
                v += math.pi * (zb - za) * (ra * ra + ra * rb + rb * rb) / 3
    for cx, cy, rr in B.holes:
        top = max(z for s in B.solids if s[0] == "rev" and (s[1], s[2]) == (cx, cy) for _, z in s[3])
        v -= math.pi * rr * rr * top
    return v


# ---- STEP (ISO 10303-21, AP214) -----------------------------------------------------------
def num(x):
    x = round(float(x), 9) + 0.0
    s = repr(x)
    if "e" in s:
        m, e = s.split("e")
        return (m if "." in m else m + ".") + "E" + str(int(e))
    return s[:-1] if s.endswith(".0") else s


def write_step(B, path, title):
    out = []

    def ent(text):
        out.append("#%d = %s;" % (len(out) + 1, text))
        return "#%d" % len(out)

    def pt(p):
        return ent("CARTESIAN_POINT('',(%s,%s,%s))" % tuple(num(c) for c in p))

    def dr(d):
        n = math.sqrt(sum(c * c for c in d))
        return ent("DIRECTION('',(%s,%s,%s))" % tuple(num(c / n) for c in d))

    def ax(o, z, x):
        return ent("AXIS2_PLACEMENT_3D('',%s,%s,%s)" % (pt(o), dr(z), dr(x)))

    vid = {k: ent("VERTEX_POINT('',%s)" % pt(p)) for k, p in sorted(B.points.items())}
    eid = {}
    for k, (s, e, curve) in B.edges.items():
        if curve[0] == "LINE":
            a, b = B.points[s], B.points[e]
            d = [q - p for p, q in zip(a, b)]
            c = ent("LINE('',%s,%s)" % (pt(a), ent("VECTOR('',%s,1.)" % dr(d))))
        else:
            c = ent("CIRCLE('',%s,%s)" % (ax(curve[1], (0, 0, 1), (1, 0, 0)), num(curve[2])))
        eid[k] = ent("EDGE_CURVE('',%s,%s,%s,.T.)" % (vid[s], vid[e], c))
    oe = {}

    def loop(lp):
        refs = []
        for k, fwd in lp:
            if (k, fwd) not in oe:
                oe[(k, fwd)] = ent("ORIENTED_EDGE('',*,*,%s,%s)" % (eid[k], ".T." if fwd else ".F."))
            refs.append(oe[(k, fwd)])
        return ent("EDGE_LOOP('',(%s))" % ",".join(refs))

    faces = []
    for surf, same, outer, inner in B.faces:
        if surf[0] == "PLANE":
            s = ent("PLANE('',%s)" % ax(surf[1], surf[2], surf[3]))
        elif surf[0] == "CYL":
            s = ent("CYLINDRICAL_SURFACE('',%s,%s)" % (ax(surf[1], (0, 0, 1), (1, 0, 0)), num(surf[2])))
        else:
            s = ent("CONICAL_SURFACE('',%s,%s,%s)" % (ax(surf[1], (0, 0, surf[2]), (1, 0, 0)),
                                                       num(surf[3]), num(surf[4])))
        bounds = [ent("FACE_OUTER_BOUND('',%s,.T.)" % loop(outer))]
        bounds += [ent("FACE_BOUND('',%s,.T.)" % loop(lp)) for lp in inner]
        faces.append(ent("ADVANCED_FACE('',(%s),%s,%s)" % (",".join(bounds), s, ".T." if same else ".F.")))
    shell = ent("CLOSED_SHELL('',(%s))" % ",".join(faces))
    brep = ent("MANIFOLD_SOLID_BREP('%s',%s)" % (B.name, shell))
    mm = ent("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    rad = ent("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    sr = ent("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = ent("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),%s,'distance_accuracy_value',"
              "'confusion accuracy')" % mm)
    ctx = ent("( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((%s)) "
              "GLOBAL_UNIT_ASSIGNED_CONTEXT((%s,%s,%s)) REPRESENTATION_CONTEXT('Context #1',"
              "'3D Context with UNIT and UNCERTAINTY') )" % (unc, mm, rad, sr))
    rep = ent("ADVANCED_BREP_SHAPE_REPRESENTATION('',(%s,%s),%s)" % (ax((0, 0, 0), (0, 0, 1), (1, 0, 0)), brep, ctx))
    app = ent("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    ent("APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,%s)" % app)
    prod = ent("PRODUCT('%s','%s','%s',(%s))" % (B.name, B.name, title, ent("PRODUCT_CONTEXT('',%s,'mechanical')" % app)))
    pdf = ent("PRODUCT_DEFINITION_FORMATION('','',%s)" % prod)
    pd = ent("PRODUCT_DEFINITION('design','',%s,%s)" % (pdf, ent("PRODUCT_DEFINITION_CONTEXT('part definition',%s,'design')" % app)))
    ent("SHAPE_DEFINITION_REPRESENTATION(%s,%s)" % (ent("PRODUCT_DEFINITION_SHAPE('','',%s)" % pd), rep))
    ent("PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(%s))" % prod)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    head = ["ISO-10303-21;", "HEADER;",
            "FILE_DESCRIPTION(('%s'),'2;1');" % title,
            "FILE_NAME('%s','%s',('EXSU620 Team 6'),('McGill University'),'make_step.py',"
            "'make_step.py (Team 6)','');" % (os.path.basename(path), stamp),
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));", "ENDSEC;", "DATA;"]
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(head + out + ["ENDSEC;", "END-ISO-10303-21;"]) + "\n")
    return len(out)


PARTS = [
    (tray, "Team 6 CO2 flow-cell tray, version 1, mm"),
    (lid, "Team 6 CO2 flow-cell lid, version 1, mm"),
    (coupon, "Team 6 tubing barb fit coupon, version 1, mm"),
]

if __name__ == "__main__":
    for build, title in PARTS:
        B, sdf = build()
        v, e, f, genus = B.check()
        tested, wrong = compare(B, sdf)
        if wrong:
            raise SystemExit("%s: %d of %d test points disagree with make_parts.py; update the sizes at "
                             "the top of make_step.py" % (B.name, wrong, tested))
        path = os.path.join(HERE, B.name + ".step")
        n = write_step(B, path, title)
        print("%-20s %3d faces  %3d edges  %3d vertices  %d through-holes  %5d STEP entities  "
              "%5.2f cm3  same shape as make_parts.py at %d test points"
              % (B.name, f, e, v, genus, n, volume(B) / 1000, tested))
