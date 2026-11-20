"""덧붙임 1 2절: 패치마다 원통 안 지금 점(면 찾기 전 원통 안 모든 점 = raw_n 의 점들)의 A2 값 — c 중앙값, c ≥ 5 비율, f/(c+f) 평균. 참값 읽지 않음. CPU.
원통 고르기는 mf2 와 같음(지붕 H 10 · 나머지 5 m, LoD2 벽 R 0.125 · 나머지 0.075 m). 점검: 여기서 센 원통 점 수 = patch/none 의 raw_n.
사용: mf13_A2_patch.py <tile> [...]"""
import sys, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC

def main(tiles_):
    MC.cfg(); n = 819; T = Timer(); SRC = O/os.environ.get('MF_A2DIR', 'a2'); D = O/os.environ.get('MF_A2OUT', 'a2_patch'); D.mkdir(exist_ok=True)   # 회신 1 4절: 문턱마다 다른 폴더
    exe = O/'bin/cyl_attr'
    if not exe.exists(): subprocess.run(['g++', '-O3', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/cyl_attr.cpp', '-o', str(exe)], check=True)
    C = np.memmap(SRC/'px_c.u16', dtype='<u2', mode='r', shape=(n, H*Wd)); F = np.memmap(SRC/'px_f.u16', dtype='<u2', mode='r', shape=(n, H*Wd))
    FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'
    for t in tiles_:
        if (D/f'{t}.json').exists(): continue
        P = WI/'points'/t; X = np.load(P/'mvs_a_xyz.npy', mmap_mode='r'); assert X.dtype == np.dtype('<f4'); V = np.load(P/'mvs_a_view.npy'); pix = np.load(O/'pixmap'/f'{t}.npy')
        cv = np.empty(len(V), '<u2'); fv = np.empty(len(V), '<u2')
        order = np.argsort(V, kind='stable'); Vs = V[order]; cuts = np.flatnonzero(np.diff(Vs)) + 1
        for seg in np.split(order, cuts):
            v = int(V[seg[0]]); ci = np.asarray(C[v]); fi = np.asarray(F[v]); cv[seg] = ci[pix[seg]]; fv[seg] = fi[pix[seg]]
        assert (cv >= 1).all(), '지금 점의 화소에 c 가 없음'
        attr = FAST/f'a2attr_{D.name}_{t}.u16'; np.c_[cv, fv].astype('<u2').tofile(attr)
        rec = dict(at=now(), tile=t, points=int(len(V)))
        with open(P/'mvs_a_xyz.npy', 'rb') as f: ver = np.lib.format.read_magic(f); np.lib.format._read_array_header(f, ver); off = f.tell()
        out = {}
        for prior in ['LoD2', 'ALS']:
            gp = JC/'geometry_raw'/f'{t}__{prior}.npz'
            if not gp.exists(): continue
            g = loadz(gp, ['centre', 'normal', 'kind', 'patch_id']); kind = g['kind']
            Hh = np.where(kind == 1, 10., 5.); R = np.where((kind == 2) & (prior == 'LoD2'), .125, .075)
            cores = FAST/f'a2cores_{D.name}_{t}_{prior}.bin'; np.c_[g['centre'], np.nan_to_num(g['normal']), Hh, R].astype('<f8').tofile(cores); res = FAST/f'a2res_{D.name}_{t}_{prior}.bin'
            subprocess.run([str(exe), str(P/'mvs_a_xyz.npy'), str(off), str(len(V)), str(attr), str(cores), str(res)], check=True, stderr=subprocess.DEVNULL)
            r = np.fromfile(res, '<f8').reshape(-1, 4); cores.unlink(); res.unlink()
            bad = ~np.isfinite(g['normal']).all(1); r[bad, 0] = -1
            ref = loadz(O/'patch/none'/f'{t}.npz', [f'{prior}__raw_n', f'{prior}__patch_id'])
            assert np.array_equal(ref[f'{prior}__patch_id'], g['patch_id'])
            eq = int((r[:, 0].astype(int) == ref[f'{prior}__raw_n']).sum())
            out.update({f'{prior}__patch_id': g['patch_id'], f'{prior}__raw_n': r[:, 0].astype(int), f'{prior}__c_median': r[:, 1], f'{prior}__c_ge5_frac': r[:, 2], f'{prior}__f_ratio_mean': r[:, 3]})
            rec[f'{prior}_patches'] = len(kind); rec[f'{prior}_raw_n_equal_none'] = eq
        attr.unlink(); savez(D/f'{t}.npz', **out); rec.update(seconds=T.s()); dump(D/f'{t}.json', rec); print('A2PATCH', json.dumps(jsafe(rec)), flush=True)

if __name__ == '__main__': main(sys.argv[1:])
