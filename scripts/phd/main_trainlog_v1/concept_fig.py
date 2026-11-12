"""Concept figure draft (2026-11-12): for reviewers who do not know Gaussian splatting. One real training camera (DJI_20241217091247_0146_D) in every panel,
so every row shows the same pixels. CPU, reads concept_prep.py / concept_mesh.py / renders outputs only.
  A (how it learns, this run): columns = input, 0, 300, 1,000, 2,000, 10,000, 30,000 iterations; rows =
     1 discs: the Gaussians that are the per-pixel top contributor somewhere in the frame, drawn as their 1-sigma ellipse filled with the SH-degree-0 colour,
       far first, alpha = opacity (floor 0.15); 2 render (r27 renderer, renders/<state>/train1_rgb.png) with PSNR to the photo;
     3 render depth minus the TARGET depth map of this camera (only where the target has weight > 0 and render alpha > 0.5);
     4 mesh (TSDF of the 203 real views, gtj pipeline) ray-cast from the camera, grey headlight shading.
  B (why, 30,000 iterations, the same camera): image-only 2DGS, prior-first GeoGS (ALS), this method; rows = render with PSNR, mesh coloured where the
     mesh face is farther than TAU from the GT dense reference (GT for colouring only, red = above, blue = below).
scientific_verdict: null"""
import sys
from common import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import EllipseCollection
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle, Patch
from PIL import Image
from concept_mesh import cast
P_ = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(P_); plt.rcParams['font.family'] = fm.FontProperties(fname=P_).get_name(); plt.rcParams['axes.unicode_minus'] = False
OUTC = O/'concept'; FIG = D/'figures_concept'; STATES = ['0', '300', '1000', '2000', '10000', '30000']; TAU = .212; NAVY = '#16263d'; INK = '#2e3a48'
CROP_A = (520, 20, 760, 260)    # u0, v0, u1, v1 (pixels of the 1024 x 741 camera): roof edge, changed green roof, top of the glass skylight
CROP_B = (440, 0, 800, 741)     # the whole B173 roof in this photo
PURPLE = np.array(to_rgb('#7B3FA0')); GREYM = np.array(to_rgb('#D3D1CA')); RED = np.array(to_rgb('#C0392B')); BLUE = np.array(to_rgb('#2E6DB4'))

def crop(img, c): return img[c[1]:c[3], c[0]:c[2]]
def show(ax, img, c, title=None):
    ax.imshow(img, extent=(0, c[2]-c[0], c[3]-c[1], 0), interpolation='nearest'); ax.set_xlim(0, c[2]-c[0]); ax.set_ylim(c[3]-c[1], 0); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_color('#B4B2A9'); s.set_linewidth(.6)
    if title: ax.set_title(title, fontsize=11, color=NAVY)
def note(ax, s, loc='lower left', fs=8.5):
    x, y, ha, va = {'lower left': (.02, .02, 'left', 'bottom'), 'upper left': (.02, .98, 'left', 'top')}[loc]
    ax.text(x, y, s, transform=ax.transAxes, ha=ha, va=va, fontsize=fs, color='#1b1b1b', bbox=dict(boxstyle='round,pad=.25', fc='white', ec='none', alpha=.85))

def rot(q):
    r, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y-r*z), 2*(x*z+r*y)], -1), np.stack([2*(x*y+r*z), 1-2*(x*x+z*z), 2*(y*z-r*x)], -1), np.stack([2*(x*z-r*y), 2*(y*z+r*x), 1-2*(x*x+y*y)], -1)], 1)

