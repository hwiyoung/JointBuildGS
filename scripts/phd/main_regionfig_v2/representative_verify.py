"""Verify presentation against the supplied NPZ and unchanged prior artifacts."""
from rfcore import *
from PIL import Image
from pathlib import Path

def main():
    rev='representative_v1';root=DOC/rev;design=load(CFG/rev/'design.json');checks=[]
    def check(name,value):
        checks.append(dict(check=name,pass_=bool(value)))
        assert value,name
    check('locked design',sha(CFG/rev/'design.json')==load(CFG/rev/'design.lock.json')['config_sha256'])
    for protected in design['protected_inputs']:
        check('unchanged '+protected['path'],sha(protected['path'])==protected['sha256'])
    for ex in load(CFG/'regionfig_v2.json')['examples']:
        i=ex['id'];r=load(root/f'대표그림_{i}.json');f=r['focus'];pid=f['focus_patch_id']
        with np.load(PAY/'input'/f'{ex["prior"]}_sites.npz',allow_pickle=False) as z:
            ix=np.flatnonzero(z['patch_id']==pid);check(i+' unique supplied patch',len(ix)==1);ix=int(ix[0])
            v={k:z[k][ix] for k in ['gt_p','mvs_p','tau','z_category','z_check','judgment','cell']}
            for k,x in v.items():
                expected=f['focus_values'][k]
                check(i+' source '+k,(expected is None and np.isnan(x)) or expected==x)
            check(i+' correct source building',z['building'][ix]=='DEBY_LOD2_'+ex['building'])
            old=load(DOC/f'figures/영역표본_{i}_{ex["slug"]}.json')
            crop=np.isin(z['patch_id'],old['result_patch_ids'])
            if int(i)<=6:
                target=crop&(z['cell']=={1:0,2:1,3:1,4:2,5:2,6:2}[int(i)])
            else:
                target=crop&np.isin(z['cell'],[4,5])&((z['judgment']==4) if i=='7' else (z['judgment']!=4))
            check(i+' population matches original crop and source cells',set(z['patch_id'][target])==set(f['target']['patch_ids']))
            area=z['area'].astype(float);den=area[target].sum()
            check(i+' denominator area',abs(den-f['target']['area_m2'])<1e-8)
            for key in ['category','check']:
                ok=abs(z['z_'+key].astype(float)-z['gt_p'])<=z['tau']
                check(i+' supplied area rate '+key,abs(100*area[target&ok].sum()/den-f['target']['ok_'+key+'_pct'])<1e-8)
        c=abs(v['z_category']-v['gt_p'])<=v['tau'];k=abs(v['z_check']-v['gt_p'])<=v['tau']
        p=abs(v['gt_p'])<=v['tau'];j=v['judgment'];cell=v['cell']
        cases={'1':cell==0 and c and k,'2':cell==1 and j==1 and not c and k,
          '3':cell==1 and j==1 and k,'4':cell==2 and p and j==0 and c and k,
          '5':cell==2 and p and j==1 and c and not k,'6':cell==2 and p and j==0 and not k,
          '7':cell in [4,5] and j==4 and not np.isfinite(v['mvs_p']) and v['z_category']==v['z_check']==0,
          '8':cell==5 and j==1 and not p and not np.isfinite(v['mvs_p']) and v['z_category']==v['z_check']==0}
        check(i+' same-patch case conjunction',cases[i])
        actual=np.array([-float(v['gt_p']),float(v['z_category'])-float(v['gt_p']),float(v['z_check'])-float(v['gt_p'])])*100
        check(i+' exact focus error chart',np.allclose(actual,r['focus_normal_error_cm'],rtol=0,atol=1e-10))
        check(i+' fixed section retained',r['section']==load(PAY/f'section_{i}.json'))
        check(i+' focus belongs to fixed section',pid in r['section']['band_patch_ids'])
        check(i+' photo source unchanged',sha(DOC/f'figures/crops/{i}_원본.png')==r['photo_source_sha256'])
        check(i+' figure hash',sha(root/f'대표그림_{i}.png')==r['figure_sha256'])
        with Image.open(root/f'대표그림_{i}.png') as im:
            check(i+' image 5400x3600 at 300dpi',im.size==(5400,3600) and all(abs(x-300)<.1 for x in im.info['dpi']))
            check(i+' nonblank image',any(a!=b for a,b in im.getextrema()))
        check(i+' explicit outcome selection',f['exact_focus_selected_after_results'] is True)
        check(i+' no scientific verdict',r['scientific_verdict'] is None)
    trace=load(root/'photo_shortage_trace.json')
    check('7 shortage traced to existing public point',trace['values']['selected_count']<3 and trace['values']['judgment'][0]==4)
    check('not pure preservation',70<load(root/'대표그림_4.json')['focus']['target']['ok_check_pct']<90)
    record=dict(at=now(),status='PASS',checks=checks,passed=len(checks),total=len(checks),
      protected_files=len(design['protected_inputs']),environment=environment(),scientific_verdict=None)
    dump(root/'verification.json',record);print('VERIFIED',len(checks),'checks; protected',len(design['protected_inputs']),flush=True)

if __name__=='__main__':main()
