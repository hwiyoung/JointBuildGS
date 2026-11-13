"""Concept video, another case (TL_CASE=B0_b10__LoD2, 2026-11-13): the two zones. Read-only on inputs; writes /tl/concept_v2/case_zones.json and a copy in /docs.
Wall zones. The section line of a zone runs perpendicular to one LoD2 prior wall face (horizontal face normal), 12 m long, centred on the wall (6 m inside,
6 m outside); box = line x +-4 m along the wall (12 x 8 m, as the B173 zone 1); the ② zoom looks at the wall from outside (azimuth of the outward normal,
elevation 35).
  zone 1 'hidden wall' = the place of the user's story: GTJUDGE GT rows (rows.npz) that are wall rows with the prior right (<= TAU) and no / wrong image depth,
         dense part = 4 m cells with >= 200 such rows (cv2_site_look.py cluster A); centre = their median xy; the wall face = the LoD2 wall face (|n.up| < 0.3,
         area >= 2 m2) nearest that centre.
  zone 2 'seen wall' (control: a wall the photos see) = among LoD2 wall faces of area >= 20 m2, the one whose GT wall rows within 0.5 m of the face plane and
         inside the face extent are most often 'prior right and image depth right' (share, then count); centre = the median xy of those rows.
Chosen BY GT rows (places of a story, not representative places); recorded. GT is used only to place the zones, to score and to draw. scientific_verdict: null"""
from common import *
from shapely.geometry import shape
assert TL_CASE == 'B0_b10__LoD2', TL_CASE
TAU = 0.211856; L = 12.0; HALF = 4.0; DENSE = 200

def main():
    t0 = time.monotonic(); c = cfg(); up = np.asarray(c['coordinates']['up'], float); up /= np.linalg.norm(up)
    pm = loadz(S1/'defs'/SITE/f'prior_{PRIOR}.npz', ['V', 'F']); V, F = pm['V'].astype(float), pm['F'].astype('i8'); T = V[F]
    nrm = np.cross(T[:, 1]-T[:, 0], T[:, 2]-T[:, 0]); area = np.linalg.norm(nrm, axis=1)/2; nrm /= np.maximum(2*area[:, None], 1e-12)
    wall = (np.abs(nrm@up) < .3) & (area >= 2.); fp = shape(c['scope']['buffered_footprint']); ctr = T.mean(1)
    wall &= shapely.contains_xy(fp, ctr[:, 0], ctr[:, 1])
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence', 'wall'])
    X = row['xyz'].astype(float); rw = row['wall'].astype(bool); pr = row['prior_presence'].astype(bool) & (row['prior_distance_m'] <= TAU)
    mp = row['mvs_presence'].astype(bool); mright = mp & (row['mvs_distance_m'] <= TAU); mbad = ~mp | (row['mvs_distance_m'] > .5)
    def line_for(fi, centre_xy, name, rule):
        n = nrm[fi]; nh = n-(n@up)*up; nh /= np.linalg.norm(nh); n2 = nh[:2]/np.linalg.norm(nh[:2])
        P0 = ctr[fi]; d = (centre_xy-P0[:2])@np.array([-n2[1], n2[0]]); foot = P0[:2]+d*np.array([-n2[1], n2[0]])   # centre projected on the wall line
        # outward = away from the footprint interior
        out = n2 if not fp.contains(shapely.Point(*(foot+1.5*n2))) else -n2
        o = foot-(L/2)*out; t = out; nn = np.array([-t[1], t[0]])
        box = [(o+a*t+b*nn).tolist() for a, b in [(0, -HALF), (L, -HALF), (L, HALF), (0, HALF)]]
        return dict(name=name, rule=rule, wall_face_index=int(fi), wall_face_area_m2=round(float(area[fi]), 2), wall_normal_out_xy=out.tolist(), wall_foot_xy=foot.tolist(),
                    line_origin_xy=o.tolist(), line_unit_xy=t.tolist(), line_length_m=L, box_polygon_xy=box, zoom_azimuth_deg=round(float(np.degrees(np.arctan2(out[1], out[0])) % 360), 1))
    # zone 1
    case = rw & pr & mbad; ci = np.flatnonzero(case); ij = np.floor(X[ci, :2]/4).astype(int); keys, inv, cnt = np.unique(ij, axis=0, return_inverse=True, return_counts=True)
    A = ci[cnt[inv.ravel()] >= DENSE]; cA = np.median(X[A, :2], 0); wi = np.flatnonzero(wall)
    fi1 = wi[np.argmin(np.linalg.norm(ctr[wi, :2]-cA, axis=1))]
    z1 = line_for(fi1, cA, '가려진 벽', 'zone 1: dense case rows (wall, prior right, image depth absent or > 0.5 m), nearest LoD2 wall face')
    z1.update(case_rows=int(len(A)), case_centre_xy=cA.tolist())
    # zone 2
    best = None
    for fi in wi[area[wi] >= 20.]:
        n = nrm[fi]; P0 = ctr[fi]; dist = np.abs((X-P0)@n); tri = T[fi]; e = tri.max(0)-tri.min(0)
        near = rw & (dist <= .5) & np.all((X >= tri.min(0)-.5) & (X <= tri.max(0)+.5), axis=1)
        if near.sum() < 300: continue
        good = near & pr & mright; share = good.sum()/near.sum()
        if best is None or (share, near.sum()) > (best[1], best[2]): best = (fi, float(share), int(near.sum()), np.median(X[good, :2], 0) if good.any() else P0[:2])
    fi2, sh2, n2r, c2 = best
    z2 = line_for(fi2, c2, '잘 보이는 벽', 'zone 2: LoD2 wall face (area >= 20 m2) whose GT wall rows near the face are most often prior right & image depth right')
    z2.update(face_rows=n2r, prior_and_image_right_share=round(sh2, 3))
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, zones={'1': z1, '2': z2}, prior=str(S1/'defs'/SITE/f'prior_{PRIOR}.npz'), rows=str(GT/'scenes'/STEM/'rows.npz'), seconds=round(time.monotonic()-t0, 1))
    dump(O/'concept_v2'/'case_zones.json', rec); dump(D/'case_zones.json', rec); print('ZONES', json.dumps(rec['zones'], ensure_ascii=False)[:1500], flush=True)

