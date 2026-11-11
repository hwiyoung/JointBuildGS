"""Video v2 (configs/phd/main_trainlog_v1/trainlog_v1.video_v2.json). CPU.
  prep            static 2D references (photo, prior depth, MVS depth, scope pixels), G static, curve data H
  frames <k> <n>  render frame chunk k of n (normal frames + rotation frames at hold states)
Frames are drawn only from saved states; nothing is interpolated."""
import sys
from proto_v2 import *
from PIL import Image
V2 = O/'video_v2'; CA = V2/'cache'; FR2 = V2/'frames'
CAM = 'DJI_20241217091247_0146_D'; ASPECT = 940/375; HOLDS = ['0', '3000_pre_reset', '7000', '15000', '30000']; ROT = [180+15*k for k in range(1, 24)]
STAGE0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'/SITE

def vcfg():
    p = C/'trainlog_v1.video_v2.json'; assert sha(p) == json.loads((C/'trainlog_v1.video_v2.lock.json').read_text())['config_sha256']; return json.loads(p.read_text())

class Ctx(Scene):
    def __init__(self):
        super().__init__(); sc = self.c['scope']; g = sc['buffered_footprint']; ring = np.asarray(g['coordinates'][0] if g['type'] == 'Polygon' else g['coordinates'][0][0], float)[:, :2]
        fp = np.asarray(sc['footprint']['coordinates'][0], float)[:, :2]; zt = float(np.nanmax(self.pz))+1.5; self.corners = np.array([[x, y, z] for x, y in fp for z in (self.c['scope']['ground_z'], zt)])
        saves = [json.loads(l) for l in (RUNM/'trainlog/saves.jsonl').read_text().splitlines()]; self.it = {s['name']: s['iteration'] for s in saves}
        self.names = sorted(self.it, key=lambda n: (self.it[n], 0 if n.endswith('pre_reset') else 1)); self.keys = set(self.c['key_iterations']); self.ground = sc['ground_z']
        self.gline, (self.c2, self.a1, self.a2, self.gax, self.gnrm) = section_line(self, 'cross', 28.); self.gat = 28.
    def view(self, az):
        B = basis(self.c, az); q = (self.corners-self.ctr)@B[:2].T; hx, hy = np.abs(q).max(0)*1.03
        if hx/hy < ASPECT: hx = hy*ASPECT
        else: hy = hx/ASPECT
        self.half = (hx, hy); return B
    def mesh_of(self, n):
        it = self.it[n]
        if (A/f'mesh_{n}.npz').exists(): return n
        k = [x for x in self.keys if x < it or (x == it and not n.endswith('pre_reset'))]; return str(max(k))

def ramp(v, lo, hi, fit=None):
    a = np.clip((v-lo)/(hi-lo), 0, 1)[..., None]; col = P0*(1-a)+P1*a
    return col if fit is None else np.where(fit[..., None], FIT, col)

