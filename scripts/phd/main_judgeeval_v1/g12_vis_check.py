"""덧붙임 1 4절: ② 가시성 분석 확인(참값 안 읽음, 판단 값 바꾸지 않음).
1 인공 시험: 평면 하나·카메라 하나(W 61 x H 41), 깊이 지도 넷(면 뒤 D = 1.2 Z, 면 앞 0.8 Z, 면 위 Z, 왼쪽 반 뒤·오른쪽 반 앞)을 COLMAP .bin 꼴로 써서
  judgevis vis(판단 코드의 분류 함수)와 g11_figs.fig2 의 끝점 식(그림 함수)을 모두 돌려 기대와 맞댐. 법선을 카메라 쪽·반대쪽 둘로.
2 실제 패치: fig7_2_examples 본보기 넷 + ②를 거친 정답 영상 패치 하나. 분류마다 영상 셋까지 Z, D, δ, 분류, 카메라 중심, 시선 방향, 그린 끝점, 끝점의 법선 거리, 카메라의 법선 쪽.
3 깊이 지도 읽기: 영상 점 표본 1,000점을 그 화소 깊이로 다시 옮김(깊이 = 카메라 z / 시선 거리 두 해석)과 저장 좌표 거리.
나오는 것: docs/tables/다/t4_*.csv/md, work/ga3/vis_check.json. 사용: GT_STAGE=ga3 g12_vis_check.py"""
from common import *
import pandas as pd
from g11_figs import cams, read_depth, load, CLS
A1 = json.loads((C/'judgeeval_v1_add1.json').read_text()); assert sha(C/'judgeeval_v1_add1.json') == json.loads((C/'judgeeval_v1_add1.lock.json').read_text())['config_sha256'], 'add1 config changed after lock'
TD = D/'tables/다'
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.4f}' if isinstance(x, float) else str(x))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def fig_class_and_end(Rm, tt, K, ref, Dd):
    """g11_figs.fig2 와 같은 식(그대로 옮김)."""
    Y = Rm@ref + tt; Z = Y[2]; cl = 0 if not Dd > 0 else (1 if Dd > 1.01*Z else (2 if Dd < .99*Z else 3)); cc = -Rm.T@tt; dr = ref - cc; dr /= np.linalg.norm(dr); end = cc + dr*Dd*np.linalg.norm(ref - cc)/Z
    return cl, end, Z
def synthetic():
    T = O/'tmp/synth'; T.mkdir(parents=True, exist_ok=True); W, H = 61, 41; fx = fy = 60.; cx, cy = 30., 20.; Rm = np.eye(3); tt = np.zeros(3)   # 카메라 원점, +z 를 봄
    with (T/'cams.bin').open('wb') as f: f.write(struct.pack('<iii', 1, W, H)); f.write(np.r_[Rm.ravel(), tt, fx, fy, cx, cy].astype('<f8').tobytes())
    s = np.array([0., 0., 10.]); rows = []
    maps = {'면 뒤(D = 1.2 Z)': lambda Z: 1.2*Z, '면 앞(D = 0.8 Z)': lambda Z: .8*Z, '면 위(D = Z)': lambda Z: Z}
    for nsign, nname in [(-1, '법선 카메라 쪽'), (1, '법선 반대쪽')]:
        n = np.array([0., 0., nsign]); u = np.array([1., 0., 0.])
        for half, place in [(1.0, '화면 가운데')]:
            for mname, fn in list(maps.items()) + [('왼쪽 반 뒤·오른쪽 반 앞', None)]:
                # 깊이 지도: 평면 z = 10 이므로 화소마다 Z = 10. 줄 우선(raw[row][col]) 으로 씀
                D2 = np.full((H, W), 10., np.float32)
                if fn is not None: D2[:] = fn(10.)
                else: D2[:, :cx.__int__()] = 12.; D2[:, int(cx):] = 8.
                p = T/f'depth_{len(rows)}.bin'; p.write_bytes(f'{W}&{H}&1&'.encode() + D2.astype('<f4').tobytes()); (T/'maps.txt').write_text(f'{p}\t{p}\n')
                for sx, sname in ([(0., '')] if fn is not None else [(-2., '왼쪽 자리'), (2., '오른쪽 자리')]):
                    sp = s + np.array([sx, 0, 0]); pb = T/'p.bin'; np.ascontiguousarray(np.r_[sp, n, u, half][None], '<f8').tofile(pb)
                    subprocess.run([str(VBIN), 'vis', str(T/'cams.bin'), str(T/'maps.txt'), str(pb), '1', str(T/'o.bin'), str(T/'pp.bin')], check=True, stderr=subprocess.DEVNULL)
                    o = np.fromfile(T/'o.bin', '<f8').reshape(-1, 20)[0]
                    # 그림 함수: 중심 화소
                    Y = Rm@sp + tt; cu = int(round(fx*Y[0]/Y[2] + cx)); cv = int(round(fy*Y[1]/Y[2] + cy)); Dd = float(D2[cv, cu])
                    cl, end, Z = fig_class_and_end(Rm, tt, None, sp, Dd); e = end - sp; cam_side = float((-Rm.T@tt - sp)@n)
                    exp = {'면 뒤(D = 1.2 Z)': 1, '면 앞(D = 0.8 Z)': 2, '면 위(D = Z)': 3}.get(mname, 1 if sx < 0 else 2)
                    got = int(np.argmax(o[0:4])) if o[0:4].sum() else 0; gotc = int(np.argmax(o[12:16]))
                    rows.append(dict(법선=nname, 깊이_지도=mname + (f' · {sname}' if sname else ''), 기대=CLS[exp][0], 판단_화소_분류=CLS[got][0], 판단_화소수=' / '.join(f'{CLS[k][0]} {int(o[k])}' for k in range(4)),
                                     판단_중심=CLS[gotc][0], 그림_분류=CLS[cl][0], 그림_끝점_법선거리_m=float(e@n), 카메라_쪽_법선거리_m=cam_side,
                                     그림_끝점_자리='카메라 쪽(면 앞)' if (e@n)*cam_side > 1e-9 else ('면 위' if abs(e@n) < 1e-9 else '카메라 반대쪽(면 뒤)'),
                                     맞음=bool(got == exp and gotc == exp and cl == exp and ((exp == 1 and (e@n)*cam_side < 0) or (exp == 2 and (e@n)*cam_side > 0) or (exp == 3 and abs(e@n) < 1e-6)))))
    return pd.DataFrame(rows)
