"""③ 구현 점검(판정에 안 씀): 구역 하나의 영상 깊이 점 무작위 20만 개에서 COLMAP 규칙 일관된 점 비율과 A2 비율."""
from common import *
def main():
    build_vis(); t = '6910_53361'; vw = np.load(inp('image_point_view', tile=t), mmap_mode='r'); px = np.load(inp('image_point_pixel', tile=t), mmap_mode='r')
    rng = np.random.default_rng(7); s = np.sort(rng.choice(len(vw), 200000, replace=False)); st = np.c_[np.asarray(vw[s]), np.asarray(px[s])].astype('<i4')
    sb = O/'tmp/chk.bin'; ob = O/'tmp/chk.out'; st.tofile(sb)
    subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(st)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'))
    R = np.fromfile(ob, '<i4').reshape(-1, 3); rec = dict(at=now(), tile=t, sample=len(st), colmap_consistent_share=float(R[:, 0].mean()), a2_self_ge5_share=float(((R[:, 2] + 1) >= 5).mean()),
        cluster_hist=np.bincount(np.minimum(R[:, 1], 5), minlength=6).tolist(), a2_hist=np.bincount(np.minimum(R[:, 2], 10), minlength=11).tolist(), scientific_verdict=None)
    dump(O/'work/ga3/step3_random_check.json', rec); print(rec)
if __name__ == '__main__': main()
