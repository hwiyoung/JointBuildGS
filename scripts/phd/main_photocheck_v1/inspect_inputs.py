"""Read camera lineage and source schema before locking the new computation."""
import sys,struct,zipfile,time
from common import *
sys.path.insert(0,'/repo/scripts/phd/main_widen0_v2')
from preflight import images
from photo_geometry import calibration,project
from image_inventory import rotation
def main():
    import torch,cv2,open3d
    t0=time.monotonic();spl=load(W/'image_split.json');poses=images(DENSE/'sparse/images.bin')
    inventory=load(W/'inputs/image_inventory.json')['rows'];ir={r['name']:r for r in inventory}
    assert len(spl['train'])==819 and not set(spl['train'])&set(spl['evaluation'])
    iw,ih,p=calibration();model=images(W/'mvs/full/sparse/images.bin')
    checks=[]
    for name in spl['train']:
        assert name in poses and name in model and ir[name]['original_zip_member']
        checks.append(max(np.max(np.abs(np.array(poses[name]['q'])-model[name]['q'])),np.max(np.abs(np.array(poses[name]['t'])-model[name]['t']))))
    assert max(checks)<1e-12
    with zipfile.ZipFile(RAW/'raw/uav/Images.zip') as z:
        names=set(z.namelist());assert all(ir[n]['original_zip_member'] in names for n in spl['train'])
    rows=[];schema=None
    for sealed in [False,True]:
        for f in sorted((W/('holdout/patch_values' if sealed else 'patch_values')).glob('*.npz')):
            # Only geometry/support metadata are reported for holdout.
            with np.load(f) as z:
                if schema is None:schema={k:dict(shape=z[k].shape,dtype=str(z[k].dtype)) for k in z.files}
                roof=z['kind']==1;wall=(z['kind']==2)&(z['building']=='DEBY_LOD2_4906968')
                rows.append(dict(file=f.name,holdout=sealed,roof_patches=int(roof.sum()),roof_area_m2=float(z['area'][roof].sum()),
                    pilot_roof_patches=int((roof&np.isin(z['building'],EXAMPLES)).sum()) if not sealed else None,
                    pilot_wall_patches=int(wall.sum()) if not sealed else None,
                    undefined_roof_normal=int((roof&~z['normal_defined']).sum())))
    record=dict(status='PASS',at=now(),train_images=len(spl['train']),max_pose_difference=max(checks),width=iw,height=ih,calibration=p,
        sources={str(q):sha(q) for q in [W/'image_split.json',W/'building_split.json',CAL/'cameras.txt',DENSE/'sparse/images.bin',W/'mvs/full/sparse/images.bin']},
        schema=schema,inventory=rows,versions=dict(torch=torch.__version__,cv2=cv2.__version__,open3d=open3d.__version__,numpy=np.__version__),environment=env(),seconds=time.monotonic()-t0)
    dump(O/'input_preflight.json',record)
    print(json.dumps(clean(dict(status='PASS',width=iw,height=ih,train=819,schema=schema,roof_patches=sum(r['roof_patches'] for r in rows),pilot_roof=sum(r['pilot_roof_patches'] or 0 for r in rows),pilot_wall=sum(r['pilot_wall_patches'] or 0 for r in rows),undefined=sum(r['undefined_roof_normal'] for r in rows),versions=record['versions'])),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
