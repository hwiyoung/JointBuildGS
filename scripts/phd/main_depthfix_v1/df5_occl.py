"""Occlusion masks for the occlusion-excluded extractions (CPU, no GT). usage: df5_occl.py <stem>
  occl10 : WRONGTARGET/TRAINERR addendum 6 rule (a6_ra_render occl_10) on the 판 0 map: pixel with a target and image depth (finite > 0) nearer than it by > 10 m
  occlga : switch 가 map (order 2.1, last line): pixel whose 판 0 owner disc faces away from the camera, or 가-map 10 m rule pixel
Same masks for every arm of the stem. writes /df/stage1x/<stem>/{occl10,occlga}/<view>.npz (bool 'occ')."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *

def main(stem):
    t0 = time.monotonic(); site, prior = stem.split('__'); tb = loadz(O/'families/base/targets'/f'{stem}.npz'); ids = np.flatnonzero(tb['surface_exists'])
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text()); mvsroot = S0/'fork_inputs/s61'/site/'maps'; rows = []
    for v in ['occl10', 'occlga']: (O/'stage1x'/stem/v).mkdir(parents=True, exist_ok=False)
    for name, meta in idx['views'].items():
        M = np.asarray(meta['W2C']); Cc = cam_centre(M); front = np.zeros(len(tb['area']), bool); front[ids] = ((Cc[None] - tb['target'][ids])*tb['normal'][ids]).sum(1) > 0
        zb = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['depth', 'owner']); zg = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['front_rule'])
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); has = zb['owner'] >= 0
        o10 = has & np.isfinite(mvs) & (mvs > 0) & (mvs < zb['depth'] - 10.)
        oga = (has & ~front[np.maximum(zb['owner'], 0)]) | zg['front_rule']
        savez(O/'stage1x'/stem/'occl10'/f'{name}.npz', occ=o10); savez(O/'stage1x'/stem/'occlga'/f'{name}.npz', occ=oga)
        rows.append(dict(view=name, occl10=int(o10.sum()), occlga=int(oga.sum())))
    dump(O/'stage1x'/stem/'receipt.json', dict(at=now(), stem=stem, views=len(rows), totals={k: sum(r[k] for r in rows) for k in ['occl10', 'occlga']}, seconds=time.monotonic()-t0, scientific_verdict=None))
    print('OCCL', stem, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
