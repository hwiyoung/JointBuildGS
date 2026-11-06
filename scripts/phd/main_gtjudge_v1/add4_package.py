"""Seal separate requested presentation deliveries, with member-byte verification."""
from add4_common import *

def package(kind):
    names={'cases':'발표사례그림','sites':'발표실험대상','keep':'늘보존'}
    if kind=='cases':
        for c in AC['cases']:
            for tag in ['oblique','wrong_gray','wrong_dist','truth_gray']:
                j=json.loads((AF/f"{c['id']}_{tag}.json").read_text());assert j['camera'].get('angle_definition') in ['camera_centre_to_section_centre_frozen_gravity','synthetic_optical_axis_elevation_frozen_gravity'],'camera revision pending'
        files=sorted(p for p in AF.rglob('*') if p.is_file() and any(p.relative_to(AF).parts[0].startswith(c['id']) for c in AC['cases']) and 'always_keep' not in p.name)
        # Keep compatibility oblique files in the workspace; delivered substitutes are explicitly named MVS.
        aliases={f"{c['id']}_oblique{suffix}" for c in AC['cases'][:3] for suffix in ['.png','.json']}
        if (AF/'c3_B0_b10__ALS_context_MVS_cutaway.png').exists():aliases.update('c3_B0_b10__ALS_context_MVS'+s for s in ['.png','.json'])
        for c in AC['cases'][:3]:assert (AF/f"{c['id']}_context_MVS.png").exists()
        files=[p for p in files if p.name not in aliases]
    elif kind=='sites':files=sorted(p for p in AF.iterdir() if p.is_file() and (p.name.startswith('campus.') or p.name.startswith('site_')))
    else:files=sorted(p for p in AT.rglob('*') if p.is_file())+sorted(p for p in AF.rglob('*always_keep*') if p.is_file())
    assert files
    for p in files:
        if p.suffix=='.png':
            j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);assert list(im.size)==j['size_px'];assert im.info.get('icc_profile');assert not j['text_in_figure'];assert j['scientific_verdict'] is None
    payload=O/'delivery'/f"PHD-MAIN-GTJUDGE-v1_{names[kind]}.zip";payload.parent.mkdir(exist_ok=True)
    rows=[dict(member=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in files]
    effective=dict(AC);color_override=None
    if (C/'addendum5.json').exists():
        color_override=json.loads((C/'addendum5.json').read_text());effective['case_colors']=color_override['case_colors'];effective['paint_order_case_ids']=color_override['paint_order_case_ids']
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p,row in zip(files,rows):z.write(p,row['member'])
        z.writestr('manifest.json',json.dumps(dict(files=rows,kind=kind,order_sha256=AC['order_sha256'],configuration=effective,case_color_override_addendum5=color_override,
            visual_revision='User requested lower side views matched to the illustrated error. Cases c1-c2 use colored MVS at 30 degrees; c3 uses an explicitly named local MVS cutaway plus a supplemental input section detail; c4 retains a training photograph. Section XY and scoring are unchanged. Original full-range sections remain included.',
            path_resolvers={'/repo':'JointBuildGS-exp','/docs':'JointBuildGS-exp/docs/experiments/phd/main_gtjudge_v1','/gtjudge':'JointBuildGS-artifacts/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1','/art':'JointBuildGS-artifacts','/out':'JointBuildGS-artifacts/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1'},scientific_verdict=None),ensure_ascii=False,indent=2))
    with zipfile.ZipFile(payload) as z:
        assert z.testzip() is None
        for row in rows:assert hashlib.sha256(z.read(row['member'])).hexdigest()==row['sha256']
    receipt=dict(at=now(),status='PASS_ARCHIVE_INTEGRITY',path=str(payload),sha256=sha(payload),bytes=payload.stat().st_size,members=len(rows)+1,scientific_verdict=None)
    dump(D/'verification'/f'addendum4_{kind}_archive.json',receipt)
    print('ADD4_DELIVERED',json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':package(sys.argv[1])
