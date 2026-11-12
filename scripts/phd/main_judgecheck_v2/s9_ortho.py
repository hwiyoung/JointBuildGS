"""그림 바탕 정사영상: 드론 LiDAR(TUM_Downtown_ULS_20241217_nadir.laz) 점 색, 0.25 m 칸(로컬 XY), 칸마다 가장 높은 점의 색 (RESCORE 그림 6.1 / ch6 t3_ortho.py 규칙; 빈 칸 채우기 4칸 안, 그 밖은 흰색). 모든 건물 같은 색."""
from common import *
import laspy
from scipy import ndimage as ndi
RES = 0.25
def main():
    T = Timer(); ts = json.loads((W/'inputs/tiles.json').read_text()); E0 = min(t['core_global'][0] for t in ts) - 20; N0 = min(t['core_global'][1] for t in ts) - 20; E1 = max(t['core_global'][2] for t in ts) + 20; N1 = max(t['core_global'][3] for t in ts) + 20
    x0, y0 = E0 - 690953, N0 - 5336071; Wd, H = int(np.ceil((E1 - E0)/RES)), int(np.ceil((N1 - N0)/RES))
    zmax = np.full(H*Wd, -np.inf, np.float32); rgb = np.full((H*Wd, 3), 255, np.uint16); n = 0
    with laspy.open(str(PH.parent/'p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz')) as f:
        for pts in f.chunk_iterator(10_000_000):
            x = np.asarray(pts.x) - 690953.0; y = np.asarray(pts.y) - 5336071.0; z = np.asarray(pts.z, np.float32) - 604.0; n += len(x)
            ix = ((x - x0)/RES).astype(np.int64); iy = ((y - y0)/RES).astype(np.int64); ok = (ix >= 0) & (iy >= 0) & (ix < Wd) & (iy < H)
            cell = iy[ok]*Wd + ix[ok]; zz = z[ok]; col = np.stack([np.asarray(pts.red)[ok], np.asarray(pts.green)[ok], np.asarray(pts.blue)[ok]], 1)
            o = np.lexsort((-zz, cell)); cs = cell[o]; first = np.r_[True, cs[1:] != cs[:-1]]; top = o[first]; c = cell[top]
            better = zz[top] > zmax[c]; zmax[c[better]] = zz[top][better]; rgb[c[better]] = col[top][better]
    scale = 256.0 if rgb.max() > 255 else 1.0; img = np.clip(rgb/scale, 0, 255).astype(np.uint8).reshape(H, Wd, 3); okc = np.isfinite(zmax).reshape(H, Wd)
    d, (iy, ix) = ndi.distance_transform_edt(~okc, return_indices=True); fill = (~okc) & (d <= 4); img[fill] = img[iy[fill], ix[fill]]; img[(~okc) & (d > 4)] = 255
    savez(O/'figures_cache/ortho_campus.npz', rgb=img, x0=x0, y0=y0, res=RES, top=zmax.reshape(H, Wd))
    dump(O/'figures_cache/ortho_campus.json', dict(at=now(), points=n, shape=[H, Wd], x0=x0, y0=y0, res=RES, filled_share=float(fill.mean()), empty_share=float(((~okc) & (d > 4)).mean()), seconds=T.mark('end'), scientific_verdict=None))
    print('ORTHO', n, H, Wd, round(T.mark('end')), flush=True)
if __name__ == '__main__': main()
