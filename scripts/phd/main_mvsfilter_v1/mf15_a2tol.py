"""회신 1 (11/20 23시) 1·4절. 참값 읽지 않음(처음 상태 pc 는 패치 무리 나눔에만). CPU. 값을 고르지 않음.
단계 count : a2_count 를 깊이 일치 문턱 1 %(덧붙임 본 판)·0.5·0.2·0.1 %(세션이 정한 판, COLMAP 기본값 아님)로 돌림. 되비춤 2 화소·법선 10°·c ≥ 5 그대로.
             1 % 판의 c·f·o·m·q 가 앞 판(a2/)과 바이트까지 같은지 확인. 마스크 A2d0p5·A2d0p2·A2d0p1. 화소 c = 1 나눔(1절).
단계 hist  : 구역마다 원통 안 점의 막대그림 — (가) c = 1 나눔 부호, (나) 카메라까지 깊이(0.25 m 칸) — 차이가 유의한 패치를 면 x 처음 상태 무리로(cyl_hist.cpp).
단계 table : t5_A2_diag, t5_A2_scale, t5_A2_tol.
사용: mf15_a2tol.py count | hist <tile> [...] | table"""
import sys, os, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import a1_variants as A1
import pandas as pd
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mfcommon as MC
TOLS = [(0.01, '1p0'), (0.005, '0p5'), (0.002, '0p2'), (0.001, '0p1')]
NIMG = 819; HH, WW = MC.H, MC.Wd
DIAG = ['c ≥ 2', 'c = 1 · 본 다른 영상 없음(m = 1)', 'c = 1 · 깊이 1 % 안 영상 있음 · 되비춤 2 화소에서만 빠짐', 'c = 1 · 깊이 1 % 안 영상 있음 · 법선 10° 에서만 빠짐',
        'c = 1 · 깊이 1 % 안 영상 있음 · 둘 다(한 영상에서 둘 다 못 넘음, 또는 영상마다 까닭이 섞임)', 'c = 1 · 앞에 다른 면·지나쳐 봄만']
ZBIN = .25; KZ = 1200
STATES = [(0, '두 자료 모두 유효'), (1, '사전정보 오류'), (2, '영상 깊이 오류'), (4, '영상 깊이 결측'), (None, '그 밖(네 경우 밖·처음 상태 없음)')]
DIR = lambda tag: MC.O/'a2tol'/f't{tag}'

def diag_code(c, m, q, qr, qn, qb):
    k = np.zeros(len(c), np.uint16); one = c == 1
    k[one & (m == 1)] = 1; hq = one & (m > 1) & (q >= 1)
    k[hq & (qn == 0) & (qb == 0)] = 2; k[hq & (qr == 0) & (qb == 0)] = 3; k[hq & ~(((qn == 0) & (qb == 0)) | ((qr == 0) & (qb == 0)))] = 4
    k[one & (m > 1) & (q == 0)] = 5; return k

