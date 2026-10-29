"""Independent boundary/identity checks and requested delivered-value checks."""
import argparse,ast,tempfile
import open3d as o3d
from interview_common import *

def preflight():
    from interview_counts import curve_bins
    from interview_gaussians import column_counts,saved_visibility
    from interview_meshio import crop
    from interview_figures import photo,measure_points,points_image
    config();checks=[]
    for p in Path(__file__).parent.glob('interview_*.py'):ast.parse(p.read_text())
    x=np.array([0,.499999,.5,7.5,8,8.000001,np.nan,np.inf])
    assert np.array_equal(curve_bins(x),[0,0,1,15,15,16,-1,-1]);checks.append('curve closed upper endpoint 8 and missing bins')
    xyz=np.array([[0,0,0],[.12,.12,.19],[.126,0,0],[0,0,.201]])
    count,prior,median,opaque=column_counts(xyz,np.array([.1,.8,.9,.9]),np.array([0,1,1,1]),np.zeros((1,3)),
        np.array([[0,0,1]]),np.array([[1,0,0]]),np.array([[0,1,0]]),np.array([.2]))
    assert count.tolist()==[2] and prior.tolist()==[1] and np.allclose(median,[.45]) and opaque.tolist()==[True]
    checks.append('normal patch column excludes transverse and axial outsiders; opacity threshold tests individual centres')
    with tempfile.TemporaryDirectory() as td:
        vertices=[];faces=[]
        for x,z in [(0,.3),(2,-.3)]:
            off=len(vertices);vertices.extend([[x-.4,-.4,z],[x+.4,-.4,z],[x+.4,.4,z],[x-.4,.4,z]])
            faces.extend([[off,off+1,off+2],[off,off+2,off+3]])
        testmesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces))
        p=Path(td)/'plane.ply';assert o3d.io.write_triangle_mesh(str(p),testmesh)
        centres=np.array([[0.,0,0],[2,0,0],[4,0,0]])
        e=dict(centre=centres,normal=np.tile([0.,0,1],(3,1)),p_gt=np.zeros(3),p_mvs=np.zeros(3),in_eval=np.ones(3,bool),scoring_allowed=np.ones(3,bool))
        delta,ids=measure_points(p,centres,e)
        assert np.allclose(delta[:2],[.3,-.3],atol=1e-6) and np.isnan(delta[2])
        cam=dict(width=100,height=100,eye=[0,0,10],direction=[0,0,1],right=[1,0,0],up=[0,1,0],fov_x_deg=45)
        for value in [.3,-.3,np.nan]:
            pixel=points_image(np.zeros((1,3)),np.array([value]),cam)[50,50]
            assert (pixel[0]>pixel[2]) if value>0 else (pixel[2]>pixel[0]) if value<0 else np.array_equal(pixel,[160,160,160])
    checks.append('exact first hit gives positive outside, negative inside, missing NaN; red / blue / grey rendering verified')
    for site in SITES:
        for prior_name in PRIORS:
            e,v,base=evaluation(site,prior_name)
            with np.load(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior_name}.npz') as r:
                assert np.array_equal(e['centre'],r['centre']) and np.array_equal(e['area'],r['area'])
            if prior_name=='LoD2':
                with np.load(S0/'s61/box'/site/prior_name/'units.npz') as u:
                    assert np.array_equal(e['centre'],u['loc_center'])
                ids=np.flatnonzero(eligible(e)&np.isin(e['cell'],[2,4]))[:10]
                views,angles,rec=saved_visibility(site,prior_name,e,ids)
                assert rec['status']=='PASS'
                im,info=photo(dict(site=site,prior=prior_name,patch_indices=ids.tolist()),e)
                assert im is not None and info['stored_visible_patch_area_fraction']>0
            for prefix in ['nojudge','lt_dynnow']:
                z,p=patch_values(site,prior_name,f'{prefix}_{prior_name}_s0',e)
                assert len(z['z'])==len(e['area'])
            checks.append(f'{site} {prior_name}: exact evaluation / region / patch-value identity')
    p=O/'case_meshes/B173-날개/nojudge_ALS_s0/before.ply'
    mesh=o3d.io.read_triangle_mesh(str(p));V=np.asarray(mesh.vertices)
    lo=V.min(0)+(V.max(0)-V.min(0))*.1;hi=V.max(0)-(V.max(0)-V.min(0))*.1
    expected=mesh.crop(o3d.geometry.AxisAlignedBoundingBox(lo,hi));actual=crop(p,lo,hi)
    assert np.array_equal(np.asarray(expected.vertices),np.asarray(actual.vertices))
    assert np.array_equal(np.asarray(expected.triangles),np.asarray(actual.triangles))
    checks.append('streamed exact PLY crop equals Open3D crop on existing B173 wing source crop')
    result=dict(status='PASS',checks=checks,created_at=now(),scientific_verdict=None)
    dump(IDOC/'checks/preflight.json',result);print(json.dumps(result,ensure_ascii=False))

