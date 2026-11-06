"""Requested acceptance checks only; source hashes, camera identity and local counts."""
from add4_common import *

def main():
    checks=[];summary=[]
    for c in AC['cases']:
        rec=getcase(c);row=loadz(root_of(c)/'rows.npz');take=section_mask(row['xyz'],rec['section']);reference=int(take.sum());cameras=[]
        for tag in ['top','top_crop','oblique','wrong_gray','wrong_dist','truth_gray','section']:
            p=AF/f"{c['id']}_{tag}.png";j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p)
            assert j['text_in_figure'] is False and im.info.get('icc_profile')
            assert list(im.size)==j['size_px'] and j['scientific_verdict'] is None
            if tag!='section':assert im.width>=1600
            assert all(np.isfinite(j[k]).all() for k in ['A_px','Aprime_px'])
            for source in j['sources']:assert proof(source['path'])['sha256']==source['sha256'],source['path']
            if 'camera' in j:
                cameras.append(j['camera']);assert j['camera']['angle_definition'] in ['camera_centre_to_section_centre_frozen_gravity','synthetic_optical_axis_elevation_frozen_gravity']
                xy=np.array(j['line_polyline_px']);assert (xy[:,0]>=0).all() and (xy[:,0]<=im.width).all() and (xy[:,1]>=0).all() and (xy[:,1]<=im.height).all()
            if tag=='wrong_dist':assert j['distance_sampling']=='visible_pixel_surface_point'
            if tag=='top':assert j['case_basis']=='stage1 normal_line'
            if tag=='top_crop':assert abs(im.width/im.height-1.25)<.002
        assert all(x==cameras[0] for x in cameras)
        bounds=[];our=None
        for m in c['methods']:
            p=AF/c['id']/f'section_{m}.png';j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);assert im.size==(1200,120) and im.mode=='RGBA';assert j['n_gt']==reference;bounds.append(j['axis_bounds'])
            z=loadz(root_of(c)/'distances'/f'{m}.npz',['row_s'])['row_s'][take];v=100*float(np.mean(np.isfinite(z)&(abs(z)<=row['row_tau_m'][take]))) if reference else None
            assert v is None or abs(v-j['completeness_pct'])<1e-10
            if m=='FINALTRAIN_30000':our=v
        assert all(b==bounds[0] for b in bounds)
        checks.append(dict(case=c['id'],same_camera=True,same_section_axes=True,no_added_text=True,sRGB=True,exact_existing_section=True,section_width_m=1.,n_reference_rows=reference,saved_distances_reused=True))
        summary.append(dict(case=c['id'],image=cameras[0]['name'],source_type=cameras[0].get('source_type','training photograph'),section_our_completeness_pct=our,n_gt=reference,reference_mesh='확인 불가: PCA-normal point rendering supplied',camera_fallback=cameras[0]['selection_fallback']))
    dump(D/'verification/addendum4_cases.json',dict(at=now(),status='PASS_REQUESTED_CHECKS_WITH_DISCLOSED_REFERENCE_MESH_UNAVAILABLE',checks=checks,summary=summary,
        training_started=False,training_interrupted=False,GT_triangulated=False,addendum3_original_available=False,scientific_verdict=None))
    print('ADD4_VALIDATED',json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