def v3(shift=5.0):
    """Zones v3 (2026-11-13, user '진행하자' after the zone-2 corner was found): zone 1 = the v1 zone 1 unchanged; zone 2 = the v1 zone-2 line slid `shift` m
    along its own wall, in the direction cross(up, outward) (away from the inner corner, which lies 1.1 m on the other side of the v1 line), so the 8 m box holds
    that wall only. Read-only on the v1 file; writes /tl/concept_v2/case_zones_v3.json and /docs/case_zones_v3.json.
    Why (GT rows, recorded): the v1 zone-2 box straddled an inner corner (wall rows facing the zone direction 3,332, perpendicular corner wall 7,357);
    slid 5 m: 1,806 and 40; image depth right on that wall 99.7 %, LoD2 right 99.9 %. 4 m kept 123 corner rows, 6 m keeps fewer wall rows (wall ends
    ~8 m from the corner inside the building scope). GT used only to place the zone, to score and to draw."""
    c = cfg(); up = np.asarray(c['coordinates']['up'], float); up /= np.linalg.norm(up)
    v1 = json.loads((O/'concept_v2'/'case_zones.json').read_text()); z = json.loads(json.dumps(v1['zones']['2']))
    out = np.r_[z['wall_normal_out_xy'], 0.]; al = np.cross(up, out); a2 = al[:2]/np.linalg.norm(al[:2]); d = shift*a2
    t = np.asarray(z['line_unit_xy'], float); o = np.asarray(z['line_origin_xy'], float)+d; nn = np.array([-t[1], t[0]])
    z.update(line_origin_xy=o.tolist(), wall_foot_xy=(np.asarray(z['wall_foot_xy'], float)+d).tolist(), box_polygon_xy=[(o+a*t+b*nn).tolist() for a, b in [(0, -HALF), (L, -HALF), (L, HALF), (0, HALF)]],
             rule=z['rule']+f'; v3: line slid {shift} m along the wall (cross(up, outward)), away from the inner corner, so the box holds this wall only', v1_line_origin_xy=v1['zones']['2']['line_origin_xy'],
             slide_m=shift, slide_unit_xy=a2.tolist())
    rec = dict(at=now(), rule=v3.__doc__, scientific_verdict=None, zones={'1': v1['zones']['1'], '2': z}, v1=str(O/'concept_v2'/'case_zones.json'), v1_sha256=sha(O/'concept_v2'/'case_zones.json'))
    dump(O/'concept_v2'/'case_zones_v3.json', rec); dump(D/'case_zones_v3.json', rec); print('ZONES_V3', json.dumps(z, ensure_ascii=False)[:600], flush=True)

if __name__ == '__main__':
    import time, shapely, sys
    if sys.argv[1:] == ['v3']: v3()
    else: main()
