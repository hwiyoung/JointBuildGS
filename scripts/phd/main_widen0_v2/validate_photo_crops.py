"""Verify native crop dimensions and unchanged original pixels outside outlines."""
import io
import json
import zipfile
import numpy as np
from PIL import Image
from analysis_common import O,DOC,save_table,dump
from preflight import sha

def main():
    records=json.loads((DOC/'tables/대표사진_기록.json').read_text())['rows']
    inventory={r['name']:r for r in json.loads((O/'inputs/image_inventory.json').read_text())['rows']}
    rows=[]
    with zipfile.ZipFile('/art/phase-payloads/p0-audit/data/raw/uav/Images.zip') as archive:
        for r in records:
            if r['status']!='PASS':continue
            source=inventory[r['image']]
            assert source['split']=='train' and source['nadir']
            assert source['original_zip_member']==r['original_zip_member']
            original=Image.open(io.BytesIO(archive.read(r['original_zip_member']))).convert('RGB')
            crop=Image.open(DOC/r['crop_file']).convert('RGB')
            x0,y0,x1,y1=r['crop_px'];assert crop.size==(x1-x0,y1-y0)
            expected=np.asarray(original.crop((x0,y0,x1,y1)));actual=np.asarray(crop)
            changed=np.any(expected!=actual,axis=2)
            assert np.all(actual[changed]==[255,210,0]),r['component_id']
            assert np.any(~changed),r['component_id']
            for ext in ['png','pdf','json']:
                assert (DOC/r['panel_file']).with_suffix('.'+ext).is_file()
            rows.append(dict(component_id=r['component_id'],crop_file=r['crop_file'],image=r['image'],
                original_size_px=list(original.size),crop_size_px=list(crop.size),crop_px=r['crop_px'],
                unchanged_pixels=int((~changed).sum()),outline_changed_pixels=int(changed.sum()),
                native_resolution_verified=True,all_changed_pixels_are_yellow_outline=True,
                crop_sha256=sha(DOC/r['crop_file'])))
    save_table('사진_원본해상도_검사',rows,rule='Exact RGB comparison with the original JPEG crop; only yellow outline pixels may differ; no resampling.')
    dump(O/'gates/photo_crops.json',dict(status='PASS',verified_crops=len(rows),
        unavailable_photos=sum(r['status']!='PASS' for r in records),scientific_verdict=None))
    print('native photo crop checks PASS',len(rows),flush=True)

if __name__=='__main__':main()
