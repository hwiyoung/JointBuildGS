"""단계 0-3 (발주 3.3): 세 실험 지역의 MVS 깊이(UNCERT mvs_a = STAGE0 s61 export)가 전 건물 판정에 쓰는 MVS(WIDEN0 캠퍼스)·탐색 지역 MVS(DISCARD)와 같은 것인지."""
from common import *
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
def read_bin(p):
    with open(p, 'rb') as f:
        head = b''
        while head.count(b'&') < 3: head += f.read(1)
        w, h, c = map(int, head.split(b'&')[:3]); a = np.fromfile(f, np.float32).reshape(c, h, w).transpose(1, 2, 0).squeeze()
    return a
def main():
    cfg(); rows = []; region_of = {'B0_b10': 'B0', 'B173nb_b10': 'R2', 'R1rep_b10': 'R1'}
    wnames = {p.name.split('.')[0] for p in (W/'mvs/full/stereo/depth_maps').glob('*.geometric.bin')}
    for site in SITES:
        exp = sorted(p.stem for p in (S0/'s61/export'/site/'LoD2/mvs').glob('*.npy'))
        reg = region_of[site]; dnames = {p.name.split('.')[0] for p in (DR/'mvs'/reg/'stereo/depth_maps').glob('*.geometric.bin')}
        common_w = sorted(set(exp) & wnames); common_d = sorted(set(exp) & dnames)
        cmp = []
        for name in (common_w[:3] + common_d[:3]):
            e = np.load(S0/'s61/export'/site/'LoD2/mvs'/f'{name}.npy').astype(float)
            for tag, root in [('WIDEN0', W/'mvs/full'), ('DISCARD_'+reg, DR/'mvs'/reg)]:
                p = root/'stereo/depth_maps'/f'{name}.JPG.geometric.bin'
                if not p.exists(): continue
                o = read_bin(p).astype(float)
                if o.shape != e.shape: cmp.append(dict(image=name, other=tag, shape=[list(e.shape), list(o.shape)])); continue
                both = np.isfinite(e) & (e > 0) & np.isfinite(o) & (o > 0)
                cmp.append(dict(image=name, other=tag, valid_both=int(both.sum()), valid_exp=int((np.isfinite(e) & (e > 0)).sum()), valid_other=int((np.isfinite(o) & (o > 0)).sum()),
                                equal_share=float(np.mean(e[both] == o[both])) if both.any() else None, median_abs_diff_m=float(np.median(np.abs(e[both]-o[both]))) if both.any() else None))
        rows.append(dict(site=site, search_region=reg, experiment_views=len(exp), widen0_views=len(wnames), discard_views=len(dnames), common_with_widen0=len(common_w), common_with_discard=len(common_d), samples=cmp))
    same = all(all(c.get('equal_share') == 1.0 for c in r['samples'] if c['other'] == 'WIDEN0') and r['experiment_views'] == r['common_with_widen0'] for r in rows)
    dump(O/'stage0/mvs_identity.json', dict(at=now(), experiment_equals_widen0=same, rows=rows, decision='본값 판은 WIDEN0 캠퍼스 MVS(전 건물에 같은 MVS), 세 지역의 지금 판은 JUDGEAPPLY/FINALTRAIN 파일', GT_read=False, scientific_verdict=None))
    for r in rows: print(r['site'], r['experiment_views'], r['common_with_widen0'], r['common_with_discard'], [(c['image'][-9:], c['other'], c.get('equal_share'), c.get('median_abs_diff_m'), c.get('shape')) for c in r['samples']])
if __name__ == '__main__': main()