def validate():
    checks=[];pending=[]
    jobs=json.loads((IDOC/'jobs.json').read_text())['jobs']
    for job in jobs:
        path=IDOC/'status'/(job['tag']+'.json')
        if not path.exists() or json.loads(path.read_text())['status'] not in ['PASS','PARTIAL']:
            pending.append(job['tag']);continue
        if job['tag'].startswith('fig-'):
            r=json.loads(path.read_text());table=json.loads((IDOC/'tables'/('figure_'+job['tag'][4:]+'.json')).read_text())['rows']
            assert r['rows']==table
            for row in table:
                e,_,_=evaluation(row['site'],row['prior']);z,_=patch_values(row['site'],row['prior'],row['result'],e)
                case=next(c for c in json.loads((IDOC/'cases.json').read_text())['cases'] if c['slug']==row['slug'])
                ids=np.asarray(case['patch_indices']);within=np.isfinite(z['z'][ids])&~z['no_surface'][ids]&(np.abs(z['z'][ids]-e['p_gt'][ids])<=e['tau'][ids])
                floating=np.isfinite(z['z'][ids])&~z['no_surface'][ids]&~within&(z['side'][ids]==2)&(z['z'][ids]>e['p_gt'][ids]+e['tau'][ids])
                area=e['area'][ids]
                for key,mask in [('within_tau_pct',within),('floating_pct',floating)]:assert np.isclose(row[key],100*area[mask].sum()/area.sum())
            checks.append(dict(job=job['tag'],check='figure displayed values equal packaged table and independent first-hit classification',status='PASS'))
    for name in ['comparison','counts','virtual_baseline']:
        p=IDOC/'checks'/(name+'.json')
        if p.exists():
            r=json.loads(p.read_text());assert r['status']=='PASS';checks.append(dict(check=name,status='PASS'))
        else:pending.append(name)
    if (IDOC/'tables/axis_curves.json').exists():
        rows=json.loads((IDOC/'tables/axis_curves.json').read_text())['rows']
        four=json.loads((IDOC/'tables/lod2_four_way.json').read_text())['rows']
        for site in SITES:
            for prior in PRIORS:
                e,_,_=evaluation(site,prior)
                for prefix in ['nojudge','lt_dynnow']:
                    for axis,cell in [('correction',1),('preservation',2)]:
                        rr=[r for r in rows if (r['site'],r['prior'],r['result'],r['axis'])==(site,prior,f'{prefix}_{prior}_s0',axis)]
                        mask=eligible(e)&(e['cell']==cell)
                        assert len(rr)==18 and sum(r['patches'] for r in rr)==int(mask.sum())
                        assert np.isclose(sum(r['area_m2'] for r in rr),e['area'][mask].sum(),rtol=1e-12,atol=1e-8)
                        for r in rr:
                            assert sum(r[k+'_patches'] for k in CATEGORIES)==r['patches']
        for site in SITES:
            for cell in ['0~3','0','1','2','3','보정','보존']:
                rr=[r for r in four if r['site']==site and r['cell']==cell]
                assert len(rr)==4
                if rr[0]['denominator_m2']:
                    assert np.isclose(sum(r['pct'] for r in rr),100,atol=1e-9)
                    assert np.isclose(sum(r['area_m2'] for r in rr),rr[0]['denominator_m2'])
        checks.append(dict(check='independent curve areas/counts reconcile to raw evaluation and four diagnostic fractions sum to 100',status='PASS'))
    dump(IDOC/'checks/delivery_validation.json',dict(status='PARTIAL' if pending else 'PASS',checks=checks,pending=pending,scientific_verdict=None))
    record('validation',status='PARTIAL' if pending else 'PASS',checks=len(checks),pending=pending)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--preflight',action='store_true');a=ap.parse_args()
    preflight() if a.preflight else validate()
