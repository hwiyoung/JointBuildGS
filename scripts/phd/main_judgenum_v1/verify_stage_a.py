"""Independent row/formula checks and real-point brute-force replay."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from PIL import Image
from lock_config import dump,sha,stamp
from cylinder_runtime import RADII,HS
C=Path('/cfg');O=Path('/out');D=Path('/docs');R=Path('/repo')

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());allowed=set(cfg['scope']['development'])
    held=set(json.loads((O/'holdout/scope_membership.json').read_text())['buildings'])
    excluded={r['building'] for r in cfg['scope']['excluded']};checked=0;unknown=0
    for p in sorted((O/'core_points_stage_a').glob('*.npz')):
        with np.load(p) as z:
            assert set(z['building'])<=allowed and not(set(z['building'])&(held|excluded))
            n=z['n'];j=z['judgment_before'];a=np.nan_to_num(z['a_cm'],nan=0.)
            valid=(n>=4)&np.isfinite(z['s_cm'])&np.isfinite(z['sigma_p_cm'])
            dl=1.96*np.sqrt(z['s_cm'][valid]**2/n[valid]+a[valid]**2+2.75**2+z['sigma_p_cm'][valid]**2)
            assert np.allclose(z['DL_cm'][valid],dl,atol=1e-10,rtol=1e-12)
            assert np.array_equal(j[valid],(np.abs(z['d_mean_cm'][valid])>dl).astype(np.int8))
            assert np.all(j[(n>=0)&(n<4)]==2) and not np.any(j[n<0]==2)
            assert np.all(j[(n>=4)&~valid]==-1)
            unknown+=int((j<0).sum());checked+=len(n)
    spec=importlib.util.spec_from_file_location('reference_face','/repo/scripts/phd/main_widen0_v2/u_core.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    tile='6907_53359';W=Path(cfg['sources']['widen']);X=np.load(W/'holdout/internal/points'/tile/'mvs_a_xyz.npy').astype(float)
    receipt=json.loads((O/'cylinders'/f'{tile}.complete.json').read_text())
    raw=np.memmap(O/'cylinders'/f'{tile}.bin',dtype='<f8',mode='r',shape=(sum(r['count'] for r in receipt['parts']),3,10,7))
    replay=0;maxdiff=0.;core_ids=[]
    for part in receipt['parts']:
        with np.load(part['file']) as z:
            for kind in [1,2]:
                candidates=np.flatnonzero((z['kind']==kind)&z['normal_defined'])
                if not len(candidates):continue
                for i in np.unique(candidates[[0,len(candidates)//2,-1]]):
                    core_ids.append(str(z['patch_id'][i]));v=X-z['centre'][i];n=z['normal'][i];t=v@n
                    ll=v-t[:,None]*n;r2=np.sum(ll*ll,axis=1)
                    for h,H in enumerate(HS):
                        for ri,r in enumerate(RADII):
                            col=t[(np.abs(t)<=H)&(r2<=r*r)];o,_,_=mod.find_face(col,H,cfg['cylinder']['outer_face'])
                            vals=col[(col>=o-1)&(col<=o+1)] if o is not None else np.empty(0)
                            expected=np.full(7,np.nan);expected[0]=len(vals);expected[6]=len(col)
                            if len(vals):
                                med=np.median(vals);expected[1:6]=[np.mean(vals),med,np.std(vals,ddof=1) if len(vals)>1 else np.nan,1.4826*np.median(np.abs(vals-med)),o]
                            got=raw[part['start']+i,h,ri];finite=np.isfinite(expected)
                            assert np.array_equal(np.isfinite(got),finite)
                            assert np.allclose(got[finite],expected[finite],atol=1e-8,rtol=1e-10),(core_ids[-1],h,ri,got,expected)
                            maxdiff=max(maxdiff,float(np.max(np.abs(got[finite]-expected[finite]))));replay+=1
    scanned=0
    for root in [C,D,R/'scripts/phd/main_judgenum_v1']:
        for p in root.rglob('*'):
            if p.is_file() and p.suffix in ['.json','.md','.csv','.txt','.py','.sh','.cpp']:
                text=p.read_text();assert not any(bid in text for bid in held),f'holdout identity in public file: {p}'
                scanned+=1
    images=[]
    for p in (D/'figures').glob('*.png'):
        assert p.with_suffix('.json').exists()
        with Image.open(p) as im:
            assert min(im.info.get('dpi',(0,0)))>299
            images.append({'file':p.name,'width':im.width,'height':im.height,'dpi':im.info['dpi']})
    old=json.loads((O/'holdout/private_config_history/judgenum_v1.r0.lock.json').read_text())
    for path,digest in old['sources'].items():assert sha(path)==digest,path
    result={'status':'PASS','at':stamp(),'all_core_rows_checked':checked,'unavailable_rows':unknown,
      'real_source_cylinders_replayed':replay,'replayed_patch_ids':core_ids,'real_replay_maximum_absolute_difference_m':maxdiff,
      'public_text_files_scanned_for_holdout_ids':scanned,'figures':images,
      'inherited_source_locks_unchanged':True,'scientific_verdict':None}
    dump(O/'stage_a_verification.json',result);dump(D/'tables/stage_a_verification.json',result)
    text=(D/'중간보고_v1.md').read_text().replace('원통 반지름, 검출 한계, 판단 1, 최소 넓이, 처음 선택, 민감도, 확인용 셈은 완료 결과로 보고하지 않는다. 이후 계산 결과에 따라 이 중간 보고를 갱신한다.',
      '원통 반지름·검출 한계·처리 전 판단 1을 계산했다. 최소 넓이·처음 선택·민감도·확인용 셈은 아직 완료하지 않았다.')
    text+='\n## 판단 1 지도와 단면\n\n처리 후 지도와 단면의 사진 판단·처음 선택은 단계 나 이후에 추가한다. 아직 없는 값을 회색 판단이나 0으로 표시하지 않았다.\n'
    for prior in ['LoD2','ALS']:text+=f'\n![{prior} 판단 1](figures/stage_a_judgment_map_{prior}.png)\n'
    for i,sec in enumerate(cfg['figures']['section_coordinates']):text+=f"\n![단면 {i+1}](figures/stage_a_section_{i+1}_{sec['prior']}.png)\n"
    text+=f'\n확인: 전체 {checked:,}행의 검출 한계·판단 식, 실제 자료 원통 {replay}개 직접 비교, 앞 작업 입력 잠금, 공개 파일의 확인용 건물 번호 제외, PNG 300 dpi를 검사했다. 직접 비교의 최대 차이는 {maxdiff:.3g} m다. 과학적 결론은 내리지 않았다.\n'
    (D/'중간보고_v1.md').write_text(text)
    print('STAGE_A_VERIFICATION_PASS',checked,replay,maxdiff)

if __name__=='__main__':main()
