"""방법 A의 살아남은 화소 (발주 4.1). 융합 결과 fused.ply/.vis 만 읽는다(참값 없음). CPU.
1) .vis 의 영상 번호가 가리키는 영상 차례(COLMAP 모형 차례)를 앞 2만 점의 깊이 일치로 확인(파일 차례 / 번호 차례 가운데 맞는 쪽).
2) fusion_survive.cpp: 융합 점을 .vis 영상에 투영(COLMAP 융합과 같은 화소 규약: 축척한 K, 반 화소 빼지 않음, 반올림), 깊이가 상대 1 % 안이면 그 화소 표시.
3) masks/none.npy(깊이 > 0 화소 모두), masks/A.npy, 영상마다 살아남은 비율, 검산 3(표본 1만 점: 살아남은 화소를 지금 점 규약으로 역투영한 점과 융합 점의 거리 <= 융합 점 깊이의 1 %).
사용: mf1_surviveA.py [campus]"""
import sys, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *

def ply_xyz(path, count=None):
    with open(path, 'rb') as f:
        props = []; n = 0; inv = False
        while True:
            l = f.readline().decode().strip()
            if l.startswith('element vertex'): n = int(l.split()[2]); inv = True
            elif l.startswith('element'): inv = False
            elif l.startswith('property') and inv: _, t, nm = l.split(); props.append((nm, {'float': '<f4', 'uchar': 'u1', 'double': '<f8'}[t]))
            elif l == 'end_header': break
        dt_ = np.dtype(props); a = np.fromfile(f, dtype=dt_, count=n if count is None else min(n, count))
    return n, np.c_[a['x'], a['y'], a['z']].astype(np.float32)

def vis_head(path, k):
    a = np.fromfile(path, dtype='<u4', count=2 + 200*k)   # 앞부분만
    p = 2; out = []
    for _ in range(k):
        n = int(a[p]); out.append(a[p+1:p+1+n].copy()); p += 1 + n
    return out

