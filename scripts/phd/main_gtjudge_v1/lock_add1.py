from common import *
p=C/'gtjudge_v1.add1.json'
assert not p.exists()
v=dict(task_id='PHD-MAIN-GTJUDGE-v1',at=now(),parent_config_sha256=sha(C/'gtjudge_v1.json'),order_sha256=sha(D/'provenance/addendum1.md'),scientific_verdict=None,
 normal_line=dict(reference_normals='AXES71 PCA; exact coordinates then nearest normal point',roof_sign='nz>=0',wall_sign='nearest training camera dot positive',reference_surface_files=None,missing_reference_policy='PCA pointcloud authorized; never triangulate'),
 scoring=dict(accuracy='dense reference cylinder minimum absolute axial coordinate, no mean',cylinder_radius='max(0.05,2*median nearest-neighbor reference spacing)',accuracy_exclusion='nearest reference Euclidean distance >1m'),
 stage0=dict(fallback='unavailable or signal remains after one implementation correction -> RECOUNT',unavailable_is_fallback_authority=True,correction='five central/cross offsets plus four diagonal tangent offsets at radius 0.05 m; definition otherwise unchanged'),
 freespace=dict(calibrate_iteration=500,first_iteration=500,minimum_candidates_at_500=100,deferred_candidates_strict_gt=100,check_interval=100,weight_before_calibration=0,prune_recency_iterations=100),
 execution=dict(preflight_reuse_commit='1923967f',previous_passed_units_not_repeated=True,reference_triangulation=False,scene_order=[['R1rep_b10','ALS'],['B173nb_b10','LoD2'],['B173nb_b10','ALS'],['R1rep_b10','LoD2'],['B0_b10','ALS'],['B0_b10','LoD2']]))
dump(p,v);dump(C/'gtjudge_v1.add1.lock.json',dict(at=now(),config_sha256=sha(p),parent_config_sha256=v['parent_config_sha256'],scientific_verdict=None))
dump(C/'stage0.add1.initial.lock.json',dict(at=now(),config_sha256=sha(p),first_calculation_started=False,scientific_verdict=None))
print('ADD1_LOCKED',sha(p))
