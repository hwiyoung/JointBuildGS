"""덧붙임 1 방법 A2 (세션이 정한 판): 화소마다 일치 시점 수 c·지나쳐 봄 f·앞에 다른 면 o·본 영상 m (a2_count.cpp). 살아남음 = c ≥ 5 (방법 A 의 min_num_pixels 5).
볼 영상 = 깊이 지도가 있는 모든 학습 영상(819) 가운데 화면 안에 드는 것(줄이지 않음). 참값 읽지 않음. CPU.
사용: mf12_A2.py [threads]"""
import sys, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *

def main(threads='32'):
    cfg(); T = Timer(); names = json.loads((W/'image_split.json').read_text())['train']; rows = poses(WS/'sparse/images.bin'); K = intrinsics()
    A2 = O/'a2'; A2.mkdir(exist_ok=True); tmp = O/'tmp/a2'; tmp.mkdir(parents=True, exist_ok=True)
    cam = np.zeros((len(names), 12))
    for i, nm in enumerate(names): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WS/'stereo/depth_maps'/f'{nm}.geometric.bin') for nm in names) + '\n')
    (tmp/'normals.txt').write_text('\n'.join(str(WS/'stereo/normal_maps'/f'{nm}.geometric.bin') for nm in names) + '\n')
    exe = O/'bin/a2_count'; subprocess.run(['g++', '-O3', '-fopenmp', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/a2_count.cpp', '-o', str(exe)], check=True); T.mark('build')
    subprocess.run([str(exe), str(len(names)), str(Wd), str(H), *map(repr, [K['fx'], K['fy'], K['cx'], K['cy']]), str(tmp/'depths.txt'), str(tmp/'normals.txt'), str(tmp/'cams.bin'),
                    str(A2/'px'), str(A2/'stats.txt'), str(threads)], check=True); T.mark('count')
    n = len(names); c = np.memmap(A2/'px_c.u16', dtype='<u2', mode='r', shape=(n, H*Wd))
    none = load_mask('none').reshape(n, -1); tot = int(none.sum())
    a2 = np.zeros((n, H*Wd), bool); hist = {}; agg = dict(c2=0, c5=0)
    for i in range(n):
        ci = np.asarray(c[i]); v = none[i]; assert not (ci[~v] > 0).any() and (ci[v] >= 1).all()
        a2[i] = v & (ci >= 5); agg['c2'] += int((ci[v] >= 2).sum()); agg['c5'] += int(a2[i].sum())
        for k, cnt in zip(*np.unique(np.minimum(ci[v], 60), return_counts=True)): hist[int(k)] = hist.get(int(k), 0) + int(cnt)
    save_mask('A2', a2.reshape(n, H, Wd)); T.mark('mask')
    def q(name):
        x = np.memmap(A2/f'px_{name}.u16', dtype='<u2', mode='r', shape=(n, H*Wd)); s = 0; ss = 0
        for i in range(0, n, 50): xi = np.asarray(x[i:i+50])[none[i:i+50]].astype(np.int64); s += xi.sum(); ss += len(xi)
        return s/ss
    import pandas as pd
    st = pd.read_csv(A2/'stats.txt', sep=' ')
    rec = dict(at=now(), method='A2 화소마다 일치 시점 수 (세션이 정한 판, COLMAP 명령 아님)', rule=dict(depth_rel_tol=0.01, reproj_px=2.0, normal_deg=10.0, survive='c >= 5', views='화면 안의 모든 학습 영상(819 중), 줄이지 않음; 영상 고르기는 7점마다 표본이 하나라도 화면 안이면 봄'),
               pixels_valid=tot, pixels_survived=agg['c5'], survived_pct=100*agg['c5']/tot, check_c_ge2_pct=100*agg['c2']/tot,
               mean_c=q('c'), mean_f=q('f'), mean_o=q('o'), mean_m=q('m'), mean_q=q('q'), c_hist_capped60=hist,
               per_image_median_c_quantiles={str(p): float(np.quantile(st['median_c'], p)) for p in [0, .1, .5, .9, 1]}, seconds=T.s(), marks=T.marks, GT_read=False, scientific_verdict=None)
    dump(O/'masks/A2.json', rec); print('A2', json.dumps(jsafe({k: rec[k] for k in ['survived_pct', 'check_c_ge2_pct', 'mean_c', 'mean_f', 'mean_o', 'mean_m', 'mean_q', 'seconds']}), ensure_ascii=False), flush=True)
    progress(f'mf12 A2 끝: 살아남은 화소 {rec["survived_pct"]:.2f} % (c≥5), c≥2 {rec["check_c_ge2_pct"]:.2f} %, {round(T.s())} 초')

if __name__ == '__main__': main(*sys.argv[1:])