def real():
    c = cfg(); C_, W, H = cams(); maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]; L = load('LoD2'); meta = json.loads((D/'figures/fig7_2_examples.json').read_text())['examples']
    pos = {int(x): k for k, x in enumerate(L['i'])}; picks = [(e['truth'], pos[e['patch_index']]) for e in meta]
    m = np.flatnonzero((L['J']['r1'] == 2) & (L['J']['J_판 4'] != 2) & (L['t'] == 1)); rng = np.random.default_rng(A1['step2_check']['seed'])   # ② 를 거쳐 ③ 에서 영상이 된 정답 영상 패치
    if len(m): picks.append(('영상(②→③ 영상)', m[rng.integers(len(m))]))
    rows = []; cache = {}; side = []
    for tn, k in picks:
        n = np.nan_to_num(L['n'][k]); ref = L['c'][k] + np.nan_to_num(L['ph'][k])*n; per = {x: 0 for x in range(4)}; sides = []
        for im in range(len(C_)):
            Rm = C_[im, :9].reshape(3, 3); tt = C_[im, 9:12]; Y = Rm@ref + tt
            if Y[2] <= .05: continue
            uu = C_[im, 12]*Y[0]/Y[2] + C_[im, 14]; vv = C_[im, 13]*Y[1]/Y[2] + C_[im, 15]; cu, cv = int(round(uu)), int(round(vv))
            if not (0 <= cu < W and 0 <= cv < H): continue
            if im not in cache: cache[im] = read_depth(maps[im])
            Dd = float(cache[im][cv, cu]); cl, end, Z = fig_class_and_end(Rm, tt, None, ref, Dd); cc = -Rm.T@tt; cs = float((cc - ref)@n); sides.append(cs)
            if per[cl] >= 3: continue
            per[cl] += 1; dr = (ref - cc)/np.linalg.norm(ref - cc)
            rows.append(dict(본보기=tn, 패치=int(L['i'][k]), 건물=L['b'][k].replace('DEBY_LOD2_', ''), 지붕벽=KN[int(L['kind'][k])], 영상=im, 화소_열=cu, 화소_줄=cv, Z_m=Z, D_m=Dd if Dd > 0 else np.nan, delta_m=.01*Z,
                             분류=CLS[cl][0], 카메라_x=cc[0], 카메라_y=cc[1], 카메라_z=cc[2], 시선_x=dr[0], 시선_y=dr[1], 시선_z=dr[2], 끝점_x=end[0] if Dd > 0 else np.nan, 끝점_y=end[1] if Dd > 0 else np.nan, 끝점_z=end[2] if Dd > 0 else np.nan,
                             끝점_법선거리_m=float((end - ref)@n) if Dd > 0 else np.nan, 카메라_법선거리_m=cs, 끝점_쪽=('' if not Dd > 0 else ('카메라 쪽' if ((end - ref)@n)*cs > 0 else '카메라 반대쪽'))))
        side.append(dict(본보기=tn, 패치=int(L['i'][k]), 지붕벽=KN[int(L['kind'][k])], 법선_z=float(n[2]), 본_영상=len(sides), 카메라가_법선_양쪽인_영상=int((np.array(sides) > 0).sum()), 카메라가_법선_음쪽인_영상=int((np.array(sides) < 0).sum())))
    return pd.DataFrame(rows), pd.DataFrame(side)
