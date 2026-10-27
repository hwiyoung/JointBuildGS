"""Replay the new section from coordinates and overlay two files in the R6 handover."""
import ast,hashlib,json,platform,re,zipfile
from PIL import Image
import PIL,matplotlib
from common import *

OUT=DOC/'revision_07';FIG=OUT/'figures';CACHE=PAY/'revision_07'

def main():
    config();checks=[]
    def check(n,ok,detail=None):
        assert ok,(n,detail);checks.append(dict(name=n,status='PASS',detail=detail))
    c=load(CFG/'keep_shape_revision_07.json');r=load(OUT/'keep_section.json');m=load(FIG/'figS_e_aim_keep.json')
    check('config_pin',sha(CFG/'keep_shape_revision_07.json')=='d617f7f3610fd61207e0a1db17b25ae56e5cd500c5c8d8a92c4173615908584e')
    check('config_record',r['config']==c and r['config_sha256']==sha(CFG/'keep_shape_revision_07.json'))
    check('cloud_pin',sha(PAY/c['source_cloud'])==c['source_cloud_sha256'])
    check('view_pin',sha(DOC/c['source_view_metadata'])==c['source_view_metadata_sha256'])
    v=load(DOC/c['source_view_metadata']);check('centre_and_tangent_unchanged',r['source_view']['centre']==v['view']['centre'] and r['source_view']['axis1']==v['view']['axis1'] and r['previous_tilted_view']==v['view'])
    sp=DOC/'figures/task0_specular_candidates.json';component=load(sp)['selected'];check('normal_and_tau_source_pin',sha(sp)==r['normal_and_tau_source_sha256']=='fec01fe7a0bc438104e8a4d3c95f83b301dcb8b51c3e0c31ec109e55a7ffded9')
    mid=np.asarray(v['view']['centre']);e1=np.asarray(v['view']['axis1']);e2=np.asarray(r['source_view']['axis2']);cross=np.cross(e1,e2);edges=np.asarray(r['edges_m']);h=r['section_half_width_m'];source=np.load(PAY/c['source_cloud'])
    check('exact_component_normal',np.allclose(component['normal'],e2,rtol=0,atol=1e-12) and abs(e1@e2)<1e-12)
    check('exact_tau',r['tau_m']==component['tau_m']==r['display']['reference_band_m']==.2)
    residual=(source['prior']-source['gt'])@e2;pa=r['local_paired_prior_audit'];check('paired_prior_audit',len(residual)==pa['points']==241 and float(residual.min())==pa['signed_min_m'] and float(residual.max())==pa['signed_max_m'] and float(np.median(abs(residual)))==pa['absolute_median_m'] and float(np.mean(abs(residual)<=.2))==pa['within_tau_share'])
    check('fixed_length_bins',np.array_equal(edges,np.arange(-3,3.01,.5)))
    for row in r['width_support_audit']:
        width=row['half_width_m'];complete=True
        for key in ['gt','prior','mvs']:
            q=source[key]-mid;x=q@e1;t=q@cross;sel=(abs(t)<=width)&(x>=-3)&(x<=3);b=np.minimum(np.floor((x[sel]+3)/.5).astype(int),11);n=np.bincount(b,minlength=12)
            check(f'width_counts:{width}:{key}',np.array_equal(n,row['counts'][key]));complete&=bool(np.all(n>=1))
        check(f'width_support:{width}',complete==row['all_bins_supported'])
    check('smallest_supported_width',h==r['width_support_audit'][-1]['half_width_m'] and all(not row['all_bins_supported'] for row in r['width_support_audit'][:-1]) and r['width_support_audit'][-1]['all_bins_supported'])
    for key in ['gt','prior','mvs']:
        q=source[key]-mid;uv=np.c_[q@e1,q@e2];t=q@cross;ids=np.flatnonzero((abs(t)<=h)&(uv[:,0]>=-3)&(uv[:,0]<=3));s=r['series'][key]
        check('exact_points:'+key,np.array_equal(ids,s['point_indices']) and np.allclose(uv[ids],s['projected_points'],rtol=0,atol=1e-12))
        bins=np.minimum(np.floor((uv[ids,0]+3)/.5).astype(int),11);med=[];mn=[];mx=[];ns=[]
        for b in range(12):
            values=uv[ids[bins==b],1];ns.append(len(values));med.append(float(np.median(values)) if len(values) else np.nan);mn.append(float(values.min()) if len(values) else np.nan);mx.append(float(values.max()) if len(values) else np.nan)
        check('median_replay:'+key,np.allclose(med,s['median'],rtol=0,atol=1e-12,equal_nan=True) and ns==s['counts'])
        check('full_range_record:'+key,np.allclose(mn,s['minimum'],equal_nan=True) and np.allclose(mx,s['maximum'],equal_nan=True))
        check('no_displayed_median_clipping:'+key,min(med)>=r['display']['y_limits_m'][0] and max(med)<=r['display']['y_limits_m'][1])
    gt=np.asarray(r['series']['gt']['median']);check('whole_reference_band_visible',min(gt-.2)>=r['display']['y_limits_m'][0] and max(gt+.2)<=r['display']['y_limits_m'][1])
    check('explanation_within_tolerance',m['explanation']==['허용 범위의 사전 정보는','영상이 틀려도 지킨다'])
    check('comparison_metadata',m['comparison']==r)
    old=load(DOC/'revision_06/figures/figS_e_aim_keep.json');check('same_photo_and_crop',m['photo']['source']==old['photo']['source'] and m['photo']['crop_in_rotated_native_px']==old['photo']['crop_in_rotated_native_px'])
    X=mid+np.linspace(-3,3,61)[:,None]*e1;check('photo_section_xyz',np.allclose(X,m['photo']['section_centre_line_xyz'],rtol=0,atol=1e-12))
    p=m['photo']['source']['photo'];pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));uv,_=G.project(X,pose,p['camera']);uv=np.c_[uv[:,1],p['camera']['w']-uv[:,0]];box=m['photo']['crop_in_rotated_native_px'];uv=(uv-box[:2])*[1080/(box[2]-box[0]),600/(box[3]-box[1])]
    check('photo_projection_replay',np.allclose(uv,m['photo']['section_line_display_px'],rtol=0,atol=1e-10))
    check('photographic_marker_is_section',m['photo']['old_patch_hull_drawn'] is False and m['photo']['section_half_width_m']==h)
    card=Image.open(FIG/'figS_e_aim_keep.png');combined=Image.open(FIG/'figS_e_purpose_overview.png');old_combined=Image.open(DOC/'revision_06/figures/figS_e_purpose_overview.png')
    check('other_three_cards_identical',combined.crop((1080,0,4320,1620)).tobytes()==old_combined.crop((1080,0,4320,1620)).tobytes())
    check('keep_card_combined_identical',combined.crop((0,0,1078,1620)).tobytes()==card.crop((0,0,1078,1620)).tobytes())
    check('plot_pixels',card.crop((0,890,1080,1410)).tobytes()==Image.open(CACHE/'keep_shape.png').convert('RGB').tobytes())
    for n,size,preview in [('figS_e_aim_keep',(1080,1620),(400,600)),('figS_e_purpose_overview',(4320,1620),(1600,600))]:
        im=Image.open(FIG/f'{n}.png');check('dimensions:'+n,im.size==size);check('preview:'+n,Image.open(OUT/'previews'/f'{n}.png').size==preview);check('font_over_24:'+n,68*preview[0]/size[0]>24)
    qa=load(OUT/'qa/blind_reviews.json');check('blind_reviews',set(x['figure'] for x in qa['final_reviews'])=={'figS_e_aim_keep','figS_e_purpose_overview'})
    for name in ['keep_shape_revision_07.py','verify_package_revision_07.py']:ast.parse((REPO/'scripts/phd/slide_photo_v1'/name).read_text());check('syntax:'+name,True)
    base=PAY/'PHD-SLIDE-PHOTO-v1_handover_R6.zip';check('R6_preserved',sha(base)=='0eb0613bd134a37c795ef005a5f1890c7c17a0777705caf5fca84389d7fe1151')
    commit=sys.argv[1];assert re.fullmatch('[0-9a-f]{40}',commit)
    result=dict(task_id=c['task_id'],scientific_verdict=None,at=now(),source_commit=commit,status='PASS_TECHNICAL',checks=checks,config_sha256=sha(CFG/'keep_shape_revision_07.json'),source_sha256=c['source_cloud_sha256'],scripts_sha256={n:sha(REPO/'scripts/phd/slide_photo_v1'/n) for n in ['keep_shape_revision_07.py','verify_package_revision_07.py']},versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__),docker_image=(PAY/'image_id.txt').read_text().strip(),crs='EPSG:25832; inherited local shifted coordinates',execution='Docker CPU only; no training or GPU',interpretation='Local binned input shape, not a new preservation success result')
    dump(OUT/'verification.json',result)
    with zipfile.ZipFile(base) as z:members={n:z.read(n) for n in z.namelist() if n!='MANIFEST_SHA256.json'}
    for n in ['보고_R6.md','verification.json','issues.md','qa/blind_reviews.json']:members['history/revision_06/'+n]=members.pop(n)
    for root,prefix in [(FIG,'figures'),(OUT/'previews','previews')]:
        for p in root.glob('*'):members[prefix+'/'+p.name]=p.read_bytes()
    for n in ['보고_R7.md','verification.json','issues.md','keep_section.json','qa/blind_reviews.json']:members[n]=(OUT/n).read_bytes()
    for n in ['keep_shape_revision_07.py','verify_package_revision_07.py']:members['scripts/phd/slide_photo_v1/'+n]=(REPO/'scripts/phd/slide_photo_v1'/n).read_bytes()
    members['configs/phd/slide_photo_v1/keep_shape_revision_07.json']=(CFG/'keep_shape_revision_07.json').read_bytes();members['derived_inputs/selected_clouds.npz']=(PAY/c['source_cloud']).read_bytes();members['components/keep_shape.png']=(CACHE/'keep_shape.png').read_bytes()
    # R6 invariants remain in history; all unmodified figure members must match.
    changed={'figures/'+n+ext for n in ['figS_e_aim_keep','figS_e_purpose_overview'] for ext in ['.png','.json']}
    with zipfile.ZipFile(base) as z:
        for n in z.namelist():
            if n.startswith('figures/') and n not in changed:assert members[n]==z.read(n),n
    manifest={n:hashlib.sha256(b).hexdigest() for n,b in members.items()};target=PAY/'PHD-SLIDE-PHOTO-v1_handover_R7.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,b in members.items():z.writestr(n,b)
        z.writestr('MANIFEST_SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for n,hsh in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==hsh
    receipt=dict(task_id=c['task_id'],scientific_verdict=None,at=now(),archive=str(target),sha256=sha(target),bytes=target.stat().st_size,members=len(members)+1,figure_pngs=sum(n.startswith('figures/') and n.endswith('.png') for n in members),crc='PASS',member_sha256='PASS',verified_members=manifest,source_commit=commit)
    dump(OUT/'package_receipt.json',receipt);dump(CACHE/'package_receipt.json',receipt);print('PASS',len(checks),'checks',receipt['bytes'],receipt['sha256'],flush=True)

if __name__=='__main__':main()