def discs(ax, n, K, W2C, c):
    z = loadz(OUTC/f'discs_{n}.npz'); R = W2C[:3, :3]; t = W2C[:3, 3]; Xc = z['xyz'].astype(float)@R.T+t; Z = Xc[:, 2]; fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    u = fx*Xc[:, 0]/Z+cx-c[0]; v = fy*Xc[:, 1]/Z+cy-c[1]; Rm = rot(z['quat'].astype(float)); s = z['scale'].astype(float)
    def J(a): ac = a@R.T; return np.stack([fx*(ac[:, 0]/Z-Xc[:, 0]*ac[:, 2]/Z**2), fy*(ac[:, 1]/Z-Xc[:, 1]*ac[:, 2]/Z**2)], -1)
    p1, p2 = J(Rm[:, :, 0]*s[:, 0:1]), J(Rm[:, :, 1]*s[:, 1:2]); S = np.einsum('ni,nj->nij', p1, p1)+np.einsum('ni,nj->nij', p2, p2); w, V = np.linalg.eigh(S)
    major = V[:, :, 1]; ang = np.degrees(np.arctan2(major[:, 1], major[:, 0])); big, small = 2*np.sqrt(np.maximum(w[:, 1], 0)), 2*np.sqrt(np.maximum(w[:, 0], 0))
    pad = 30; m = (u > -pad) & (u < c[2]-c[0]+pad) & (v > -pad) & (v < c[3]-c[1]+pad) & (Z > 0); o = np.flatnonzero(m)[np.argsort(-Z[m])]
    fc = np.c_[z['rgb'][o].astype(float), np.clip(z['opacity'][o].astype(float), .15, 1)]
    ax.add_collection(EllipseCollection(big[o], np.maximum(small[o], .6), ang[o], units='xy', offsets=np.c_[u[o], v[o]], offset_transform=ax.transData, facecolors=fc, edgecolors=(.1, .1, .1, .35), linewidths=.25))
    ax.set_facecolor('black'); ax.set_xlim(0, c[2]-c[0]); ax.set_ylim(c[3]-c[1], 0); ax.set_xticks([]); ax.set_yticks([])
    return int(z['n_all']), int(m.sum())

def shade(mz, W2C):
    R = W2C[:3, :3]; f = R[2]; n = mz['normal'].astype(float); return np.where(mz['hit'][..., None], (.25+.7*np.abs(n@f))[..., None]*np.ones(3), 1.)

def completeness(n):
    p = O/'meshes'/f'tl_{n}'/'score.json'
    if not p.exists(): return None
    rows = [r for r in json.loads(p.read_text())['rows'] if r.get('surface') == 'all' and r.get('case_id') == 0]
    return rows[0]['completeness_pct'] if rows else None

