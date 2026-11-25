"""③ 점검(진단만, 판정에 안 씀): 시작 점 표본에서 겹침 영상마다 깊이·법선 조건을 따로 셈."""
from common import *
WS = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/mvs/full'
def rmap(p, ch):
    raw = Path(p).read_bytes(); end = 0
    for _ in range(3): end = raw.find(b'&', end, 100) + 1
    w, h, c = map(int, raw[:end].split(b'&')[:3]); a = np.frombuffer(raw, '<f4', offset=end, count=w*h*c).reshape((c, w, h)).transpose(2, 1, 0); return a[..., 0] if c == 1 else a
def main():
    cams = np.fromfile(VIS/'cams.bin', dtype='<i4', count=3); NI, W, H = cams; C = np.fromfile(VIS/'cams.bin', dtype='<f8', offset=12).reshape(NI, 16)
    ov = np.fromfile(VIS/'overlap.bin', dtype='<i4', offset=8).reshape(NI, -1); maps = [l.split('\t') for l in (VIS/'maps.txt').read_text().splitlines()]
    S = loadz(O/'work/ga3/step1_ALS.npz', ['starts']); rng = np.random.default_rng(1); st = S['starts'][rng.choice(len(S['starts']), 40, replace=False)]
    cache = {}
    def get(i):
        if i not in cache: cache[i] = (rmap(maps[i][0], 1), rmap(maps[i][1].strip(), 3))
        return cache[i]
    stats = dict(proj_in=0, depth_ok=0, normal_ok=0, both=0, tried=0); dots = []; derr = []
    for im, pix in st:
        r0, c0 = divmod(int(pix), W); Dm, Nm = get(im); d0 = Dm[r0, c0]; R = C[im, :9].reshape(3, 3); t = C[im, 9:12]; fx, fy, cx, cy = C[im, 12:]
        Y = np.array([(c0 - cx)/fx*d0, (r0 - cy)/fy*d0, d0]); X = R.T@(Y - t); N0 = R.T@Nm[r0, c0]
        for j in ov[im][:50]:
            if j < 0: continue
            Rj = C[j, :9].reshape(3, 3); tj = C[j, 9:12]; Yj = Rj@X + tj
            if Yj[2] <= 0: continue
            u = fx*Yj[0]/Yj[2] + cx; v = fy*Yj[1]/Yj[2] + cy; cc, rr = int(round(u)), int(round(v)); stats['tried'] += 1
            if not (0 <= cc < W and 0 <= rr < H): continue
            Dj, Nj = get(j); d = Dj[rr, cc]
            if not d > 0: continue
            if stats['proj_in'] < 25: print('PAIR', im, j, round(float(Yj[2]),2), round(float(d),2), 'dist_m', round(float(np.linalg.norm(Rj.T@(np.array([(cc-cx)/fx*d,(rr-cy)/fy*d,d])-tj) - X)),3), 'cam_dist', round(float(np.linalg.norm(-R.T@t + Rj.T@tj)),1))
            stats['proj_in'] += 1; e = abs((Yj[2] - d)/d); derr.append(e); dok = e <= .01; nj = Rj.T@Nj[rr, cc]; dt = float(N0@nj); dots.append(dt); nok = dt >= np.cos(np.deg2rad(10))
            stats['depth_ok'] += dok; stats['normal_ok'] += nok; stats['both'] += dok and nok
    print(stats, 'depth err median', np.median(derr), 'normal dot median', np.median(dots), 'norm of n', np.linalg.norm(Nm[r0, c0]))
if __name__ == '__main__': main()
