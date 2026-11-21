"""덧붙임 2 1절: 패치마다 원통 안 지금 점의 A2 본 판(1 %) 값 더 — m 중앙값, c/m 중앙값, o/m 평균, c 10·90 % 값, '2c ≥ m 또는 c ≥ 5' 비율(2.3절).
새 화소 셈 없음(a2/px_{c,f,o,m}.u16 을 읽음). 참값 읽지 않음. CPU. 원통 고르기는 mf13 과 같음.
검산: 원통 점 수 = patch/none raw_n, c 중앙값·c≥5 비율·f/(c+f) 평균 = a2_patch(덧붙임 1) 값.
사용: mf17_A2_patch2.py <tile> [...]  (MF_CPUS 만큼 구역을 함께)"""
import sys, subprocess
from multiprocessing import Pool
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC
KEYS = ['raw_n', 'c_median', 'c_ge5_frac', 'f_ratio_mean', 'm_median', 'cm_median', 'om_mean', 'c_p10', 'c_p90', 'half_or5_frac', 'm_sum']
SRC = O/'a2'; D = O/'a2_patch2'; EXE = O/'bin/cyl_attr2'; NIMG = 819

def one(t):
    if (D/f'{t}.json').exists(): return None
    T = Timer(); FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'
    P = WI/'points'/t; X = np.load(P/'mvs_a_xyz.npy', mmap_mode='r'); assert X.dtype == np.dtype('<f4'); V = np.load(P/'mvs_a_view.npy'); pix = np.load(O/'pixmap'/f'{t}.npy')
    mm = {k: np.memmap(SRC/f'px_{k}.u16', dtype='<u2', mode='r', shape=(NIMG, H*Wd)) for k in 'cfom'}
    vals = {k: np.empty(len(V), '<u2') for k in 'cfom'}
    order = np.argsort(V, kind='stable'); cuts = np.flatnonzero(np.diff(V[order])) + 1
    for seg in np.split(order, cuts):
        v = int(V[seg[0]])
        for k in 'cfom': vals[k][seg] = np.asarray(mm[k][v])[pix[seg]]
    assert (vals['c'] >= 1).all() and (vals['m'] >= vals['c']).all(), 'c ≥ 1, m ≥ c'
    attr = FAST/f'a2attr2_{t}.u16'; np.c_[vals['c'], vals['f'], vals['o'], vals['m']].astype('<u2').tofile(attr)
    rec = dict(at=now(), tile=t, points=int(len(V)))
    with open(P/'mvs_a_xyz.npy', 'rb') as f: ver = np.lib.format.read_magic(f); np.lib.format._read_array_header(f, ver); off = f.tell()
    out = {}
    for prior in ['LoD2', 'ALS']:
        gp = JC/'geometry_raw'/f'{t}__{prior}.npz'
        if not gp.exists(): continue
        g = loadz(gp, ['centre', 'normal', 'kind', 'patch_id']); kind = g['kind']
        Hh = np.where(kind == 1, 10., 5.); R = np.where((kind == 2) & (prior == 'LoD2'), .125, .075)
        cores = FAST/f'a2cores2_{t}_{prior}.bin'; np.c_[g['centre'], np.nan_to_num(g['normal']), Hh, R].astype('<f8').tofile(cores); res = FAST/f'a2res2_{t}_{prior}.bin'
        subprocess.run([str(EXE), str(P/'mvs_a_xyz.npy'), str(off), str(len(V)), str(attr), str(cores), str(res)], check=True, stderr=subprocess.DEVNULL)
        r = np.fromfile(res, '<f8').reshape(-1, len(KEYS)); cores.unlink(); res.unlink()
        bad = ~np.isfinite(g['normal']).all(1); r[bad, 0] = -1; r[bad, 1:] = np.nan
        ref = loadz(O/'a2_patch'/f'{t}.npz')
        assert np.array_equal(ref[f'{prior}__patch_id'], g['patch_id'])
        rec[f'{prior}_patches'] = len(kind); rec[f'{prior}_raw_n_equal_a2'] = int((r[:, 0].astype(int) == ref[f'{prior}__raw_n']).sum())
        for j, k in [(1, 'c_median'), (2, 'c_ge5_frac'), (3, 'f_ratio_mean')]:
            a, b = r[:, j], ref[f'{prior}__{k}']; same = (np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= 1e-9)
            rec[f'{prior}_{k}_equal_a2'] = int(same.sum())
        out[f'{prior}__patch_id'] = g['patch_id']
        for j, k in enumerate(KEYS): out[f'{prior}__{k}'] = r[:, j].astype(int) if k == 'raw_n' else r[:, j]
    attr.unlink(); savez(D/f'{t}.npz', **out); rec.update(seconds=T.s()); dump(D/f'{t}.json', rec); return rec

def main(tiles_):
    MC.cfg(); T = Timer(); D.mkdir(exist_ok=True)
    subprocess.run(['g++', '-O3', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/cyl_attr2.cpp', '-o', str(EXE)], check=True)
    with Pool(int(os.environ.get('MF_CPUS', '4'))) as p:
        for rec in p.imap_unordered(one, tiles_):
            if rec: print('A2PATCH2', json.dumps(jsafe(rec)), flush=True)
    MC.progress(f'mf17 A2 패치 값 더(덧붙임 2) {len(tiles_)} 구역 끝, {round(T.s())} 초')

if __name__ == '__main__': main(sys.argv[1:])
