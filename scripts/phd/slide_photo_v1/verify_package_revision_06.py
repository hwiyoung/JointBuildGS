"""Verify the presentation revision and package the final replacements only."""
import ast, hashlib, platform, re, zipfile
from common import *
from PIL import Image
import PIL, matplotlib

OUT=DOC/'revision_06'; FIG=OUT/'figures'; QA=OUT/'qa'; PREVIEW=OUT/'previews'
NAME='PHD-SLIDE-PHOTO-v1_handover_R6.zip'

def main():
    config();PREVIEW.mkdir(exist_ok=True);checks=[]
    def check(name,condition,detail=None):
        assert condition,(name,detail);checks.append(dict(name=name,status='PASS',detail=detail))
    locked=load(CFG/'layout_revision_02.json')
    for name,digest in locked['source_metadata_hashes'].items():
        check('original_metadata:'+name,sha(DOC/'figures'/name)==digest)
    check('semantic_config_pin',sha(CFG/'semantic_revision_03.json')=='203613113bdd7566a8e0c76a76e459047b6544aaf147302a13618eda8be18d28')
    check('context_config_pin',sha(CFG/'context_revision_04.json')=='a80ae4fd915ef8cc388535fe16db867a1841b70aba5f1eb4a5e5ec5e356af540')
    check('R6_selection_pin',sha(CFG/'representative_audit_06.json')=='8b2aa5921f855f5e3b35bfb991b0a6398c820bda81936539c22ec5f23aba722f')
    check('R6_display_pin',sha(CFG/'presentation_revision_06.json')=='fae3b7adebea6301b6ed5e029d0fc16b3977bab6af8e287792199188c93762fa')
    a=load(FIG/'figS_a_image_limits.json');original=load(DOC/'figures/figS_a_image_limits.json')
    check('A_other_two_sources_unchanged',all(x['source']==y for x,y in zip(a['panels'][1:],original['panels'][1:])))
    check('A_old_roof_withdrawn',original['panels'][0]['pixels']==20 and a['roof_selection_replaced'] and a['panels'][0]['source']['pixels']!=20)
    audit=load(OUT/'roof_representativeness_audit.json');roof=load(OUT/'roof_photo_evidence.json');c=load(CFG/'representative_audit_06.json')
    check('A_audit_config_matches',audit['config']==c and audit['config_sha256']==sha(CFG/'representative_audit_06.json'))
    good=sorted([r for r in audit['rows'] if r['eligible']],key=lambda r:(-r['missing_pixels'],-r['pixels'],r['site'],r['face'],r['view']))
    check('A_input_only_ranking',audit['selected']==good[0] and not c['selection_uses_gt'] and not c['selection_uses_training_results'])
    check('A_audit_scope',len(audit['rows'])==334 and len(good)==4)
    check('A_new_roof_source',a['panels'][0]['source']==roof and (roof['site'],roof['face'],roof['photo']['view'])==(good[0]['site'],good[0]['face'],good[0]['view']))
    for name,actual,minimum in [('projected_pixels',roof['pixels'],c['minimum_projected_pixels']),('missing_share',roof['missing_share'],c['minimum_missing_share']),('visible_unique_patch_fraction',good[0]['visible_unique_patch_fraction'],c['minimum_visible_unique_patch_fraction']),('connected_missing_pixels',good[0]['largest_missing_component_pixels'],c['minimum_connected_missing_pixels'])]:
        check('A_support:'+name,actual>=minimum,dict(actual=actual,minimum=minimum))
    dp=Path(roof['source_depth']);cp=Path(roof['confidence']);lp=dp.parent.parent/'locmap'/dp.name;lm=np.load(lp);roi=np.isin(lm,roof['patch_indices']);D=np.load(dp);cf=np.load(cp);valid=np.isfinite(D)&(D>0)&(cf>0)
    vis=load(PAY/'task0/global_visibility/complete.json');Z=np.load(PAY/'task0/global_visibility/zbuffer.npy',mmap_mode='r')[vis['names'].index(roof['photo']['view'])].reshape(lm.shape);known=np.isfinite(Z);missing=roi&~valid;wrong=roi&valid&known&(abs(D-Z)>roof['tau_m'])
    check('A_global_visibility_24_tiles',len(vis['tiles'])==24 and 'all 24' in roof['visibility'])
    check('A_R1_roof_threshold',roof['tau_m']==.6828)
    check('A_pixel_replay',int(roi.sum())==roof['pixels']==68197 and int(missing.sum())==39904 and int((missing&known).sum())==roof['missing_painted_pixels']==39893)
    check('A_unknown_and_wrong_replay',float((roi&~known).sum()/roi.sum())==roof['unknown_gt_share'] and float(wrong.sum()/roi.sum())==roof['wrong_share'])
    check('A_native_projection_fraction_disclosed',.7<roof['photo']['projected_fraction']<.8 and not a['panels'][0]['whole_roof_visible'])
    check('A_no_texture_cause_title','무늬' not in a['roof_scope'])
    from photos import models
    import layout_revision_02 as L
    # Reopen the exact original JPEG and validate its recorded digest.
    L.native(roof['photo']);check('A_original_JPEG_sha256',True)
    input_hashes={str(p):sha(p) for p in [dp,cp,lp,U/'patch_values'/f'{roof["site"]}__LoD2__R1.5.npz',PAY/'task0/global_visibility/complete.json']}
    d=load(FIG/'figS_d_gs_real.json');original=load(DOC/'figures/figS_d_gs_real.json')
    check('D_frozen_source',d['source']==original)
    check('D_gaussians_175',len(d['gaussian_photo_pair']['gaussian_ids'])==original['gaussian_display']['shown']==175)
    check('D_shared_depth_colour',d['shared_depth_colour_range_m']==original['depth_colour_range_m'])
    x0,y0,x1,y1=d['shared_additional_crop_after_rotation_px'];aspect=(x1-x0)/(y1-y0)
    check('D_no_anisotropic_resize',all(abs(r['rect_px'][2]/r['rect_px'][3]/aspect-1)<.003 for r in d['panels']))
    for key in ['keep','correct','refine','inherit']:
        name='figS_e_aim_'+key;m=load(FIG/f'{name}.json')
        check('E_frozen_source:'+key,m['photo']['source']==load(DOC/'figures'/f'{name}.json'))
        check('E_photos_no_fill:'+key,m['photo']['photo_fill']=='none')
    ref=load(DOC/'figures/figS_c_repr.json');m=load(FIG/'figS_e_aim_refine.json')
    check('E_refine_exact_section',m['comparison']['section']==ref['section'])
    corr=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'][0];m=load(FIG/'figS_e_aim_correct.json')
    check('E_correct_exact_section',m['comparison']['height_values']==corr['heights_model_m'] and m['comparison']['section_bins']==corr['bin_centres_m'])
    pm=m['photo'];check('E_correct_no_patch_hull',pm['old_patch_hull_drawn'] is False)
    check('E_correct_exact_locator',pm['section_line_xyz']==corr['photo']['line_xyz'] and len(pm['section_line_xyz'])==240)
    p=pm['source']['photo'];pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));uv,_=G.project(np.asarray(pm['section_line_xyz']),pose,p['camera']);uv=np.c_[uv[:,1],p['camera']['w']-uv[:,0]];crop=pm['crop_in_rotated_native_px'];uv=(uv-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])]
    check('E_correct_locator_projection_replay',np.allclose(uv,pm['section_line_display_px'],rtol=0,atol=1e-10))
    check('E_correct_locator_visibility',pm['section_hidden_segments']==(np.asarray(corr['photo']['line_midpoint_occluded'])|~np.asarray(corr['photo']['line_midpoint_known'])).tolist())
    for key in ['keep','correct','refine','inherit']:
        name='figS_e_aim_'+key;m=load(FIG/f'{name}.json');r4=load(DOC/'revision_04/figures'/f'{name}.json');check('E_comparison_values_unchanged:'+key,m['comparison']==r4['comparison'])
        path=PAY/'revision_04/keep_comparison.png' if key=='keep' else PAY/'revision_03'/f'e_{key}_comparison.png'
        check('E_comparison_raster_unchanged:'+key,m['comparison_raster_sha256']==sha(path) and Image.open(FIG/f'{name}.png').crop((0,890,1080,1410)).tobytes()==Image.open(path).convert('RGB').tobytes())
    m=load(FIG/'figS_e_aim_keep.json');old_keep=load(DOC/'figures/figS_c_specular.json');sel=load(DOC/'figures/task0_specular_candidates.json')['selected']
    check('E_keep_frozen_residual_medians',m['comparison']['absolute_residual_median_cm']==[old_keep['reference_prior_abs_median_m']*100,old_keep['reference_mvs_abs_median_m']*100])
    check('E_keep_frozen_tau',m['comparison']['tau_cm']==sel['tau_m']*100)
    metal=a['panels'][2]['source'];kp=m['photo']['source']['photo'];check('A_E_same_metal_original_photo',metal['photo']['view']==kp['view'] and metal['photo']['original_sha256']==kp['original_sha256'])
    check('A_E_missing_distinct_from_error',metal['missing_share']<.04 and metal['wrong_share']>.79 and m['explanation'][0]=='깊이값이 있어도 틀리면')
    for name in ['figS_d_gs_real','figS_b_correction_sections','figS_b_all_methods']:
        check('retained_R3:'+name,sha(FIG/f'{name}.png')==sha(DOC/'revision_03/figures'/f'{name}.png'))
    original=load(DOC/'figures/figS_b_correction_sections.json')
    for name in ['figS_b_correction_sections','figS_b_all_methods']:
        m=load(FIG/f'{name}.json');check('B_all_segments_bounds_metrics:'+name,m['source']==original)
    sizes={'figS_a_image_limits':((2700,1200),(900,400),74),'figS_d_gs_real':((3200,800),(1600,400),52),
           'figS_b_correction_sections':((3200,1077),(1664,560),35*100/72),'figS_b_all_methods':((3200,1077),(1664,560),35*100/72),
           'figS_e_purpose_overview':((4320,1620),(1600,600),68)}
    for k in ['keep','correct','refine','inherit']:sizes['figS_e_aim_'+k]=((1080,1620),(400,600),68)
    figures=[]
    for name,(expected,slide,font) in sizes.items():
        p=FIG/f'{name}.png';im=Image.open(p);check('dimensions:'+name,im.size==expected,list(im.size))
        effective=font*slide[0]/expected[0];check('font_over_24:'+name,effective>24,effective)
        im.resize(slide,Image.Resampling.LANCZOS).save(PREVIEW/f'{name}.png')
        figures.append(dict(name=name,pixels=expected,slide_pixels=slide,min_slide_font_px=effective,sha256=sha(p)))
    reviews=load(QA/'blind_reviews.json');check('all_new_figures_blind_read',set(sizes)=={x['figure'] for x in reviews['final_reviews']})
    for n in ['representative_audit_06.py','presentation_revision_06.py','verify_package_revision_06.py']:
        ast.parse((REPO/'scripts/phd/slide_photo_v1'/n).read_text());check('python_syntax:'+n,True)
    zip_old=PAY/'PHD-SLIDE-PHOTO-v1_handover.zip'
    check('previous_handover_preserved',sha(zip_old)=='c575bffa53885e00762b5cb1e087bdc65735a7c011801af829344a40119d45d3')
    check('R4_handover_preserved',sha(PAY/'PHD-SLIDE-PHOTO-v1_handover_R4.zip')=='15cee3446b82b5e442a29ee3dd7d4d924ffc9f17b5faec5511db91d834ff4389')
    base=sys.argv[1];assert re.fullmatch('[0-9a-f]{40}',base),'Pass the host worktree commit as argument 1.'
    result=dict(task_id='PHD-SLIDE-PHOTO-v1-R6',at=now(),scientific_verdict=None,status='PASS_TECHNICAL',
        presentation_intent='Independent readings recorded; these are intent checks, not user acceptance or scientific validation',
        source_commit_at_verification=base,checks=checks,figures=figures,
        versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__),
        docker_image=(PAY/'image_id.txt').read_text().strip(),
        config_sha256={n:sha(CFG/n) for n in ['slide_photo_v1.json','layout_revision_02.json','semantic_revision_03.json','context_revision_04.json','representative_audit_06.json','presentation_revision_06.json']},
        script_sha256={n:sha(REPO/'scripts/phd/slide_photo_v1'/n) for n in ['representative_audit_06.py','presentation_revision_06.py','verify_package_revision_06.py']},
        derived_inputs=input_hashes|{str(p):sha(p) for p in [PAY/'task0/selected_clouds.npz',PAY/'revision_02/b_raw_reference_bands.npz']},
        missing_depth_breakdown=dict(raw_depth_absent=int((roi&(~np.isfinite(D)|(D<=0))).sum()),confidence_only_filtered=int((roi&np.isfinite(D)&(D>0)&~(cf>0)).sum())),
        execution='Docker CPU only; no training or GPU',crs='EPSG:25832; local shifted model coordinates retain frozen source registration',
        scientific_limitations='See 보고_R6.md; no texture/material causality, whole-roof rate, independent truth, current hidden-wall or universal method superiority claim')
    dump(OUT/'verification.json',result)
    # Flat presentation directory, with source records and reproduction code separate.
    members={}
    def add(path,name):
        assert name not in members,name;members[name]=path
    for p in sorted(FIG.glob('*')):add(p,'figures/'+p.name)
    for suffix in ['change','repr','specular']:
        for ext in ['png','json']:
            p=DOC/'figures'/f'figS_c_{suffix}.{ext}';add(p,'figures/'+p.name)
    for p in [OUT/'보고_R6.md',OUT/'verification.json',OUT/'issues.md',OUT/'roof_representativeness_audit.json',OUT/'roof_photo_evidence.json',QA/'blind_reviews.json']:add(p,p.relative_to(OUT).as_posix())
    for p in sorted(PREVIEW.glob('*.png')):add(p,'previews/'+p.name)
    for p in sorted((REPO/'scripts/phd/slide_photo_v1').glob('*')):
        if p.is_file() and p.name!='polish_revision_05.py':add(p,'scripts/phd/slide_photo_v1/'+p.name)
    for p in sorted(CFG.glob('*')):
        if p.is_file() and p.name!='polish_revision_05.json':add(p,'configs/phd/slide_photo_v1/'+p.name)
    for p in sorted((DOC/'figures').glob('*.json')):add(p,'source_metadata/'+p.name)
    for k in ['keep','correct','refine','inherit']:
        p=DOC/'revision_02/figures'/f'figS_e_aim_{k}.png';add(p,'source_locator_photos/'+p.name)
    for p in sorted((DOC/'revision_02/figures').glob('*.json')):add(p,'source_metadata/revision_02/'+p.name)
    for p in sorted((DOC/'revision_03/figures').glob('*.json')):add(p,'source_metadata/revision_03/'+p.name)
    for p in sorted((DOC/'revision_04/figures').glob('*.json')):add(p,'source_metadata/revision_04/'+p.name)
    add(DOC/'revision_03/qa/blind_reviews.json','source_metadata/revision_03/blind_reviews.json')
    add(DOC/'보고_v1.md','source_metadata/보고_v1.md')
    for rel in ['scripts/phd/main_regionfig_v1/common.py','scripts/phd/main_photofig_v1/pf_geo.py',
                'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json','configs/phd/main_regionfig_v1/regionfig_v1.json','configs/phd/main_uncert_v1/uncert_v1.json']:
        add(REPO/rel,'source_dependencies/'+rel)
    manifest={n:sha(p) for n,p in members.items()};target=PAY/NAME
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in members.items():z.write(path,name)
        z.writestr('MANIFEST_SHA256.json',__import__('json').dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    receipt=dict(task_id='PHD-SLIDE-PHOTO-v1-R6',at=now(),scientific_verdict=None,archive=str(target),sha256=sha(target),bytes=target.stat().st_size,
                 members=len(members)+1,figure_pngs=sum(n.startswith('figures/') and n.endswith('.png') for n in members),crc='PASS',member_sha256='PASS',
                 verified_members=manifest,previous_archive_untouched=True,source_commit=base)
    dump(OUT/'package_receipt.json',receipt);dump(PAY/'revision_06/package_receipt.json',receipt)
    print('VERIFIED',len(checks),'checks;',len(figures),'new PNGs; PACKAGE',receipt['bytes'],receipt['sha256'],flush=True)

if __name__=='__main__':main()
