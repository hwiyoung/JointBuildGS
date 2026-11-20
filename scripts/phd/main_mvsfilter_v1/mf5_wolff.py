"""방법 B (Wolff 외 2016) 두 판의 살아남은 화소 (발주 4.2). 참값 읽지 않음. CPU.
색: COLMAP 작업 공간 영상(1400x1013 왜곡 보정)을 깊이 지도 크기(1024x741)로 줄임(cv2 INTER_AREA), RGB 0~1.
σ: 영상마다 patch_match.log 의 depth_max - depth_min 의 1 %. t_v 원문 = 819 x 0.075.
사용: mf5_wolff.py [threads]"""
import sys, subprocess, math
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import cv2

def main(threads='32'):
    cf = cfg()['method_B_wolff2016']; T = Timer(); names = json.loads((W/'image_split.json').read_text())['train']; rows = poses(WS/'sparse/images.bin')
    tmp = O/'tmp/wolff'; tmp.mkdir(parents=True, exist_ok=True); K = intrinsics()
    rng_ = {}; cur = None
    for l in (WS/'patch_match.log').read_text(errors='replace').splitlines():
        if 'Processing view' in l: cur = l.rsplit(' for ', 1)[1].split(' ===')[0].strip()
        elif 'depth_min:' in l and cur: rng_.setdefault(cur, {})['min'] = float(l.rsplit(':', 1)[1])
        elif 'depth_max:' in l and cur:
            e = rng_.setdefault(cur, {}); e.setdefault('max', float(l.rsplit(':', 1)[1])); cur = None
    sig = np.array([(rng_[n]['max'] - rng_[n]['min'])*.01 for n in names]); sig.tofile(tmp/'sigma.f64')
    cam = np.zeros((len(names), 12))
    for i, nm in enumerate(names): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WS/'stereo/depth_maps'/f'{nm}.geometric.bin') for nm in names) + '\n')
    cp = tmp/'colors.u8'
    if not cp.exists():
        mm = np.lib.format.open_memmap(tmp/'colors.npy', mode='w+', dtype=np.uint8, shape=(len(names), H, Wd, 3))
        for i, nm in enumerate(names):
            im = cv2.imread(str(WS/'images'/nm), cv2.IMREAD_COLOR); assert im is not None and im.shape[:2] == (1013, 1400), nm
            mm[i] = cv2.resize(im, (Wd, H), interpolation=cv2.INTER_AREA)[..., ::-1]
        mm.flush(); np.asarray(mm).tofile(cp); del mm; (tmp/'colors.npy').unlink()
    T.mark('prepare')
    exe = O/'bin/wolff'; exe.parent.mkdir(exist_ok=True)
    subprocess.run(['g++', '-O3', '-fopenmp', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/wolff.cpp', '-o', str(exe)], check=True)
    tvo = len(names)*0.075
    args = [str(exe), str(len(names)), str(Wd), str(H), *map(repr, [K['fx'], K['fy'], K['cx'], K['cy']]), str(tmp/'depths.txt'), str(cp), str(tmp/'cams.bin'), str(tmp/'sigma.f64'),
            repr(cf['t_d_over_sigma']), repr(cf['t_p']), repr(tvo), str(tmp/'flags.u8'), str(tmp/'stats.txt'), str(threads)]
    subprocess.run(args, check=True); T.mark('wolff')
    fl = np.fromfile(tmp/'flags.u8', dtype=np.uint8).reshape(len(names), H*Wd)
    none = load_mask('none').reshape(len(names), -1); assert np.array_equal(none, (fl & 128) > 0)
    bo = (fl & 135) == 135; bv = (fl & 139) == 139
    save_mask('B_orig', bo.reshape(len(names), H, Wd)); save_mask('B_view', bv.reshape(len(names), H, Wd))
    np.save(O/'masks/B_flags.npy', fl)
    import pandas as pd
    st = pd.read_csv(tmp/'stats.txt', sep=' ')
    tot = int(none.sum()); cnt = lambda b: int(((fl & b) == b).sum() - 0)
    rec = dict(at=now(), t_v_original=tvo, sigma_m_quantiles={str(q): float(np.quantile(sig, q)) for q in [0, .5, 1]}, pixels_valid=tot,
               condition_pass_pct={'거리 (-t_d<d<0)': 100*cnt(129)/tot, '색 (p<t_p)': 100*cnt(130)/tot, 'v>t_v 원문': 100*cnt(132)/tot, 'v>t_v 시점': 100*cnt(136)/tot, '법선 없음': 100*cnt(144)/tot},
               B_orig_pct=100*float(bo.sum()/tot), B_view_pct=100*float(bv.sum()/tot), median_v=float(st['median_v'].median()), median_in_frame=float(st['median_in_frame'].median()),
               per_image=st.to_dict(orient='records'), seconds=T.s(), marks=T.marks, scientific_verdict=None)
    dump(O/'masks/B.json', rec)
    print('WOLFF', json.dumps({k: rec[k] for k in ['B_orig_pct', 'B_view_pct', 'condition_pass_pct', 'median_v', 'median_in_frame']}, ensure_ascii=False), flush=True)
    progress(f'mf5 방법 B 끝: B-원문 살아남은 화소 {rec["B_orig_pct"]:.2f} %, B-시점 {rec["B_view_pct"]:.2f} %, {round(T.s())} 초')

if __name__ == '__main__': main(*sys.argv[1:])
