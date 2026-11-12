"""Prototype for the strip critique (2026-11-12): why the Gaussian row and the mesh row do not read alike, and a mesh coloured by the Gaussian that draws it.
For one place and a few key states, from the close-up camera of spot_strips_cams.json:
  row 1 = visible discs (as in the strips, colour = role of the Gaussian),
  row 2 = mesh as in the strips (colour = judgment of the nearest patch if within TAU of the GT, purple beyond),
  row 3 = the same mesh coloured by the role of the per-pixel max alpha*T Gaussian of the same camera (spot_visible id image),
          used only where that Gaussian's centre lies within 0.5 m of the mesh hit along the view; else light grey ('이 시점에서 앞을 가린 원반').
Also counts, per state, the mesh-pixel shares by role of the drawing Gaussian. CPU."""
import sys
from video_v2 import *
from src.phd.prior_propagation_v6.orientation import axes_of_quat
from matplotlib.collections import EllipseCollection
from scipy.spatial import cKDTree
import spot_strips as SS
PLACE = sys.argv[1] if len(sys.argv) > 1 else 'wing'; STATES = sys.argv[2].split(',') if len(sys.argv) > 2 else ['2000', '10000', '30000']
OUTP = O/'spot_strips/proto'; OUTP.mkdir(parents=True, exist_ok=True); GATE = .5; NEUTRAL = np.array(to_rgb('#E5E3DC'))
ROLE = {'bound': None, 'released': '#FFFFFF', 'free': '#888780', 'old': PINK, 'outside': '#D3D1C7'}

def role_cols(vid, d, f_ord, f_sorted, full_idx):
    hit = np.isin(vid, full_idx); row = np.full(len(vid), -1); row[hit] = f_ord[np.searchsorted(f_sorted, vid[hit])]
    tag = np.where(row >= 0, d['target_tag'][row.clip(0)], -1); j = np.where(row >= 0, d['judgment'][row.clip(0)], -1); wr = (row >= 0) & (d['group33'][row.clip(0)] == 1)
    col = np.array([to_rgb(JC.get(int(jj), '#888780')) if tg == 1 else (to_rgb('#888780') if tg == 0 else ((1, 1, 1) if tg == 2 else to_rgb('#D3D1C7'))) for jj, tg in zip(j, tag)]).reshape(-1, 3)
    if len(col): col[wr] = to_rgb(PINK)
    lab = np.where(wr, 'old', np.where(tag == 1, 'bound', np.where(tag == 2, 'released', np.where(tag == 0, 'free', 'outside'))))
    return col, tag, lab

