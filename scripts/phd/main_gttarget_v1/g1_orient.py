"""Stage 1 (order 3.2, outward normal): per GT plane region the normal sign that the training views see.
For every training view the patch discs are drawn (same rasterizer as the maps); per region the frontmost pixels are counted as front-facing
(normal toward the camera) or back-facing. A region with more back-facing than front-facing pixels is flipped (normal and t1; centres unchanged:
the flipped grid is the same lattice). usage (CPU container): g1_orient.py <site>
writes /gt/surface/<site>/patches.npz (oriented; the AXES71-sign version kept as patches_axes71.npz) and orientation.json"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from g1_maps import rasterizer_env

def main(site):
    c = cfg(1); t0 = time.monotonic(); root = O/'surface'/site; src = root/'patches_axes71.npz'
    if not src.exists(): (root/'patches.npz').rename(src)
    p = loadz(src); N = len(p['area']); env, _ = rasterizer_env(); fn = env['rasterizer']()
    points = np.c_[p['centre'], p['normal'], np.sqrt(p['area']/np.pi), np.arange(N)].astype(float)
    fti = json.loads((FT/'stage1'/f'{site}__LoD2'/'maps/index.json').read_text()); front = np.zeros(N); back = np.zeros(N)
    for name, fv in fti['views'].items():
        K = np.asarray(fv['K']); M = np.asarray(fv['W2C'])
        depth, owner, _, _ = env['draw'](fn, points, dict(H=741, W=1024, W2C=M, fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2]))
        yy, xx = np.nonzero(owner >= 0); o = owner[yy, xx]; ray = np.c_[(xx-K[0, 2])/K[0, 0], (yy-K[1, 2])/K[1, 1], np.ones(len(xx))]
        b = ((p['normal'][o]@M[:3, :3].T)*ray).sum(1) > 0
        back += np.bincount(o[b], minlength=N); front += np.bincount(o[~b], minlength=N)
    S = p['surf'].max()+1; fr = np.bincount(p['surf'], weights=front, minlength=S); bk = np.bincount(p['surf'], weights=back, minlength=S)
    flip_region = bk > fr; flip = flip_region[p['surf']]; q = dict(p)
    q['normal'] = np.where(flip[:, None], -p['normal'], p['normal']); q['t1'] = np.where(flip[:, None], -p['t1'], p['t1']); q['flipped'] = flip
    q['front_pixels'] = front; q['back_pixels'] = back; savez(root/'patches.npz', **q)
    wall = p['kind'] == 2; seen = (fr+bk) > 0
    rec = dict(at=now(), site=site, title=TITLE, regions=int(S), regions_seen=int(seen.sum()), regions_flipped=int(flip_region.sum()),
        patches_flipped=int(flip.sum()), patches_flipped_wall=int((flip & wall).sum()), patches_flipped_roof=int((flip & ~wall).sum()),
        back_pixels_before=float(back.sum()), back_pixels_after=float(np.where(flip, front, back).sum()), front_pixels_after=float(np.where(flip, back, front).sum()),
        patches_unseen=int(((front+back) == 0).sum()), views=len(fti['views']), seconds=time.monotonic()-t0,
        rule='영역마다 가장 앞 원판 화소의 앞면 수 < 뒷면 수이면 법선 뒤집기 (바깥 = 학습 영상이 보는 쪽)', scientific_verdict=None)
    dump(root/'orientation.json', rec); print('ORIENT', site, json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(sys.argv[1])
