"""덧붙임 4 이름표 점검 묶음(사람이 눈으로 봄, 에이전트는 맞음·틀림을 판정하지 않음).
뽑기: 사전 정보마다 가2 정답 여섯 종류마다 20개(씨앗 고정), 한 건물 5개까지, 지붕·벽은 그 정답의 넓이 비율대로, 모자라면 있는 만큼.
칸: 그림 2와 같은 단면(드론 LiDAR, 사전 정보 면, 영상 깊이 점, 0 ± τ, h_I ± τ). 칸 위 = 번호만, 칸 아래 = 건물·자리·지붕/벽·τ. 정답 이름·색·점 수 없음.
쪽: 20칸(4 x 5), 사전 정보마다 6쪽. 정답이 쪽으로 드러나지 않게 사전 정보 안 120칸을 섞어 쪽에 나눔.
나오는 것: /docs/audit/가2/page_{L,A}_NN.png(+json), audit_sheet.csv, audit_key.csv(번호 ↔ 가2 정답). 사용: g8_audit.py"""
from common import *
import pandas as pd
import g4_figs as G4
from g4_figs import plt, Patch, Slices, draw, attach_prior, prior_surface, geo
AD = D/'audit/가2'; ABBR = {'LoD2': 'L', 'ALS': 'A'}
def sample(f, cfgA, rng):
    out = []; notes = []
    for a in FWD:
        g = f[f.answer == a]; A = g.groupby('surface').area_m2.sum(); want = {}
        if not len(g): notes.append(dict(answer=a, wanted=cfgA['per_answer'], got=0)); continue
        if len(A) == 1: want[A.index[0]] = cfgA['per_answer']
        else:
            r = int(round(cfgA['per_answer']*A.get('지붕', 0)/A.sum())); want = {'지붕': r, '벽': cfgA['per_answer'] - r}
        got = []; per = {}   # 한 건물 5개 = 정답 종류 하나 안에서(지붕·벽 합)
        for s_, k in want.items():
            h = g[g.surface == s_]; order = rng.permutation(len(h)); taken = 0
            if k == 0: notes.append(dict(answer=a, surface=s_, wanted=0, got=0, candidates=len(h))); continue
            for i in order:
                b = h.building.iloc[i]
                if per.get(b, 0) >= cfgA['max_per_building']: continue
                per[b] = per.get(b, 0) + 1; got.append(h.iloc[i]); taken += 1
                if taken == k: break
            notes.append(dict(answer=a, surface=s_, wanted=k, got=taken, candidates=len(h)))
        out += got
    return out, notes
def main():
    c = cfg(); A_ = c['ga2']['audit']; rng = np.random.default_rng(A_['seed']); G4.COL = c['colours']; G4.HLAB = 'h_I'; AD.mkdir(parents=True, exist_ok=True)
    sheet = []; key = []; allnotes = []
    for prior in PRIORS:
        f = pd.read_csv(O/f'forward_{prior}_ga2.csv.gz'); rows, notes = sample(f, A_, rng); allnotes += [dict(prior=PN[prior], **n) for n in notes]
        order = rng.permutation(len(rows)); rows = [rows[i] for i in order]; Pg = geo(prior); S = prior_surface(Pg, prior); exs = []
        for k, row in enumerate(rows):
            i = int(row.patch_index); n = Pg['normal'][i]; ph = Pg['prior_height_m'][i]; u = Pg['tangent1'][i] - (Pg['tangent1'][i]@n)*n; u /= np.linalg.norm(u)
            lab = f'{ABBR[prior]}-{k+1:03d}'; e = dict(ref=Pg['centre'][i] + np.nan_to_num(ph)*n, n=n, u=u, H=5. if row.kind == 2 else 10., tau=row.tau_m, hM=row.h_I_m, tile=Pg['tiles'][Pg['tile'][i]],
                building=row.building, place=row.place, surface=row.surface, answer=row.answer, nb0=row.gt_band_prior, nbM=row.gt_band_image, clusters=[], blind=True, label=lab)
            exs.append(e); sheet.append({'번호': lab, '사전 정보': PN[prior], '패치 번호': row.patch_id, '건물': row.building, '자리': row.place, '지붕·벽': row.surface, 'τ (m)': row.tau_m, '쪽': f'{ABBR[prior]}-{k//20+1:02d}', '보이는 것': '', '메모': ''})
            key.append({'번호': lab, '가2 정답': row.answer, '묶음 가 정답': row.ga_answer, 'h_I (m)': row.h_I_m, '0±τ 참값 점': row.gt_band_prior, 'h_I±τ 참값 점': row.gt_band_image, '기둥 안 참값 점': row.gt_column})
        Slices(exs); attach_prior(exs, S)
        for pg in range(0, len(exs), 20):
            part = exs[pg:pg+20]; fig, axs = plt.subplots(4, 5, figsize=(9.2, 8.8), constrained_layout=True)
            for j, ax in enumerate(axs.flat):
                if j >= len(part): ax.axis('off'); continue
                draw(ax, part[j], dict(prior=part[j]['prior_pts']))
            hd = [Patch(color='k', label='드론 LiDAR'), Patch(color='#534AB7', label='사전 정보 면'), Patch(color='#3B6D11', label='영상 깊이 점'), Patch(color='#AFA9EC', label='0 ± τ'), Patch(color='#97C459', label='h_I ± τ')]
            fig.legend(handles=hd, loc='lower center', ncol=5, fontsize=6, frameon=False, bbox_to_anchor=(.5, -.025)); name = f'page_{ABBR[prior]}_{pg//20+1:02d}'
            fig.suptitle(f'{PN[prior]} 이름표 점검 {pg//20+1}쪽 (가로 = 패치 칸 옆 방향 m, 세로 = 법선 거리 m, 사전 정보 = 0)', fontsize=8.5)
            fig.savefig(AD/f'{name}.png', dpi=300, bbox_inches='tight', pad_inches=.08); plt.close(fig)
            dump(AD/f'{name}.json', dict(at=now(), page=name, labels=[e['label'] for e in part], source=str(O/f'forward_{prior}_ga2.csv.gz'), note='정답 이름은 audit_key.csv 에만', scientific_verdict=None)); print('PAGE', name, flush=True)
    pd.DataFrame(sheet).to_csv(AD/'audit_sheet.csv', index=False); pd.DataFrame(key).to_csv(AD/'audit_key.csv', index=False)
    dump(AD/'audit_sampling.json', dict(at=now(), seed=A_['seed'], rule=A_, counts=allnotes, scientific_verdict=None)); progress(f'점검 묶음: {len(sheet)}칸, {len(set(s["쪽"] for s in sheet))}쪽')
if __name__ == '__main__': main()