def main():
    S = Ctx(); P = SS.places(S)[PLACE]; cm = json.loads((O/'analysis/spot_strips_cams.json').read_text())['cams'][PLACE]; cam = dict(B=np.asarray(cm['B']), ctr=np.asarray(cm['ctr']), lo=np.asarray(cm['lo']), hi=np.asarray(cm['hi']))
    fig, axs = plt.subplots(3, len(STATES), figsize=(5.2*len(STATES), 10.5), facecolor='white'); ptree = cKDTree(S.pt[:, :2]); out = []
    for ci, n in enumerate(STATES):
        d = loadz(DER/'gaussians'/f'{n}.npz'); full_idx = d['full_gaussian_index'].astype(np.int64); f_ord = np.argsort(full_idx); f_sorted = full_idx[f_ord]
        vz = loadz(O/'spot_strips/visible'/f'{n}__{PLACE}.npz'); vid = vz['ids']; vcol, vtag, vlab = role_cols(vid, d, f_ord, f_sorted, full_idx)
        vx = vz['xyz'].astype(float); vax = axes_of_quat(vz['quat'].astype('f4')); vs = vz['scale'].astype(float); vop = vz['opacity'].astype(float)
        idimg0 = vz['id_image']; Hh, Ww = idimg0.shape; pos0 = np.searchsorted(vid, idimg0.clip(0)).clip(0, len(vid)-1); ok0 = (idimg0 >= 0) & (vid[pos0] == idimg0)
        a = axs[0, ci]; SS.show(a, cam, np.where(ok0[..., None], vcol[pos0], 1.))   # per pixel: role of the Gaussian that the renderer shows most there
        s, ang = SS.ell(cam, vx, vax[0]*vs[:, 0:1], vax[1]*vs[:, 1:2]); x, y, dz = SS.proj(cam, vx); o = np.argsort(-dz)
        a.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=a.transData, facecolors='none', edgecolors=(.17, .17, .16, .35), linewidths=.35))
        a.set_title(f'{S.it[n]:,}회', fontsize=13, color=NAVY)
        z = loadz(A/f'mesh_{n}.npz', ['vertices', 'faces', 'vertex_error_m']); V = z['vertices'].astype(float); F = z['faces']; cen = V[F].mean(1); wf = SS.in_win(P, cen[:, :2], margin=2.); Fk = F[wf]
        sc = SS.scene_of(V, Fk); W = int(vz['W']); hit, pid, nrm, (H, W_), dep = SS.cast(cam, sc, W=W); H = min(H, int(vz['H'])); hit = hit.reshape(-1, W)[:H]; pid = pid.reshape(-1, W)[:H]; nrm = nrm.reshape(-1, W, 3)[:H]; dep = dep[:H]
        fe = z['vertex_error_m'][Fk].mean(1); fc = cen[wf]; fn = np.cross(V[Fk[:, 1]]-V[Fk[:, 0]], V[Fk[:, 2]]-V[Fk[:, 0]]); fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        dd, ii = ptree.query(fc[:, :2]); reg = np.where((dd <= .5) & (np.abs(fn[:, 2]) >= .5), S.pj[ii], -1); base = np.tile(NEUTRAL, (len(Fk), 1))
        for j, c in JC.items(): base[reg == j] = to_rgb(c)
        T_ = TAU/100; a_ = np.clip((np.abs(fe)-T_)/(1-T_), 0, 1)[:, None]; col = np.where((np.abs(fe) <= T_)[:, None], base, P0*(1-a_)+P1*a_); sh = (.55+.45*np.abs(nrm@LT))
        img = np.where(hit[..., None], col[pid.clip(0, len(Fk)-1)]*sh[..., None], 1.); SS.show(axs[1, ci], cam, np.clip(img, 0, 1))
        idimg = vz['id_image'][:H, :W]; pos = np.searchsorted(vid, idimg.clip(0)); pos = pos.clip(0, len(vid)-1); ok_id = (idimg >= 0) & (vid[pos] == idimg)
        rdep = vz['depth_image'][:H, :W].astype(float)-500.; gate = ok_id & hit & (np.abs(rdep-dep) <= .25)   # the rendered surface there is the mesh surface (PROCFIG 0.25 m depth gate)
        bad = hit & (np.abs(fe[pid.clip(0, len(Fk)-1)]) > T_); rimg = np.where(gate[..., None], vcol[pos]*sh[..., None], np.where(hit[..., None], np.array(to_rgb('#EDEBE4'))*sh[..., None], 1.)); rimg = np.where(bad[..., None], np.array(to_rgb('#3C3489'))*sh[..., None], rimg); SS.show(axs[2, ci], cam, np.clip(rimg, 0, 1))
        labs = vlab[pos]; tot = int(hit.sum()); row = dict(state=n, mesh_pixels=tot, gated_pct=round(100*gate.sum()/max(tot, 1), 1))
        for k in ['bound', 'released', 'free', 'old', 'outside']: row[f'{k}_pct_of_gated'] = round(100*(gate & (labs == k)).sum()/max(gate.sum(), 1), 1)
        out.append(row); print('ROLE', row, flush=True)
    for r, t in enumerate(['가우시안 (화소마다 렌더에 가장 많이 보인 원반의 역할색, 선 = 원반 1σ)', '메시 (지금 띠 그림: 자리 판정색, 보라 = 참값과 21 cm 넘게 다름)', '메시 (그 화소를 그린 원반의 역할색, 보라 = 참값과 21 cm 넘게)']): axs[r, 0].set_ylabel(t, fontsize=10)
    hd = [Patch(color=JC[j], label=f'{JN[j]}에 묶인 원반') for j in [0, 2, 1, 4]]+[Patch(facecolor='white', edgecolor='#2C2C2A', label='풀린 원반'), Patch(color='#888780', label='자유 원반'), Patch(color=PINK, label='옛 지붕에 놓인 원반'),
          Patch(color='#D3D1C7', label='건물 범위 밖 원반'), Patch(color='#EDEBE4', label='렌더 면과 메시 면이 25 cm 넘게 다름'), Patch(color=P1, label='참값에서 21 cm 넘게 (둘째 줄)')]
    fig.legend(handles=hd, loc='lower center', ncol=5, frameon=False, fontsize=9); fig.tight_layout(rect=(0, .06, 1, 1)); fig.savefig(OUTP/f'{PLACE}_role.png', dpi=100, facecolor='white'); plt.close(fig)
    dump(OUTP/f'{PLACE}_role.json', dict(at=now(), rule=__doc__, rows=out, scientific_verdict=None)); print('DONE', flush=True)

if __name__ == '__main__': main()
