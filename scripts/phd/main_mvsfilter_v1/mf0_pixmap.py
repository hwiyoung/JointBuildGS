"""지금 점(WIDEN0 캠퍼스 MVS 점, 구역마다 mvs_a_xyz.npy)과 깊이 지도 화소의 대응표를 만든다. 학습 없음, CPU.
WIDEN0 mvs_points.py 의 역투영 순서(영상, 행, 열 → 구역 버퍼 → 무작위 키 정렬)를 그대로 다시 밟아 화소 번호(행*1024+열)를 점 차례로 늘어놓는다.
검산: 영상 번호 배열이 mvs_a_view.npy 와 모두 같음, 키가 mvs_a_key.npy 와 모두 같음, 구역마다 표본 20만 점의 좌표가 float32 로 같음.
출력: /out/pixmap/<tile>.npy (int32), /out/pixmap/valid_counts.json. 사용: mf0_pixmap.py"""
import sys, json, struct, time
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *

def main():
    T = Timer(); cfgw = json.loads(Path('/repo/configs/phd/main_widen0_v2/widen0_v2.json').read_text())
    names = json.loads((W/'image_split.json').read_text())['train']; tiles = json.loads((W/'inputs/tiles.json').read_text())
    rows = poses(WS/'sparse/images.bin'); assert sorted(rows) == sorted(names)
    with (WS/'sparse/cameras.bin').open('rb') as f:
        nc, = struct.unpack('<Q', f.read(8)); cid, model, iw, ih = struct.unpack('<iiQQ', f.read(24)); fx, fy, cx, cy = struct.unpack('<4d', f.read(32))
    fx, fy, cx, cy = fx*1024/iw, fy*741/ih, cx*1024/iw, cy*741/ih; cx -= .5; cy -= .5; f32 = np.float32
    p00, p11 = f32(2*fx/1024), f32(2*fy/741); p02, p12 = f32((2*cx+1-1024)/1024), f32((2*cy+1-741)/741)
    fx, fy = float(f32(f32(1024/2)*p00)), float(f32(f32(741/2)*p11))
    cx = float(f32(f32(f32(1024/2)*p02)+f32((1024-1)/2))); cy = float(f32(f32(f32(741/2)*p12)+f32((741-1)/2)))
    OUTP = O/'pixmap'; OUTP.mkdir(parents=True, exist_ok=True)
    ZC = []; buf = {t['id']: [] for t in tiles}; vbuf = {t['id']: [] for t in tiles}; valid = {}
    boxes = []
    for t in tiles:
        x0, y0, x1, y1 = t['buffer_global']; boxes.append((t['id'], x0-690953., x1-690953., y0-5336071., y1-5336071.))
    for i, name in enumerate(names):
        z = read_depth(WS/'stereo/depth_maps'/f'{name}.geometric.bin'); assert z.shape == (741, 1024); ZC.append(z)
        vv, uu = np.nonzero(np.isfinite(z) & (z > 0)); dd = z[vv, uu].astype(float); valid[name] = int(len(vv))
        cam = np.column_stack([(uu-cx)/fx*dd, (vv-cy)/fy*dd, dd])
        q, tt = rows[name]; Wm = np.eye(4, dtype=np.float32); Wm[:3, :3] = rotation(q); Wm[:3, 3] = tt
        Cm = np.linalg.inv(Wm.astype(float)); X = (cam@Cm[:3, :3].T+Cm[:3, 3]).astype(np.float32)
        pix = (vv*1024+uu).astype(np.int32)
        for tid, x0, x1, y0, y1 in boxes:
            m = (X[:, 0] >= x0) & (X[:, 0] < x1) & (X[:, 1] >= y0) & (X[:, 1] < y1)
            if m.any(): buf[tid].append(pix[m]); vbuf[tid].append(np.full(int(m.sum()), i, np.int16))
        if i % 100 == 0: print('pixmap read', i, len(names), round(T.s()), flush=True)
    CHK = []
    for idx, t in enumerate(tiles):
        tid = t['id']; P = WI/'points'/tid
        pix = np.concatenate(buf.pop(tid)) if vbuf[tid] else np.empty(0, np.int32); view = np.concatenate(vbuf.pop(tid)) if len(pix) else np.empty(0, np.int16)
        n = len(pix); keys = np.random.default_rng([cfgw['split']['seed'], idx, 0]).random(n); order = np.argsort(keys, kind='stable')
        pix = pix[order]; view = view[order]; keys = keys[order]
        V0 = np.load(P/'mvs_a_view.npy', mmap_mode='r'); K0 = np.load(P/'mvs_a_key.npy', mmap_mode='r'); X0 = np.load(P/'mvs_a_xyz.npy', mmap_mode='r')
        eqv = bool(len(V0) == n and np.array_equal(np.asarray(V0), view)); eqk = bool(len(K0) == n and np.array_equal(np.asarray(K0), keys))
        # 좌표 표본 검산
        rs = np.random.default_rng([20261119, idx]); s = np.sort(rs.choice(n, min(n, 200000), replace=False)) if n else np.empty(0, int)
        Xr = unproject(view[s], pix[s], names, rows, (fx, fy, cx, cy), ZC) if n else np.empty((0, 3), np.float32)
        eqx = int(np.sum(np.all(Xr == np.asarray(X0[s]), 1))) if n else 0
        np.save(OUTP/f'{tid}.npy', pix)
        CHK.append(dict(tile=tid, points=n, view_equal=eqv, key_equal=eqk, xyz_sample=len(s), xyz_equal=eqx)); print('PIXMAP', json.dumps(CHK[-1]), flush=True)
        assert eqv and eqk and eqx == len(s), CHK[-1]
    dump(OUTP/'valid_counts.json', dict(at=now(), names=names, valid_pixels=valid, checks=CHK, intrinsics=dict(fx=fx, fy=fy, cx=cx, cy=cy), seconds=T.s(), scientific_verdict=None))
    progress(f'mf0 화소 대응표 끝: 구역 {len(CHK)}, 점 {sum(c["points"] for c in CHK):,}, 검산 모두 같음, {round(T.s())} 초')

if __name__ == '__main__': main()
