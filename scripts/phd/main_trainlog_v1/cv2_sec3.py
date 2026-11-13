"""Concept video v2 r3 (2026-11-13, user: 'the sections must show the floating surfaces unfiltered'): section layers of every state with nothing filtered out.
The r2 sections drew (a) only building-scope Gaussians (discs/<key>.npz), (b) the mesh after the building-scope cut (footprint + 1 m, z 0.3-25.4 m above
ground), (c) only what fell inside the fixed height axis and (d) only 0 <= s <= L, while the largest concentration of roof-height floaters lies 0-3 m
outside the building edge where the zone 2 line starts. r3 takes, for each zone band (|offset| <= 0.5 m, -EXT <= s <= L+EXT, EXT = 3 m drawn beyond each
line end; the line itself is unchanged):
  Gaussians = ALL Gaussians of the saved state (ours: RUNM/trainlog/scene/<n>.pt without the 'inside' mask; comparisons: the full point_cloud.ply),
              any height, any opacity: s, height above the scope ground, opacity;
  mesh      = the cut of the UNCUT original-rule mesh (gtj final.ply, before the building-scope cut) by the vertical plane of the zone line
              (cv2_frames.cut with s within -EXT..L+EXT);
  GT        = GT dense points in the same band and s range (sections_r3/gt.npz; drawn light, as the reference only).
Also recorded per key and zone: how many band Gaussians the r2 scope dropped, mesh cut length r2 vs r3, and the height extent of both.
Writes concept_v2/sections_r3/<key>.npz and concept_v2/sections_r3.json only. No training, no meshing, no scoring. scientific_verdict: null"""
import sys
from cv2_frames import *
import torch
from cv2_prep import read_ply, COMP as CPLY
OUTS = SECD; EXT = 3.0   # sections_r3 (r5) or sections_z1b (CV2_VARIANT=z1b, cv2_frames)
assert VAR != 'r6', 'r6 reads sections_r3 unchanged (it already holds the 2DGS cuts of zone 1)'
MESH = {**{f'ours_{n}': O/'gtj/meshes'/f'{STEM}__tl_{n}'/'final.ply' for n in STATES},
        'nojudge_15000': V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_15000'/'final.ply', 'nojudge_30000': V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_30000_v203'/'final.ply',
        '2dgs_7000': V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_7000'/'final.ply', '2dgs_30000': V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_30000_v203'/'final.ply'}

def gaussians(key):
    if key.startswith('ours_'):
        p = RUNM/'trainlog/scene'/f"{key[5:]}.pt"; d = torch.load(p, map_location='cpu', weights_only=False)
        return d['xyz'].numpy().astype(float), (1/(1+np.exp(-d['opacity'].numpy().reshape(-1).astype(float)))), d['inside'].numpy().astype(bool), p
    p = CPLY[key]; v = read_ply(p); xyz = np.c_[v['x'], v['y'], v['z']].astype(float)
    return xyz, 1/(1+np.exp(-v['opacity'].astype(float))), scope_mask(xyz, cfg()), p

def cut_ext(V, F, z, L):
    zz = dict(z); zz['L'] = L+2*(EXT-.5); zz['o'] = np.asarray(z['o'])-(EXT-.5)*np.asarray(z['t'])   # cut() keeps -0.5..L'+0.5 around the shifted origin
    seg = cut(V, F, zz); seg[:, :, 0] -= EXT-.5; return seg

def main(keys):
    S = Static(); sj = json.loads(STJ.read_text()); OUTS.mkdir(parents=True, exist_ok=True); jp = SECJ
    rec = dict(rule=__doc__, ext_m=EXT, keys={}, scientific_verdict=None)
    G = loadz(Path(sj['gt']), ['xyz'])['xyz'].astype(float); gout = {}
    for k in (1, 2):
        L = sj['zones'][str(k)]['line_length_m']; s, v = sv(G, S.zones[k]); b = (np.abs(v) <= BAND) & (s >= -EXT) & (s <= L+EXT); gout[f'gt{k}'] = np.c_[s[b], G[b, 2]-S.ground].astype('f4')
    savez(OUTS/'gt.npz', **gout); rec['gt'] = {k: int(len(v)) for k, v in gout.items()}
    for key in keys:
        t0 = time.monotonic(); P, op, insc, gp = gaussians(key); out = {}; r = dict(gaussian_source=str(gp), gaussian_source_sha256=sha(gp), mesh=str(MESH[key]), mesh_sha256=sha(MESH[key]), zones={})
        m = o3d.io.read_triangle_mesh(str(MESH[key])); V = np.asarray(m.vertices, float); F = np.asarray(m.triangles).astype('i8'); del m
        r2m = loadz(V2/'meshcol'/f'{key}.npz', ['V', 'F'])
        for k in (1, 2):
            z = S.zones[k]; L = sj['zones'][str(k)]['line_length_m']; y0, y1 = sj['zones'][str(k)]['section_height_limits_m']
            s, v = sv(P, z); b = (np.abs(v) <= BAND) & (s >= -EXT) & (s <= L+EXT); h = P[b, 2]-S.ground
            seg = cut_ext(V, F, z, L); seg2 = cut(r2m['V'].astype(float), r2m['F'].astype('i8'), z)
            ln = lambda q: float(np.linalg.norm(q[:, 1]-q[:, 0], axis=1).sum()) if len(q) else 0.
            out[f'g{k}_s'] = s[b].astype('f4'); out[f'g{k}_h'] = h.astype('f4'); out[f'g{k}_op'] = op[b].astype('f4'); out[f'g{k}_in_scope'] = insc[b]; out[f'm{k}'] = seg.astype('f4')
            mh = seg[:, :, 1].reshape(-1) if len(seg) else np.zeros(0)
            r['zones'][str(k)] = dict(band_gaussians=int(b.sum()), band_gaussians_outside_scope=int((b & ~insc).sum()), band_gaussians_outside_r2_axis=int(((h < y0) | (h > y1)).sum()),
                                      gaussian_height_min_max=[float(h.min()), float(h.max())] if len(h) else None, gaussian_height_p1_p99=np.percentile(h, [1, 99]).tolist() if len(h) else None,
                                      mesh_cut_length_r3_m=round(ln(seg), 2), mesh_cut_length_r2_scope_m=round(ln(seg2), 2), mesh_height_min_max=[float(mh.min()), float(mh.max())] if len(mh) else None,
                                      mesh_length_outside_r2_axis_m=round(ln(seg[((seg[:, :, 1] < y0) | (seg[:, :, 1] > y1)).any(1)]) if len(seg) else 0., 2), r2_axis=[y0, y1])
        savez(OUTS/f'{key}.npz', **out); r['seconds'] = round(time.monotonic()-t0, 1); rec['keys'][key] = r; rec['at'] = now(); dump(jp, rec); print('SEC3', key, json.dumps(r['zones']), r['seconds'], flush=True)
        del P, op, V, F

if __name__ == '__main__': main(sys.argv[1].split(',') if len(sys.argv) > 1 else list(MESH))
