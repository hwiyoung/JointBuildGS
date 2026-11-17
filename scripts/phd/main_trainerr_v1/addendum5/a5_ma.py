"""Work ma (order 7): why seeds placed on a wrong target are deleted. GPU (/source = r31), six record scenes (addendum 4 work ra RECORD).
Seeds: prior seeds (seeds.npz origin 1) of the column patches of the addendum-4 work ra points (2,000 fixed + 2,000 kept, rng 0): 'fixed' = target wrong,
result right (the order's 'wrong target'); 'kept' = control. In the record run each seed Gaussian (born at initialization, init_id = seed) is followed:
  run <stem> : delete event (iteration, reason, first prune check after a reset), release / retarget before deletion; at every saved <reset>_pre_reset scene
               dump the addendum-4 work na values of the seeds alive then (2DGS compositing over every training view containing the centre: own alpha*T,
               front accumulated opacity, front weight by kind) -> payload addendum5/ma/seeds_<stem>.npz
  tables     : deleted wrong-target seeds vs deleted / surviving control seeds -> tables/ma_seeds.csv
Photo-loss difference with / without the seed: not computed (확인 불가: one extra render pair per seed and view; not in the records)."""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
MA5 = A5O/'ma'
SCENES = ['B0_b10__ALS', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B173nb_b10__LoD2', 'R1rep_b10__ALS', 'R1rep_b10__LoD2']
RESETS = [3000, 6000, 9000, 12000]

def run(stem):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_ra as RA, a4_na as NA4, a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); m_ = RA.RECORD[stem][0]; P = RA.points(stem); praw = gt_row_patch(stem)
    sd = loadz(PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1'/stem/'seeds.npz', ['patch', 'origin']); sets = {}
    for name in ['fixed', 'kept']:
        pr = np.unique(praw[P[name]['pid']]); pr = pr[pr >= 0]; sets[name] = np.flatnonzero((sd['origin'] == 1) & np.isin(sd['patch'], pr))
    S0 = D4.load_pt(m_, '0'); i0 = S0['init_id'].numpy(); assert np.array_equal(i0, np.arange(len(i0))); uid0 = S0['uid'].numpy()
    E = load_events(m_, ('delete', 'release', 'retarget')); de = E['delete']; dl = {int(u): (int(r), int(it)) for u, r, it in zip(de['uid'], de['reason'], de['iteration'])}
    rel = {}; ret = {}
    for u, it in zip(E['release'].get('uid', []), E['release'].get('iteration', [])): rel.setdefault(int(u), []).append(int(it))
    for u, it in zip(E['retarget'].get('uid', []), E['retarget'].get('iteration', [])): ret.setdefault(int(u), []).append(int(it))
    S30 = D4.load_pt(m_, '30000'); live_init = set(S30['init_id'].numpy().tolist()); alive30 = set(S30['uid'].numpy().tolist())
    # seeds outside the record range have no delete event: deletion = first full-scene dump without the seed (reason unknown, -1)
    allu = np.concatenate([uid0[v] for v in sets.values()]); miss = {int(x) for x in allu if int(x) not in dl and int(x) not in alive30}
    if miss:
        names_ = sorted({p.stem for p in (m_/'trainlog/scene').glob('*.pt')}, key=lambda n: (int(n.split('_')[0]), 0 if 'pre' in n else 1)); left = set(miss)
        for n in names_:
            if not left: break
            us = set(D4.load_pt(m_, n)['uid'].numpy().tolist()); gone = {x for x in left if x not in us}
            for x in gone: dl[x] = (-1, int(n.split('_')[0]))
            left -= gone
        print('MA FALLBACK', stem, len(miss), 'unresolved', len(left), flush=True)
    out = {}
    for name, seeds in sets.items():
        u = uid0[seeds]; d_it = np.array([dl.get(int(x), (0, -1))[1] for x in u]); d_rs = np.array([dl.get(int(x), (0, -1))[0] for x in u])
        out[name] = dict(seed=seeds, uid=u, del_it=d_it, del_reason=d_rs, alive30=np.isin(u, list(alive30)), lineage30=np.isin(seeds, list(live_init)),
                         released_before=np.array([any(t < (d if d >= 0 else 10**9) for t in rel.get(int(x), [])) for x, d in zip(u, d_it)]),
                         retargeted_before=np.array([any(t < (d if d >= 0 else 10**9) for t in ret.get(int(x), [])) for x, d in zip(u, d_it)]))
    md, mi = D4.views_of(stem); names = sorted(mi)
    for rs in RESETS:
        st = f'{rs}_pre_reset'
        if not (m_/'trainlog/scene'/f'{st}.pt').exists(): continue
        S = D4.load_pt(m_, st); ix = {int(x): i for i, x in enumerate(S['uid'].numpy())}
        rows_all = {name: np.array([ix[int(x)] for x in o['uid'] if int(x) in ix], 'i8') for name, o in out.items()}
        allrows = np.unique(np.concatenate(list(rows_all.values()))) if any(len(v) for v in rows_all.values()) else np.zeros(0, 'i8')
        if not len(allrows): continue
        with torch.no_grad():
            g = D4.gmodel(S); tag = torch.as_tensor(S['target_tag'].long().numpy(), device='cuda'); tidx = torch.as_tensor(S['target_index'].long().numpy(), device='cuda')
            X = S['xyz'].double().numpy()[allrows]; acc = {k: [] for k in ['row', 'front', 'self_w', 'kind']}
            for j, nm in enumerate(names):
                mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
                with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape
                uu = K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]; vv = K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]; ins = okz & (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
                if not ins.any(): continue
                FA, SW, FK, ACC = NA4.comp(g, tag, tidx, camera(W, H, K, M, nm), np.floor(uu[ins]).astype('i8'), np.floor(vv[ins]).astype('i8'), z[ins], allrows[ins])
                acc['row'].append(allrows[ins]); acc['front'].append(FA); acc['self_w'].append(SW); acc['kind'].append(FK)
        R_ = {k: np.concatenate(v) for k, v in acc.items()}; uidr = S['uid'].numpy()
        for name, o in out.items():
            cw = np.full(len(o['uid']), np.nan); ov = np.full(len(o['uid']), np.nan); nv = np.zeros(len(o['uid'])); fk = np.zeros((len(o['uid']), 4))
            pos = {int(x): i for i, x in enumerate(o['uid'])}
            for r_, fa, sw, k4 in zip(R_['row'], R_['front'], R_['self_w'], R_['kind']):
                i = pos.get(int(uidr[r_]))
                if i is None: continue
                cw[i] = (0 if np.isnan(cw[i]) else cw[i])+sw; ov[i] = (0 if np.isnan(ov[i]) else ov[i])+(fa < .5); nv[i] += 1; fk[i] += k4
            o[f'cw_{rs}'] = cw; o[f'open_{rs}'] = ov; o[f'views_{rs}'] = nv; o[f'fk_{rs}'] = fk
        print('MA STATE', stem, st, len(allrows), round(time.monotonic()-t0), flush=True)
    MA5.mkdir(parents=True, exist_ok=True); savez(MA5/f'seeds_{stem}.npz', **{f'{n}__{k}': v for n, o in out.items() for k, v in o.items()})
    print('MA', stem, {n: len(o['uid']) for n, o in out.items()}, round(time.monotonic()-t0), flush=True)

def tables():
    rows = []; KO = ['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것']
    for stem in SCENES:
        p = MA5/f'seeds_{stem}.npz'
        if not p.exists(): continue
        z = loadz(p); avail = sorted({int(k.split('__')[1].split('_')[1]) for k in z if '__cw_' in k})
        for name, grp, sel in [('fixed', '틀린 목표 씨앗 · 제거됨', lambda o: o['del_it'] >= 0), ('kept', '대조: 지킨 점 씨앗 · 제거됨', lambda o: o['del_it'] >= 0), ('kept', '대조: 지킨 점 씨앗 · 살아남음', lambda o: o['alive30'])]:
            o = {k.split('__', 1)[1]: z[k] for k in z if k.startswith(name+'__')}; m = sel(o); n = int(m.sum())
            r = dict(stem=stem, group=grp, seeds_total=len(o['uid']), n=n, small_group=n < 30, lineage_alive_30000_pct=pct(o['lineage30']))
            if n:
                d = o['del_it'][m]; dd = d[d >= 0]
                r['deleted_iteration_q'] = q4(dd); r['deleted_at_first_check_after_reset_pct'] = pct(np.isin(dd, [x+100 for x in RESETS])) if len(dd) else None
                rs = o['del_reason'][m][d >= 0]; r['reason_opacity_pct'] = pct(rs == 1) if len(rs) else None; r['reason_size_pct'] = pct((rs == 2) | (rs == 3)) if len(rs) else None
                r['reason_unknown_outside_record_range'] = int((rs == -1).sum()); r['deleted_iteration_rule'] = 'delete event; reason -1 = no event (outside the record range): first full-scene dump without the seed'
                r['released_before_pct'] = pct(o['released_before'][m]); r['retargeted_before_pct'] = pct(o['retargeted_before'][m])
                # values at the reset before deletion (deleted) or at 3000 (surviving)
                cw, ov, nv, fk = [], [], [], np.zeros(4); used = []
                for i in np.flatnonzero(m):
                    di = o['del_it'][i]; cand = [x for x in avail if (di < 0 and x == 3000) or (di >= 0 and x < di)]
                    if not cand: continue
                    x = max(cand); used.append(x)
                    if np.isnan(o[f'cw_{x}'][i]): continue
                    cw.append(o[f'cw_{x}'][i]); ov.append(o[f'open_{x}'][i]); nv.append(o[f'views_{x}'][i]); fk += o[f'fk_{x}'][i]
                r['values_n'] = len(cw); r['reset_used'] = {str(k): used.count(k) for k in sorted(set(used))}
                r['colour_weight_sum_q'] = q4(cw); r['open_views_q'] = q4(ov); r['views_q'] = q4(nv)
                for k, ko in enumerate(KO): r[f'front_{ko}_share_pct'] = 100*float(fk[k]/max(fk.sum(), 1e-12)) if fk.sum() > 0 else None
                r['no_reset_dump_before_deletion'] = int(n-len(used)) if grp.endswith('제거됨') else None
            r['photo_loss_difference'] = '확인 불가(씨앗을 빼고 다시 그린 광도 손실은 기록에 없고 계산하지 않음)'
            rows.append(r)
    table5('ma_seeds', rows); print('MA TABLE', len(rows), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'run': lambda: run(a[1]), 'tables': tables}[a[0]]()
