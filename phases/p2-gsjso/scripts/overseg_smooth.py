#!/usr/bin/env python3
"""P2 overseg-lever Phase A — INPUT-SMOOTHING lever: flatten GS roof high-frequency noise before Roofer.

Per-cell local-plane projection (MLS-style, slope-preserving): bin class-6 (building) points into
`cell`-sized xy cells; for each cell fit a plane z=ax+by+c from the cell + its 8 neighbours (robust,
many points), then REPLACE each point's z by the plane value at its xy. This removes z-scatter
(roughness that makes Roofer detect spurious planes) while preserving real slopes and m-scale steps
(steps fall across cell boundaries, not within a `cell`-sized neighbourhood at cell<=1m). Non-building
classes (ground=2 etc.) pass through unchanged. NO retrain, NO reference used. EPSG:25832.

Runs in jointbuildgs-p0-tools:t0 (numpy/laspy). Out: a new classified LAS for Roofer.
"""
import argparse
import numpy as np
import laspy


def _boxsum(G, w):
    """sum over a (2w+1)x(2w+1) window at every grid cell, via an integral image (zero-padded)."""
    I = np.zeros((G.shape[0] + 1, G.shape[1] + 1))
    I[1:, 1:] = np.cumsum(np.cumsum(G, 0), 1)
    H, W = G.shape
    r = np.arange(H); c = np.arange(W)
    r0 = np.clip(r - w, 0, H); r1 = np.clip(r + w + 1, 0, H)
    c0 = np.clip(c - w, 0, W); c1 = np.clip(c + w + 1, 0, W)
    A = I[np.ix_(r1, c1)] - I[np.ix_(r0, c1)] - I[np.ix_(r1, c0)] + I[np.ix_(r0, c0)]
    return A


def smooth_cell_plane(P, cell, npass, win=2):
    """MLS-on-grid: fit z=ax+by+c over a (2*win+1)-cell WINDOW around each cell (overlapping support ->
    near-continuous, no cell-boundary jumps), then evaluate the plane at each point's TRUE xy. Slope-
    preserving, removes high-frequency z-noise. Singular/sparse windows fall back to windowed mean-z."""
    c0 = P[:, :2].mean(0)
    z = P[:, 2].copy()
    for _ in range(npass):
        x = P[:, 0] - c0[0]; y = P[:, 1] - c0[1]
        gx = np.floor(P[:, 0] / cell).astype(np.int64); gy = np.floor(P[:, 1] / cell).astype(np.int64)
        gx -= gx.min(); gy -= gy.min()
        H, W = gx.max() + 1, gy.max() + 1
        def grid(v):
            G = np.zeros((H, W)); np.add.at(G, (gx, gy), v); return G
        Gn = _boxsum(grid(np.ones(len(z))), win)
        Gx, Gy, Gz = _boxsum(grid(x), win), _boxsum(grid(y), win), _boxsum(grid(z), win)
        Gxx, Gyy, Gxy = _boxsum(grid(x * x), win), _boxsum(grid(y * y), win), _boxsum(grid(x * y), win)
        Gxz, Gyz = _boxsum(grid(x * z), win), _boxsum(grid(y * z), win)
        A = np.zeros((H, W)); B = np.zeros((H, W))
        C = np.divide(Gz, Gn, out=np.zeros_like(Gz), where=Gn > 0)
        ii, jj = np.where(Gn >= 6)
        for i, j in zip(ii, jj):
            n = Gn[i, j]
            M = np.array([[Gxx[i, j], Gxy[i, j], Gx[i, j]],
                          [Gxy[i, j], Gyy[i, j], Gy[i, j]],
                          [Gx[i, j], Gy[i, j], n]])
            r = np.array([Gxz[i, j], Gyz[i, j], Gz[i, j]])
            try:
                A[i, j], B[i, j], C[i, j] = np.linalg.solve(M, r)
            except np.linalg.LinAlgError:
                C[i, j] = Gz[i, j] / n
        z = A[gx, gy] * x + B[gx, gy] * y + C[gx, gy]
    out = P.copy(); out[:, 2] = z
    return out


def roof_top_mask(P, cell=1.0, band=1.5):
    """bool mask of P keeping per-`cell` xy-cell top-surface points (z >= cell-max - band) = roof, not wall."""
    gx = np.floor(P[:, 0] / cell).astype(np.int64); gy = np.floor(P[:, 1] / cell).astype(np.int64)
    _, cid = np.unique(np.stack([gx, gy], 1), axis=0, return_inverse=True)
    cmax = np.full(cid.max() + 1, -np.inf); np.maximum.at(cmax, cid, P[:, 2])
    return P[:, 2] >= cmax[cid] - band


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--win", type=int, default=2, help="window radius in cells; support=(2*win+1)*cell m")
    ap.add_argument("--npass", type=int, default=1)
    ap.add_argument("--bclass", type=int, default=6)
    a = ap.parse_args()
    las = laspy.read(a.inp)
    cl = np.asarray(las.classification)
    P = np.column_stack([np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)]).astype(float)
    m = cl == a.bclass
    n_before = int(m.sum())
    moved = 0.0; n_roof = 0
    if n_before >= 4:
        bi = np.where(m)[0]              # indices of building (class6) points
        Pb = P[bi]
        rmask = roof_top_mask(Pb)        # smooth ONLY roof-top pts (exclude walls -> no z contamination)
        ri = bi[rmask]; n_roof = len(ri)
        if n_roof >= 4:
            z0 = P[ri, 2].copy()
            P[ri] = smooth_cell_plane(P[ri], a.cell, a.npass, a.win)
            moved = float(np.median(np.abs(P[ri, 2] - z0)))
            las.z = P[:, 2]
    las.write(a.out)
    print(f"[smooth] {a.inp.split('/')[-1]} class{a.bclass} n={n_before} roof_top={n_roof} cell={a.cell} "
          f"win={a.win} median|dz|={moved:.3f}m -> {a.out.split('/')[-1]}")


if __name__ == "__main__":
    main()