# ---------------- prep ----------------
def prep():
    S = Ctx(); CA.mkdir(parents=True, exist_ok=True); cams = {v['name']: v for v in json.loads((O/'renders/cameras.json').read_text())['training']}; v = cams[CAM]
    K = np.asarray(v['K']); E = np.asarray(v['W2C']); W, H = v['width'], v['height']; R = E[:3, :3]; Cw = -R.T@E[:3, 3]
    uu, vv = np.meshgrid(np.arange(W), np.arange(H)); dc = np.stack([(uu-K[0, 2])/K[0, 0], (vv-K[1, 2])/K[1, 1], np.ones_like(uu, float)], -1).reshape(-1, 3); dw = dc@R
    z = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(z['V'].astype('f4')); tm.triangle.indices = o3d.core.Tensor(z['F'].astype('i4')); sc.add_triangles(tm)
    t = sc.cast_rays(o3d.core.Tensor(np.c_[np.tile(Cw, (len(dw), 1)), dw].astype('f4')))['t_hit'].numpy().reshape(H, W); prior = np.where(np.isfinite(t), t, np.nan)
    mvs = np.load(STAGE0/'maps/mvs'/f'{CAM}.npy').astype(float); conf = np.load(STAGE0/'maps/conf'/f'{CAM}.npy'); mvs = np.where(np.isfinite(mvs) & (mvs > 0) & (conf > 0), mvs, np.nan)
    ref = np.where(np.isfinite(mvs), mvs, prior); Pw = Cw+dw*ref.reshape(-1, 1); scope = scope_mask(Pw, S.c).reshape(H, W) & np.isfinite(ref)
    photo = np.asarray(Image.open(STAGE0/f'scene_{PRIOR}/images/{CAM}.jpg').convert('RGB'), np.float32)/255
    savez(CA/'static2d.npz', prior=prior.astype('f4'), mvs=mvs.astype('f4'), scope=scope, photo=photo)
    # G static: prior cut, truth in band, targets in band
    pseg = cut(z['V'].astype(float), z['F'], S.c2, S.gnrm, S.gat, S.gax); rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz'])['xyz'].astype(float)
    rv = (rows[:, :2]-S.c2)@S.gnrm; rm = (rv >= S.gat) & (rv < S.gat+1) & scope_mask(rows, S.c); pv = (S.pt[:, :2]-S.c2)@S.gnrm; pm = (pv >= S.gat) & (pv < S.gat+1)
    savez(CA/'gstatic.npz', prior_seg=pseg, gt_s=(rows[rm, :2]-S.c2)@S.gax, gt_z=rows[rm, 2], tg_s=(S.pt[pm, :2]-S.c2)@S.gax, tg_z=S.pt[pm, 2], tg_w=1.96*S.psig[pm], tg_j=S.pj[pm])
    # E rasters and 30,000 occlusion depth for every camera used
    need = {}
    for n in S.names: need.setdefault(S.mesh_of(n), set()).add(180)
    for n in HOLDS: need.setdefault(S.mesh_of(n), set()).update(a % 360 for a in ROT)
    for az in [180]+[a % 360 for a in ROT]:
        B = S.view(az); np.save(CA/f'D30_{az}.npy', S.raster(S.m30, B, 940)[1].astype('f4'))
    for mk, azs in need.items():
        m = S.mesh(mk)
        for az in sorted(azs):
            B = S.view(az); img, _ = S.raster(m, B, 940); savez(CA/f'E_{mk}_{az}.npz', img=(np.clip(img, 0, 1)*255).astype('u1'))
        print('E', mk, len(azs), flush=True)
    # curves H
    curve = [json.loads(l) for l in (RUNM/'trainlog/curve.jsonl').read_text().splitlines()]
    st2 = loadz(CA/'static2d.npz'); from scipy.spatial import cKDTree; tree = cKDTree(S.pt[:, :2]); out = {}
    ref_rows = loadz(PF/'work/reference_building.npz'); pg = loadz(PF/'work/patch_groups.npz', ['group'])['group']; own = ref_rows['owner']; g1 = np.where(own >= 0, pg[own.clip(0)], 0) == 1; rid = ref_rows['row_id']
    tau = loadz(GT/'scenes'/STEM/'rows.npz', ['row_tau_m'])['row_tau_m'][rid]
    for n in S.names:
        d = loadz(DER/'gaussians'/f'{n}.npz'); r = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha']); dep = r['train1_depth'].astype(float); ok = (r['train1_alpha'].astype(float) > .5) & (dep > 0) & st2['scope']
        rec = dict(iteration=S.it[n], d_prior_m=float(np.nanmedian(np.abs(dep-st2['prior'])[ok & np.isfinite(st2['prior'])])) if (ok & np.isfinite(st2['prior'])).any() else None,
                   d_mvs_m=float(np.nanmedian(np.abs(dep-st2['mvs'])[ok & np.isfinite(st2['mvs'])])) if (ok & np.isfinite(st2['mvs'])).any() else None, wrong_alive=int((d['group33'] == 1).sum()))
        nw = ~d['wall']; dd, ii = tree.query(d['xyz'][nw, :2].astype(float)); near = dd <= .35; j = S.pj[ii]; tag = d['target_tag'][nw]
        for jj in [0, 2, 1, 4]:
            m = near & (j == jj); rec[f'bound_frac_{jj}'] = float((tag[m] == 1).mean()*100) if m.any() else None
        p = O/'gtj/scenes'/STEM/'distances'/f'tl_{n}.npz'
        if p.exists(): s = loadz(p, ['row_s'])['row_s'][rid]; rec['wrong_site_fit_pct'] = float((np.isfinite(s) & (np.abs(s) <= tau))[g1].mean()*100)
        out[n] = rec; print('H', n, flush=True)
    dump(CA/'H.json', dict(states=out, losses=[dict(iteration=c_['iteration'], rgb=c_['rgb'], depth=c_['depth'], dist=c_['dist'], normal=c_['normal']) for c_ in curve], scientific_verdict=None))

