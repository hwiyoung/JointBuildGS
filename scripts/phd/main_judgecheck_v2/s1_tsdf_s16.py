"""[16칸 판: 구역(100 m)을 25 m 칸 16개로 나누고 각 칸 + 12 m 상자. 사분면 판도 16 GB를 넘은 6909_53361 때문. 규칙은 s1_tsdf.py 와 같음]
참값 쪽 MVS 면 (발주 2.3, RESCORE 'MVS' 줄 = AXES71 mvs_surface.py 규칙): Open3D ScalableTSDFVolume 0.05 m, 잘림 0.25 m,
깊이 300 m, 깊이 > 0, 상자 밖 화소는 0, 후처리 없음. WIDEN0 학습 819장의 COLMAP 기하 단계 깊이, 구역(100 m) + 12 m 상자. 영상 jointbuildgs:geogs-conf-guided-v1 (open3d 0.19, AXES71과 같은 영상)."""
from common import *
import open3d as o3d
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras, read_depth
f32 = np.float32
def main(tile):
    if (O/'truth/mvs_surface'/f'{tile}.npz').exists(): return
    for q in range(16): quadrant(tile, q)
    dump(O/'truth/mvs_surface'/f'{tile}_s16.complete.json', dict(at=now(), tile=tile, boxes=16, scientific_verdict=None))
def quadrant(tile, q):
    dest = O/'truth/mvs_surface'/f'{tile}_s{q}.npz'
    if dest.exists(): return
    T = Timer(); t = next(x for x in json.loads((W/'inputs/tiles.json').read_text()) if x['id'] == tile)
    e0, n0, e1, n1 = t['core_global']; qe, qn = e0 + 25*(q % 4), n0 + 25*(q // 4)
    lo = np.array([qe-690953-12, qn-5336071-12]); hi = np.array([qe+25-690953+12, qn+25-5336071+12])
    zs = []
    for f in ['lod2_mesh.npz', 'als_mesh.npz']:
        V = np.load(WI/'prior_tiles'/tile/f)['V']; m = (V[:, :2] >= lo).all(1) & (V[:, :2] <= hi).all(1)
        if m.any(): zs.append(V[m, 2])
    z = np.concatenate(zs); BOX = np.array([[lo[0], lo[1], z.min()-3], [hi[0], hi[1], z.max()+3]])
    cam = Cameras(); K = cam.K; H, Wd = 741, 1024
    u, v = np.meshgrid(np.arange(Wd, dtype=f32), np.arange(H, dtype=f32))
    vol = o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=0.05, sdf_trunc=0.25, color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    intr = o3d.camera.PinholeCameraIntrinsic(width=Wd, height=H, cx=float(K[0, 2]), cy=float(K[1, 2]), fx=float(K[0, 0]), fy=float(K[1, 1]))
    rgb = o3d.geometry.Image(np.zeros((H, Wd, 3), np.uint8)); used = []; px_box = 0
    for j, name in enumerate(cam.names):
        p = W/'mvs/full/stereo/depth_maps'/f'{name}.geometric.bin'
        if not p.exists(): continue
        d = read_depth(p).astype(f32); d = np.where(np.isfinite(d) & (d > 0), d, f32(0))
        M = cam.M[j].astype(np.float64); c2w = np.linalg.inv(M)
        Pc = np.stack([(u - K[0, 2])/K[0, 0]*d, (v - K[1, 2])/K[1, 1]*d, d], -1).reshape(-1, 3).astype(np.float64)
        Pw = Pc @ c2w[:3, :3].T + c2w[:3, 3]
        mk = ((Pw >= BOX[0]) & (Pw <= BOX[1])).all(-1).reshape(H, Wd) & (d > 0)
        if not mk.any(): continue
        dd = np.ascontiguousarray(np.where(mk, d, f32(0)), dtype=f32); px_box += int(mk.sum())
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(rgb, o3d.geometry.Image(dd), depth_trunc=300.0, convert_rgb_to_intensity=False, depth_scale=1.0)
        vol.integrate(rgbd, intrinsic=intr, extrinsic=M); used.append(name)
    mesh = vol.extract_triangle_mesh(); V = np.asarray(mesh.vertices); F = np.asarray(mesh.triangles)
    savez(dest, V=V.astype(np.float64), F=F.astype(np.int32), box=BOX)
    dump(dest.with_suffix('.json'), dict(at=now(), tile=tile, quadrant=q, core_local=[[qe-690953, qn-5336071], [qe+25-690953, qn+25-5336071]], box=BOX, views_used=len(used), pixels_in_box=px_box, vertices=len(V), triangles=len(F), seconds=T.mark('end'), open3d=o3d.__version__,
         settings=dict(voxel_m=0.05, sdf_trunc_m=0.25, depth_trunc_m=300.0, depth_scale=1.0, colour='constant (geometry only)', post_processing='none'), GT_read=False, scientific_verdict=None))
    print('TSDF_DONE', tile, q, len(used), len(F), round(T.mark('end')), flush=True)
if __name__ == '__main__':
    for t in sys.argv[1:]: main(t)
