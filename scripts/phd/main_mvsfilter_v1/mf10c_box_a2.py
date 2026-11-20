"""덧붙임 1: 상자 MVS(세 실험 지역)에 방법 A2(세션 판, 화소마다 일치 시점 수 c ≥ 5)를 캠퍼스와 같은 a2_count.cpp·같은 값으로 적용 → 원통 A2·A2_rm(지워진 점만, 점검 2). 참값 읽지 않음. CPU.
볼 영상 = 그 상자의 깊이 지도가 있는 모든 영상. 사용: mf10c_box_a2.py <지역> [...]  (mf10_box·mf10b_box_bc 뒤)"""
import sys, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mf10_box as MB
from mf10_box import GEO, A1, J3, unproject_b, site_patches, cyl
from mf10b_box_bc import load
from mfcommon import *
import mfcommon as MC

def run(site):
    T = Timer(); WSb, rows, names, none, depth = load(site); n = len(names); K = intrinsics()
    has = [(WSb/'stereo/depth_maps'/f'{nm}.geometric.bin').exists() for nm in names]; tmp = O/'tmp'/f'a2_box_{site}'; tmp.mkdir(parents=True, exist_ok=True)
    cam = np.zeros((n, 12))
    for i, nm in enumerate(names): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WSb/'stereo/depth_maps'/f'{nm}.geometric.bin') if h else '-' for nm, h in zip(names, has)) + '\n')
    (tmp/'normals.txt').write_text('\n'.join(str(WSb/'stereo/normal_maps'/f'{nm}.geometric.bin') if h else '-' for nm, h in zip(names, has)) + '\n')
    exe = O/'bin/a2_count'; assert exe.exists()
    subprocess.run([str(exe), str(n), str(Wd), str(H), *map(repr, [K['fx'], K['fy'], K['cx'], K['cy']]), str(tmp/'depths.txt'), str(tmp/'normals.txt'), str(tmp/'cams.bin'), str(tmp/'px'), str(tmp/'stats.txt'), os.environ.get('MF_CPUS', '16')],
                   check=True, stderr=subprocess.DEVNULL); T.mark('count')
    c = np.fromfile(tmp/'px_c.u16', '<u2').reshape(n, H*Wd); nn = none.reshape(n, -1); assert not (c[~nn] > 0).any() and (c[nn] >= 1).all()
    a2 = nn & (c >= 5); tot = int(nn.sum()); save_mask(f'box_{site}_A2', a2.reshape(n, H, Wd))
    rec = dict(at=now(), name=f'box_{site}', images=n, depth_maps=int(sum(has)), pixels_valid=tot, pixels_survived=int(a2.sum()), survived_pct=100*a2.sum()/tot, check_c_ge2_pct=100*int((c[nn] >= 2).sum())/tot, scientific_verdict=None)
    dump(O/'masks'/f'box_{site}_A2.json', rec); print('A2BOX', site, rec['survived_pct'], rec['check_c_ge2_pct'], flush=True)
    for f in tmp.glob('px_*.u16'): f.unlink()
    M = a2.reshape(n, H, Wd); FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'; GEO.BASE.mkdir(parents=True, exist_ok=True)
    if not (GEO.BASE/'cylinders').exists(): GEO.build()
    out = dict(site=site, survive=rec, priors={})
    for prior in ['LoD2', 'ALS']:
        sc = {nm: ext for nm, ext, _ in J3.scenes(prior)}
        if site not in sc: continue
        ext = sc[site]; d = A1.load(prior); idx, C, Nn, kind = site_patches(prior, ext, d); z0 = np.load(O/'box'/f'{site}__{prior}.npz'); assert np.array_equal(z0['idx'], idx)
        lo = [ext[0] - 3, ext[1] + 3, ext[2] - 3, ext[3] + 3]; X = []; S = []
        for i, nm in enumerate(names):
            v = np.flatnonzero(none[i].ravel())
            if not len(v): continue
            x = unproject_b(np.full(len(v), i), v, names, rows, K, depth); kk = (x[:, 0] >= lo[0]) & (x[:, 0] <= lo[1]) & (x[:, 1] >= lo[2]) & (x[:, 1] <= lo[3])
            X.append(x[kk]); S.append(M[i].ravel()[v[kk]])
        X = np.concatenate(X); s = np.concatenate(S); res = {}
        for tag, mk in [('A2', s), ('A2_rm', ~s)]:
            tp = FAST/f'pts_box_{site}_{tag}.npy'; np.save(tp, X[mk]); res[tag] = cyl(tp, prior, C, Nn, kind, f'{site}_{tag}'); tp.unlink()
        r0 = z0['none__raw_n']; v = r0 >= 0; eq = int((r0[v] == res['A2']['raw_n'][v] + res['A2_rm']['raw_n'][v]).sum())
        np.savez(O/'box'/f'{site}__{prior}__A2.npz', idx=idx, **{f'{t}__{k_}': a for t in res for k_, a in res[t].items()})
        out['priors'][prior] = dict(box_points=int(len(X)), box_points_survived=int(s.sum()), check2_patches=int(v.sum()), check2_equal=eq)
    out.update(seconds=T.s(), marks=T.marks, GT_read_for_filtering=False, scientific_verdict=None); dump(O/'box'/f'{site}__A2.json', out)
    print('BOXA2', site, json.dumps(jsafe(out['priors']), ensure_ascii=False), round(T.s()), flush=True)

def main(sites):
    MC.cfg()
    for s in sites:
        if not (O/'box'/f'{s}__A2.json').exists(): run(s)
    MB.table(sites); MC.progress(f'mf10c 상자 MVS A2 {sites} 끝')

if __name__ == '__main__': main(sys.argv[1:])
