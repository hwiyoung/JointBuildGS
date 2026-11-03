from common import *
import shutil
import calibrate
def main():
    previous=json.loads((O/'calibration.json').read_text());backup=O/'revisions/pre_ring'
    assert not backup.exists(), 'Reconciliation runs only once'
    backup.mkdir(parents=True)
    for name in ['calibration.json','geometry_raw','geometry']:
        p=O/name
        if p.is_dir():shutil.copytree(p,backup/name)
        else:shutil.copy2(p,backup/name)
    changes=[]
    for site in cfg()['sites']:
      for prior in cfg()['priors']:
        p=O/'geometry_raw'/f'{site}__{prior}.npz';d=loadz(p);rr=loadz(O/'ring_recomputed'/p.name)
        assert np.array_equal(d['patch_id'],rr['patch_id'])
        old=np.isfinite(d['u_mvs']);assert np.array_equal(d['u_mvs'][old],rr['u_mvs'][old])
        hit=~old&np.isfinite(rr['u_mvs']);d.update(u_mvs=rr['u_mvs'],ring_recompute_status=rr['status'])
        savez(p,**d);changes.append(dict(site=site,prior=prior,recovered=int(hit.sum()),patch_id=d['patch_id'][hit].tolist()))
    calibrate.main();current=json.loads((O/'calibration.json').read_text())
    same_sw=previous['sigma_W_m']==current['sigma_W_m'];oldr={ (x['site'],x['prior'],x['kind']):x['r_m'] for x in previous['r_rows']}
    same_b0_r=all(x['r_m']==oldr[(x['site'],x['prior'],x['kind'])] for x in current['r_rows'] if x['site']=='B0_b10')
    # Candidate planes depend on r; all_within also depends on the corrected uncertainty.
    if same_b0_r:
      for prior in cfg()['priors']:
        p=O/'photo_geometry'/f'B0_b10__{prior}.npz';shutil.copy2(p,backup/p.name)
        g=loadz(p);d=loadz(O/'geometry'/p.name);mp=loadz(O/'photo_mapping'/p.name);within=np.ones(len(g['point_id']),bool)
        np.logical_and.at(within,mp['point_index'],d['geometry']==0);g['all_within']=within;savez(p,**g)
    receipt=dict(at=now(),changes=changes,sigma_W_unchanged=same_sw,B0_r_unchanged=same_b0_r,
         B0_photo_score_reusable=same_b0_r,GT_read=False,scientific_verdict=None)
    dump(O/'ring_reconciliation.json',receipt)
    progress(f'원래 링 정의 재계산 반영: {sum(r["recovered"] for r in changes)}개 복구. 이전 잠정 기하값은 revisions/pre_ring에 보존. sigma_W 동일={same_sw}, B0 r 동일={same_b0_r}. B0 사진 점의 all_within은 최종 기하값으로 갱신. 설정 재잠금 없음.')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
