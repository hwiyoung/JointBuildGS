"""Addendum 2 work 가 2.1 (qualitative): B0_b10__LoD2 south-wall images. CPU container.
Per image (same crop for every panel): 원본, 목표깊이_<arm>, 영상깊이_전, 영상깊이_후, 출처_<arm>, 차이_<arm> -> docs addendum2/figures/ga_<image>_<panel>.png + json; legends; tables ga_photo_views."""
from a2_common import *
from PIL import Image, ImageDraw
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib import cm as mcm, colors as mcolors, colormaps
STEM, SITE = 'B0_b10__LoD2', 'B0_b10'; SIZE = (1600, 1280); FIG = A2D/'figures'
NAMED = ['DJI_20241217094933_0013_D', 'DJI_20241217093905_0026_D']
def hexrgb(h): return np.array([int(h[i:i+2], 16) for i in (1, 3, 5)], 'f8')
def cross(draw, p, s=14):
    x, y = p
    for col, w in [((0, 0, 0), 5), ((255, 255, 0), 2)]: draw.line([(x-s, y), (x+s, y)], fill=col, width=w); draw.line([(x, y-s), (x, y+s)], fill=col, width=w)

def main():
    c = bcfg(); t0 = Timer('a2_ga_photo'); FIG.mkdir(parents=True, exist_ok=True); CC = json.loads((R/'configs/phd/main_gtjudge_v1/addendum6.json').read_text())['case_colors']
    sel = {}
    for arm in ARMS:
        pv = json.loads((A2O/'ga'/f'{STEM}__{arm}.json').read_text())['per_view']; order = sorted(pv, key=lambda r: (-r['south_pixels'], r['view']))
        sel[arm] = [r['view'] for r in order if r['view'] not in NAMED][:3]
    images = NAMED+sel['own']; cam = cameras(SITE); S0dir = Path('/s0/fork_inputs/s61')/SITE/'maps'
    tg = {arm: loadz(targets_of(STEM, arm), ['kind', 'area']) for arm in ARMS}; N = len(tg['own']['area']); pcase = patch_case(STEM, N); zones = {arm: wall_zone_patches(STEM, arm) for arm in ARMS}
    idx = {arm: json.loads((maps_dir(STEM, arm)/'index.json').read_text())['views'] for arm in ARMS}
    W, H = SIZE; recs = []
    for name in images:
        j = cam.names.index(name); corners = place_corners('south_wall'); uvc, _ = native(corners, cam, j); crop = bounds_crop(uvc, cam.w, cam.h)
        xs = crop[0]+(np.arange(W)+.5)*(crop[2]-crop[0])/W; ys = crop[1]+(np.arange(H)+.5)*(crop[3]-crop[1])/H; X, Y = np.meshgrid(xs, ys)
        fx, fy, cx, cy = cam.p[:4]; dc = np.stack([(X-cx)/fx, (Y-cy)/fy, np.ones_like(X)], -1).reshape(-1, 3); dw = dc@cam.R[j]
        mi = idx['own'][name]; K = np.asarray(mi['K']); E = np.asarray(mi['W2C']); assert np.allclose(np.asarray(idx['gt'][name]['W2C']), E) and np.allclose(np.asarray(idx['gt'][name]['K']), K)
        dt = dw@E[:3, :3].T; u = K[0, 0]*dt[:, 0]/dt[:, 2]+K[0, 2]; v = K[1, 1]*dt[:, 1]/dt[:, 2]+K[1, 2]; ui = np.floor(u+.5).astype(int); vi = np.floor(v+.5).astype(int)
        mvs = np.load(S0dir/'mvs'/f'{name}.npy'); conf = np.load(S0dir/'conf'/f'{name}.npy'); Hh, Ww = mvs.shape; inside = (ui >= 0) & (ui < Ww) & (vi >= 0) & (vi < Hh) & (dt[:, 2] > 0)
        uic, vic = np.clip(ui, 0, Ww-1), np.clip(vi, 0, Hh-1)
        Cf = -cam.R[j].T@cam.t[j]; Ct = -E[:3, :3].T@E[:3, 3]; ang = float(np.degrees(np.arccos(np.clip((np.trace(cam.R[j]@E[:3, :3].T)-1)/2, -1, 1))))
        geom = dict(full_camera=dict(model='undistorted pinhole crop of the FULL_OPENCV training camera', fx=float(fx), fy=float(fy), cx=float(cx), cy=float(cy), full_opencv=cam.p.tolist(), width=cam.w, height=cam.h, R=cam.R[j].tolist(), t=cam.t[j].tolist()),
                    crop_xyxy=crop.tolist(), output_size=list(SIZE), map_camera=dict(K=K.tolist(), W2C=E.tolist(), width=Ww, height=Hh), centre_difference_m=float(np.linalg.norm(Cf-Ct)), rotation_difference_deg=ang,
                    sampling='output pixel ray -> map camera -> floor(u + 0.5), nearest', output_pixels_inside_map=float(inside.mean()))
        md_raw = np.where(inside, mvs[vic, uic], np.nan).reshape(H, W); md_ok = np.where(inside & (conf[vic, uic] > 0), mvs[vic, uic], np.nan).reshape(H, W)
        md_raw = np.where(np.isfinite(md_raw) & (md_raw > 0), md_raw, np.nan); md_ok = np.where(np.isfinite(md_ok) & (md_ok > 0), md_ok, np.nan)
        maps = {}
        for arm in ARMS:
            with np.load(maps_dir(STEM, arm)/idx[arm][name]['file']) as z: own_ = z['owner']; dep = z['depth']
            ow = np.where(inside, own_[vic, uic], -1).reshape(H, W); td = np.where(ow >= 0, dep[vic, uic].reshape(H, W), np.nan); maps[arm] = (ow, td)
        lo, hi = np.nanpercentile(maps['own'][1], [2, 98]) if np.isfinite(maps['own'][1]).any() else (np.nanpercentile(md_raw, 2), np.nanpercentile(md_raw, 98))
        vir = colormaps['viridis']; grey = np.array([200, 200, 200], 'u1')
        def depth_img(d):
            out = np.empty((H, W, 3), 'u1'); out[:] = grey; f = np.isfinite(d); out[f] = (255*np.asarray(vir(np.clip((d[f]-lo)/max(hi-lo, 1e-6), 0, 1)))[:, :3]).astype('u1'); return Image.fromarray(out)
        cuv = (uvc-crop[:2])*[W/(crop[2]-crop[0]), H/(crop[3]-crop[1])]
        def save(img, panel, extra=None):
            d = ImageDraw.Draw(img)
            for q in cuv: cross(d, q)
            p = FIG/f'ga_{name}_{panel}.png'; img.save(p); dump(p.with_suffix('.json'), dict(stem=STEM, image=name, panel=panel, **geom, depth_colour_range_m=[float(lo), float(hi)], corners_xyz=corners.tolist(), corners_px=cuv.tolist(), **(extra or {}), text_in_figure=False, at=now(), scientific_verdict=None))
        im, src = undistort_crop(cam, j, crop, SIZE); save(im, '원본', dict(source=src))
        save(depth_img(md_raw), '영상깊이_전', dict(source=str(S0dir/'mvs'/f'{name}.npy'), no_value_colour='#C8C8C8'))
        save(depth_img(md_ok), '영상깊이_후', dict(source=str(S0dir/'conf'/f'{name}.npy'), mask='finite, > 0, conf > 0', no_value_colour='#C8C8C8'))
        rdbu = colormaps['RdBu_r']
        for arm in ARMS:
            ow, td = maps[arm]; save(depth_img(td), f'목표깊이_{arm}', dict(source=str(maps_dir(STEM, arm)/idx[arm][name]['file']), no_value_colour='#C8C8C8'))
            src_ = np.empty((H, W, 3), 'f8'); src_[:] = hexrgb('#303030'); bgm = (ow < 0) & np.isfinite(md_ok); src_[bgm] = hexrgb('#A0A0A0'); has = ow >= 0
            if has.any():
                o = ow[has]; cs = pcase[o]; col = np.array([hexrgb(CC[str(k)]) if k >= 0 else hexrgb('#9467BD') for k in range(-1, 5)])[cs+1]
                roof = tg[arm]['kind'][o] != 2; col[roof] = .45*col[roof]+.55*255; src_[has] = col
            save(Image.fromarray(src_.astype('u1')), f'출처_{arm}', dict(colours=dict(cases=CC, case_none='#9467BD', roof='case colour 55 % toward white', wall='case colour', mvs_background='#A0A0A0', nothing='#303030')))
            df = np.where(has & np.isfinite(md_raw), td-md_raw, np.nan); out = np.full((H, W, 3), 255, 'u1'); f = np.isfinite(df)
            out[f] = (255*np.asarray(rdbu(np.clip((df[f]+3)/6, 0, 1)))[:, :3]).astype('u1'); out[has & ~np.isfinite(md_raw)] = [255, 215, 0]
            save(Image.fromarray(out), f'차이_{arm}', dict(rule='target depth - raw MVS depth, RdBu_r over -3..+3 m (positive = image depth in front of the target)', target_without_image_depth='#FFD700', no_target='#FFFFFF'))
            sw = np.isin(ow, zones[arm]['south']); fw = sw & np.isfinite(md_raw)
            recs.append(dict(image=name, arm=arm, chosen_by='named in the order' if name in NAMED else 'top south-wall target pixels (own)', crop_south_wall_target_pixels=int(sw.sum()),
                             crop_front_pct=100*float((fw & (md_raw < td-1)).sum())/max(1, int(sw.sum())), crop_same_pct=100*float((fw & (np.abs(md_raw-td) <= 1)).sum())/max(1, int(sw.sum())),
                             crop_behind_pct=100*float((fw & (md_raw > td+1)).sum())/max(1, int(sw.sum())), crop_none_pct=100*float((sw & ~np.isfinite(md_raw)).sum())/max(1, int(sw.sum())),
                             centre_difference_m=geom['centre_difference_m'], rotation_difference_deg=ang))
        print('GA_PHOTO', name, flush=True)
    btable('ga_photo_views', recs); btable('ga_photo_selection', [dict(arm=a, top3_excluding_named=sel[a]) for a in ARMS])
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    fig, ax = plt.subplots(figsize=(8, 3.6)); ax.axis('off'); items = [(CC[str(k)], f'벽 패치: {CNAME[k]}') for k in range(5)]+[('#9467BD', '벽 패치: 경우 없음(참값 점 없음)')]
    for i, (col, lab) in enumerate(items): ax.scatter([.02], [1-i*.12], c=col, s=60, marker='s'); ax.text(.06, 1-i*.12, lab, va='center', fontsize=9)
    for i, (col, lab) in enumerate([('#d9d9d9', '지붕 패치 = 같은 색을 옅게'), ('#A0A0A0', '패치 없음, 영상 깊이(마스크 뒤) 있음'), ('#303030', '목표도 영상 깊이도 없음'), ('#FFD700', '차이: 목표 화소에 영상 깊이 없음'), ('#C8C8C8', '깊이: 값 없음'), ('#FFFF00', '십자: 남쪽 끝 벽 자리 모서리')]):
        ax.scatter([.55], [1-i*.12], c=col, s=60, marker='s', edgecolors='k'); ax.text(.59, 1-i*.12, lab, va='center', fontsize=9)
    ax.set_xlim(0, 1.25); ax.set_ylim(.2, 1.1); fig.savefig(FIG/'ga_legend.png', dpi=200, bbox_inches='tight'); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, .9)); fig.colorbar(mcm.ScalarMappable(mcolors.Normalize(-3, 3), 'RdBu_r'), cax=ax, orientation='horizontal', label='목표 깊이 − 영상 깊이 (m), + = 영상 깊이가 앞'); fig.savefig(FIG/'ga_legend_diff.png', dpi=200, bbox_inches='tight'); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, .9)); fig.colorbar(mcm.ScalarMappable(mcolors.Normalize(0, 1), 'viridis'), cax=ax, orientation='horizontal', label='깊이: 영상마다 목표 깊이의 2~98 % 범위(json의 depth_colour_range_m)'); fig.savefig(FIG/'ga_legend_depth.png', dpi=200, bbox_inches='tight'); plt.close(fig)
    bprogress(f'일 가 2.1 사진 그림 {len(images)}장 ({t0.done():.0f} s)')
if __name__ == '__main__': main()
