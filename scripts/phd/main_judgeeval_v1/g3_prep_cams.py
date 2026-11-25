"""②·③ 준비: 학습 영상(image_split train, 819장)의 카메라(cams.bin), 깊이·법선 지도 목록(maps.txt), 겹침 영상 50장(overlap.bin).
겹침 = COLMAP Model::GetMaxOverlappingImages 처럼 희소 모델에서 같은 3차원 점을 본 수가 많은 차례로 50장(삼각측량 각 문턱은 두지 않음; issues 에 적음).
점검: 영상 깊이 점 표본(구역 하나, 300점)을 그 화소의 깊이로 다시 3차원으로 옮겨 저장된 좌표와 맞댐. 사용: g3_prep_cams.py"""
from common import *
WS = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/mvs/full'
def images_bin(path):
    out = {}
    with Path(path).open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            iid, = struct.unpack('<i', f.read(4)); q = struct.unpack('<4d', f.read(32)); t = struct.unpack('<3d', f.read(24)); cid, = struct.unpack('<i', f.read(4)); name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\0': break
                name.extend(c)
            n, = struct.unpack('<Q', f.read(8)); a = np.frombuffer(f.read(n*24), dtype=[('x', '<f8'), ('y', '<f8'), ('p', '<i8')]); out[name.decode()] = (q, t, a['p'][a['p'] >= 0])
    return out
def main():
    c = cfg(); names = json.loads(inp('image_split').read_text())['train']; K = json.loads(inp('intrinsics').read_text())['intrinsics']; IB = images_bin(WS/'sparse/images.bin'); V = O/'vis'; V.mkdir(parents=True, exist_ok=True)
    Wd, Hh = 1024, 741
    with (V/'cams.bin').open('wb') as f:
        f.write(struct.pack('<iii', len(names), Wd, Hh))
        for nm in names:
            q, t, _ = IB[nm]; f.write(np.r_[rotation(q).ravel(), t, K['fx'], K['fy'], K['cx'], K['cy']].astype('<f8').tobytes())
    (V/'maps.txt').write_text(''.join(f"{WS}/stereo/depth_maps/{nm}.geometric.bin\t{WS}/stereo/normal_maps/{nm}.geometric.bin\n" for nm in names))
    # 겹침
    pid = {};
    for i, nm in enumerate(names):
        for p in np.unique(IB[nm][2]): pid.setdefault(int(p), []).append(i)
    M = np.zeros((len(names), len(names)), np.int32)
    for lst in pid.values():
        if len(lst) > 1: a = np.array(lst); M[np.ix_(a, a)] += 1
    np.fill_diagonal(M, 0); k = c['judgment']['step3_multiview']['check_num_images'][0]; ov = np.full((len(names), k), -1, np.int32)
    for i in range(len(names)):
        o = np.argsort(-M[i], kind='stable'); o = o[M[i, o] > 0][:k]; ov[i, :len(o)] = o
    with (V/'overlap.bin').open('wb') as f: f.write(struct.pack('<ii', len(names), k)); f.write(ov.tobytes())
    # 점검: 다시 옮기기
    t = '6910_53361'; X = np.load(inp('image_points', tile=t), mmap_mode='r'); vw = np.load(inp('image_point_view', tile=t), mmap_mode='r'); px = np.load(inp('image_point_pixel', tile=t), mmap_mode='r')
    rng = np.random.default_rng(c['seed']); s = np.sort(rng.choice(len(X), 300, replace=False)); err = []
    for i in s:
        v = int(vw[i]); p = int(px[i]); row, col = divmod(p, Wd); nm = names[v]
        raw = (WS/'stereo/depth_maps'/f'{nm}.geometric.bin').read_bytes(); end = 0
        for _ in range(3): end = raw.find(b'&', end, 100) + 1
        D = np.frombuffer(raw, dtype='<f4', offset=end, count=Wd*Hh).reshape((Wd, Hh), order='F').T[row, col]
        q, tt, _ = IB[nm]; R_ = rotation(q); Y = np.array([(col - K['cx'])/K['fx']*D, (row - K['cy'])/K['fy']*D, D]); Xw = R_.T@(Y - np.array(tt)); err.append(np.linalg.norm(Xw - X[i]))
    err = np.array(err); rec = dict(at=now(), images=len(names), overlap_k=k, overlap_filled=int((ov >= 0).sum()), reproject_check=dict(tile=t, sample=len(s), max_m=float(err.max()), median_m=float(np.median(err))), scientific_verdict=None)
    dump(V/'prep.json', rec); print(rec)
if __name__ == '__main__': main()