# ---------------- frames ----------------
def gline_of(S, n):
    if (A/f'mesh_{n}.npz').exists() and (S.it[n] in S.keys or n.endswith('pre_reset')):
        m = loadz(A/f'mesh_{n}.npz', ['vertices', 'faces']); return 'mesh', cut(m['vertices'].astype(float), m['faces'], S.c2, S.gnrm, S.gat, S.gax)
    cams = json.loads((O/'renders/cameras.json').read_text())['training']; r = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha', 'train2_depth', 'train2_alpha']); ss, zz = [], []
    for i, v in enumerate(cams):
        dep = r[f'train{i+1}_depth'].astype(float); al = r[f'train{i+1}_alpha'].astype(float); K = np.asarray(v['K']); E = np.asarray(v['W2C']); y, x = np.nonzero((al > .5) & (dep > 0)); d = dep[y, x]
        Pc = np.c_[(x-K[0, 2])*d/K[0, 0], (y-K[1, 2])*d/K[1, 1], d]; Pw = (Pc-E[:3, 3])@E[:3, :3]; pv = (Pw[:, :2]-S.c2)@S.gnrm; m = (pv >= S.gat) & (pv < S.gat+1)
        ss.append((Pw[m, :2]-S.c2)@S.gax); zz.append(Pw[m, 2])
    s = np.concatenate(ss); z = np.concatenate(zz); k = np.floor(s/.1).astype(int); ks = np.unique(k)
    return 'depth', (np.array([(q+.5)*.1 for q in ks]), np.array([np.median(z[k == q]) for q in ks]))