def mapread():
    c = cfg(); C_, W, H = cams(); names = json.loads(inp('image_split').read_text())['train']; maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]; rng = np.random.default_rng(A1['step2_check']['seed'])
    out = []
    for t in ['6910_53361', '6907_53359']:
        X = np.load(inp('image_points', tile=t), mmap_mode='r'); vw = np.load(inp('image_point_view', tile=t), mmap_mode='r'); px = np.load(inp('image_point_pixel', tile=t), mmap_mode='r')
        s = np.sort(rng.choice(len(X), 500, replace=False)); cache = {}
        for i in s:
            im = int(vw[i]); p = int(px[i]); row, col = divmod(p, W)
            if im not in cache: cache[im] = read_depth(maps[im])
            Dd = float(cache[im][row, col]); Rm = C_[im, :9].reshape(3, 3); tt = C_[im, 9:12]; ray = np.array([(col - C_[im, 14])/C_[im, 12], (row - C_[im, 15])/C_[im, 13], 1.])
            Xz = Rm.T@(ray*Dd - tt); Xr = Rm.T@(ray/np.linalg.norm(ray)*Dd - tt); Xt = Rm.T@(np.array([(row - C_[im, 14])/C_[im, 12], (col - C_[im, 15])/C_[im, 13], 1.])*Dd - tt)
            out.append(dict(tile=t, z=np.linalg.norm(Xz - X[i]), ray=np.linalg.norm(Xr - X[i]), swapped=np.linalg.norm(Xt - X[i])))
    df = pd.DataFrame(out)
    return pd.DataFrame([dict(해석=nm, 표본=len(df), 중앙값_m=float(df[k].median()), 최대_m=float(df[k].max()), 안_1mm_비율=float((df[k] < 1e-3).mean())) for k, nm in [('z', '깊이 = 카메라 z, 화소 (열, 줄) = (u, v)'), ('ray', '깊이 = 시선 거리'), ('swapped', '화소 열·줄 바꿈')]])
def main():
    T = Timer(); build_vis(); s = synthetic(); write('t4_1_synthetic', s, '② 인공 시험: 카메라 원점·+z, 평면 z = 10, 칸 2 x 2 m. 판단 = judgevis vis(화소·중심), 그림 = g11_figs.fig2 의 끝점 식. 끝점 자리: 카메라 쪽 = 면 앞')
    r, sd = real(); write('t4_2_real_pixels', r, '② 실제 패치(fig7_2 본보기 넷 + ②→③ 영상 하나): 패치 중심 화소, 분류마다 영상 셋까지. 끝점 법선 거리 = (끝점 − 패치 중심)·n, 카메라 법선 거리 = (카메라 중심 − 패치 중심)·n')
    write('t4_2_normal_side', sd, '본보기 패치의 법선 방향과 카메라 쪽: 카메라가 법선 음쪽이면 단면 그림의 위·아래가 카메라 기준으로 뒤집혀 보인다')
    mr = mapread(); write('t4_3_map_read', mr, '깊이 지도 읽기: 영상 점 1,000점을 그 화소 깊이로 다시 옮긴 점과 저장 좌표의 거리')
    rec = dict(at=now(), synthetic_all_ok=bool(s['맞음'].all()), real_rows=len(r), map_read=mr.to_dict('records'), normal_side=sd.to_dict('records'), seconds=T.s(), scientific_verdict=None)
    dump(O/'work'/STAGE/'vis_check.json', rec); progress(f'4절 ② 확인: 인공 시험 모두 맞음 {rec["synthetic_all_ok"]}, {T.s():.0f} s'); print(json.dumps(jsafe(rec), ensure_ascii=False)[:3000])
if __name__ == '__main__': main()
