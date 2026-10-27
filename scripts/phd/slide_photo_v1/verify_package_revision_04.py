"""Verify the presentation revision and package the final replacements only."""
import ast, hashlib, platform, re, zipfile
from common import *
from PIL import Image
import PIL, matplotlib

OUT=DOC/'revision_04'; FIG=OUT/'figures'; QA=OUT/'qa'; PREVIEW=OUT/'previews'
NAME='PHD-SLIDE-PHOTO-v1_handover_R4.zip'

def main():
    config();PREVIEW.mkdir(exist_ok=True);checks=[]
    def check(name,condition,detail=None):
        assert condition,(name,detail);checks.append(dict(name=name,status='PASS',detail=detail))
    locked=load(CFG/'layout_revision_02.json')
    for name,digest in locked['source_metadata_hashes'].items():
        check('original_metadata:'+name,sha(DOC/'figures'/name)==digest)
    check('semantic_config_pin',sha(CFG/'semantic_revision_03.json')=='203613113bdd7566a8e0c76a76e459047b6544aaf147302a13618eda8be18d28')
    check('context_config_pin',sha(CFG/'context_revision_04.json')=='a80ae4fd915ef8cc388535fe16db867a1841b70aba5f1eb4a5e5ec5e356af540')
    a=load(FIG/'figS_a_image_limits.json');original=load(DOC/'figures/figS_a_image_limits.json')
    check('A_sites_views_patches_counts_ratios',all(x['source']==y for x,y in zip(a['panels'],original['panels'])))
    check('A_sparse_roof_support_retained',original['panels'][0]['pixels']==20 and original['panels'][0]['missing_painted_pixels']==4)
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
    m=load(FIG/'figS_e_aim_keep.json');old_keep=load(DOC/'figures/figS_c_specular.json');sel=load(DOC/'figures/task0_specular_candidates.json')['selected']
    check('E_keep_frozen_residual_medians',m['comparison']['absolute_residual_median_cm']==[old_keep['reference_prior_abs_median_m']*100,old_keep['reference_mvs_abs_median_m']*100])
    check('E_keep_frozen_tau',m['comparison']['tau_cm']==sel['tau_m']*100)
    for name in ['figS_d_gs_real','figS_b_correction_sections','figS_b_all_methods']:
        check('retained_R3:'+name,sha(FIG/f'{name}.png')==sha(DOC/'revision_03/figures'/f'{name}.png'))
    original=load(DOC/'figures/figS_b_correction_sections.json')
    for name in ['figS_b_correction_sections','figS_b_all_methods']:
        m=load(FIG/f'{name}.json');check('B_all_segments_bounds_metrics:'+name,m['source']==original)
    sizes={'figS_a_image_limits':((2700,1200),(900,400),74),'figS_d_gs_real':((3200,800),(1600,400),52),
           'figS_b_correction_sections':((3200,1077),(1664,560),35*100/72),'figS_b_all_methods':((3200,1077),(1664,560),35*100/72),
           'figS_e_purpose_overview':((4320,1620),(1600,600),50*100/72)}
    for k in ['keep','correct','refine','inherit']:sizes['figS_e_aim_'+k]=((1080,1620),(400,600),50*100/72)
    figures=[]
    for name,(expected,slide,font) in sizes.items():
        p=FIG/f'{name}.png';im=Image.open(p);check('dimensions:'+name,im.size==expected,list(im.size))
        effective=font*slide[0]/expected[0];check('font_over_24:'+name,effective>24,effective)
        im.resize(slide,Image.Resampling.LANCZOS).save(PREVIEW/f'{name}.png')
        figures.append(dict(name=name,pixels=expected,slide_pixels=slide,min_slide_font_px=effective,sha256=sha(p)))
    reviews=load(QA/'blind_reviews.json');check('all_new_figures_blind_read',set(sizes)=={x['figure'] for x in reviews['final_reviews']})
    for n in ['layout_revision_02.py','semantic_revision_03.py','context_revision_04.py','verify_package_revision_04.py']:
        ast.parse((REPO/'scripts/phd/slide_photo_v1'/n).read_text());check('python_syntax:'+n,True)
    zip_old=PAY/'PHD-SLIDE-PHOTO-v1_handover.zip'
    check('previous_handover_preserved',sha(zip_old)=='c575bffa53885e00762b5cb1e087bdc65735a7c011801af829344a40119d45d3')
    base=sys.argv[1];assert re.fullmatch('[0-9a-f]{40}',base),'Pass the host worktree commit as argument 1.'
    result=dict(task_id='PHD-SLIDE-PHOTO-v1-R4',at=now(),scientific_verdict=None,status='PASS_TECHNICAL',
        presentation_intent='Independent readings recorded; these are intent checks, not user acceptance or scientific validation',
        source_commit_at_verification=base,checks=checks,figures=figures,
        versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__),
        docker_image=(PAY/'image_id.txt').read_text().strip(),
        config_sha256={n:sha(CFG/n) for n in ['slide_photo_v1.json','layout_revision_02.json','semantic_revision_03.json','context_revision_04.json']},
        script_sha256={n:sha(REPO/'scripts/phd/slide_photo_v1'/n) for n in ['layout_revision_02.py','semantic_revision_03.py','context_revision_04.py','verify_package_revision_04.py']},
        derived_inputs={str(p):sha(p) for p in [PAY/'task0/selected_clouds.npz',PAY/'revision_02/b_raw_reference_bands.npz']},
        execution='Docker CPU only; no training or GPU',crs='EPSG:25832; local shifted model coordinates retain frozen source registration',
        scientific_limitations='See 보고_R4.md; no independent truth, material causality, current hidden-wall or universal method superiority claim')
    dump(OUT/'verification.json',result)
    # Flat presentation directory, with source records and reproduction code separate.
    members={}
    def add(path,name):
        assert name not in members,name;members[name]=path
    for p in sorted(FIG.glob('*')):add(p,'figures/'+p.name)
    for suffix in ['change','repr','specular']:
        for ext in ['png','json']:
            p=DOC/'figures'/f'figS_c_{suffix}.{ext}';add(p,'figures/'+p.name)
    for p in [OUT/'보고_R4.md',OUT/'verification.json',OUT/'issues.md',QA/'blind_reviews.json']:add(p,p.relative_to(OUT).as_posix())
    for p in sorted(PREVIEW.glob('*.png')):add(p,'previews/'+p.name)
    for p in sorted((REPO/'scripts/phd/slide_photo_v1').glob('*')):
        if p.is_file():add(p,'scripts/phd/slide_photo_v1/'+p.name)
    for p in sorted(CFG.glob('*')):
        if p.is_file():add(p,'configs/phd/slide_photo_v1/'+p.name)
    for p in sorted((DOC/'figures').glob('*.json')):add(p,'source_metadata/'+p.name)
    for k in ['keep','correct','refine','inherit']:
        p=DOC/'revision_02/figures'/f'figS_e_aim_{k}.png';add(p,'source_locator_photos/'+p.name)
    for p in sorted((DOC/'revision_02/figures').glob('*.json')):add(p,'source_metadata/revision_02/'+p.name)
    for p in sorted((DOC/'revision_03/figures').glob('*.json')):add(p,'source_metadata/revision_03/'+p.name)
    add(DOC/'revision_03/qa/blind_reviews.json','source_metadata/revision_03/blind_reviews.json')
    add(DOC/'보고_v1.md','source_metadata/보고_v1.md')
    for rel in ['scripts/phd/main_regionfig_v1/common.py','scripts/phd/main_photofig_v1/pf_geo.py',
                'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json','configs/phd/main_regionfig_v1/regionfig_v1.json']:
        add(REPO/rel,'source_dependencies/'+rel)
    manifest={n:sha(p) for n,p in members.items()};target=PAY/NAME
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in members.items():z.write(path,name)
        z.writestr('MANIFEST_SHA256.json',__import__('json').dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    receipt=dict(task_id='PHD-SLIDE-PHOTO-v1-R4',at=now(),scientific_verdict=None,archive=str(target),sha256=sha(target),bytes=target.stat().st_size,
                 members=len(members)+1,figure_pngs=sum(n.startswith('figures/') and n.endswith('.png') for n in members),crc='PASS',member_sha256='PASS',
                 verified_members=manifest,previous_archive_untouched=True,source_commit=base)
    dump(OUT/'package_receipt.json',receipt);dump(PAY/'revision_04/package_receipt.json',receipt)
    print('VERIFIED',len(checks),'checks;',len(figures),'new PNGs; PACKAGE',receipt['bytes'],receipt['sha256'],flush=True)

if __name__=='__main__':main()