def frame(S, n, az, prev, out, V2c, H):
    it = S.it[n]; B = S.view(az); st = loadz(CA/'static2d.npz'); gs = loadz(CA/'gstatic.npz'); d = dict(loadz(DER/'gaussians'/f'{n}.npz')); d['_name'] = n
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor='white')
    stage = '불투명도 되돌림 직전' if n.endswith('pre_reset') else ('불투명도 되돌림 직후' if it in [3000, 6000, 9000, 12000] else ('밀도 제어 전' if it < 600 else ('밀도 제어 중' if it <= 14900 else '밀도 제어 끝')))
    fig.text(.012, .968, f'B173 · 학습 {it:,}회', fontsize=19, fontweight='bold', color=NAVY, va='center'); fig.text(.215, .968, stage+(f' · 방위 {az % 360}°' if az != 180 else ''), fontsize=12, color='#5F5E5A', va='center')
    ax = fig.add_axes([.44, .958, .55, .02]); ax.barh(0, 30000, color='#E5E3DC', height=1); ax.barh(0, it, color='#5F5E5A', height=1); ax.set_xlim(0, 30000); ax.axis('off')
    for x in [0, 3000, 7000, 15000, 30000]: ax.plot([x, x], [-.5, .5], color='white', lw=1.5)
    # row 1
    r = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha']); dep = r['train1_depth'].astype(float); al = r['train1_alpha'].astype(float) > .5
    rgb = np.asarray(Image.open(O/'renders'/n/'train1_rgb.png').convert('RGB'), np.float32)/255; ph = st['photo']
    def dmap(refd):
        diff = np.abs(dep-refd); okm = al & (dep > 0) & np.isfinite(refd); img = ramp(diff, TAU/100, 1., diff <= TAU/100); img = np.where(st['scope'][..., None], img, img*.35+.65); return np.where(okm[..., None], img, 1.)
    panels = [('A 실제 사진', ph), ('B GS 렌더', rgb), ('C 사진 손실 |렌더−사진|', ramp(np.abs(rgb-ph).mean(2), .05, .4, np.abs(rgb-ph).mean(2) <= .05)), ('D1 깊이 − 사전 정보 깊이', dmap(st['prior'])), ('D2 깊이 − 영상(MVS) 깊이', dmap(st['mvs']))]
    for i, (t, img) in enumerate(panels):
        a = fig.add_axes([.006+i*.199, .715, .19, .22]); a.imshow(np.clip(img, 0, 1)); a.axis('off'); a.set_title(t, fontsize=10.5, loc='left', color='#2e3a48', pad=3)
    # row 2
    aE = fig.add_axes([.006, .345, .49, .347]); aF = fig.add_axes([.504, .345, .49, .347]); mk = S.mesh_of(n)
    img = loadz(CA/f'E_{mk}_{az % 360}.npz')['img'].astype(np.float32)/255; d30 = np.load(CA/f'D30_{az % 360}.npy').astype(float)
    draw_E(aE, S, img, B, S.gline, depth=d30); draw_F(aF, S, d, B, d30, prev, S.gline)
    aE.set_title('E 메시 표면'+(f' (메시: {int(S.it[mk]) if mk in S.it else int(mk):,}회)' if mk != n else ''), fontsize=11, loc='left', color='#2e3a48', pad=2); aF.set_title('F 판정 지도 + 가우시안', fontsize=11, loc='left', color='#2e3a48', pad=2)
    # row 3: G
    aG = fig.add_axes([.04, .105, .40, .195]); g = gs; kind, gl = gline_of(S, n); grd = S.ground
    for j in JC:
        q = g['tg_j'] == j; aG.errorbar(g['tg_s'][q], g['tg_z'][q]-grd, yerr=g['tg_w'][q], fmt='none', ecolor=PALEJ[j], elinewidth=3)
    aG.add_collection(LineCollection(np.stack([g['prior_seg'][:, :, 0], g['prior_seg'][:, :, 1]-grd], 2), colors=PINK, linewidths=1.2, linestyles=(0, (5, 3))))
    aG.scatter(g['gt_s'], g['gt_z']-grd, s=1.2, c='black', lw=0)
    if kind == 'mesh': aG.add_collection(LineCollection(np.stack([gl[:, :, 0], gl[:, :, 1]-grd], 2), colors=NAVY, linewidths=1.2))
    else: aG.plot(gl[0], gl[1]-grd, color=NAVY, lw=1.2)
    gp = d['xyz'].astype(float); pv = (gp[:, :2]-S.c2)@S.gnrm; gm = (pv >= S.gat) & (pv < S.gat+1); gsx = (gp[:, :2]-S.c2)@S.gax; wr = d['group33'] == 1; tag = d['target_tag']
    aG.scatter(gsx[gm & (tag == 0) & ~wr], gp[gm & (tag == 0) & ~wr, 2]-grd, s=3, c=GREYG, lw=0)
    aG.scatter(gsx[gm & (tag == 2) & ~wr], gp[gm & (tag == 2) & ~wr, 2]-grd, s=9, facecolors='none', edgecolors='#2C2C2A', linewidths=.5)
    for j in JC:
        q = gm & (tag == 1) & (d['judgment'] == j) & ~wr; aG.scatter(gsx[q], gp[q, 2]-grd, s=5, c=JDARK[j], lw=0)
    aG.scatter(gsx[gm & wr], gp[gm & wr, 2]-grd, s=22, c=PINK, edgecolors='white', linewidths=.6, zorder=6)
    aG.set_xlim(g['gt_s'].min()-1, g['gt_s'].max()+1); aG.set_ylim(12, 25.5); aG.set_xlabel('건물 가로 방향 (m)', fontsize=9); aG.set_ylabel('지면 위 높이 (m)', fontsize=9); aG.tick_params(labelsize=8)
    aG.set_title('G 가로 단면 (긴 방향 28 m) · 면 선: '+('메시' if kind == 'mesh' else '렌더 깊이'), fontsize=11, loc='left', color='#2e3a48', pad=2)
    # row 3: H1 losses, H2 depth diffs, H3 fit
    hs = H['states']; xs = [hs[m]['iteration'] for m in S.names if not m.endswith('pre_reset')]; nn = [m for m in S.names if not m.endswith('pre_reset')]
    def series(ax, x, y, **kw):
        x = np.asarray(x, float); y = np.asarray([np.nan if v is None else v for v in y], float); lab = kw.pop('label', None); ax.plot(x, y, alpha=.25, **kw); m = x <= it; ax.plot(x[m], y[m], label=lab, **kw)
    def axfmt(ax, title):
        ax.axvline(it, color=NAVY, lw=1); ax.set_xlim(-300, 30300); ax.set_xticks([0, 15000, 30000]); ax.set_xticklabels(['0', '15,000', '30,000']); ax.tick_params(labelsize=7.5); ax.set_title(title, fontsize=10, loc='left', color='#2e3a48', pad=2)
        for r_ in [3000, 6000, 9000, 12000]: ax.axvline(r_, color='#B4B2A9', lw=.6, ls=':')
    h1 = fig.add_axes([.49, .105, .15, .195]); L = H['losses']; lx = [l_['iteration'] for l_ in L]
    for key, kw in [('rgb', dict(color='#2C2C2A', lw=1.1, label='사진')), ('depth', dict(color='#2C2C2A', lw=1.1, ls='--', label='깊이')), ('dist', dict(color='#888780', lw=1, label='2DGS 분포')), ('normal', dict(color='#888780', lw=1, ls='--', label='2DGS 법선'))]:
        series(h1, lx, [max(l_[key], 1e-4) if l_[key] else None for l_ in L], **kw)
    h1.set_yscale('log'); axfmt(h1, 'H1 손실'); h1.legend(fontsize=6.5, frameon=False, loc='upper right')
    h2 = fig.add_axes([.67, .105, .145, .195])
    series(h2, xs, [hs[m]['d_prior_m'] for m in nn], color=PINK, lw=1.4, label='사전 정보 깊이와'); series(h2, xs, [hs[m]['d_mvs_m'] for m in nn], color='#2C2C2A', lw=1.4, label='영상 깊이와')
    h2.axhline(TAU/100, color=NAVY, lw=.7, ls='--'); h2.set_yscale('log'); h2.set_ylim(.01, 20); axfmt(h2, 'H2 깊이 차 중앙값 (m)'); h2.legend(fontsize=6.5, frameon=False, loc='upper right')
    h3 = fig.add_axes([.845, .105, .13, .195])
    for jj in [0, 2, 1, 4]: series(h3, xs, [hs[m][f'bound_frac_{jj}'] for m in nn], color=JC[jj], lw=1.3, label=f'{JN[jj]} 영역 묶임')
    kx = [hs[m]['iteration'] for m in nn if 'wrong_site_fit_pct' in hs[m]]; ky = [hs[m]['wrong_site_fit_pct'] for m in nn if 'wrong_site_fit_pct' in hs[m]]
    series(h3, kx, ky, color=NAVY, lw=1.6, marker='o', ms=3, label='틀린 판정 자리 면 맞음'); h3.set_ylim(0, 102); axfmt(h3, 'H3 맞아 들어감 (%)')
    h3b = h3.twinx(); series(h3b, xs, [hs[m]['wrong_alive'] for m in nn], color=PINK, lw=1.2, ls='--', label='옛 지붕 출신 수 (오른쪽)'); h3b.set_yscale('log'); h3b.set_ylim(10, 5000); h3b.tick_params(labelsize=7, colors=PINK)
    a1_, b1_ = h3.get_legend_handles_labels(); a2_, b2_ = h3b.get_legend_handles_labels(); h3.legend(a1_+a2_, b1_+b2_, fontsize=6, frameon=False, loc='center right')
    hd = [Patch(color=PALEJ[j], label=f'바탕 {JN[j]}') for j in [0, 2, 1, 4]]+[Line2D([], [], marker='o', ls='', color=JDARK[j], label=f'묶임 {JN[j]}') for j in [0, 2, 1, 4]]
    hd += [Line2D([], [], marker='o', ls='', markerfacecolor='none', markeredgecolor='#2C2C2A', label='풀림'), Line2D([], [], marker='o', ls='', color=GREYG, label='자유(배경 출신)'),
           Line2D([], [], marker='o', ls='', color=PINK, label='옛 지붕 출신·틀린 판정 자리·사전 정보'), Line2D([], [], marker='x', ls='', color='#5F5E5A', label='지워짐'),
           Patch(color=FIT, label='맞음 (τ 안)'), Patch(color=P1, label='어긋남 (1 m까지 진해짐)'), Line2D([], [], color=NAVY, label='면 · 단면 위치'), Line2D([], [], marker='o', ls='', color='black', ms=3, label='참값')]
    fig.legend(handles=hd, loc='lower center', ncol=9, frameon=False, fontsize=8.6, bbox_to_anchor=(.5, -.005), handlelength=1.1, columnspacing=.9)
    fig.savefig(out, facecolor='white'); plt.close(fig)

