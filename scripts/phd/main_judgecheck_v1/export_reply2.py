"""Canonical development per-tile files; roof/wall composite point identity preserved."""
import json,sys
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez
BASE=O/'r2'
CORE_STACKED={'photo_code','new_photo_code','region','reason','arm_region','arm_height_m'}
PHOTO_STACKED={'best_score','best_height','texture','new_code'}
def main():
    rows=[]
    for folder,stacked in [('core_points',CORE_STACKED),('photo_points',PHOTO_STACKED)]:
        files=sorted((BASE/folder).glob('*__*__*.npz'));pairs=sorted(set('__'.join(p.stem.split('__')[:2]) for p in files))
        for pair in pairs:
            pieces=[loadz(p) for p in files if p.stem.startswith(pair+'__')];keys=set(pieces[0]);assert all(set(x)==keys for x in pieces)
            data={k:np.concatenate([p[k] for p in pieces],axis=1 if k in stacked else 0) for k in keys}
            ids=data['patch_id'] if folder=='core_points' else data['point_id'];composite=list(zip(data['kind'].tolist(),ids.tolist()));assert len(set(composite))==len(ids)
            dest=O/folder/f'{pair}.npz';savez(dest,**data);rows.append(dict(path=str(dest),sha256=sha(dest),bytes=dest.stat().st_size,count=len(ids)))
    schema=dict(at=now(),point_identity=['tile','prior','kind','point_id'],note='Original photo IDs are retained and may repeat between roof and wall; never join without kind.',
        photo_array_axes={'best_score/best_height/texture':['mode (clipped, unclipped)','point','plane (prior, MVS)'],'new_code':['mode (clipped, unclipped)','point'],'selected_images':['point','plane (prior, MVS)','selected photo slot, max 10'],'selected_count':['point','plane (prior, MVS)'],'plane_centres/plane_normals':['point','plane (prior, MVS)','XYZ']},
        arm_region_axis='same nine arms and core axis as arm_height_m; -1 counts and NaN are unavailable',
        core_stacked_axis_0={'region':['new_clipped','new_unclipped','new_oldphoto','old_rule','always_prior','always_mvs'],'reason':'same six variants; 9 where no photo/default reason applies','photo_code':'unified internal labels: first two corrected, third legacy mapped to 8 ambiguous/6 texture/7 views; old_photo_code keeps exact legacy 0..4','new_photo_code':['clipped','unclipped'],'arm_height_m':['main','all_oracle','geometry_oracle','cause_oracle','always_mix','always_prior','always_mvs','default_only','oldphoto']},
        old_photo_code={0:'지지',1:'반박',2:'애매',3:'무늬 없음',4:'사진 부족',9:'범위 없음/셀 수 없음'},new_photo_code={0:'지지',1:'반박',2:'둘 다 낮음',3:'둘 다 높음',4:'MVS 면 없음',5:'조각 부족',6:'무늬 없음',7:'사진 부족',9:'비대상/범위 없음'},
        region={0:'일치',1:'보존',2:'보정',3:'빈 공간 보정',4:'결측',9:'셀 수 없음'},reason={0:'사진 지지',1:'사진 반박',2:'기본 방향',9:'해당 없음'},cell={0:'둘 다 맞음',1:'사전 정보만 틀림',2:'영상만 틀림',3:'둘 다 틀림',4:'영상 없음 사전 정보 맞음',5:'영상 없음 사전 정보 틀림',6:'참값 없음',9:'사전 정보 높이/법선 없음'},
        target_type_bits={1:'target1 outside',2:'target2 unchanged agreement sample',4:'target3 evaluation-only'},nonfinite='NaN is unavailable, never zero',crs='EPSG:25832; coordinates in COLMAP local frame, origin [690953,5336071,604]m',
        source_tag='[이 발주에서 냄]',scientific_verdict=None)
    dump(O/'schema_reply2.json',schema);dump(D/'data_schema.json',schema);dump(BASE/'canonical_export.json',dict(at=now(),files=rows,scientific_verdict=None));print('CANONICAL_EXPORT',len(rows),sum(r['bytes'] for r in rows),flush=True)
if __name__=='__main__':main()
