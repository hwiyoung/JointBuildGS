from rfcore import *
import shutil

revision=PAY/'revision_01';assert not revision.exists();revision.mkdir()
for p in (DOC/'figures').rglob('*'):
    if p.is_file():
        dst=revision/p.relative_to(DOC/'figures');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
amend=dict(at=now(),original_config_sha256=sha(CFG/'regionfig_v2.json'),scientific_verdict=None,
    reason='Native FULL_OPENCV rational projection folds outside the calibrated field. Figure 1 diagnostic found 2636 crop-assigned centres outside the actual training-camera field, causing long false polygons.',
    change='For overlay and every crop statistic, require both the native crop and positive-depth calibrated PINHOLE image field. Reuse W/full exact pose and camera. Set bar x-axis bounds to include low-area categories.',
    changes_input_values=False,changes_section=False,changes_photo_selection=False,changes_native_crop=False,changes_rotation=False,
    previous_render_directory=str(revision),before_revised_render=True)
dump(CFG/'amendment_01_projection.json',amend)
dump(CFG/'amendment_01_projection.lock.json',dict(at=now(),sha256=sha(CFG/'amendment_01_projection.json'),scientific_verdict=None))
print(amend)