def main(name='campus'):
    cf = cfg(); T = Timer(); F = O/'fusion'/name; assert json.loads((F/'fusion_receipt.json').read_text())['exit_code'] == 0
    names = json.loads((W/'image_split.json').read_text())['train']; assert names == sorted(names)
    rows = poses(WS/'sparse/images.bin'); ids = image_ids(WS/'sparse/images.bin')
    with (WS/'sparse/cameras.bin').open('rb') as f:
        nc, = struct.unpack('<Q', f.read(8)); cid, model, iw, ih = struct.unpack('<iiQQ', f.read(24)); fx, fy, cx, cy = struct.unpack('<4d', f.read(32))
    Kc = (fx*1024/iw, fy*741/ih, cx*1024/iw, cy*741/ih)      # COLMAP Camera::Rescale (융합이 쓰는 K)
    orders = {'images.bin 파일 차례': list(ids), 'image_id 차례': sorted(ids, key=lambda s: ids[s]), '이름 차례': sorted(ids)}
    lg = {}; cur = None
    for l in (WS/'patch_match.log').read_text(errors='replace').splitlines():
        if 'Processing view' in l: cur = l.rsplit(' for ', 1)[1].split(' ===')[0].strip()
        elif 'ref_image_idx:' in l and cur is not None: lg[int(l.rsplit(':', 1)[1])] = cur; cur = None
    if len(lg) == len(ids) and sorted(lg) == list(range(len(ids))): orders['patch_match.log ref_image_idx'] = [lg[i] for i in range(len(ids))]
    n_f, X = ply_xyz(F/'fused.ply', 20000); V = vis_head(F/'fused.ply.vis', len(X))
    Zc = {}
    def depth(nm):
        if nm not in Zc: Zc[nm] = read_depth(WS/'stereo/depth_maps'/f'{nm}.geometric.bin')
        return Zc[nm]
    test = {}
    for on, order in orders.items():
        ok = tot = 0
        for k in range(0, len(X), 40):
            for im in V[k]:
                nm = order[int(im)]; q, t = rows[nm]; Q = rotation(q)@X[k].astype(float) + np.array(t)
                c = int(round(Kc[0]*Q[0]/Q[2] + Kc[2])); r = int(round(Kc[1]*Q[1]/Q[2] + Kc[3])); tot += 1
                if 0 <= c < 1024 and 0 <= r < 741:
                    z = depth(nm)[r, c]; ok += int(z > 0 and abs(z - Q[2]) <= .01*Q[2])
        test[on] = dict(entries=tot, matched=ok, pct=100*ok/max(tot, 1))
    best = max(test, key=lambda k: test[k]['pct']); order = orders[best]; print('ORDER', json.dumps(test, ensure_ascii=False), best, flush=True)
    tmp = O/'tmp'/f'survA_{name}'; tmp.mkdir(parents=True, exist_ok=True)
    cam = np.zeros((len(order), 12))
    for i, nm in enumerate(order): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WS/'stereo/depth_maps'/f'{nm}.geometric.bin') if (WS/'stereo/depth_maps'/f'{nm}.geometric.bin').exists() else '-' for nm in order) + '\n')
    exe = O/'bin/fusion_survive'; exe.parent.mkdir(exist_ok=True)
    subprocess.run(['g++', '-O3', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/fusion_survive.cpp', '-o', str(exe)], check=True)
    tol = cf['method_A_colmap_stereo_fusion']['survival']['relative_depth_tol']
    args = [str(exe), str(F/'fused.ply'), str(F/'fused.ply.vis'), str(tmp/'cams.bin'), str(tmp/'depths.txt'), '1024', '741', *map(repr, Kc), str(tol), str(tmp/'mask.u8'), str(tmp/'stats.txt'), '997', str(tmp/'sample.bin')]
    subprocess.run(args, check=True); T.mark('survive')
    st = dict(l.split(' ', 1) for l in (tmp/'stats.txt').read_text().splitlines())
    mk = np.fromfile(tmp/'mask.u8', dtype='u1').reshape(len(order), 741, 1024).astype(bool)
    pos = {nm: i for i, nm in enumerate(order)}; mA = mk[[pos[nm] for nm in names]]; del mk
    none = np.zeros_like(mA)
    for i, nm in enumerate(names): z = depth(nm) if nm in Zc else read_depth(WS/'stereo/depth_maps'/f'{nm}.geometric.bin'); none[i] = np.isfinite(z) & (z > 0)
    assert not (mA & ~none).any()
    if not (O/'masks/none.npy').exists(): save_mask('none', none)
    save_mask('A', mA)
    vp = none.reshape(len(names), -1).sum(1); sp = mA.reshape(len(names), -1).sum(1); ratio = sp/np.maximum(vp, 1)
    # 검산 3
    smp = np.fromfile(tmp/'sample.bin', dtype=np.dtype([('k', '<u4'), ('im', '<u4'), ('r', '<u4'), ('c', '<u4'), ('x', '<f4'), ('y', '<f4'), ('z', '<f4')]))
    rs = np.random.default_rng(20261119); s = smp[np.sort(rs.choice(len(smp), min(10000, len(smp)), replace=False))]
    vi = np.array([names.index(order[int(i)]) for i in s['im']]); pix = (s['r'].astype(np.int64)*1024 + s['c']).astype(np.int32)
    K = intrinsics(); Xp = unproject(vi, pix, names, rows, (K['fx'], K['fy'], K['cx'], K['cy']))
    Xf = np.c_[s['x'], s['y'], s['z']].astype(float); dist = np.linalg.norm(Xp - Xf, axis=1)
    dep = np.array([(rotation(rows[names[v]][0])@x + np.array(rows[names[v]][1]))[2] for v, x in zip(vi, Xf)])
    chk3 = dict(sample=len(s), within_1pct=int((dist <= .01*dep).sum()), median_dist_m=float(np.median(dist)), max_ratio=float((dist/dep).max()))
    rec = dict(at=now(), name=name, fused_points=int(st['points']), stats={k: v for k, v in st.items()}, order_test=test, order_used=best, K_colmap=Kc, tol=tol,
               pixels_valid=int(vp.sum()), pixels_survived=int(sp.sum()), survived_pct=100*float(sp.sum()/vp.sum()),
               per_image_ratio_quantiles={str(q): float(np.quantile(ratio[vp > 0], q)) for q in [0, .1, .25, .5, .75, .9, 1]},
               per_image=[dict(name=n_, valid=int(a), survived=int(b)) for n_, a, b in zip(names, vp, sp)], check3=chk3, seconds=T.s(), scientific_verdict=None)
    dump(O/'masks/A.json', rec)
    print('SURVIVE_A', json.dumps({k: rec[k] for k in ['fused_points', 'pixels_valid', 'pixels_survived', 'survived_pct', 'check3', 'order_used']}, ensure_ascii=False), flush=True)
    progress(f'mf1 방법 A 살아남은 화소: 융합 점 {rec["fused_points"]:,}, 화소 {rec["pixels_survived"]:,}/{rec["pixels_valid"]:,} ({rec["survived_pct"]:.1f} %), 검산 3 {chk3["within_1pct"]}/{chk3["sample"]}, {round(T.s())} 초')

if __name__ == '__main__': main(*sys.argv[1:])