def plan(S):
    items = []; prev = None
    for n in S.names:
        items.append(dict(name=n, az=180, prev=prev, kind='normal', hold=n in HOLDS))
        if n in HOLDS: items += [dict(name=n, az=a, prev=None, kind='rotation', hold=False) for a in ROT]
        prev = n
    return items

def frames(k, nchunks):
    S = Ctx(); FR2.mkdir(parents=True, exist_ok=True); H = json.loads((CA/'H.json').read_text()); items = plan(S); V2c = vcfg()
    for i, it_ in enumerate(items):
        if i % int(nchunks) != int(k): continue
        out = FR2/f'{i:04d}_{it_["name"]}_{it_["az"] % 360}.png'
        if out.exists(): continue
        frame(S, it_['name'], it_['az'], it_['prev'], out, V2c, H); print('FRAME', i, it_['name'], it_['az'], flush=True)
    if int(k) == 0:
        dump(V2/'frames.json', dict(at=now(), items=[dict(i, index=j, file=f'frames/{j:04d}_{i["name"]}_{i["az"] % 360}.png') for j, i in enumerate(items)], config=str(C/'trainlog_v1.video_v2.json'),
             config_sha256=sha(C/'trainlog_v1.video_v2.json'), plate='새 판 (다시 돌린 판), tl_B173nb_b10_ALS_s0 attempt2', camera='az 180 el 35 orthographic; rotation 15 deg steps at holds', scientific_verdict=None))

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'prep': prep()
    elif a[0] == 'frames': frames(a[1], a[2])

def one(n, az, prev=None):
    S = Ctx(); FR2.mkdir(parents=True, exist_ok=True); H = json.loads((CA/'H.json').read_text()); frame(S, n, int(az), prev, V2/f'test_{n}_{az}.png', vcfg(), H)
if __name__ == '__main__' and sys.argv[1] == 'one': one(*sys.argv[2:])
