"""패치 표 만들기 (JC 저장 값 읽기만). 사전 정보마다 /out/patch_<prior>.npz (JC gid 차례), /out/photo_<prior>.npz (사진 점, s5_judge 차례).
참값은 패치의 경우(JC majority_counts)에만 붙인다."""
from common import *
def main(prior):
    cfg(); T = Timer(); ts = tiles(prior); pz = loadz(JC/'analysis'/f'patches_{prior}.npz')
    assert list(pz['gid_offset_tiles']) == ts
    cols = {}; bld_names = {}; pts = []
    def add(k, v):
        cols.setdefault(k, []).append(v)
    for ti, t in enumerate(ts):
        g = loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'building', 'kind', 'area', 'centre', 'normal', 'tangent1', 'surf', 'region', 'prior_height_m', 'n', 'n10', 'mvs_mean_m', 'mvs_median_m', 'mvs_sd_m', 'mvs_face_m', 'd_m', 'roof_type'])
        b = loadz(JC/'geometry/base'/f'{t}__{prior}.npz'); j = loadz(JC/'judge/base'/f'{t}__{prior}.npz')
        pl = loadz(JC/'place'/f'{t}__{prior}.npz', ['place', 'face']); tx = loadz(JC/'texture'/f'{t}__{prior}.npz', ['textureless'])
        assert np.array_equal(b['patch_id'], g['patch_id']) and np.array_equal(j['patch_id'], g['patch_id'])
        N = len(g['kind']); add('tile', np.full(N, ti, np.int16)); add('local', np.arange(N, dtype=np.int32))
        for k in ['kind', 'area', 'centre', 'normal', 'tangent1', 'surf', 'prior_height_m', 'n', 'n10', 'mvs_mean_m', 'mvs_median_m', 'mvs_sd_m', 'mvs_face_m', 'd_m']: add(k, g[k])
        add('region', g['region'].astype('<U4')); add('building', g['building'].astype('<U40')); add('roof_type', g['roof_type'].astype('<U8'))
        for k in ['u_M', 'sigma_P', 'sigma_W', 'r_m', 'L_m', 'd_for_check', 'geometry']: add(k, b[k])
        add('j_region', j['region'].T); add('j_reason', j['reason'].T); add('target_h', j['target_h'].T)
        for k in ['photo_code', 's_P', 's_M', 't']: add(k, j[k])
        add('place', pl['place']); add('face', pl['face']); add('textureless', tx['textureless'])
        # 사진 점 값 -> 패치
        pp = JC/'photo_prepared'/f'{t}.npz'; sc = JC/'photo_scores'/t/'scores.npz'
        obs = {k: np.full(N, np.nan) for k in ['fit_nmad', 'fit_count', 'plane_angle', 'views_P', 'views_M', 'texture_P', 'texture_M', 'mask_P', 'mask_M', 'nsel_P', 'nsel_M', 'pp_area']}
        mvs_av = np.zeros(N, bool); pp_row = np.full(N, -1, np.int64)
        if pp.exists():
            q = loadz(pp, ['point_id', 'source_index', 'prior', 'kind', 'area', 'available', 'selected_images', 'mvs_fit_count', 'mvs_fit_nmad_m', 'mvs_normal_angle_deg', 'mask_fraction_at_zero', 'centres', 'normals', 'tangent1'])
            s = loadz(sc) if sc.exists() else None
            if s is not None: assert np.array_equal(s['point_id'], q['point_id'])
            m = np.flatnonzero(q['prior'] == prior)
            grp = loadz(JC/'photo_groups'/f'{t}__{prior}.npz', ['patch_point', 'region']); geo = b['geometry']; P = len(grp['region'])
            assert np.array_equal(grp['patch_point'], j['photo_point'])
            allw = np.bincount(grp['patch_point'], weights=(geo != 0).astype(float), minlength=P) == 0
            lut = np.full(P, -1, np.int64); lut[q['source_index'][m]] = m; r = lut[j['photo_point']]; has = r >= 0; rr = r[has]
            nsel = (q['selected_images'] >= 0).sum(-1)
            obs['fit_nmad'][has] = q['mvs_fit_nmad_m'][rr]; obs['fit_count'][has] = q['mvs_fit_count'][rr]; obs['plane_angle'][has] = q['mvs_normal_angle_deg'][rr]
            obs['mask_P'][has] = q['mask_fraction_at_zero'][rr, 0]; obs['mask_M'][has] = q['mask_fraction_at_zero'][rr, 1]
            obs['nsel_P'][has] = nsel[rr, 0]; obs['nsel_M'][has] = nsel[rr, 1]; obs['pp_area'][has] = q['area'][rr]; mvs_av[has] = q['available'][rr, 1]; pp_row[has] = rr
            if s is not None:
                obs['views_P'][has] = s['valid_image_count'][rr, 0]; obs['views_M'][has] = s['valid_image_count'][rr, 1]; obs['texture_P'][has] = s['texture'][rr, 0]; obs['texture_M'][has] = s['texture'][rr, 1]
            # 사진 점 표 (s5_judge 와 같은 열)
            si = q['source_index'][m]
            e = dict(tile=np.full(len(m), ti, np.int16), row=m, kind=q['kind'][m], area=q['area'][m], region=grp['region'][si].astype('<U4'), all_within=allw[si], mvs_available=q['available'][m][:, 1],
                     n_selected=nsel[m], source_index=si, centre_M=q['centres'][m][:, 1], normal_M=q['normals'][m][:, 1], tangent1_M=q['tangent1'][m][:, 1], selected_M=q['selected_images'][m][:, 1])
            if s is not None: e.update(s_P=s['score'][m][:, 0], s_M=s['score'][m][:, 1], texture=s['texture'][m], scored=np.ones(len(m), bool))
            else: e.update(s_P=np.full(len(m), np.nan), s_M=np.full(len(m), np.nan), texture=np.full((len(m), 2), np.nan), scored=np.zeros(len(m), bool))
            pts.append(e)
        for k, v in obs.items(): add(k, v)
        add('mvs_available', mvs_av); add('pp_row', pp_row); add('photo_point', j['photo_point'])
    d = {k: np.concatenate(v) for k, v in cols.items()}
    cnt = pz['majority_counts']; assert len(cnt) == len(d['kind'])
    tot = cnt.sum(1); d['gt_n'] = tot; d['case'] = np.where(tot > 0, cnt.argmax(1), -1).astype(np.int8)
    with np.errstate(invalid='ignore', divide='ignore'): d['case_share'] = np.where(tot > 0, cnt.max(1)/tot, np.nan)
    d['mixed'] = (tot > 0) & (d['case_share'] < 0.8); d['majority_counts'] = cnt
    d['no_uM'] = (d['n'] >= 4) & np.isfinite(d['prior_height_m']) & np.isfinite(d['mvs_mean_m']) & (d['geometry'] == 9) & ~np.isfinite(d['u_M'])
    d['tiles'] = np.array(ts)
    savez(O/f'patch_{prior}.npz', **d)
    P = {k: np.concatenate([e[k] for e in pts]) for k in pts[0]}; savez(O/f'photo_{prior}.npz', **P)
    rec = dict(at=now(), prior=prior, patches=len(d['kind']), photo_points=len(P['kind']), outside=int((d['geometry'] == 1).sum()), no_uM=int(d['no_uM'].sum()), with_case=int((d['case'] >= 0).sum()), mixed=int(d['mixed'].sum()), seconds=T.s(), scientific_verdict=None)
    dump(O/f'patch_{prior}.json', rec); print('BUILD', json.dumps(rec), flush=True)
if __name__ == '__main__': main(sys.argv[1])
