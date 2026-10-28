"""Real prior-wall fixture tests the new join/report path, never a new measurement."""
import shutil
from common import *
import common,wall_report,wall_prepare,wall_measure
from cameras import Cameras
def main():
    target=O/'validation/report_smoke';doc=D/'validation/report_smoke';target.mkdir(parents=True,exist_ok=True);doc.mkdir(parents=True,exist_ok=True)
    actual=O;reference=Path('/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1');cam=Cameras();count=0
    for geo in sorted((actual/'geometry').glob('*__LoD2.npz')):
        old=reference/'work/pilot'/geo.name
        if not old.exists():continue
        p=npz(old);ids=np.flatnonzero((p['kind']==2)&(p['building']=='DEBY_LOD2_4906968'))
        if not len(ids):continue
        g=npz(geo);keys={tuple(np.round(c,8)):i for i,c in enumerate(g['centre'])};indices=np.array([keys[tuple(np.round(c,8))] for c in p['centre'][ids]])
        z={k:v[ids] for k,v in p.items()};z['geometry_index']=indices;z['point_id']=np.array(['development:'+str(x) for x in g['point_id'][indices]]);z['face_ext']=g['face_ext'][indices]
        vertical=np.abs(cam.R[:,2,2])>=np.cos(np.deg2rad(15));sel=z['selected_images'];z['selected_vertical_count']=(vertical[np.maximum(sel,0)]&(sel>=0)).sum(1).astype(np.int8);z['normal_azimuth_deg']=((np.degrees(np.arctan2(z['normal'][:,0],z['normal'][:,1]))+360)%360).astype(np.float32)
        folder=target/'geometry';folder.mkdir(exist_ok=True)
        for f in [geo,geo.with_name(geo.stem+'__mapping.npz')]:shutil.copyfile(f,folder/f.name)
        dest=target/'work/pilot'/geo.name;wall_measure.atomic_npz(dest,z);dump(dest.with_suffix('.json'),dict(fixture_only=True,source_sha256=sha(old)))
        count+=len(ids)
    assert count>0
    common.O=wall_report.O=wall_measure.O=target
    common.D=wall_report.D=wall_prepare.D=doc
    result=wall_report.summarize('pilot');assert result['points']==count
    from wall_validate import main as validate
    import wall_validate
    wall_validate.O=target;wall_validate.D=doc;validate()
    dump(actual/'gates/report_fixture.json',dict(at=now(),status='PASS',fixture='earlier 4906968 wall point results; only join/export/report tested; not new wall observations',points=count,summary=result,scientific_verdict=None))
    print('actual legacy wall fixture report PASS',count,flush=True)
if __name__=='__main__':main()