def count():
    MC.cfg(); T = Timer(); names = json.loads((MC.W/'image_split.json').read_text())['train']; tmp = MC.O/'tmp/a2'; K = MC.intrinsics(); exe = MC.O/'bin/a2_count_r1'
    subprocess.run(['g++', '-O3', '-fopenmp', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/a2_count.cpp', '-o', str(exe)], check=True)
    none = MC.load_mask('none').reshape(NIMG, -1); tot = int(none.sum()); REC = []
    for tol, tag in TOLS:
        D = DIR(tag); D.mkdir(parents=True, exist_ok=True)
        if not (D/'done.json').exists():
            subprocess.run([str(exe), str(NIMG), str(WW), str(HH), *map(repr, [K['fx'], K['fy'], K['cx'], K['cy']]), str(tmp/'depths.txt'), str(tmp/'normals.txt'), str(tmp/'cams.bin'), str(D/'px'), str(D/'stats.txt'),
                            os.environ.get('MF_CPUS', '32'), repr(tol)], check=True, stderr=subprocess.DEVNULL)
            dump(D/'done.json', dict(at=now(), tol=tol))
        c = np.memmap(D/'px_c.u16', dtype='<u2', mode='r', shape=(NIMG, HH*WW)); s5 = s2 = 0; same = None
        if tag == '1p0':
            same = {}
            for k in 'cfomq':
                a = np.memmap(MC.O/'a2'/f'px_{k}.u16', dtype='<u2', mode='r'); b = np.memmap(D/f'px_{k}.u16', dtype='<u2', mode='r'); same[k] = bool(all(np.array_equal(a[i:i+50_000_000], b[i:i+50_000_000]) for i in range(0, len(a), 50_000_000)))
            assert all(same.values()), same
            qq = {k: np.memmap(D/f'px_{k}.u16', dtype='<u2', mode='r', shape=(NIMG, HH*WW)) for k in ['m', 'q', 'qr', 'qn', 'qb']}; dc = np.zeros(len(DIAG), np.int64); qsum_ok = True
            for i in range(NIMG):
                v = none[i]; ci = np.asarray(c[i])[v]; a = {k: np.asarray(x[i])[v] for k, x in qq.items()}; qsum_ok &= bool(np.array_equal(a['q'], a['qr'] + a['qn'] + a['qb']))
                dc += np.bincount(diag_code(ci, a['m'], a['q'], a['qr'], a['qn'], a['qb']), minlength=len(DIAG))
            dump(MC.O/'masks/A2_diag_pixels.json', dict(at=now(), codes=DIAG, counts=dc.tolist(), pct_of_valid=(100*dc/tot).tolist(), q_equals_qr_qn_qb=qsum_ok, scientific_verdict=None))
            print('DIAG', [round(x, 2) for x in (100*dc/tot)], qsum_ok, flush=True)
        mk = np.zeros((NIMG, HH*WW), bool)
        for i in range(NIMG):
            ci = np.asarray(c[i]); mk[i] = none[i] & (ci >= 5); s5 += int(mk[i].sum()); s2 += int((ci[none[i]] >= 2).sum())
        if tag != '1p0': MC.save_mask(f'A2d{tag}', mk.reshape(NIMG, HH, WW))
        else: assert np.array_equal(np.packbits(mk, axis=1), np.load(MC.O/'masks/A2.npy'))
        REC.append(dict(tol=tol, tag=tag, method='A2' if tag == '1p0' else f'A2d{tag}', survived_pct=100*s5/tot, c_ge2_pct=100*s2/tot, same_as_a2=same))
        for k in (['o', 'q', 'qr', 'qn', 'qb', 'm'] if tag != '1p0' else ['c', 'f', 'o']):   # 줄인 판은 c·f 만 남김(패치 값), 본 판은 a2/ 에 c·f·o 가 있음
            (D/f'px_{k}.u16').unlink(missing_ok=True)
        print('TOL', REC[-1], round(T.s()), flush=True)
    dump(MC.O/'masks/A2_tol.json', dict(at=now(), rows=REC, note='깊이 일치 문턱만 바꿈. 1 % = 덧붙임 본 판(a2/ 와 같음), 나머지는 세션이 정한 판', seconds=T.s(), scientific_verdict=None))

def hist(tiles_):
    MC.cfg(); D1 = DIR('1p0'); out = MC.O/'a2tol/hist'; out.mkdir(parents=True, exist_ok=True); exe = MC.O/'bin/cyl_hist'
    if not exe.exists(): subprocess.run(['g++', '-O3', '-std=c++17', '/repo/scripts/phd/main_mvsfilter_v1/cyl_hist.cpp', '-o', str(exe)], check=True)
    arr = {k: np.memmap((MC.O/'a2' if k == 'c' else D1)/f'px_{k}.u16', dtype='<u2', mode='r', shape=(NIMG, HH*WW)) for k in ['c', 'm', 'q', 'qr', 'qn', 'qb']}
    names = json.loads((MC.W/'image_split.json').read_text())['train']; rows = MC.poses(MC.WS/'sparse/images.bin'); RT = np.array([np.r_[MC.rotation(rows[nm][0])[2], rows[nm][1][2]] for nm in names])
    D = {p: A1.load(p) for p in ['LoD2', 'ALS']}; SIG = {p: np.load(MC.O/'judge'/p/'patch_none.npz')['sig'] for p in D}; PC = {p: np.load(JABL/'addendum2'/f'patch_case_{p}.npz')['pc'].astype(int) for p in D}
    FAST = Path('/fast') if Path('/fast').is_dir() else MC.O/'tmp'
    for t in tiles_:
        if (out/f'{t}.npz').exists(): continue
        P = MC.WI/'points'/t; X = np.load(P/'mvs_a_xyz.npy', mmap_mode='r'); V = np.load(P/'mvs_a_view.npy'); pix = np.load(MC.O/'pixmap'/f'{t}.npy')
        with open(P/'mvs_a_xyz.npy', 'rb') as f: ver = np.lib.format.read_magic(f); np.lib.format._read_array_header(f, ver); off = f.tell()
        vals = {k: np.empty(len(V), '<u2') for k in arr}; z = np.empty(len(V), np.float32)
        order = np.argsort(V, kind='stable'); Vs = V[order]; cuts = np.flatnonzero(np.diff(Vs)) + 1
        for seg in np.split(order, cuts):
            v = int(V[seg[0]])
            for k, a in arr.items(): vals[k][seg] = np.asarray(a[v])[pix[seg]]
            xs = np.asarray(X[np.sort(seg)]).astype(np.float64); z[np.sort(seg)] = xs @ RT[v, :3] + RT[v, 3]
        dmap = MC.read_depth(MC.WS/'stereo/depth_maps'/f'{names[int(V[0])]}.geometric.bin'); s0 = np.flatnonzero(V == V[0])[:1000]
        rel = np.abs(z[s0] - dmap.ravel()[pix[s0]])/dmap.ravel()[pix[s0]]; assert np.nanmax(rel) < 1e-4, ('깊이 다시 냄', float(np.nanmax(rel)))
        codes = {'diag': diag_code(vals['c'], vals['m'], vals['q'], vals['qr'], vals['qn'], vals['qb']), 'depth': np.minimum(np.floor(z/ZBIN), KZ - 1).astype('<u2')}
        res = {}
        for name_, code in codes.items():
            cf = FAST/f'h_{name_}_{t}.u16'; code.astype('<u2').tofile(cf); Kk = len(DIAG) if name_ == 'diag' else KZ
            for prior, d in D.items():
                gp = JC/'geometry_raw'/f'{t}__{prior}.npz'
                if not gp.exists(): continue
                ti = list(d['tiles']).index(t); m = np.flatnonzero(d['tile'] == ti); g = loadz(gp, ['centre', 'normal', 'kind', 'patch_id']); assert np.array_equal(g['patch_id'], d['patch_id'][m])
                kind = g['kind']; si = np.where(kind == 1, 0, 1); pc = PC[prior][m]; st = np.full(len(m), 4); [st.__setitem__(pc == s_, j) for j, (s_, _) in enumerate(STATES[:4])]
                grp = np.where(SIG[prior][m] & np.isin(kind, [1, 2]), si*5 + st, -1)
                cores = FAST/f'h_{name_}_{t}_{prior}.bin'; np.c_[g['centre'], np.nan_to_num(g['normal']), np.where(kind == 1, 10., 5.), np.where((kind == 2) & (prior == 'LoD2'), .125, .075), grp].astype('<f8').tofile(cores)
                rb = FAST/f'h_{name_}_{t}_{prior}.out'
                subprocess.run([str(exe), str(P/'mvs_a_xyz.npy'), str(off), str(len(V)), str(cf), str(Kk), str(cores), '10', str(rb)], check=True, stderr=subprocess.DEVNULL)
                res[f'{prior}__{name_}'] = np.fromfile(rb, '<f8').reshape(10, Kk); cores.unlink(); rb.unlink()
            cf.unlink()
        np.savez(out/f'{t}.npz', **res); print('HIST', t, flush=True)

def table():
    MC.cfg(); T_ = Path('/docs/tables'); f1 = lambda v: '' if v is None or not np.isfinite(v) else f'{v:.1f}'
    px = json.loads((MC.O/'masks/A2_diag_pixels.json').read_text()); tol = json.loads((MC.O/'masks/A2_tol.json').read_text())
    H_ = {}
    for f in sorted((MC.O/'a2tol/hist').glob('*.npz')):
        z = np.load(f)
        for k in z.files: H_[k] = H_.get(k, 0) + z[k]
    fx = MC.intrinsics()['fx']; ROWS = []; SC = []
    L = ['# t5_A2_diag', '', '회신 1 1절. 방법 A2(세션 판)에서 c = 1(자기 말고 일치 시점 없음)인 화소를 나눔. "되비춤에서만" = 깊이 1 % 안이었던 영상들이 모두 되비춤 2 화소만 못 넘음, "법선에서만" = 모두 법선 10° 만 못 넘음, "둘 다" = 한 영상에서 둘 다 못 넘었거나 영상마다 까닭이 섞임. 값은 바꾸지 않음(c ≥ 2 = 86.8 % 그대로).', '', 'scientific_verdict: null', '',
         '## 화소 전체 (유효 깊이 화소 가운데 %)', '', '| 나눔 | 화소 % |', '|---|---|']
    for nm, p in zip(px['codes'], px['pct_of_valid']): L.append(f'| {nm} | {p:.2f} |')
    L += ['', '## 차이가 유의한 패치의 원통 안 점 (처음 상태마다, 점 가운데 %; 패치가 겹치면 패치마다 셈)', '', '| 사전 정보 | 면 | 처음 상태 | 원통 안 점 | ' + ' | '.join(DIAG) + ' |', '|---|---|---|---|' + '---|'*len(DIAG)]
    for prior, surfs in [('LoD2', ['지붕', '벽']), ('ALS', ['지붕'])]:
        h = H_[f'{prior}__diag']
        for si, sn in enumerate(surfs):
            for j, (s_, stn) in enumerate(STATES):
                row = h[si*5 + j]; tot = row.sum(); r = dict(prior=PN[prior], surface=sn, state=stn, points=int(tot), **{nm: 100*row[k]/tot if tot else np.nan for k, nm in enumerate(DIAG)}); ROWS.append(r)
                L.append(f"| {PN[prior]} | {sn} | {stn} | {int(tot):,} | " + ' | '.join(f1(r[nm]) for nm in DIAG) + ' |')
    (T_/'t5_A2_diag.md').write_text('\n'.join(L) + '\n'); pd.DataFrame(ROWS).to_csv(T_/'t5_A2_diag.csv', index=False)
    dump(T_/'t5_A2_diag.json', dict(pixels=px, cylinder_rows=json.loads(pd.DataFrame(ROWS).to_json(orient='records', force_ascii=False)), scientific_verdict=None))
    L = ['# t5_A2_scale', '', f'회신 1 4절. 차이가 유의한 패치의 원통 안 점(화소)에서 그 영상 카메라까지 깊이 z 의 10 / 50 / 90 % 값(0.25 m 칸 막대그림에서), 그 1 %, 깊이 지도 한 화소의 크기(= z / fx, fx = {fx:.1f} — max_image_size 1024 의 깊이 지도). '
         '한 화소 크기는 시선에 수직인 면 기준. 패치가 겹치면 패치마다 셈.', '', 'scientific_verdict: null', '', '| 사전 정보 | 면 | 처음 상태 | 원통 안 점 | 깊이 10 / 50 / 90 % (m) | 그 1 % (m) | 한 화소 (m) |', '|---|---|---|---|---|---|---|']
    def q_of(row, qs):
        cs = np.cumsum(row); tot = cs[-1]; return [((np.searchsorted(cs, q*tot) + .5)*ZBIN) for q in qs]
    for prior, surfs in [('LoD2', ['지붕', '벽']), ('ALS', ['지붕'])]:
        h = H_[f'{prior}__depth']
        for si, sn in enumerate(surfs):
            for j, (s_, stn) in list(enumerate(STATES)) + [(None, (None, '모두'))]:
                row = h[si*5:(si + 1)*5].sum(0) if j is None else h[si*5 + j]; tot = row.sum()
                if not tot: continue
                qv = q_of(row, [.1, .5, .9]); r = dict(prior=PN[prior], surface=sn, state=stn, points=int(tot), z_q10_m=qv[0], z_q50_m=qv[1], z_q90_m=qv[2]); SC.append(r)
                L.append(f"| {PN[prior]} | {sn} | {stn} | {int(tot):,} | {' / '.join(f'{x:.1f}' for x in qv)} | {' / '.join(f'{.01*x:.2f}' for x in qv)} | {' / '.join(f'{x/fx:.3f}' for x in qv)} |")
    (T_/'t5_A2_scale.md').write_text('\n'.join(L) + '\n'); pd.DataFrame(SC).to_csv(T_/'t5_A2_scale.csv', index=False); dump(T_/'t5_A2_scale.json', dict(rows=SC, fx=fx, bin_m=ZBIN, scientific_verdict=None))
    L = ['# t5_A2_tol', '', '회신 1 4절. 판 A2-깊이: 깊이 일치 문턱만 바꿈(되비춤 2 화소, 법선 10°, c ≥ 5 그대로). 1 % = 덧붙임 본 판, 0.5·0.2·0.1 % = 세션이 정한 판(COLMAP 기본값 아님). 고르지 않음.', '', 'scientific_verdict: null', '', '| 깊이 일치 문턱 | 판 | 살아남은 화소 % (c ≥ 5) | c ≥ 2 화소 % |', '|---|---|---|---|']
    for r in tol['rows']: L.append(f"| {100*r['tol']:g} % | {r['method']}{' (본 판)' if r['tag'] == '1p0' else ' (세션 판)'} | {r['survived_pct']:.1f} | {r['c_ge2_pct']:.1f} |")
    (T_/'t5_A2_tol.md').write_text('\n'.join(L) + '\n'); dump(T_/'t5_A2_tol.json', dict(rows=tol['rows'], scientific_verdict=None))
    print('\n'.join(L), flush=True)

if __name__ == '__main__':
    if sys.argv[1] == 'count': count()
    elif sys.argv[1] == 'hist': hist(sys.argv[2:])
    else: table()