def fig_a():
    zi = loadz(OUTC/'inputs.npz'); K, W2C = zi['K'].astype(float), zi['W2C'].astype(float); photo = zi['photo']; tgt = zi['target_depth'].astype(float); tw = zi['target_weight'].astype(float); c = CROP_A
    fig, axs = plt.subplots(4, 1+len(STATES), figsize=(2.35*(1+len(STATES)), 2.35*4*(c[3]-c[1])/(c[2]-c[0])+1.9), facecolor='white')
    # input column
    a = axs[0, 0]; show(a, photo, (0, 0, photo.shape[1], photo.shape[0]), '입력'); a.add_patch(Rectangle((c[0], c[1]), c[2]-c[0], c[3]-c[1], fill=False, ec='#F2C14E', lw=1.6)); note(a, '실제 사진 한 장\n(노란 틀 = 확대 자리)', 'lower left', 8)
    show(axs[1, 0], crop(photo, c), c); note(axs[1, 0], '사진 (맞출 대상 1)')
    vt = np.isfinite(tgt) & (tgt > 0) & (tw > 0); Hh, Ww = tgt.shape; R = W2C[:3, :3]; C = -R.T@W2C[:3, 3]; u, v = np.meshgrid(np.arange(Ww, dtype=float), np.arange(Hh, dtype=float))
    dzw = (np.stack([(u-K[0, 2])/K[0, 0], (v-K[1, 2])/K[1, 1], np.ones_like(u)], -1)@R)[..., 2]; zz = np.where(vt, C[2]+tgt*dzw, np.nan); lo, hi = np.nanpercentile(crop(zz, c), [2, 98])   # target as height
    pz = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); ph, pd, _, _ = cast(pz['V'].astype(float), pz['F'].astype('i8'), K, W2C, Ww, Hh)
    old = vt & (zi['target_owner'] >= 0) & ph & (np.abs(tgt-np.nan_to_num(pd.astype(float), nan=-1e9)) <= .3)   # prior-patch target lying on the ALS prior surface (concept_check.py)
    show(axs[2, 0], np.where(crop(vt, c)[..., None], plt.cm.viridis(np.clip((crop(zz, c)-lo)/(hi-lo+1e-9), 0, 1))[..., :3], .92), c); note(axs[2, 0], '깊이 목표 (맞출 대상 2)\n판정이 사전 정보·MVS 중\n골라 만든 깊이, 높이로 칠함\n(노랑 = 높다)', fs=8)
    axs[3, 0].axis('off'); axs[3, 0].text(.04, .5, '메시는 학습한 원반을\n사진기 203대에서 렌더한\n깊이를 합쳐 만든다\n(TSDF, 5 cm 칸)', fontsize=9.5, color=INK, va='center', transform=axs[3, 0].transAxes)
    rec = []
    for j, n in enumerate(STATES, start=1):
        it = int(n); rj = json.loads((O/'renders'/n/'render.json').read_text()); title = f'{it:,}회'+(' (시작)' if it == 0 else (' (끝)' if it == 30000 else ''))
        na, nv = discs(axs[0, j], n, K, W2C, c); axs[0, j].set_title(title, fontsize=11, color=NAVY); note(axs[0, j], f'원반 {na/1e4:.1f}만 개' if na < 1e6 else f'원반 {na/1e6:.2f}백만 개', fs=8)
        rgb = np.asarray(Image.open(O/'renders'/n/'train1_rgb.png').convert('RGB')); show(axs[1, j], crop(rgb, c), c); note(axs[1, j], f'사진과 일치도 {rj["train1_psnr"]:.1f} dB', fs=8)
        dz = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha']); rd = dz['train1_depth'].astype(float); ok = vt & (dz['train1_alpha'].astype(float) > .5) & np.isfinite(rd) & (rd > 0)
        dd = np.where(ok, rd-tgt, np.nan); cd = crop(dd, c); img = np.where(np.isfinite(cd)[..., None], plt.cm.RdBu_r(np.clip(np.nan_to_num(cd)/1.0*.5+.5, 0, 1))[..., :3], .92); img[crop(old & (dd > .5), c)] = PURPLE; show(axs[2, j], img, c)
        w10 = float(np.nanmean(np.abs(cd) <= .1)*100) if np.isfinite(cd).any() else float('nan'); note(axs[2, j], f'목표와 10 cm 안 {w10:.0f} %', fs=8)
        mz = loadz(OUTC/f'mesh_ours_{n}.npz'); show(axs[3, j], crop(shade(mz, W2C), c), c); cp = completeness(n); note(axs[3, j], f'참값 면이 메시에 담김\n(건물 전체) {cp:.0f} %' if cp is not None else '', fs=8)
        rec.append(dict(state=n, gaussians=na, discs_in_crop=nv, psnr=rj['train1_psnr'], depth_within_10cm_pct_crop=w10, completeness_building_pct=cp))
    for r, t in enumerate(['① 원반', '② 렌더 영상', '③ 깊이: 목표와의 차이', '④ 메시']): axs[r, 0].set_ylabel(t, fontsize=12, color=NAVY)
    fig.suptitle('가우시안 스플래팅은 어떻게 배우나: 같은 사진기, 같은 자리에서 반복마다', fontsize=15, color=NAVY, x=.01, ha='left', y=.995)
    fig.text(.01, .955, '① 장면을 작은 반투명 원반 수만~수백만 개로 나타낸다  →  ② 원반을 사진기에서 겹쳐 그린다  →  ③ 사진, 그리고 깊이 목표와 비교해 차이가 줄도록 원반의 위치·크기·색·투명도를 고치고,'
             '\n     모자란 곳은 원반을 쪼개 늘린다 (반복)  →  ④ 학습이 끝나면 여러 사진기의 렌더 깊이를 합쳐 메시를 만든다.   ③ 색: 빨강 = 렌더가 목표보다 멀다(낮다), 파랑 = 가깝다(높다), ±1 m에서 가장 진함;\n     보라 = 사전 정보 조각의 목표가 옛 ALS 지붕 높이(지금 지붕보다 약 5 m 위)에 있고 렌더가 그 높이로 가지 않는 곳 (B173은 지붕이 바뀐 건물)',
             fontsize=9.5, color=INK, va='top')
    fig.tight_layout(rect=(0, 0, 1, .93)); FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/'concept_A_학습과정.png', dpi=110, facecolor='white'); plt.close(fig)
    return rec

def fig_b():
    zi = loadz(OUTC/'inputs.npz'); W2C = zi['W2C'].astype(float); photo = zi['photo']; c = CROP_B; prep = json.loads((OUTC/'concept_prep.json').read_text())
    cols = [('사진', None, None), ('사진만 쓴 2DGS', 'imgonly_2dgs', 'imgonly_2dgs'), ('사전 정보를 미리 믿는 GeoGS (ALS)', 'geogs_als', 'geogs_als'), ('본 방법', 'ours', 'ours_30000')]
    fig, axs = plt.subplots(2, 4, figsize=(4*3.1, 2*3.1*(c[3]-c[1])/(c[2]-c[0])+1.4), facecolor='white'); rec = []
    for j, (t, rk, mk) in enumerate(cols):
        if rk is None:
            show(axs[0, j], crop(photo, c), c, t); axs[1, j].axis('off')
            axs[1, j].text(.04, .5, '메시 색\n회색 = 참값과 21 cm 안\n빨강 = 참값보다 위\n파랑 = 참값보다 아래\n흰색 = 메시 없음\n(참값은 색칠에만 씀)', fontsize=10, color=INK, va='center', transform=axs[1, j].transAxes); continue
        if rk == 'ours': rgb = np.asarray(Image.open(O/'renders/30000/train1_rgb.png').convert('RGB')); ps = json.loads((O/'renders/30000/render.json').read_text())['train1_psnr']
        else: z = loadz(OUTC/f'compare_{rk}.npz', ['rgb']); rgb = z['rgb']; ps = prep['compare'][rk]['psnr']
        show(axs[0, j], crop(rgb, c), c, t); note(axs[0, j], f'사진과 일치도 {ps:.1f} dB', fs=9)
        mz = loadz(OUTC/f'mesh_{mk}.npz'); e = mz['error_m'].astype(float); hit = mz['hit']; R = W2C[:3, :3]; sh = .3+.65*np.abs(mz['normal'].astype(float)@R[2])
        a = np.clip((np.abs(np.nan_to_num(e))-TAU)/(1-TAU), 0, 1)[..., None]; col = np.where((np.abs(np.nan_to_num(e)) <= TAU)[..., None], GREYM, np.where((e > 0)[..., None], GREYM*(1-a)+RED*a, GREYM*(1-a)+BLUE*a))
        img = np.where(hit[..., None], col*sh[..., None], 1.); show(axs[1, j], crop(img, c), c)
        ch, ce = crop(hit, c), crop(e, c); fin = ch & np.isfinite(ce); within = float((np.abs(ce[fin]) <= TAU).mean()*100) if fin.any() else float('nan')
        note(axs[1, j], f'메시 화소 중 21 cm 안 {within:.0f} %', fs=9); rec.append(dict(column=t, psnr=ps, mesh_pixels_in_crop=int(ch.sum()), within_tau_pct=within))
    axs[0, 0].set_ylabel('렌더 영상', fontsize=12, color=NAVY); axs[1, 0].set_ylabel('메시', fontsize=12, color=NAVY)
    fig.suptitle('왜 본 방법의 메시가 좋은가: 30,000회, 같은 사진기', fontsize=15, color=NAVY, x=.01, ha='left', y=.995)
    ck = json.loads((OUTC/'concept_check.json').read_text())['B']; rp = {k: ck[k]['red_pct_of_mesh'] for k in ck}
    fig.text(.01, .962, f'세 방법 모두 사진과는 비슷하게 맞춘다(윗줄). 그러나 메시는 다르다(아랫줄): 참값보다 21 cm 넘게 위로 뜬 면이 2DGS {rp["imgonly_2dgs"]:.0f} %, GeoGS {rp["geogs_als"]:.0f} %, 본 방법 {rp["ours_30000"]:.0f} %.\n'
             '크게 다른 점은 깊이 목표다: 2DGS는 깊이 목표가 없고, GeoGS는 사전 정보 깊이와 단안 깊이 추정(DA3)을 쓰며(설정 기록 기준), 본 방법은 판정이 사전 정보·MVS 중에서 고른 깊이를 쓴다.\n'
             '다만 처음 원반을 놓는 방법 등 다른 차이도 있어, 이 그림만으로 메시 차이를 깊이 목표 하나의 몫이라고 나눌 수는 없다.\n'
             '뜬 면 가운데 옛 ALS 지붕 면과 30 cm 안에 겹치는 것은 세 방법 모두 3 % 아래라, GeoGS의 뜬 면이 옛 지붕 탓인지는 이 그림으로 알 수 없다. 유리 채광창의 파란 줄은 세 방법 모두 유리 면보다 아래에 면을 만든 곳이다.', fontsize=9.5, color=INK, va='top')
    fig.tight_layout(rect=(0, 0, 1, .9)); fig.savefig(FIG/'concept_B_왜잘되나.png', dpi=110, facecolor='white'); plt.close(fig)
    return rec

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'AB'; out = dict(at=now(), rule=__doc__, crop_a=CROP_A, crop_b=CROP_B, tau_m=TAU, scientific_verdict=None)
    if 'A' in which: out['A'] = fig_a(); print('A', out['A'], flush=True)
    if 'B' in which: out['B'] = fig_b(); print('B', out['B'], flush=True)
    dump(FIG/f'concept_fig_{which}.json', out); print('DONE', flush=True)

if __name__ == '__main__': main()
